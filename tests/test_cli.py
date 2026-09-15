"""Real-process contracts for the uv entry point; no active installation is edited."""

import os
import subprocess


def test_uv_entry_point_help_and_missing_environment():
    help_result = subprocess.run(
        ["uv", "run", "--frozen", "cubrid-conf-tui", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert help_result.returncode == 0
    assert "limited offline mode" in help_result.stdout
    environment = dict(os.environ)
    environment.pop("CUBRID", None)
    result = subprocess.run(
        ["uv", "run", "--frozen", "cubrid-conf-tui"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "Set CUBRID" in result.stderr
    assert "Traceback" not in result.stderr


def test_uv_terminal_launch_and_clean_exit(tmp_path):
    import fcntl
    import pty
    import select
    import struct
    import termios
    import time

    root = tmp_path / "installation"
    (root / "bin").mkdir(parents=True)
    (root / "conf").mkdir()
    executable = root / "bin/cubrid"
    executable.write_text(
        '#!/bin/sh\n[ "$1" = "--version" ] || exit 1\nprintf \'CUBRID 11.5.0\\n\' >&2\n'
    )
    executable.chmod(0o755)
    target = root / "conf/cubrid.conf"
    target.write_text("[common]\nmax_clients=100\n")
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
    before = termios.tcgetattr(slave)
    environment = dict(os.environ, CUBRID=str(root), TERM="xterm-256color")
    environment.pop("CUBRID_CONF_FILE", None)
    environment["CUBRID_DATABASES"] = str(tmp_path / "empty-registry")
    process = subprocess.Popen(
        ["uv", "run", "--frozen", "cubrid-conf-tui"],
        env=environment,
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    output = b""
    try:
        deadline = time.monotonic() + 15
        while b"max_clients" not in output and time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                output += os.read(master, 65536)
        assert b"max_clients" in output, output.decode(errors="replace")
        assert b"Limited offline" in output
        os.write(master, b"\x11")  # Ctrl+Q
        process.wait(timeout=10)
        assert process.returncode == 0
        assert termios.tcgetattr(slave) == before
        assert target.read_text() == "[common]\nmax_clients=100\n"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)
