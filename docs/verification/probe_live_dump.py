"""Run only in a disposable, PID-limited VM/container (see ticket-03.md)."""

import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from textual.widgets import Input, OptionList, Static

from cubrid_conf_tui.app import ConfigurationApp


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _stop_server(
    executable: str,
    environment: dict[str, str],
    working_directory: Path,
    database: str,
    server: subprocess.Popen[bytes],
) -> None:
    try:
        subprocess.run(
            [executable, "server", "stop", database],
            env=environment,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    if server.poll() is not None:
        return
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate(server)


def _validate_master_endpoint(endpoint: Path, private_tmp: Path) -> None:
    if endpoint == Path("/tmp/CUBRID1523"):
        raise RuntimeError("Refusing shared host master endpoint /tmp/CUBRID1523")
    if endpoint.parent.resolve() != private_tmp.resolve():
        raise RuntimeError(
            f"Master endpoint lies outside private CUBRID_TMP: {endpoint}"
        )
    if os.path.lexists(endpoint):
        raise RuntimeError(f"Master endpoint already exists: {endpoint}")


def _process_owns_unix_socket(process_id: int, endpoint: Path) -> bool:
    try:
        socket_inodes = {
            fields[6]
            for line in Path("/proc/net/unix").read_text().splitlines()[1:]
            if len(fields := line.split(maxsplit=7)) == 8 and fields[7] == str(endpoint)
        }
        if not socket_inodes:
            return False
        for descriptor in Path(f"/proc/{process_id}/fd").iterdir():
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in socket_inodes:
                return True
    except OSError:
        return False
    return False


async def _wait_for_master(master: subprocess.Popen[bytes], endpoint: Path) -> None:
    for _ in range(100):
        returncode = master.poll()
        if returncode is not None:
            raise RuntimeError(
                f"Private master exited with status {returncode} before readiness"
            )
        is_socket = endpoint.is_socket()
        if is_socket:
            if _process_owns_unix_socket(master.pid, endpoint):
                return
        elif os.path.lexists(endpoint):
            raise RuntimeError(
                f"Private master created a non-socket endpoint: {endpoint}"
            )
        await asyncio.sleep(0.05)
    if endpoint.is_socket():
        raise RuntimeError(f"Private master does not own endpoint: {endpoint}")
    raise RuntimeError(f"Private master did not create endpoint: {endpoint}")


async def probe(source: Path, captures: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="conf-tui-live-") as temporary:
        base = Path(temporary)
        root = base / "installation"
        root.mkdir()
        for name in ("bin", "lib", "conf", "msg", "locales", "timezones"):
            shutil.copytree(source / name, root / name, symlinks=True)
        for name in ("var", "tmp", "log"):
            (root / name).mkdir()
        dbdir = base / "databases"
        dbdir.mkdir()
        (dbdir / "databases.txt").touch()
        target = root / "conf/cubrid.conf"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            master_port = int(reservation.getsockname()[1])
        target.write_text(
            f"[common]\ncubrid_port_id={master_port}\n"
            "max_clients=100\nstored_procedure=no\n"
            "data_buffer_size=32M\nlog_buffer_size=4M\n"
        )
        environment = {
            "CUBRID": str(root),
            "CUBRID_DATABASES": str(dbdir),
            "CUBRID_CONF_FILE": str(target),
            "CUBRID_TMP": str(root / "tmp"),
            "HOME": str(base),
            "PATH": f"{root / 'bin'}:/usr/bin:/bin",
            "LD_LIBRARY_PATH": str(root / "lib"),
            "LANG": "C.UTF-8",
            "CUBRID_NO_DAEMON": "1",
        }
        executable = str(root / "bin/cubrid")
        database = "tui_probe"
        private_tmp = root / "tmp"
        master_endpoint = private_tmp / f"CUBRID{master_port}"

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [executable, *args],
                env=environment,
                cwd=dbdir,
                capture_output=True,
                text=True,
                timeout=45,
            )
            if result.returncode:
                raise RuntimeError(f"{args}: {result.stdout}\n{result.stderr}")
            return result

        _validate_master_endpoint(master_endpoint, private_tmp)
        run(
            "createdb",
            "--db-volume-size=64M",
            "--log-volume-size=64M",
            database,
            "en_US.utf8",
        )
        _validate_master_endpoint(master_endpoint, private_tmp)
        master: subprocess.Popen[bytes] | None = None
        server: subprocess.Popen[bytes] | None = None
        try:
            master = subprocess.Popen(
                [str(root / "bin/cub_master")],
                env=environment,
                cwd=dbdir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await _wait_for_master(master, master_endpoint)
            server = subprocess.Popen(
                [str(root / "bin/cub_server"), database],
                env=environment,
                cwd=dbdir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(100):
                try:
                    run("paramdump", "--CS-mode", database)
                    break
                except RuntimeError:
                    await asyncio.sleep(0.1)
            else:
                raise RuntimeError("Isolated server did not become available")
            captures.mkdir(parents=True, exist_ok=True)
            for kind, flags in (("ordinary", []), ("hidden", ["--dump-flag=0x8"])):
                result = run("paramdump", "--CS-mode", *flags, database)
                # Preserve records and comments, redact only temporary root paths.
                (captures / f"{kind}.txt").write_text(
                    result.stdout.replace(str(base), "<isolated-root>")
                )
            app = ConfigurationApp(environment=environment, database=database)
            async with app.run_test(size=(120, 40)) as pilot:
                for _ in range(200):
                    await pilot.pause(0.05)
                    if "Discovering" not in str(app.query_one("#mode", Static).content):
                        break
                mode = str(app.query_one("#mode", Static).content)
                assert mode.startswith("Live discovery"), (
                    mode,
                    app.query_one("#status", Static).content,
                )
                count = app.query_one("#settings", OptionList).option_count
                app.query_one("#search", Input).value = "max_clients"
                await pilot.pause()
                await pilot.press("enter")
                details = str(app.screen.query_one("#details", Static).content)
                assert "S: 100 • default: 100" in details, details
                print(
                    json.dumps(
                        {
                            "version": run("--version").stdout
                            + run("--version").stderr,
                            "rows": count,
                            "details": details,
                            "library_sha256": hashlib.sha256(
                                (source / "lib/libcubrid.so.11.5").read_bytes()
                            ).hexdigest(),
                        },
                        indent=2,
                    )
                )
            _stop_server(executable, environment, dbdir, database, server)
            server = None
            _terminate(master)
            master = None
            app = ConfigurationApp(environment=environment, database=database)
            async with app.run_test(size=(120, 40)) as pilot:
                for _ in range(200):
                    await pilot.pause(0.05)
                    if "Discovering" not in str(app.query_one("#mode", Static).content):
                        break
                assert "Incomplete discovery" in str(
                    app.query_one("#mode", Static).content
                )
                await pilot.press("m", "x", "c", "enter")
                assert "S: unavailable" in str(
                    app.screen.query_one("#details", Static).content
                )
                print("Stopped-server offline editing: passed")
        finally:
            try:
                if server is not None:
                    _stop_server(executable, environment, dbdir, database, server)
            finally:
                if master is not None:
                    _terminate(master)


if __name__ == "__main__":
    # PID 1 is necessary but not sufficient; ticket-03 also requires a PID limit.
    if os.getpid() != 1:
        raise SystemExit(
            "Run only in the documented disposable, PID-limited VM/container."
        )
    asyncio.run(probe(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
