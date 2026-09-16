"""Supported offline metadata through the full application boundary."""

import json
import os
import sys
from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, Static

from cubrid_conf_tui.app import ConfigurationApp


def supported_payload(root: Path) -> dict[str, object]:
    return {
        "protocol": 1,
        "status": "supported",
        "artifact": {
            "path": str(root / "lib/libcubrid.so.11.5"),
            "sha256": "1" * 64,
            "build_id": "2" * 40,
            "role": "server",
            "needed_by": str(root / "bin/cub_server"),
            "soname": "libcubrid.so.11.5",
            "mode": "debug",
        },
        "compatibility": {
            "layout": "validated-test-layout",
            "evidence": "exact artifact identity and ELF contract",
            "registry_size": 1680,
        },
        "provenance": {
            "runtime_values_read": False,
            "cpu_derived": "metadata reflects the helper process environment",
        },
        "parameters": [
            {
                "id": 0,
                "name": "hidden_switch",
                "type": "boolean",
                "hidden": True,
                "client": False,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": False},
                "lower": {"state": "null"},
                "upper": {"state": "null"},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 1,
                "name": "max_clients",
                "type": "integer",
                "hidden": False,
                "client": False,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": 100},
                "lower": {"state": "value", "value": 10},
                "upper": {"state": "value", "value": 4000},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 2,
                "name": "old_switch",
                "type": "boolean",
                "hidden": False,
                "client": False,
                "server": True,
                "obsolete": True,
                "default": {"state": "value", "value": True},
                "lower": {"state": "null"},
                "upper": {"state": "null"},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 3,
                "name": "stored_procedure_port",
                "type": "integer",
                "hidden": False,
                "client": True,
                "server": False,
                "obsolete": False,
                "default": {"state": "value", "value": -1},
                "lower": {"state": "null"},
                "upper": {"state": "null"},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 4,
                "name": "max_connection_worker",
                "type": "integer",
                "hidden": False,
                "client": False,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": 40},
                "lower": {"state": "value", "value": 1},
                "upper": {"state": "value", "value": 80},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "helper_cpu",
                    "keywords": None,
                },
            },
            {
                "id": 5,
                "name": "unfill_factor",
                "type": "float",
                "hidden": False,
                "client": False,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": 0.1},
                "lower": {"state": "value", "value": 0.0},
                "upper": {"state": "value", "value": 0.3},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 6,
                "name": "error_log",
                "type": "string",
                "hidden": False,
                "client": True,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": "cub_server.err"},
                "lower": {"state": "null"},
                "upper": {"state": "null"},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 7,
                "name": "call_stack_dump_deactivation_list",
                "type": "integer_list",
                "hidden": False,
                "client": True,
                "server": True,
                "obsolete": False,
                "default": {"state": "unavailable"},
                "lower": {"state": "null"},
                "upper": {"state": "null"},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 8,
                "name": "error_log_level",
                "type": "keyword",
                "hidden": False,
                "client": True,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": 4},
                "lower": {"state": "value", "value": 0},
                "upper": {"state": "value", "value": 4},
                "has_custom_callbacks": False,
                "semantics": {
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
                },
            },
            {
                "id": 9,
                "name": "ddl_audit_log_size",
                "type": "bigint",
                "hidden": False,
                "client": True,
                "server": False,
                "obsolete": False,
                "default": {"state": "value", "value": 10485760},
                "lower": {"state": "value", "value": 10485760},
                "upper": {"state": "value", "value": 2147483648},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "size",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 10,
                "name": "callback_integer",
                "type": "integer",
                "hidden": False,
                "client": False,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": 5},
                "lower": {"state": "value", "value": 1},
                "upper": {"state": "value", "value": 10},
                "has_custom_callbacks": True,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 11,
                "name": "ha_mode",
                "type": "keyword",
                "hidden": False,
                "client": True,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": 0},
                "lower": {"state": "value", "value": 0},
                "upper": {"state": "value", "value": 5},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 12,
                "name": "thread_stacksize",
                "type": "bigint",
                "hidden": False,
                "client": False,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": 1048576},
                "lower": {"state": "value", "value": 65536},
                "upper": {"state": "value", "value": 2147483647},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "size",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
            {
                "id": 13,
                "name": "dual_toggle",
                "type": "boolean",
                "hidden": False,
                "client": True,
                "server": True,
                "obsolete": False,
                "default": {"state": "value", "value": True},
                "lower": {"state": "null"},
                "upper": {"state": "null"},
                "has_custom_callbacks": False,
                "semantics": {
                    "unit": "none",
                    "unit_adjusted": False,
                    "bounds_source": "static",
                    "keywords": None,
                },
            },
        ],
    }


@pytest.fixture
def offline_installation(tmp_path: Path):
    root = tmp_path / "cubrid"
    (root / "bin").mkdir(parents=True)
    (root / "conf").mkdir()
    (root / "lib").mkdir()
    cubrid = root / "bin/cubrid"
    cubrid.write_text("#!/bin/sh\nprintf 'CUBRID 11.5.0\\n'\n")
    cubrid.chmod(0o755)
    (root / "bin/cub_server").write_bytes(b"server fixture")
    (root / "lib/libcubrid.so.11.5").write_bytes(b"library fixture")
    target = root / "conf/cubrid.conf"
    target.write_text("[common]\nmax_clients=100\nold_switch=no\n")
    payload = root / "payload.json"
    payload.write_text(json.dumps(supported_payload(root)))
    helper = root / "helper.py"
    helper.write_text(
        "import pathlib, sys\nprint(pathlib.Path(sys.argv[1]).read_text())\n"
    )
    command = (sys.executable, str(helper), str(payload))
    return {"CUBRID": str(root)}, target, command


async def wait_for_metadata(app: ConfigurationApp, pilot) -> None:
    for _ in range(200):
        if "Discovering offline catalog" not in str(
            app.query_one("#mode", Static).content
        ):
            return
        await pilot.pause(0.02)
    pytest.fail("Offline metadata discovery did not finish")


async def wait_for_all_discovery(app: ConfigurationApp, pilot) -> None:
    for _ in range(300):
        if "Discovering" not in str(app.query_one("#mode", Static).content):
            return
        await pilot.pause(0.02)
    pytest.fail("Discovery did not finish")


async def test_supported_offline_catalog_can_be_inspected_and_saved(
    offline_installation,
):
    environment, target, command = offline_installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        assert "Supported offline catalog" in str(
            app.query_one("#mode", Static).content
        )
        await pilot.press("h", "s", "w")
        assert app.query_one("#settings", OptionList).option_count == 1
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "hidden_switch • hidden • server" in details
        assert "Raw compiled default (boolean): false" in details
        assert "Raw lower constraint: null sentinel" in details
        assert "Configuration default text: no" in details
        assert "metadata reflects the helper process environment" in details
        assert "libcubrid.so.11.5 • server • debug" in details
        selector = app.screen.query_one("#boolean-values", OptionList)
        assert selector.option_count == 3
        assert selector.highlighted == 1
        await pilot.press("space", "enter")

        assert target.read_text() == (
            "[common]\nmax_clients=100\nold_switch=no\nhidden_switch=yes\n"
        )
        assert target.with_suffix(".conf.bak").read_bytes() == original
        assert app.query_one("#search", Input).value == "hsw"


@pytest.mark.parametrize("change_key", ["up", "space"])
async def test_boolean_selector_changes_and_escape_cancels_without_mutation(
    offline_installation, change_key
):
    environment, target, command = offline_installation
    target.write_text("[common]\nhidden_switch=no\n")
    original = target.read_bytes()
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "hidden_switch"
        await pilot.pause()
        await pilot.press("enter")
        selector = app.screen.query_one("#boolean-values", OptionList)
        assert selector.highlighted == 1
        await pilot.press(change_key)
        assert selector.highlighted == 0
        await pilot.press("escape")
        assert target.read_bytes() == original
        assert not target.with_suffix(".conf.bak").exists()


@pytest.mark.parametrize(
    ("name", "value", "validation_text"),
    [
        ("max_clients", "4000", "integer from 10 to 4000"),
        ("unfill_factor", "0.25", "float from 0 to 0.3"),
        ("error_log", "server test.log", "string; empty text is distinct"),
        (
            "call_stack_dump_deactivation_list",
            "100,-200,300",
            "comma-separated integer list",
        ),
        ("error_log_level", "warning", "fatal, error, syntax, warning"),
        ("thread_stacksize", "1M", "size unit"),
    ],
)
async def test_typed_values_save_configuration_text(
    offline_installation, name, value, validation_text
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = name
        await pilot.pause()
        await pilot.press("enter")
        assert validation_text in str(app.screen.query_one("#details", Static).content)
        app.screen.query_one("#value", Input).value = value
        await pilot.press("enter")
        assert f"{name}={value}" in target.read_text()


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("max_clients", "0", "at least 10"),
        ("max_clients", "12.5", "whole decimal integer"),
        ("unfill_factor", "0.31", "at most 0.3"),
        ("unfill_factor", "nan", "finite decimal number"),
        (
            "call_stack_dump_deactivation_list",
            "1,,2",
            "comma-separated decimal integers",
        ),
        ("error_log_level", "4", "known keyword"),
        ("thread_stacksize", "63K", "at least 65536 bytes"),
        ("ddl_audit_log_size", "10XB", "supported size unit"),
    ],
)
async def test_known_invalid_typed_values_are_blocked_without_a_write(
    offline_installation, name, value, reason
):
    environment, target, command = offline_installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = name
        await pilot.pause()
        await pilot.press("enter")
        app.screen.query_one("#value", Input).value = value
        await pilot.press("enter")
        assert reason in str(app.screen.query_one("#save-status", Static).content)
        assert target.read_bytes() == original
        assert not target.with_suffix(".conf.bak").exists()


@pytest.mark.parametrize(
    ("name", "value", "limit_reason"),
    [
        ("max_connection_worker", "999", "helper CPU"),
        ("callback_integer", "5", "custom callback"),
        ("ha_mode", "replica", "keyword table unavailable"),
    ],
)
async def test_unknown_constraints_save_with_visible_limited_validation(
    offline_installation, name, value, limit_reason
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = name
        await pilot.pause()
        await pilot.press("enter")
        assert limit_reason in str(app.screen.query_one("#details", Static).content)
        app.screen.query_one("#value", Input).value = value
        await pilot.press("enter")
        assert f"{name}={value}" in target.read_text()
        status = str(app.query_one("#status", Static).content)
        assert "Limited validation" in status
        assert "startup" in status


async def test_client_only_bounds_from_server_artifact_are_not_enforced(
    offline_installation,
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "ddl_audit_log_size"
        await pilot.pause()
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "different or shared artifact role" in details
        assert "at least 10485760 bytes" not in details
        assert "Configuration default text: unavailable" in details
        app.screen.query_one("#value", Input).value = "9M"
        await pilot.press("enter")
        assert "ddl_audit_log_size=9M" in target.read_text()
        assert "different or shared artifact role" in str(
            app.query_one("#status", Static).content
        )


async def test_explicit_default_is_saved_then_remove_override_deletes_assignment(
    offline_installation,
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "max_clients"
        await pilot.pause()
        await pilot.press("enter")
        app.screen.query_one("#value", Input).value = "default"
        await pilot.press("enter")
        assert "max_clients=default" in target.read_text()
        await pilot.press("enter")
        assert "default sentinel" in str(
            app.screen.query_one("#details", Static).content
        )
        await pilot.press("ctrl+r")
        assert "max_clients=" not in target.read_text()


async def test_boolean_default_sentinel_is_selectable_and_distinct_from_remove(
    offline_installation,
):
    environment, target, command = offline_installation
    target.write_text("[common]\nhidden_switch=default\n")
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "hidden_switch"
        await pilot.pause()
        await pilot.press("enter")
        selector = app.screen.query_one("#boolean-values", OptionList)
        assert selector.highlighted == 2
        await pilot.press("enter")
        assert "hidden_switch=default" in target.read_text()
        await pilot.press("enter")
        assert "default sentinel" in str(
            app.screen.query_one("#details", Static).content
        )
        await pilot.press("ctrl+r")
        assert "hidden_switch=" not in target.read_text()


async def test_boolean_default_sentinel_can_be_written_for_absent_assignment(
    offline_installation,
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "hidden_switch"
        await pilot.pause()
        await pilot.press("enter")
        selector = app.screen.query_one("#boolean-values", OptionList)
        assert selector.highlighted == 1
        await pilot.press("down", "enter")
        assert "hidden_switch=default" in target.read_text()


async def test_role_limited_boolean_default_does_not_choose_a_concrete_value(
    offline_installation,
):
    environment, target, command = offline_installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "dual_toggle"
        await pilot.pause()
        await pilot.press("enter")
        selector = app.screen.query_one("#boolean-values", OptionList)
        assert selector.highlighted is None
        assert "Configuration default text: unavailable" in str(
            app.screen.query_one("#details", Static).content
        )
        await pilot.press("enter")
        assert target.read_bytes() == original
        assert app.screen.query_one("#boolean-values", OptionList) is selector
        await pilot.press("space", "enter")
        assert "dual_toggle=yes" in target.read_text()


@pytest.mark.parametrize(
    ("name", "assignment"),
    [
        ("max_clients", 'max_clients=" 100 "'),
        ("error_log_level", "error_log_level=' warning '"),
    ],
)
async def test_quoted_typed_text_validates_without_losing_raw_spelling(
    offline_installation, name, assignment
):
    environment, target, command = offline_installation
    target.write_text(f"[common]\n{assignment}\n")
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = name
        await pilot.pause()
        await pilot.press("enter")
        assert (
            app.screen.query_one("#value", Input).value == assignment.split("=", 1)[1]
        )
        await pilot.press("enter")
        assert target.read_text() == f"[common]\n{assignment}\n"
        assert "Saved file" in str(app.query_one("#status", Static).content)


async def test_quoted_boolean_selection_preserves_quote_style(offline_installation):
    environment, target, command = offline_installation
    target.write_text('[common]\nhidden_switch=" yes "\n')
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "hidden_switch"
        await pilot.pause()
        await pilot.press("enter")
        selector = app.screen.query_one("#boolean-values", OptionList)
        assert selector.highlighted == 0
        await pilot.press("enter")
        assert target.read_text() == '[common]\nhidden_switch=" yes "\n'
        await pilot.press("enter")
        await pilot.press("space", "enter")
        assert target.read_text() == '[common]\nhidden_switch=" no "\n'


async def test_unknown_keyword_empty_text_saves_with_limited_validation(
    offline_installation,
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "ha_mode"
        await pilot.pause()
        await pilot.press("enter")
        assert app.screen.query_one("#value", Input).value == ""
        await pilot.press("enter")
        assert "ha_mode=\n" in target.read_text()
        assert "keyword table unavailable" in str(
            app.query_one("#status", Static).content
        )


async def test_obsolete_parameter_is_not_available_but_existing_override_is_removable(
    offline_installation,
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "old_switch"
        await pilot.pause()
        assert app.query_one("#settings", OptionList).option_count == 1
        await pilot.press("enter", "home", "shift+end", "y", "e", "s", "enter")
        assert "obsolete" in str(app.screen.query_one("#save-status", Static).content)
        assert "old_switch=no" in target.read_text()
        await pilot.press("ctrl+r")
        assert "old_switch" not in target.read_text()


async def test_helper_cpu_constraints_are_not_authoritative_validation(
    offline_installation,
):
    environment, target, command = offline_installation
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "max_connection_worker"
        await pilot.pause()
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "Previous assignment: <absent>" in details
        assert "Raw compiled default (integer): 40" in details
        assert "Raw lower constraint: 1" in details
        assert "Raw upper constraint: 80" in details
        assert "C: unavailable" in details
        assert "S: unavailable" in details
        assert "helper CPU bounds are displayed but not enforced" in details
        await pilot.press("home", "shift+end", "5", "0", "0", "0", "enter")
        assert "max_connection_worker=5000" in target.read_text()


async def test_known_non_common_catalog_entry_cannot_be_inserted(
    offline_installation,
):
    environment, target, command = offline_installation
    original = target.read_bytes()
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        app.query_one("#search", Input).value = "stored_procedure_port"
        await pilot.pause()
        await pilot.press("enter", "1", "enter")
        assert "not supported in [common]" in str(
            app.screen.query_one("#save-status", Static).content
        )
        assert target.read_bytes() == original


async def test_offline_metadata_and_live_observation_share_one_parameter_row(
    offline_installation,
):
    environment, target, command = offline_installation
    cubrid = target.parents[1] / "bin/cubrid"
    cubrid.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('CUBRID 11.5.0'); raise SystemExit\n"
        "if '--dump-flag=0x8' in sys.argv:\n"
        "    print('[S*] hidden_switch=yes (no)')\n"
        "else:\n"
        "    print('[C ] max_clients=100 (100)')\n"
    )
    app = ConfigurationApp(
        environment=environment,
        database="Demo",
        metadata_command=command,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_all_discovery(app, pilot)
        mode = str(app.query_one("#mode", Static).content)
        assert "Live discovery • Demo" in mode
        assert "Supported offline catalog" in mode
        app.query_one("#search", Input).value = "hidden_switch"
        await pilot.pause()
        assert app.query_one("#settings", OptionList).option_count == 1
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "Raw compiled default (boolean): false" in details
        assert "S: yes • default: no • default difference: yes" in details
        assert "C: unavailable" in details
        await pilot.press("space", "enter")
        assert "hidden_switch=yes" in target.read_text()
        await pilot.press("enter")
        details = str(app.screen.query_one("#details", Static).content)
        assert "Previous assignment: yes (true)" in details
        assert "S: yes • default: no • default difference: yes" in details


async def test_editor_distinguishes_assignment_and_metadata_states(
    offline_installation,
):
    environment, target, command = offline_installation
    target.write_text(
        "[common]\n"
        "hidden_switch=no\n"
        "max_clients=0\n"
        "error_log=\n"
        "call_stack_dump_deactivation_list=null\n"
        "mystery=no\n"
    )
    app = ConfigurationApp(environment=environment, metadata_command=command)

    expected = {
        "hidden_switch": "Previous assignment: no (false)",
        "max_clients": "Previous assignment: 0 (zero)",
        "error_log": "Previous assignment: <empty text>",
        "call_stack_dump_deactivation_list": (
            "Previous assignment: null (null sentinel)"
        ),
        "unfill_factor": "Previous assignment: <absent>",
        "mystery": "Type / constraints: unavailable",
    }
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        for name, marker in expected.items():
            app.query_one("#search", Input).value = name
            await pilot.pause()
            await pilot.press("enter")
            details = str(app.screen.query_one("#details", Static).content)
            assert marker in details
            if name == "mystery":
                assert "no (false)" not in details
            await pilot.press("escape")


async def test_database_picker_does_not_cancel_offline_catalog_discovery(
    offline_installation,
):
    environment, target, command = offline_installation
    root = target.parents[1]
    (root / "databases.txt").write_text("Demo /db localhost /log\n")
    environment["CUBRID_DATABASES"] = str(root)
    helper = root / "slow-helper.py"
    helper.write_text(
        "import pathlib, sys, time\n"
        "time.sleep(0.2)\n"
        "print(pathlib.Path(sys.argv[1]).read_text())\n"
    )
    slow_command = (sys.executable, str(helper), command[2])
    app = ConfigurationApp(environment=environment, metadata_command=slow_command)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("enter")
        await wait_for_all_discovery(app, pilot)
        assert "Supported offline catalog" in str(
            app.query_one("#mode", Static).content
        )
        app.query_one("#search", Input).value = "hidden_switch"
        await pilot.pause()
        assert app.query_one("#settings", OptionList).option_count == 1


async def test_metadata_completion_rechecks_an_already_open_obsolete_editor(
    offline_installation,
):
    environment, target, command = offline_installation
    root = target.parents[1]
    helper = root / "delayed-helper.py"
    helper.write_text(
        "import pathlib, sys, time\n"
        "time.sleep(0.2)\n"
        "print(pathlib.Path(sys.argv[1]).read_text())\n"
    )
    delayed_command = (sys.executable, str(helper), command[2])
    app = ConfigurationApp(environment=environment, metadata_command=delayed_command)

    async with app.run_test(size=(120, 40)) as pilot:
        app.query_one("#search", Input).value = "old_switch"
        await pilot.pause()
        await pilot.press("enter", "home", "shift+end", "y", "e", "s")
        await wait_for_metadata(app, pilot)
        await pilot.press("enter")
        assert "obsolete" in str(app.screen.query_one("#save-status", Static).content)
        assert "old_switch=no" in target.read_text()


async def test_live_discovery_cannot_reintroduce_an_obsolete_catalog_entry(
    offline_installation,
):
    environment, target, command = offline_installation
    root = target.parents[1]
    target.write_text("[common]\nmax_clients=100\n")
    cubrid = root / "bin/cubrid"
    cubrid.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('CUBRID 11.5.0'); raise SystemExit\n"
        "print('[S ] old_switch=no (yes)')\n"
    )
    app = ConfigurationApp(
        environment=environment,
        database="Demo",
        metadata_command=command,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_all_discovery(app, pilot)
        app.query_one("#search", Input).value = "old_switch"
        await pilot.pause()
        assert app.query_one("#settings", OptionList).option_count == 0


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        (
            "import os, resource, signal; "
            "resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); "
            "os.kill(os.getpid(), signal.SIGSEGV)",
            "exit -11",
        ),
        ("print('{not json')", "response rejected"),
        ("import sys; sys.stdout.write('x' * 5000000)", "response exceeded the limit"),
        (
            "import json; print(json.dumps({'protocol': 1, 'status': 'unsupported', "
            "'diagnostic': 'Unknown compatibility; native access refused.'}))",
            "Unknown compatibility",
        ),
        ("import time; time.sleep(60)", "timed out"),
    ],
)
async def test_helper_failures_leave_existing_settings_editable(
    offline_installation, tmp_path: Path, program: str, expected: str
):
    environment, target, _ = offline_installation
    helper = tmp_path / "failure.py"
    helper.write_text(program + "\n")
    app = ConfigurationApp(
        environment=environment,
        metadata_command=(sys.executable, str(helper)),
        metadata_timeout=0.1,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        assert "Limited offline editing" in str(app.query_one("#mode", Static).content)
        assert expected in str(app.query_one("#mode", Static).content)
        app.query_one("#search", Input).value = "max_clients"
        await pilot.pause()
        await pilot.press("enter", "home", "shift+end", "2", "0", "0", "enter")
        assert "Saved file" in str(app.query_one("#status", Static).content)
        assert "max_clients=200" in target.read_text()


async def test_malformed_client_artifact_is_rejected_before_catalog_admission(
    offline_installation,
):
    environment, _, command = offline_installation
    payload_path = Path(command[2])
    payload = json.loads(payload_path.read_text())
    payload["artifact"]["role"] = "client"
    payload_path.write_text(json.dumps(payload))
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        assert "Limited offline editing" in str(app.query_one("#mode", Static).content)
        assert "role or mode is unsupported" in str(
            app.query_one("#mode", Static).content
        )
        app.query_one("#search", Input).value = "hidden_switch"
        await pilot.pause()
        assert app.query_one("#settings", OptionList).option_count == 0


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("unit", "pages", "unit is unsupported"),
        ("bounds_source", "universal", "bounds source is unsupported"),
        ("keywords", [], "keywords are empty"),
    ],
)
async def test_malformed_configuration_semantics_are_rejected_before_use(
    offline_installation, field, value, expected
):
    environment, target, command = offline_installation
    payload_path = Path(command[2])
    payload = json.loads(payload_path.read_text())
    payload["parameters"][8]["semantics"][field] = value
    payload_path.write_text(json.dumps(payload))
    app = ConfigurationApp(environment=environment, metadata_command=command)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        mode = str(app.query_one("#mode", Static).content)
        assert "Limited offline editing" in mode
        assert expected in mode
        app.query_one("#search", Input).value = "max_clients"
        await pilot.pause()
        await pilot.press("enter", "home", "shift+end", "2", "0", "0", "enter")
        assert "max_clients=200" in target.read_text()


async def test_quitting_cleans_up_slow_metadata_helper(
    offline_installation, tmp_path: Path
):
    environment, _, _ = offline_installation
    pid_file = tmp_path / "helper.pid"
    helper = tmp_path / "slow.py"
    helper.write_text(
        "import os, pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    app = ConfigurationApp(
        environment=environment,
        metadata_command=(sys.executable, str(helper), str(pid_file)),
    )

    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(100):
            if pid_file.exists():
                break
            await pilot.pause(0.01)
        pid = int(pid_file.read_text())
        await pilot.press("ctrl+q")
        await pilot.pause(0.1)

    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_production_helper_rejects_unknown_artifact_without_native_access(
    offline_installation,
):
    environment, _, _ = offline_installation
    app = ConfigurationApp(environment=environment)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        assert "Limited offline editing" in str(app.query_one("#mode", Static).content)
        diagnostic = str(app.query_one("#mode", Static).content)
        assert "Artifact is not a supported ELF server library" in diagnostic


async def test_helper_cannot_resolve_dependencies_from_a_foreign_cubrid_path(
    offline_installation,
):
    environment, target, command = offline_installation
    root = target.parents[1]
    environment["LD_LIBRARY_PATH"] = "/foreign/cubrid/lib:/ordinary/system/lib"
    observed = root / "helper-library-path"
    helper = root / "environment-helper.py"
    helper.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(os.environ['LD_LIBRARY_PATH'])\n"
        "print(pathlib.Path(sys.argv[2]).read_text())\n"
    )
    environment_command = (
        sys.executable,
        str(helper),
        str(observed),
        command[2],
    )
    app = ConfigurationApp(
        environment=environment,
        metadata_command=environment_command,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_metadata(app, pilot)
        assert "Supported offline catalog" in str(
            app.query_one("#mode", Static).content
        )

    assert observed.read_text().split(os.pathsep) == [
        str(root / "lib"),
        str(root / "cci/lib"),
    ]
