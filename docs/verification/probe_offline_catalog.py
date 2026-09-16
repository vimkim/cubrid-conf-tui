"""Verify the two supported native artifacts in a source-hidden sandbox.

This is developer evidence, not an application runtime dependency.  It requires
Linux bubblewrap and strace.  Expected identities and observations are recorded
here independently of the production extractor.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from textual.widgets import Input, OptionList, Static

from cubrid_conf_tui.app import ConfigurationApp


@dataclass(frozen=True)
class Expected:
    mode: str
    sha256: str
    build_id: str
    count: int
    hidden: int
    obsolete: int
    er_log_debug: bool


EXPECTED = {
    "debug": Expected(
        "debug",
        "3cbce5364fe1e63f3b1ad889f58f8c8b15ab46bc43594fb255210df5babbe98c",
        "e34e8dfb4134ce9df54ee63df56e74da39643e0e",
        393,
        157,
        12,
        True,
    ),
    "release": Expected(
        "release",
        "0aeaeee76c0d977f85eb8d8adf014bb9f9a4a9ffb6714b08cbd4cde789ba27c0",
        "bb5732f72c587c34b2f2f9388894fe8d93f362df",
        386,
        155,
        12,
        False,
    ),
}

EXPECTED_RESULTS_SOURCE = {
    "prototype_commit": "7ff8245447da1b813c0b792e60d9bbb82b859af6",
    "source_revision": "c2492f886eeb2790c4887fbc95fb3c59c419d362",
    "summary": "docs/offline-catalog-findings.md",
    "preserved_captures": ".scratch/offline-catalog/prototypes/evidence/",
}


def find_parameter(payload: dict[str, object], name: str) -> dict[str, object]:
    parameters = payload["parameters"]
    assert isinstance(parameters, list)
    matches = [item for item in parameters if item["name"] == name]
    assert len(matches) == 1
    return matches[0]


def verify_trace(trace: str, hidden_source: Path) -> dict[str, object]:
    network = [
        line
        for line in trace.splitlines()
        if re.search(r"\b(socket|connect|bind|listen|accept|sendto|recvfrom)\(", line)
    ]
    write_opens = [
        line
        for line in trace.splitlines()
        if "open" in line and re.search(r"O_(WRONLY|RDWR|CREAT|TRUNC|APPEND)", line)
    ]
    forbidden_reads = [
        line
        for line in trace.splitlines()
        if str(hidden_source) in line
        or "cubrid.conf" in line
        or "databases.txt" in line
        or re.search(r"(_volinfo|_lgat|_lgar|_lob)", line)
    ]
    assert not network, network[:10]
    assert not write_opens, write_opens[:10]
    assert not forbidden_reads, forbidden_reads[:10]
    return {
        "network_calls": len(network),
        "write_opens": len(write_opens),
        "configuration_source_or_database_reads": len(forbidden_reads),
    }


def sandbox_helper_command(
    repository: Path,
    output: Path,
    trace_name: str,
    library_path: str,
    installation: str,
    extra_mounts: tuple[str, ...] = (),
) -> list[str]:
    python = (repository / ".venv/bin/python").resolve(strict=True)
    elftools_candidates = list(
        (repository / ".venv/lib").glob("python*/site-packages/elftools")
    )
    assert len(elftools_candidates) == 1, elftools_candidates
    return [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        str(repository.parent),
        "--ro-bind",
        str(repository / "src"),
        "/tmp/cubrid-conf-tui-src",
        "--ro-bind",
        str(elftools_candidates[0]),
        "/tmp/site-packages/elftools",
        "--bind",
        str(output),
        "/tmp/output",
        *extra_mounts,
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--unshare-net",
        "--chdir",
        "/tmp",
        "--setenv",
        "PYTHONPATH",
        "/tmp/cubrid-conf-tui-src:/tmp/site-packages",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        "LD_LIBRARY_PATH",
        library_path,
        "--",
        "strace",
        "-f",
        "-qq",
        "-e",
        "trace=%file,%network",
        "-o",
        f"/tmp/output/{trace_name}",
        str(python),
        "-B",
        "-m",
        "cubrid_conf_tui.metadata_helper",
        installation,
    ]


def probe(
    label: str,
    installation: Path,
    expected: Expected,
    repository: Path,
    output: Path,
) -> dict[str, object]:
    library = installation / "lib/libcubrid.so.11.5"
    assert hashlib.sha256(library.read_bytes()).hexdigest() == expected.sha256
    trace = output / f"{label}.trace"
    command = sandbox_helper_command(
        repository,
        output,
        trace.name,
        f"{installation / 'lib'}:{installation / 'cci/lib'}",
        str(installation),
    )
    result = subprocess.run(command, capture_output=True, timeout=30, check=True)
    payload = json.loads(result.stdout)
    assert payload["status"] == "supported"
    artifact = payload["artifact"]
    assert artifact == {
        "path": str(library),
        "sha256": expected.sha256,
        "build_id": expected.build_id,
        "role": "server",
        "needed_by": str(installation / "bin/cub_server"),
        "soname": "libcubrid.so.11.5",
        "mode": expected.mode,
    }
    parameters = payload["parameters"]
    assert len(parameters) == expected.count
    assert sum(item["hidden"] for item in parameters) == expected.hidden
    assert sum(item["obsolete"] for item in parameters) == expected.obsolete
    pgbuf = find_parameter(payload, "enable_pgbuf_inspector")
    assert {
        "type": pgbuf["type"],
        "hidden": pgbuf["hidden"],
        "server": pgbuf["server"],
        "default": pgbuf["default"],
    } == {
        "type": "boolean",
        "hidden": True,
        "server": True,
        "default": {"state": "value", "value": False},
    }
    er_debug = find_parameter(payload, "er_log_debug")
    assert er_debug["default"] == {
        "state": "value",
        "value": expected.er_log_debug,
    }
    error_level = find_parameter(payload, "error_log_level")
    assert error_level["semantics"] == {
        "unit": "none",
        "unit_adjusted": False,
        "bounds_source": "static",
        "keywords": [
            {"text": "fatal", "value": 0},
            {"text": "error", "value": 1},
            {"text": "syntax", "value": 2},
            {"text": "warning", "value": 3},
            {"text": "notification", "value": 4},
        ],
    }
    audit_size = find_parameter(payload, "ddl_audit_log_size")
    assert audit_size["semantics"] == {
        "unit": "size",
        "unit_adjusted": False,
        "bounds_source": "static",
        "keywords": None,
    }
    assert audit_size["client"] is True
    assert audit_size["server"] is False
    thread_stack = find_parameter(payload, "thread_stacksize")
    assert thread_stack["semantics"] == {
        "unit": "size",
        "unit_adjusted": False,
        "bounds_source": "static",
        "keywords": None,
    }
    assert thread_stack["client"] is False
    assert thread_stack["server"] is True
    assert thread_stack["lower"] == {"state": "value", "value": 65536}
    assert thread_stack["upper"] == {"state": "value", "value": 2147483647}
    connection_worker = find_parameter(payload, "max_connection_worker")
    assert connection_worker["semantics"]["bounds_source"] == "helper_cpu"
    effects = verify_trace(trace.read_text(), repository.parent)
    capture = {
        "artifact": artifact,
        "compatibility": payload["compatibility"],
        "verification_environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "selected_installation": str(installation),
            "helper_library_path": (
                f"{installation / 'lib'}:{installation / 'cci/lib'}"
            ),
            "source_root": f"{repository.parent} hidden by an empty tmpfs",
            "network": "isolated bubblewrap network namespace",
            "filesystem": "read-only host with writable trace output only",
        },
        "expected_results_source": EXPECTED_RESULTS_SOURCE,
        "counts": {
            "all": len(parameters),
            "hidden": expected.hidden,
            "obsolete": expected.obsolete,
        },
        "independent_values": {
            "enable_pgbuf_inspector": pgbuf["default"],
            "er_log_debug": er_debug["default"],
        },
        "configuration_semantics": {
            "error_log_level": error_level["semantics"],
            "ddl_audit_log_size": audit_size["semantics"],
            "thread_stacksize": thread_stack["semantics"],
            "max_connection_worker": connection_worker["semantics"],
        },
        "observed_effects": effects,
    }
    (output / f"{label}.json").write_text(json.dumps(capture, indent=2) + "\n")
    return capture


def probe_missing_dependency(
    installation: Path, repository: Path, output: Path
) -> dict[str, object]:
    isolated = output / "missing-dependency-install"
    (isolated / "bin").mkdir(parents=True, exist_ok=True)
    (isolated / "lib").mkdir(exist_ok=True)
    shutil.copy2(installation / "bin/cub_server", isolated / "bin/cub_server")
    shutil.copy2(
        installation / "lib/libcubrid.so.11.5",
        isolated / "lib/libcubrid.so.11.5",
    )
    trace = output / "missing-dependency.trace"
    command = sandbox_helper_command(
        repository,
        output,
        trace.name,
        "/tmp/output/missing-dependency-install/lib",
        "/tmp/output/missing-dependency-install",
        ("--tmpfs", str(installation / "lib")),
    )
    result = subprocess.run(command, capture_output=True, timeout=30, check=True)
    payload = json.loads(result.stdout)
    assert payload["status"] == "unsupported", payload
    diagnostic = payload["diagnostic"]
    assert "libcascci.so.11.3" in diagnostic, diagnostic
    assert "native access was refused" in diagnostic, diagnostic
    return {
        "diagnostic": diagnostic,
        "observed_effects": verify_trace(trace.read_text(), repository.parent),
    }


async def probe_full_app(installation: Path, expected: Expected) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="conf-tui-real-app-") as directory:
        base = Path(directory)
        target = base / "selected.conf"
        original = b"[common]\nmax_clients=100\n"
        target.write_bytes(original)
        environment = dict(os.environ)
        environment.update(
            {
                "CUBRID": str(installation),
                "CUBRID_CONF_FILE": str(target),
                "CUBRID_DATABASES": str(base / "missing-registry"),
                "LD_LIBRARY_PATH": (
                    f"{installation / 'lib'}:{installation / 'cci/lib'}"
                ),
            }
        )
        app = ConfigurationApp(environment=environment)
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(300):
                if "Discovering" not in str(app.query_one("#mode", Static).content):
                    break
                await pilot.pause(0.02)
            else:
                raise AssertionError("real-artifact app discovery did not finish")
            mode = str(app.query_one("#mode", Static).content)
            assert "Supported offline catalog" in mode, (
                mode,
                app.query_one("#status", Static).content,
            )
            count = app.query_one("#settings", OptionList).option_count
            assert count == expected.count - expected.obsolete, count
            app.query_one("#search", Input).value = "enable_pgbuf_inspector"
            await pilot.pause()
            assert app.query_one("#settings", OptionList).option_count == 1
            await pilot.press("enter")
            details = str(app.screen.query_one("#details", Static).content)
            assert "Raw compiled default (boolean): false" in details
            assert f"server • {expected.mode}" in details
            await pilot.press("space", "enter")
            assert target.read_bytes() == original + b"enable_pgbuf_inspector=yes\n"
            assert target.with_suffix(".conf.bak").read_bytes() == original

            for name, value in (
                ("error_log_level", "warning"),
                ("thread_stacksize", "1M"),
                ("ddl_audit_log_size", "9M"),
                ("max_connection_worker", "999"),
            ):
                app.query_one("#search", Input).value = name
                await pilot.pause()
                await pilot.press("enter")
                editor_details = str(app.screen.query_one("#details", Static).content)
                if name == "thread_stacksize":
                    assert "from 65536 to 2147483647 bytes" in editor_details
                if name == "ddl_audit_log_size":
                    assert "different or shared artifact role" in editor_details
                    assert "at least 10485760 bytes" not in editor_details
                app.screen.query_one("#value", Input).value = value
                await pilot.press("enter")
            final = target.read_text()
            assert "error_log_level=warning" in final
            assert "thread_stacksize=1M" in final
            assert "ddl_audit_log_size=9M" in final
            assert "max_connection_worker=999" in final
            status = str(app.query_one("#status", Static).content)
            assert "helper CPU bounds are displayed but not enforced" in status
            assert "startup acceptance" in status
        return {
            "mode": mode,
            "catalog_rows": count,
            "boolean_details": details,
            "typed_saved_text": final,
            "limited_validation_status": status,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debug", type=Path)
    parser.add_argument("release", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    for executable in ("bwrap", "strace"):
        if shutil.which(executable) is None:
            raise SystemExit(f"required verification executable missing: {executable}")
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        temporary = None
    else:
        temporary = tempfile.TemporaryDirectory(prefix="conf-tui-metadata-")
        output = Path(temporary.name)
    captures = {
        "debug": probe(
            "debug", args.debug.resolve(), EXPECTED["debug"], repository, output
        ),
        "release": probe(
            "release", args.release.resolve(), EXPECTED["release"], repository, output
        ),
    }
    captures["debug"]["full_app"] = asyncio.run(
        probe_full_app(args.debug.resolve(), EXPECTED["debug"])
    )
    captures["release"]["full_app"] = asyncio.run(
        probe_full_app(args.release.resolve(), EXPECTED["release"])
    )
    captures["debug"]["missing_dependency"] = probe_missing_dependency(
        args.debug.resolve(), repository, output
    )
    print(json.dumps(captures, indent=2))
    if temporary is not None:
        temporary.cleanup()


if __name__ == "__main__":
    main()
