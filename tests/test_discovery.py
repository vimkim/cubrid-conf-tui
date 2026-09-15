"""Discovery through the full app and controlled installation executables."""

import json
import sys
from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, Static

from cubrid_conf_tui.app import ConfigurationApp


async def wait_for_discovery(app, pilot):
    for _ in range(200):
        if "Discovering" not in str(app.query_one("#mode", Static).content):
            return
        await pilot.pause(0.02)
    pytest.fail("Discovery did not finish within the test deadline")


@pytest.fixture
def live_installation(tmp_path: Path):
    root = tmp_path / "cubrid"
    (root / "bin").mkdir(parents=True)
    (root / "conf").mkdir()
    target = root / "conf/cubrid.conf"
    target.write_text("[common]\nmax_clients=100\n[@Demo]\nmax_clients=5\n")
    ordinary = (
        "# client parameters\n[C ] max_clients=100 (100)\n"
        "# server parameters\n[S*] max_clients=5 (100)\n"
    )
    hidden = "[S ] Hidden_setting=no (no)\n"
    (root / "ordinary").write_text(ordinary)
    (root / "hidden").write_text(hidden)
    executable = root / "bin/cubrid"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "root = pathlib.Path(os.environ['CUBRID'])\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('CUBRID 11.5.0'); sys.exit()\n"
        "with (root / 'calls').open('a') as f:\n"
        "    f.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')\n"
        "assert sys.argv[1:3] == ['paramdump', '--CS-mode']\n"
        "kind = 'hidden' if '--dump-flag=0x8' in sys.argv else 'ordinary'\n"
        "print((root / kind).read_text(), end='')\n"
    )
    executable.chmod(0o755)
    return {"CUBRID": str(root), "CUBRID_MAX_CLIENTS": "100"}, target


async def test_live_roles_explicit_default_and_masking_survive_save(live_installation):
    env, target = live_installation
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        assert "Live discovery" in str(app.query_one("#mode", Static).content)
        await pilot.press("m", "x", "c")
        assert app.query_one("#settings", OptionList).option_count == 1
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "Previous assignment: 100" in details
        assert "C: 100 • default: 100 • default difference: no" in details
        assert "S: 5 • default: 100 • default difference: yes" in details
        assert "Database override [@Demo]: 5" in details
        assert "Local environment CUBRID_MAX_CLIENTS=100" in details
        await pilot.press("home", "shift+end", "2", "0", "0", "enter", "enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "Previous assignment: 200" in details
        assert "S: 5 • default: 100" in details
        assert (
            target.read_text() == "[common]\nmax_clients=200\n[@Demo]\nmax_clients=5\n"
        )
        assert (
            target.with_suffix(".conf.bak")
            .read_text()
            .startswith("[common]\nmax_clients=100\n")
        )
        await pilot.press("escape")
        app.query_one("#search", Input).value = "hdst"
        await pilot.pause()
        assert app.query_one("#settings", OptionList).option_count == 1
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "Hidden_setting" in details
        assert "C: unavailable" in details
    calls = [
        json.loads(line)
        for line in (target.parents[1] / "calls").read_text().splitlines()
    ]
    assert [call["args"] for call in calls] == [
        ["paramdump", "--CS-mode", "Demo"],
        ["paramdump", "--CS-mode", "--dump-flag=0x8", "Demo"],
    ]


async def test_hidden_setting_can_be_added_and_removed_with_backup(live_installation):
    env, target = live_installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        await pilot.press("h", "d", "s", "t", "enter")
        assert "Previous assignment: <absent>" in str(
            app.screen.query_one("#details", Static).content
        )
        await pilot.press("y", "e", "s", "enter")
        assert (
            target.read_text()
            == "[common]\nmax_clients=100\nHidden_setting=yes\n[@Demo]\nmax_clients=5\n"
        )
        assert target.with_suffix(".conf.bak").read_bytes() == original
        await pilot.press("enter", "ctrl+r")
        assert target.read_bytes() == original
        assert app.query_one("#settings", OptionList).option_count == 1


async def test_known_database_only_parameter_is_read_only(live_installation):
    env, target = live_installation
    (target.parents[1] / "hidden").write_text("[S ] stored_procedure_port=-1 (-1)\n")
    original = target.read_bytes()
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        await pilot.press("s", "p", "p", "enter", "1", "enter")
        assert "not supported in [common]" in str(
            app.screen.query_one("#save-status", Static).content
        )
        assert target.read_bytes() == original


@pytest.mark.parametrize("registry_env", [None, "", "registry"])
async def test_registry_picker_and_offline_escape(
    live_installation, tmp_path, monkeypatch, registry_env
):
    env, target = live_installation
    monkeypatch.chdir(tmp_path)
    directory = tmp_path
    if registry_env is not None:
        env["CUBRID_DATABASES"] = registry_env
    if registry_env:
        directory = tmp_path / registry_env
        directory.mkdir()
    (directory / "databases.txt").write_text(
        "# candidates, not running servers\n"
        "Demo /db localhost /log\nOther /db localhost /log\n"
    )
    app = ConfigurationApp(environment=env)
    async with app.run_test(size=(120, 40)) as pilot:
        assert "Registry candidates" in str(
            app.screen.query_one("#picker-title", Static).content
        )
        await pilot.press("escape", "m", "x", "c", "enter", "escape", "ctrl+d")
        await pilot.press("enter")
        await wait_for_discovery(app, pilot)
        assert "Live discovery • Demo" in str(app.query_one("#mode", Static).content)
    calls = [
        json.loads(line)
        for line in (target.parents[1] / "calls").read_text().splitlines()
    ]
    assert all(call["cwd"] == str(tmp_path) for call in calls)


async def test_partial_dump_retains_roles_and_explains_unavailable(live_installation):
    env, target = live_installation
    (target.parents[1] / "ordinary").write_text(
        "[C ] max_clients=100 (100)\nBROKEN RECORD\n"
    )
    (target.parents[1] / "hidden").write_text("")
    app = ConfigurationApp(environment=env, database="Stopped")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        assert "Incomplete discovery" in str(app.query_one("#mode", Static).content)
        diagnostic = str(app.query_one("#status", Static).content)
        assert "ordinary line 2" in diagnostic
        assert "hidden: no supported parameter records" in diagnostic
        await pilot.press("m", "x", "c", "enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "C: 100" in details
        assert "S: unavailable" in details


@pytest.mark.parametrize("leave", ["escape", "ctrl+q"])
async def test_slow_discovery_keeps_keyboard_and_cleans_process(
    live_installation, leave
):
    import asyncio
    import os

    env, target = live_installation
    root = target.parents[1]
    executable = root / "bin/cubrid"
    executable.write_text(
        f"#!{sys.executable}\nimport os, pathlib, sys, time\n"
        "if '--version' in sys.argv:\n    print('CUBRID 11.5.0'); sys.exit()\n"
        "pathlib.Path(os.environ['CUBRID'], 'pid').write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(100):
            if (root / "pid").exists():
                break
            await asyncio.sleep(0.01)
        pid = int((root / "pid").read_text())
        await pilot.press("m", "x", "c")
        assert app.query_one("#search", Input).value == "mxc"
        await pilot.press(leave)
        await pilot.pause(0.1)
        if leave == "escape":
            assert "cancelled" in str(app.query_one("#mode", Static).content)
            await pilot.press("enter", "escape")
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize(
    "original, expected",
    [
        (b"# empty", b"# empty\n[common]\nHidden_setting=yes\n"),
        (
            b"[@Demo]\nmax_clients=5",
            b"[@Demo]\nmax_clients=5\n[common]\nHidden_setting=yes\n",
        ),
        (
            b"[COMMON]\r\nmax_clients=100",
            b"[COMMON]\r\nmax_clients=100\r\nHidden_setting=yes\r\n",
        ),
        (
            b"[common]\n# retained\n[@Demo]\nmax_clients=5\n",
            b"[common]\n# retained\nHidden_setting=yes\n[@Demo]\nmax_clients=5\n",
        ),
    ],
)
async def test_insertion_preserves_sections_and_uses_protected_writer(
    live_installation, original, expected
):
    env, target = live_installation
    target.write_bytes(original)
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        await pilot.press("h", "d", "s", "t", "enter", "y", "e", "s", "enter")
        assert target.read_bytes() == expected
        assert target.with_suffix(".conf.bak").read_bytes() == original


async def test_new_assignment_conflict_retains_input(live_installation):
    env, target = live_installation
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        await pilot.press("h", "d", "s", "t", "enter", "y", "e", "s")
        target.write_text("[common]\nexternal=1\n")
        await pilot.press("enter")
        assert target.read_text() == "[common]\nexternal=1\n"
        assert app.screen.query_one("#value", Input).value == "yes"
        assert "reload" in str(app.screen.query_one("#save-status", Static).content)


async def test_connection_failure_and_missing_registry_leave_offline_route(
    live_installation,
):
    env, target = live_installation
    root = target.parents[1]
    env["CUBRID_DATABASES"] = str(root / "missing")
    executable = root / "bin/cubrid"
    executable.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "if '--version' in sys.argv:\n    print('CUBRID 11.5.0'); sys.exit()\n"
        "print('Cannot connect to database server', file=sys.stderr); sys.exit(1)\n"
    )
    app = ConfigurationApp(environment=env, database="Stopped")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        assert "Incomplete discovery" in str(app.query_one("#mode", Static).content)
        assert "Cannot connect" in str(app.query_one("#status", Static).content)
        await pilot.press("m", "x", "c", "enter", "escape", "ctrl+d")
        assert "Registry unavailable" in str(app.screen.query(Static)[1].content)
        await pilot.press("escape", "enter")
        assert "Previous assignment: 100" in str(
            app.screen.query_one("#details", Static).content
        )


async def test_ambiguous_and_conflicting_records_are_incomplete(live_installation):
    env, target = live_installation
    (target.parents[1] / "ordinary").write_text(
        '[C ] label="one (two)" ("one (two)")\n'
        "[S ] empty= (NULL)\n"
        "[S ] max_clients=100 (100)\n"
        "[S*] max_clients=200 (100)\n"
    )
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        assert "Incomplete discovery" in str(app.query_one("#mode", Static).content)
        await pilot.press("l", "a", "b", "e", "l", "enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert 'C: "one (two)" • default: "one (two)"' in details
        await pilot.press("escape")
        app.query_one("#search", Input).value = "empty"
        await pilot.pause()
        await pilot.press("enter")
        assert "S: <empty> • default: NULL" in str(
            app.screen.query_one("#details", Static).content
        )


async def test_preserved_installed_dump_catalog_and_scope(live_installation):
    env, target = live_installation
    for kind in ("ordinary", "hidden"):
        (target.parents[1] / kind).write_bytes(
            (Path(__file__).parent / "fixtures/live" / f"{kind}.txt").read_bytes()
        )
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        assert "Live discovery" in str(app.query_one("#mode", Static).content)
        assert app.query_one("#settings", OptionList).option_count > 300
        app.query_one("#search", Input).value = "service::server"
        await pilot.pause()
        await pilot.press("enter", "1", "enter")
        assert "not supported in [common]" in str(
            app.screen.query_one("#save-status", Static).content
        )


async def test_refresh_updates_observations_after_saved_config(live_installation):
    env, target = live_installation
    app = ConfigurationApp(environment=env, database="Demo")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        await pilot.press(
            "m", "x", "c", "enter", "home", "shift+end", "2", "0", "0", "enter"
        )
        (target.parents[1] / "ordinary").write_text("[S*] max_clients=200 (100)\n")
        await pilot.press("ctrl+f")
        await wait_for_discovery(app, pilot)
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "Previous assignment: 200" in details
        assert "S: 200" in details
        assert "C: unavailable" in details


async def test_host_qualified_database_retains_masking_override(live_installation):
    env, target = live_installation
    app = ConfigurationApp(environment=env, database="Demo@localhost")
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_discovery(app, pilot)
        await pilot.press("m", "x", "c", "enter")
        assert "Database override [@Demo]: 5" in str(
            app.screen.query_one("#details", Static).content
        )
