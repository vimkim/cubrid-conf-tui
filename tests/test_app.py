from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, Static

from cubrid_conf_tui.app import ConfigurationApp


@pytest.fixture
def installation(tmp_path: Path) -> tuple[dict[str, str], Path]:
    root = tmp_path / "cubrid"
    (root / "bin").mkdir(parents=True)
    executable = root / "bin" / "cubrid"
    executable.write_text("#!/bin/sh\nprintf 'CUBRID 11.5.0\\n' >&2\n")
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
        b"[common]\nx=one\\\ny=2\n",
        b"[common]\nbroken\n",
        b"[common]\nx=1\ry=2\n",
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
    "problem",
    ["missing", "empty", "directory", "executable", "broken", "silent_failure"],
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
        code = 0 if problem == "silent_failure" else 1
        (Path(env["CUBRID"]) / "bin/cubrid").write_text(f"#!/bin/sh\nexit {code}\n")
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


async def test_save_preserves_extended_file_attributes(installation):
    import os

    env, target = installation
    os.setxattr(target, "user.ticket01", b"preserve me")
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        await pilot.press("enter")
        assert os.getxattr(target, "user.ticket01") == b"preserve me"
        backup = target.with_name(target.name + ".bak")
        assert os.getxattr(backup, "user.ticket01") == b"preserve me"


async def test_save_preserves_named_user_acl_and_removes_inherited_acl(installation):
    import os
    import struct

    env, target = installation
    acl = struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, permissions, user)
        for tag, permissions, user in [
            (1, 6, 0xFFFFFFFF),
            (2, 4, 65534),
            (4, 4, 0xFFFFFFFF),
            (16, 4, 0xFFFFFFFF),
            (32, 0, 0xFFFFFFFF),
        ]
    )
    os.setxattr(target, "system.posix_acl_access", acl)
    # Distinct inherited permissions must not leak into replacement/backup.
    inherited = acl.replace(
        struct.pack("<HHI", 2, 4, 65534), struct.pack("<HHI", 2, 4, 65533)
    )
    os.setxattr(target.parent, "system.posix_acl_default", inherited)
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        await pilot.press("enter")
        assert "Saved file" in str(app.query_one("#status", Static).content)
        assert os.getxattr(target, "system.posix_acl_access") == acl
        backup = target.with_name(target.name + ".bak")
        assert os.getxattr(backup, "system.posix_acl_access") == acl


async def test_post_commit_reload_error_reports_saved_file(installation, monkeypatch):
    import os

    env, target = installation
    app = ConfigurationApp(environment=env)
    real_replace = os.replace
    real_read = Path.read_bytes
    committed = False
    reads_after_commit = 0

    def replace(source, destination):
        nonlocal committed
        real_replace(source, destination)
        if Path(destination) == target:
            committed = True

    def read(path):
        nonlocal reads_after_commit
        if path == target and committed:
            reads_after_commit += 1
            if reads_after_commit == 2:
                raise PermissionError("injected post-commit reload failure")
        return real_read(path)

    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", replace)
            patch.setattr(Path, "read_bytes", read)
            await pilot.press("enter")
        assert "Saved file; reload failed" in str(
            app.screen.query_one("#save-status", Static).content
        )
        assert app.screen.query_one(Input).value == "200"
        assert b"max_clients = 200" in target.read_bytes()
        await pilot.press("enter")
        assert "reload before saving" in str(
            app.screen.query_one("#save-status", Static).content
        )


async def test_save_preserves_special_permission_bits(installation):
    import stat

    env, target = installation
    target.chmod(0o4640)
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        await pilot.press("enter")
        assert "Saved file" in str(app.query_one("#status", Static).content)
        assert stat.S_IMODE(target.stat().st_mode) == 0o4640
        backup = target.with_name(target.name + ".bak")
        assert stat.S_IMODE(backup.stat().st_mode) == 0o4640


async def test_remove_override_preserves_comments_scope_and_filtered_list(installation):
    env, target = installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("m", "x", "c", "enter", "ctrl+r")
        assert target.read_bytes() == (
            b"# retained\r\n[common]\r\n    # clients\r\n"
            b"enable_feature=no\r\n[@demodb]\r\nmax_clients=5\r\n"
        )
        assert target.with_name(target.name + ".bak").read_bytes() == original
        assert target.stat().st_mode & 0o777 == 0o640
        assert app.query_one("#search", Input).value == "mxc"
        assert app.query_one(OptionList).option_count == 0
        assert app.query_one(OptionList).highlighted is None
        message = str(app.query_one("#status", Static).content)
        assert "Removed override" in message
        assert "inheritance" in message


async def test_case_variants_and_repeated_common_sections_use_last_assignment(
    installation,
):
    env, target = installation
    original = (
        b"[ Common ]\r\nMax_Clients=10 # first\r\nmax_clients=20\r\n"
        b"[@Demo]\r\nMAX_CLIENTS=2\r\n[@demo]\r\nmax_clients=3\r\n"
        b"[COMMON]\r\n  MAX_CLIENTS = 30 ; last\r\nother=\r\n"
    )
    target.write_bytes(original)
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("m", "x", "c")
        assert app.query_one(OptionList).option_count == 1
        assert "MAX_CLIENTS = 30" in str(
            app.query_one(OptionList).get_option_at_index(0).prompt
        )
        await pilot.press("enter")
        assert app.screen.query_one(Input).value == "30"
        app.screen.query_one(Input).value = "40"
        await pilot.press("enter")
        edited = original.replace(b"MAX_CLIENTS = 30", b"MAX_CLIENTS = 40")
        assert target.read_bytes() == edited
        assert target.with_name(target.name + ".bak").read_bytes() == original
        await pilot.press("enter", "ctrl+r")
        assert target.read_bytes() == (
            b"[ Common ]\r\n # first\r\n"
            b"[@Demo]\r\nMAX_CLIENTS=2\r\n[@demo]\r\nmax_clients=3\r\n"
            b"[COMMON]\r\n  # ; last\r\nother=\r\n"
        )
        assert target.with_name(target.name + ".bak").read_bytes() == edited
        assert app.query_one("#search", Input).value == "mxc"
        assert app.query_one(OptionList).option_count == 0


@pytest.mark.parametrize(
    ("original", "edited", "removed"),
    [
        (b"[common]\nx=", b"[common]\nx=0", b"[common]\n"),
        (b"[common]\nx=1", b"[common]\nx=0", b"[common]\n"),
        (b'[common]\nx="" # keep', b"[common]\nx=0 # keep", b"[common]\n # keep"),
        (b"[common]\nx=1 ; keep", b"[common]\nx=0 ; keep", b"[common]\n# ; keep"),
        (b"[common]\nx=1\ny=", b"[common]\nx=0\ny=", b"[common]\ny="),
    ],
)
async def test_edit_and_remove_preserve_empty_values_and_final_line(
    installation, original, edited, removed
):
    env, target = installation
    target.write_bytes(original)
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("x", "enter")
        app.screen.query_one(Input).value = "0"
        await pilot.press("enter")
        assert target.read_bytes() == edited
        await pilot.press("enter", "ctrl+r")
        assert target.read_bytes() == removed
        assert target.with_name(target.name + ".bak").read_bytes() == edited
    reopened = ConfigurationApp(environment=env)
    async with reopened.run_test():
        assert str(reopened.query_one("#status", Static).content) == ""
        assert reopened.query_one(OptionList).option_count == (
            1 if b"y=" in removed else 0
        )


async def test_remove_last_visible_row_selects_remaining_filtered_row(installation):
    env, target = installation
    target.write_bytes(b"[common]\nx_first=1\nother=0\nx_last=2\n")
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("x", "tab", "down", "enter", "ctrl+r")
        assert app.query_one("#search", Input).value == "x"
        options = app.query_one(OptionList)
        assert options.option_count == 1
        assert options.highlighted == 0
        assert options.get_option_at_index(0).id == "x_first"
        assert target.read_bytes() == b"[common]\nx_first=1\nother=0\n"


@pytest.mark.parametrize("action", ["enter", "ctrl+r"])
@pytest.mark.parametrize(
    "redirection", ["parent_symlink", "parent_replacement", "content"]
)
async def test_remove_and_edit_block_external_changes(
    installation, action, redirection
):
    env, target = installation
    app = ConfigurationApp(environment=env)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        if redirection == "content":
            target.write_bytes(b"[common]\nmax_clients=300\n")
        else:
            parent = target.parent
            moved = parent.with_name("moved")
            parent.rename(moved)
            if redirection == "parent_symlink":
                parent.symlink_to(moved, target_is_directory=True)
            else:
                parent.mkdir()
                target.write_bytes(b"[common]\nmax_clients=400\n")
        observed = target.read_bytes()
        await pilot.press(action)
        assert app.screen.query_one(Input).value == "200"
        message = str(app.screen.query_one("#save-status", Static).content)
        assert "conflict" in message and "reload" in message
        assert target.read_bytes() == observed
        assert not target.with_name(target.name + ".bak").exists()


@pytest.mark.parametrize("action", ["enter", "ctrl+r"])
async def test_redirect_after_replacement_reports_conflict(
    installation, monkeypatch, action
):
    import os

    env, target = installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=env)
    real_replace = os.replace
    redirected = target.with_suffix(".redirected")

    def replace(source, destination):
        real_replace(source, destination)
        if Path(destination) == target:
            target.rename(redirected)
            target.symlink_to(redirected)

    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", replace)
            await pilot.press(action)
        message = str(app.screen.query_one("#save-status", Static).content)
        assert "Saved file" not in message
        assert "redirected" in message and "reload" in message.lower()
        assert app.screen.query_one(Input).value == "200"
        assert target.is_symlink()
        assert target.with_name(target.name + ".bak").read_bytes() == original


@pytest.mark.parametrize("action", ["enter", "ctrl+r"])
@pytest.mark.parametrize(
    "failure",
    [
        "stage_backup",
        "stage_new",
        "backup_replace",
        "backup_sync",
        "target_replace",
        "target_replace_then_error",
        "target_sync",
        "inspection",
        "external_after_replace",
    ],
)
async def test_interrupted_saves_preserve_recovery_and_report_actual_files(
    installation, monkeypatch, action, failure
):
    import os
    import stat

    env, target = installation
    original = target.read_bytes()
    backup = target.with_name(target.name + ".bak")
    previous_backup = b"previous recovery copy\n"
    backup.write_bytes(previous_backup)
    expected = (
        original.replace(b"max_clients = 100", b"max_clients = 200")
        if action == "enter"
        else b"# retained\r\n[common]\r\n    # clients\r\nenable_feature=no\r\n"
        b"[@demodb]\r\nmax_clients=5\r\n"
    )
    app = ConfigurationApp(environment=env)
    real_sync, real_replace, real_read = os.fsync, os.replace, Path.read_bytes
    staged = 0
    committed = False

    def sync(fd):
        nonlocal staged
        if stat.S_ISREG(os.fstat(fd).st_mode):
            staged += 1
            if (staged == 1 and failure == "stage_backup") or (
                staged == 2 and failure == "stage_new"
            ):
                raise OSError("injected staging interruption")
        elif (not committed and failure == "backup_sync") or (
            committed and failure == "target_sync"
        ):
            raise OSError("injected directory interruption")
        return real_sync(fd)

    def replace(source, destination):
        nonlocal committed
        if (Path(destination) == backup and failure == "backup_replace") or (
            Path(destination) == target and failure == "target_replace"
        ):
            raise OSError("injected replacement interruption")
        real_replace(source, destination)
        if Path(destination) == target:
            committed = True
            if failure == "target_replace_then_error":
                raise OSError("injected error after successful rename")
            if failure == "external_after_replace":
                target.write_bytes(b"[common]\nmax_clients=999\n")

    def read(path):
        if path == target and committed and failure == "inspection":
            raise PermissionError("injected inspection failure")
        return real_read(path)

    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        with monkeypatch.context() as patch:
            patch.setattr(os, "fsync", sync)
            patch.setattr(os, "replace", replace)
            patch.setattr(Path, "read_bytes", read)
            await pilot.press(action)
        assert app.screen.query_one(Input).value == "200"
        message = str(app.screen.query_one("#save-status", Static).content)
        assert "Saved file" not in message and "Removed override" not in message
        if failure == "external_after_replace":
            assert target.read_bytes() == b"[common]\nmax_clients=999\n"
            assert "changed" in message and "reload" in message.lower()
        elif committed:
            assert target.read_bytes() == expected
            assert (
                "outcome unknown" if failure == "inspection" else "New file is present"
            ) in message
            assert "reload" in message.lower()
        else:
            assert target.read_bytes() == original
            assert "Original file verified unchanged" in message
        assert backup.read_bytes() == (
            previous_backup
            if failure in {"stage_backup", "stage_new", "backup_replace"}
            else original
        )
        assert not list(target.parent.glob(".cubrid.conf.*"))
        if committed:
            await pilot.press(action)
            assert "reload before saving" in str(
                app.screen.query_one("#save-status", Static).content
            )


@pytest.mark.parametrize("action", ["enter", "ctrl+r"])
@pytest.mark.parametrize("point", ["before_target", "after_target"])
def test_process_interruption_leaves_intact_target_and_recovery(
    installation, action, point
):
    import subprocess
    import sys

    env, target = installation
    original = target.read_bytes()
    # Terminate the actual app process at a filesystem boundary. This bypasses
    # finally blocks, unlike a caught OSError, and never touches an active config.
    script = """
import asyncio
import os
import sys
from pathlib import Path
from textual.widgets import Input
from cubrid_conf_tui.app import ConfigurationApp

root, selected, action, point = sys.argv[1:]
target = Path(selected)
real_replace = os.replace

def replace(source, destination):
    if Path(destination) == target and point == "before_target":
        os._exit(91)
    real_replace(source, destination)
    if Path(destination) == target and point == "after_target":
        os._exit(91)

async def run():
    app = ConfigurationApp(environment={"CUBRID": root})
    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.query_one(Input).value = "200"
        os.replace = replace
        await pilot.press(action)

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, env["CUBRID"], str(target), action, point],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 91, result.stderr.decode()
    expected_new = (
        original.replace(b"max_clients = 100", b"max_clients = 200")
        if action == "enter"
        else b"# retained\r\n[common]\r\n    # clients\r\nenable_feature=no\r\n"
        b"[@demodb]\r\nmax_clients=5\r\n"
    )
    assert target.read_bytes() == (
        original if point == "before_target" else expected_new
    )
    assert target.with_name(target.name + ".bak").read_bytes() == original
    assert target.stat().st_mode & 0o777 == 0o640
