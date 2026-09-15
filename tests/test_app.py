from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, Static

from cubrid_conf_tui.app import ConfigurationApp


@pytest.fixture
def installation(tmp_path: Path) -> tuple[dict[str, str], Path]:
    root = tmp_path / "cubrid"
    (root / "bin").mkdir(parents=True)
    executable = root / "bin" / "cubrid"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    (root / "conf").mkdir()
    target = root / "conf" / "cubrid.conf"
    target.write_bytes(
        b"# retained\r\n[common]\r\n  max_clients = 100  # clients\r\n"
        b"enable_feature=no\r\n[@demodb]\r\nmax_clients=5\r\n"
    )
    target.chmod(0o640)
    return {"CUBRID": str(root)}, target


async def test_search_open_and_cancel_preserve_file(installation):
    env, target = installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        assert str(target) in str(app.query_one("#target", Static).content)
        assert "common" in str(app.query_one("#target", Static).content)
        assert "Limited offline" in str(app.query_one("#mode", Static).content)
        await pilot.press("m", "x", "c")
        assert app.query_one(OptionList).option_count == 1
        await pilot.press("enter")
        assert app.screen.query_one("#value", Input).value == "100"
        assert "Previous assignment: 100" in str(
            app.screen.query_one("#details", Static).content
        )
        await pilot.press("home", "shift+end", "backspace", "9", "escape")
        assert app.query_one("#search", Input).value == "mxc"
        assert app.query_one(OptionList).highlighted == 0
        assert target.read_bytes() == original
        assert not target.with_name(target.name + ".bak").exists()


async def test_save_preserves_target_scope_text_backup_and_selection(
    installation, tmp_path
):
    env, default_target = installation
    original = default_target.read_bytes()
    target = tmp_path / "selected.conf"
    target.write_bytes(original)
    target.chmod(0o640)
    env["CUBRID_CONF_FILE"] = str(target)
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press(
            "m",
            "x",
            "c",
            "enter",
            "home",
            "shift+end",
            "backspace",
            "2",
            "0",
            "0",
            "enter",
        )
        assert target.read_bytes() == (
            b"# retained\r\n[common]\r\n  max_clients = 200  # clients\r\n"
            b"enable_feature=no\r\n[@demodb]\r\nmax_clients=5\r\n"
        )
        assert default_target.read_bytes() == original
        assert target.with_name(target.name + ".bak").read_bytes() == original
        assert target.stat().st_mode & 0o777 == 0o640
        assert target.with_name(target.name + ".bak").stat().st_mode & 0o777 == 0o640
        assert app.query_one("#search", Input).value == "mxc"
        assert app.query_one(OptionList).highlighted == 0
        assert "Saved file" in str(app.query_one("#status", Static).content)
        await pilot.press("enter")
        assert app.screen.query_one("#value", Input).value == "200"


@pytest.mark.parametrize(
    "value",
    [
        "x\ny=1",
        "x\ry=1",
        "x\0y",
        "x\u2028y",
        "x\u2029y",
        "x\x85y",
        "x\vy",
        "x\fy",
        "x\x1cy",
        "yes\\",
    ],
)
async def test_rejects_setting_injection_and_retains_input(installation, value):
    env, target = installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one("#value", Input).value = value
        await pilot.press("enter")
        assert app.screen.query_one("#value", Input).value == value
        assert "Unsupported value" in str(
            app.screen.query_one("#save-status", Static).content
        )
        assert target.read_bytes() == original
        assert not target.with_name(target.name + ".bak").exists()


@pytest.mark.parametrize(
    "document",
    [
        b"[common]\nx=1\nx=2\n",
        b"[common]\nx=1\nX=2\n",
        b"[Common]\nx=1\n",
        b"[common]\nx=1\n[common]\ny=2\n",
        b"[common]\nx=one\\\ny=2\n",
        b"[common]\nbroken\n",
        b"[common]\nx=one\x00two\n",
        b"[common]\nx=" + b"a" * 510 + b"\n",
    ],
)
async def test_ambiguous_documents_fail_before_write(installation, document):
    env, target = installation
    target.write_bytes(document)
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        assert "Unsupported document" in str(app.query_one("#status", Static).content)
        await pilot.press("enter")
        assert app.query_one(OptionList).option_count == 0
        assert target.read_bytes() == document


@pytest.mark.parametrize("indirection", ["symlink", "hardlink", "parent_symlink"])
async def test_indirect_targets_fail_before_write(installation, tmp_path, indirection):
    env, target = installation
    alias = tmp_path / "alias"
    if indirection == "symlink":
        alias.symlink_to(target)
    elif indirection == "hardlink":
        alias.hardlink_to(target)
    else:
        alias.symlink_to(target.parent, target_is_directory=True)
        alias = alias / target.name
    env["CUBRID_CONF_FILE"] = str(alias)
    app = ConfigurationApp(environment=env)
    async with app.run_test():
        assert "indirection" in str(app.query_one("#status", Static).content)
        assert app.query_one(OptionList).option_count == 0


@pytest.mark.parametrize("change", ["content", "permissions", "replacement", "symlink"])
async def test_observed_external_conflict_retains_text(installation, change):
    env, target = installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one("#value", Input).value = "200"
        if change == "content":
            target.write_bytes(b"[common]\nmax_clients=300\n")
        elif change == "permissions":
            target.chmod(0o600)
        else:
            moved = target.with_suffix(".moved")
            target.rename(moved)
            if change == "replacement":
                target.write_bytes(original)
            else:
                target.symlink_to(moved)
        observed = target.read_bytes()
        await pilot.press("enter")
        assert app.screen.query_one("#value", Input).value == "200"
        assert "conflict" in str(app.screen.query_one("#save-status", Static).content)
        assert "reload" in str(app.screen.query_one("#save-status", Static).content)
        assert target.read_bytes() == observed
        assert not target.with_name(target.name + ".bak").exists()


@pytest.mark.parametrize(
    "problem", ["missing", "empty", "directory", "executable", "broken"]
)
async def test_unusable_installation_never_uses_path_or_writes(
    installation, tmp_path, problem
):
    env, target = installation
    original = target.read_bytes()
    env["CUBRID_CONF_FILE"] = str(target)
    marker = tmp_path / "called"
    other_bin = tmp_path / "other-bin"
    other_bin.mkdir()
    other = other_bin / "cubrid"
    other.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    other.chmod(0o755)
    env["PATH"] = str(other_bin)
    if problem == "missing":
        del env["CUBRID"]
    elif problem == "empty":
        env["CUBRID"] = ""
    elif problem == "directory":
        env["CUBRID"] = str(tmp_path / "missing")
    elif problem == "executable":
        (Path(env["CUBRID"]) / "bin/cubrid").chmod(0o644)
    else:
        (Path(env["CUBRID"]) / "bin/cubrid").write_text("#!/bin/sh\nexit 1\n")
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        assert "CUBRID" in str(app.query_one("#status", Static).content)
        await pilot.press("enter")
        assert app.query_one(OptionList).option_count == 0
        assert target.read_bytes() == original
        assert not marker.exists()


async def test_multiline_paste_is_rejected_without_truncation(installation):
    from textual.events import Paste

    env, target = installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).post_message(Paste("200\nother=bad"))
        await pilot.pause()
        assert "Unsupported value" in str(
            app.screen.query_one("#save-status", Static).content
        )
        assert app.screen.query_one(Input).value == "100"
        assert target.read_bytes() == original


@pytest.mark.parametrize("failure", ["backup", "replace", "sync_after_replace"])
async def test_filesystem_failures_report_verified_outcome(
    installation, monkeypatch, failure
):
    import os

    env, target = installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env)
    real_replace, real_fsync = os.replace, os.fsync
    replaced = False

    def replace(source, destination, **kwargs):
        nonlocal replaced
        if (failure == "backup" and Path(destination).name.endswith(".bak")) or (
            failure == "replace" and Path(destination) == target
        ):
            raise PermissionError("injected replacement denial")
        result = real_replace(source, destination, **kwargs)
        if Path(destination) == target:
            replaced = True
        return result

    def fsync(fd):
        if failure == "sync_after_replace" and replaced:
            raise OSError("injected directory durability failure")
        return real_fsync(fd)

    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", replace)
            patch.setattr(os, "fsync", fsync)
            await pilot.press("enter")
        assert app.screen.query_one(Input).value == "200"
        message = str(app.screen.query_one("#save-status", Static).content)
        if failure == "sync_after_replace":
            assert "New file is present" in message
            assert b"max_clients = 200" in target.read_bytes()
            assert target.with_name(target.name + ".bak").read_bytes() == original
        else:
            assert "Original file verified unchanged" in message
            assert target.read_bytes() == original
        assert not list(target.parent.glob(".cubrid.conf.*"))


async def test_unknown_type_uses_text_and_empty_assignment_remains_explicit(
    installation,
):
    env, target = installation
    target.write_bytes(b'[common]\nenable_feature=no\nempty=\nquoted="a#b" # keep\n')
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        assert app.screen.query_one(Input).value == "no"
        details = str(app.screen.query_one("#details", Static).content)
        for text in (
            "Defaults: unavailable",
            "Type / constraints: unavailable",
            "Client / server observations: unavailable",
            "Activation requirements: unavailable",
            "Limited validation",
        ):
            assert text in details
        await pilot.press("escape", "e", "m", "p", "enter")
        assert app.screen.query_one(Input).value == ""
        await pilot.press("escape")
        app.query_one("#search", Input).value = "quoted"
        await pilot.pause()
        await pilot.press("enter")
        assert app.screen.query_one(Input).value == '"a#b"'
        app.screen.query_one(Input).value = '"c;d"'
        await pilot.press("enter")
        assert (
            target.read_bytes()
            == b'[common]\nenable_feature=no\nempty=\nquoted="c;d" # keep\n'
        )


async def test_repeated_save_backs_up_immediately_previous_file(installation):
    env, target = installation
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        await pilot.press("enter")
        previous = target.read_bytes()
        await pilot.press("enter")
        app.screen.query_one(Input).value = "300"
        await pilot.press("enter")
        assert target.with_name(target.name + ".bak").read_bytes() == previous
        assert b"max_clients = 300" in target.read_bytes()
