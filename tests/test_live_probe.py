"""Safety contracts for the opt-in real-process verification probe."""

import importlib.util
import os
import re
import socket
import subprocess
from pathlib import Path
from types import ModuleType

import pytest


class ProbeStopped(Exception):
    pass


def successful_command(
    command: list[str], **kwargs: object
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")


def master_endpoint(environment: object) -> Path:
    assert isinstance(environment, dict)
    configuration = Path(environment["CUBRID_CONF_FILE"]).read_text()
    match = re.search(r"^cubrid_port_id=(\d+)$", configuration, re.MULTILINE)
    assert match is not None
    return Path(environment["CUBRID_TMP"]) / f"CUBRID{match.group(1)}"


def bind_master_endpoint(environment: object) -> socket.socket:
    endpoint_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    endpoint_socket.bind(str(master_endpoint(environment)))
    endpoint_socket.listen()
    return endpoint_socket


@pytest.fixture
def live_probe() -> ModuleType:
    path = Path(__file__).parents[1] / "docs/verification/probe_live_dump.py"
    spec = importlib.util.spec_from_file_location("probe_live_dump", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source_installation(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    for name in ("bin", "lib", "conf", "msg", "locales", "timezones"):
        (source / name).mkdir(parents=True)
    return source


async def test_probe_selects_private_master_endpoint_before_first_process(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A harmless spawn interceptor catches the historical host endpoint choice."""

    def inspect_master_spawn(
        command: list[str], **kwargs: object
    ) -> subprocess.Popen[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert Path(command[0]).name == "cub_master"
        configuration = Path(environment["CUBRID_CONF_FILE"]).read_text()
        match = re.search(r"^cubrid_port_id\s*=\s*(\d+)$", configuration, re.MULTILINE)
        port = int(match.group(1)) if match else 1523
        endpoint = Path(environment.get("CUBRID_TMP", "/tmp")) / f"CUBRID{port}"
        private_tmp = Path(environment["CUBRID"]) / "tmp"
        assert endpoint.parent == private_tmp, (
            f"probe selected shared master endpoint {endpoint}, expected {private_tmp}"
        )
        raise ProbeStopped

    monkeypatch.setattr(live_probe.subprocess, "run", successful_command)
    monkeypatch.setattr(live_probe.subprocess, "Popen", inspect_master_spawn)

    with pytest.raises(ProbeStopped):
        await live_probe.probe(source_installation, tmp_path / "captures")


async def test_probe_configures_a_nondefault_master_port_before_first_process(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def inspect_master_spawn(
        command: list[str], **kwargs: object
    ) -> subprocess.Popen[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        configuration = Path(environment["CUBRID_CONF_FILE"]).read_text()
        match = re.search(r"^cubrid_port_id\s*=\s*(\d+)$", configuration, re.MULTILINE)
        assert match is not None, "probe retained the shared default cubrid_port_id"
        assert 1024 <= int(match.group(1)) <= 65535
        assert int(match.group(1)) != 1523
        raise ProbeStopped

    monkeypatch.setattr(live_probe.subprocess, "run", successful_command)
    monkeypatch.setattr(live_probe.subprocess, "Popen", inspect_master_spawn)

    with pytest.raises(ProbeStopped):
        await live_probe.probe(source_installation, tmp_path / "captures")


async def test_probe_cleans_server_and_master_after_failure(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InjectedFailure(Exception):
        pass

    events: list[str] = []
    master_socket: socket.socket | None = None

    class FakeProcess:
        def __init__(self, name: str) -> None:
            self.name = name
            self.pid = os.getpid()

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append(f"{self.name}:terminate")

        def wait(self, timeout: float) -> int:
            nonlocal master_socket
            events.append(f"{self.name}:wait:{timeout}")
            if self.name == "master" and master_socket is not None:
                master_socket.close()
                master_socket = None
            return 0

        def kill(self) -> None:
            events.append(f"{self.name}:kill")

    def command_result(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        action = " ".join(command[1:])
        events.append(f"run:{action}")
        if command[1] == "paramdump":
            raise InjectedFailure("after server spawn")
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    def spawn(command: list[str], **kwargs: object) -> FakeProcess:
        nonlocal master_socket
        name = Path(command[0]).name
        events.append(f"spawn:{name}")
        if name == "cub_master":
            master_socket = bind_master_endpoint(kwargs["env"])
        return FakeProcess("master" if name == "cub_master" else "server")

    monkeypatch.setattr(live_probe.subprocess, "run", command_result)
    monkeypatch.setattr(live_probe.subprocess, "Popen", spawn)

    with pytest.raises(InjectedFailure, match="after server spawn"):
        await live_probe.probe(source_installation, tmp_path / "captures")

    cleanup = events[events.index("run:paramdump --CS-mode tui_probe") + 1 :]
    assert cleanup == [
        "run:server stop tui_probe",
        "server:wait:10",
        "master:terminate",
        "master:wait:10",
    ]


async def test_probe_refuses_a_preexisting_private_master_endpoint(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint_socket: socket.socket | None = None
    spawn_count = 0

    def command_result(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal endpoint_socket
        endpoint_socket = bind_master_endpoint(kwargs["env"])
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    def forbidden_spawn(
        command: list[str], **kwargs: object
    ) -> subprocess.Popen[bytes]:
        nonlocal spawn_count
        spawn_count += 1
        raise AssertionError("a process was spawned for a pre-existing endpoint")

    monkeypatch.setattr(live_probe.subprocess, "run", command_result)
    monkeypatch.setattr(live_probe.subprocess, "Popen", forbidden_spawn)

    try:
        with pytest.raises(RuntimeError, match="already exists"):
            await live_probe.probe(source_installation, tmp_path / "captures")
    finally:
        if endpoint_socket is not None:
            endpoint_socket.close()
    assert spawn_count == 0


async def test_probe_refuses_to_start_server_when_master_exits(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server_spawned = False

    class ExitedMaster:
        def poll(self) -> int:
            return 17

    def spawn(command: list[str], **kwargs: object) -> ExitedMaster:
        nonlocal server_spawned
        if Path(command[0]).name == "cub_server":
            server_spawned = True
            raise AssertionError("server started after private master exited")
        return ExitedMaster()

    async def no_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(live_probe.subprocess, "run", successful_command)
    monkeypatch.setattr(live_probe.subprocess, "Popen", spawn)
    monkeypatch.setattr(live_probe.asyncio, "sleep", no_sleep)

    with pytest.raises(RuntimeError, match="master exited.*17"):
        await live_probe.probe(source_installation, tmp_path / "captures")
    assert not server_spawned


async def test_probe_refuses_to_start_server_without_expected_master_socket(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server_spawned = False

    class SocketlessMaster:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float) -> int:
            return 0

        def kill(self) -> None:
            raise AssertionError("responsive master should not require kill")

    def spawn(command: list[str], **kwargs: object) -> SocketlessMaster:
        nonlocal server_spawned
        if Path(command[0]).name == "cub_server":
            server_spawned = True
            raise AssertionError("server started without the expected master socket")
        return SocketlessMaster()

    async def no_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(live_probe.subprocess, "run", successful_command)
    monkeypatch.setattr(live_probe.subprocess, "Popen", spawn)
    monkeypatch.setattr(live_probe.asyncio, "sleep", no_sleep)

    with pytest.raises(RuntimeError, match="did not create endpoint"):
        await live_probe.probe(source_installation, tmp_path / "captures")
    assert not server_spawned


async def test_probe_refuses_socket_not_owned_by_spawned_master(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint_socket: socket.socket | None = None
    server_spawned = False

    class UnrelatedMaster:
        pid = 2**31 - 1

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float) -> int:
            nonlocal endpoint_socket
            if endpoint_socket is not None:
                endpoint_socket.close()
                endpoint_socket = None
            return 0

        def kill(self) -> None:
            raise AssertionError("responsive fake master should not require kill")

    def spawn(command: list[str], **kwargs: object) -> UnrelatedMaster:
        nonlocal endpoint_socket, server_spawned
        if Path(command[0]).name == "cub_server":
            server_spawned = True
            raise AssertionError("server started for an unrelated socket owner")
        endpoint_socket = bind_master_endpoint(kwargs["env"])
        return UnrelatedMaster()

    async def no_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(live_probe.subprocess, "run", successful_command)
    monkeypatch.setattr(live_probe.subprocess, "Popen", spawn)
    monkeypatch.setattr(live_probe.asyncio, "sleep", no_sleep)

    with pytest.raises(RuntimeError, match="does not own endpoint"):
        await live_probe.probe(source_installation, tmp_path / "captures")
    assert not server_spawned


async def test_probe_unregisters_an_already_exited_server_before_master_cleanup(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InjectedFailure(Exception):
        pass

    events: list[str] = []
    master_socket: socket.socket | None = None

    class Master:
        pid = os.getpid()

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("master:terminate")

        def wait(self, timeout: float) -> int:
            nonlocal master_socket
            events.append(f"master:wait:{timeout}")
            if master_socket is not None:
                master_socket.close()
                master_socket = None
            return 0

        def kill(self) -> None:
            raise AssertionError("responsive fake master should not require kill")

    class ExitedServer:
        def poll(self) -> int:
            return 17

    def command_result(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        action = " ".join(command[1:])
        events.append(f"run:{action}")
        if command[1] == "paramdump":
            raise InjectedFailure("server already exited")
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    def spawn(command: list[str], **kwargs: object) -> Master | ExitedServer:
        nonlocal master_socket
        if Path(command[0]).name == "cub_master":
            master_socket = bind_master_endpoint(kwargs["env"])
            return Master()
        return ExitedServer()

    monkeypatch.setattr(live_probe.subprocess, "run", command_result)
    monkeypatch.setattr(live_probe.subprocess, "Popen", spawn)

    with pytest.raises(InjectedFailure, match="server already exited"):
        await live_probe.probe(source_installation, tmp_path / "captures")

    assert events[-3:] == [
        "run:server stop tui_probe",
        "master:terminate",
        "master:wait:10",
    ]


async def test_probe_bounds_cleanup_and_escalates_to_kill(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InjectedFailure(Exception):
        pass

    events: list[str] = []
    master_socket: socket.socket | None = None

    class StubbornProcess:
        def __init__(self, name: str) -> None:
            self.name = name
            self.waits = 0
            self.pid = os.getpid()

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append(f"{self.name}:terminate")

        def wait(self, timeout: float) -> int:
            nonlocal master_socket
            self.waits += 1
            events.append(f"{self.name}:wait:{timeout}")
            if (self.name == "server" and self.waits <= 2) or (
                self.name == "master" and self.waits == 1
            ):
                raise subprocess.TimeoutExpired(self.name, timeout)
            if self.name == "master" and master_socket is not None:
                master_socket.close()
                master_socket = None
            return 0

        def kill(self) -> None:
            events.append(f"{self.name}:kill")

    def command_result(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        action = " ".join(command[1:])
        events.append(f"run:{action}:timeout={kwargs['timeout']}")
        if command[1] == "paramdump":
            raise InjectedFailure("exercise cleanup")
        if command[1:3] == ["server", "stop"]:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    def spawn(command: list[str], **kwargs: object) -> StubbornProcess:
        nonlocal master_socket
        name = Path(command[0]).name
        if name == "cub_master":
            master_socket = bind_master_endpoint(kwargs["env"])
            return StubbornProcess("master")
        return StubbornProcess("server")

    monkeypatch.setattr(live_probe.subprocess, "run", command_result)
    monkeypatch.setattr(live_probe.subprocess, "Popen", spawn)

    with pytest.raises(InjectedFailure, match="exercise cleanup"):
        await live_probe.probe(source_installation, tmp_path / "captures")

    assert events[-11:] == [
        "run:paramdump --CS-mode tui_probe:timeout=45",
        "run:server stop tui_probe:timeout=10",
        "server:wait:10",
        "server:terminate",
        "server:wait:10",
        "server:kill",
        "server:wait:5",
        "master:terminate",
        "master:wait:10",
        "master:kill",
        "master:wait:5",
    ]


async def test_probe_failure_preserves_callers_working_directory(
    live_probe: ModuleType,
    source_installation: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stop_at_first_spawn(
        command: list[str], **kwargs: object
    ) -> subprocess.Popen[bytes]:
        raise ProbeStopped

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(live_probe.subprocess, "run", successful_command)
    monkeypatch.setattr(live_probe.subprocess, "Popen", stop_at_first_spawn)

    with pytest.raises(ProbeStopped):
        await live_probe.probe(source_installation, tmp_path / "captures")
    assert Path.cwd() == tmp_path
