"""Run only inside private user/network/IPC/PID namespaces (see ticket-03.md)."""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from textual.widgets import Input, OptionList, Static

from cubrid_conf_tui.app import ConfigurationApp


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
        target.write_text(
            "[common]\nmax_clients=100\nstored_procedure=no\n"
            "data_buffer_size=32M\nlog_buffer_size=4M\n"
        )
        environment = {
            "CUBRID": str(root),
            "CUBRID_DATABASES": str(dbdir),
            "CUBRID_CONF_FILE": str(target),
            "HOME": str(base),
            "PATH": f"{root / 'bin'}:/usr/bin:/bin",
            "LD_LIBRARY_PATH": str(root / "lib"),
            "LANG": "C.UTF-8",
            "CUBRID_NO_DAEMON": "1",
        }
        os.chdir(dbdir)
        executable = str(root / "bin/cubrid")

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [executable, *args],
                env=environment,
                capture_output=True,
                text=True,
                timeout=45,
            )
            if result.returncode:
                raise RuntimeError(f"{args}: {result.stdout}\n{result.stderr}")
            return result

        run(
            "createdb",
            "--db-volume-size=64M",
            "--log-volume-size=64M",
            "tui_probe",
            "en_US.utf8",
        )
        subprocess.Popen(
            [str(root / "bin/cub_master")],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(1)
        server = subprocess.Popen(
            [str(root / "bin/cub_server"), "tui_probe"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                run("paramdump", "--CS-mode", "tui_probe")
                break
            except RuntimeError:
                await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Isolated server did not become available")
        try:
            captures.mkdir(parents=True, exist_ok=True)
            for kind, flags in (("ordinary", []), ("hidden", ["--dump-flag=0x8"])):
                result = run("paramdump", "--CS-mode", *flags, "tui_probe")
                # Preserve records and comments, redact only temporary root paths.
                (captures / f"{kind}.txt").write_text(
                    result.stdout.replace(str(base), "<isolated-root>")
                )
            app = ConfigurationApp(environment=environment, database="tui_probe")
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
        finally:
            server.terminate()
            server.wait(timeout=15)
        app = ConfigurationApp(environment=environment, database="tui_probe")
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(200):
                await pilot.pause(0.05)
                if "Discovering" not in str(app.query_one("#mode", Static).content):
                    break
            assert "Incomplete discovery" in str(app.query_one("#mode", Static).content)
            await pilot.press("m", "x", "c", "enter")
            assert "S: unavailable" in str(
                app.screen.query_one("#details", Static).content
            )
            print("Stopped-server offline editing: passed")


if __name__ == "__main__":
    # Refuse host execution: caller must supply a PID namespace with its own procfs.
    if os.getpid() != 1:
        raise SystemExit(
            "Use the documented unshare command with a private PID namespace."
        )
    asyncio.run(probe(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
