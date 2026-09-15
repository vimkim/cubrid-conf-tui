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
