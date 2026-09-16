"""Validated protocol for the bounded installed-library metadata helper."""

import asyncio
import json
import math
import os
import re
import signal
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

PROTOCOL = 1
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_PARAMETERS = 1_000
PARAMETER_TYPES = {
    "integer",
    "float",
    "boolean",
    "keyword",
    "bigint",
    "string",
    "integer_list",
    "no_type",
}


@dataclass(frozen=True)
class RawValue:
    state: str
    value: object | None = None

    def display(self) -> str:
        if self.state == "null":
            return "null sentinel"
        if self.state == "unavailable":
            return "unavailable"
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, list):
            return "[" + ", ".join(str(item) for item in self.value) + "]"
        if isinstance(self.value, str):
            return repr(self.value)
        return str(self.value)


@dataclass(frozen=True)
class ArtifactIdentity:
    path: Path
    sha256: str
    build_id: str
    role: str
    needed_by: Path
    soname: str
    mode: str


@dataclass(frozen=True)
class Compatibility:
    layout: str
    evidence: str
    registry_size: int


@dataclass(frozen=True)
class MetadataProvenance:
    artifact: ArtifactIdentity
    compatibility: Compatibility
    cpu_derived: str


@dataclass(frozen=True)
class Keyword:
    text: str
    value: int


@dataclass(frozen=True)
class ConfigurationSemantics:
    unit: str
    unit_adjusted: bool
    bounds_source: str
    keywords: tuple[Keyword, ...] | None


@dataclass(frozen=True)
class MetadataEntry:
    name: str
    type_name: str
    hidden: bool
    client: bool
    server: bool
    obsolete: bool
    default: RawValue
    lower: RawValue
    upper: RawValue
    has_custom_callbacks: bool
    semantics: ConfigurationSemantics
    provenance: MetadataProvenance


@dataclass
class MetadataCatalog:
    parameters: dict[str, MetadataEntry] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    supported: bool = False


class InvalidMetadata(ValueError):
    pass


def _keys(value: dict[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise InvalidMetadata(f"{label} fields are invalid")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise InvalidMetadata(f"{label} must be an object")
    return value


def _string(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4_096
        or any(ord(char) < 32 for char in value)
    ):
        raise InvalidMetadata(f"{label} must be a nonempty safe string")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidMetadata(f"{label} must be boolean")
    return value


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise InvalidMetadata(f"{label} must be an integer in range")
    return value


def _semantics(value: object, type_name: str) -> ConfigurationSemantics:
    item = _mapping(value, "parameter.semantics")
    _keys(
        item,
        {"unit", "unit_adjusted", "bounds_source", "keywords"},
        "parameter.semantics",
    )
    unit = _string(item.get("unit"), "parameter.semantics.unit")
    if unit not in {"none", "size", "time"}:
        raise InvalidMetadata("parameter semantics unit is unsupported")
    if unit != "none" and type_name not in {"integer", "bigint", "float"}:
        raise InvalidMetadata("parameter unit does not match its type")
    unit_adjusted = _boolean(
        item.get("unit_adjusted"), "parameter.semantics.unit_adjusted"
    )
    bounds_source = _string(
        item.get("bounds_source"), "parameter.semantics.bounds_source"
    )
    if bounds_source not in {"static", "helper_cpu"}:
        raise InvalidMetadata("parameter bounds source is unsupported")
    if bounds_source == "helper_cpu" and type_name != "integer":
        raise InvalidMetadata("helper-CPU bounds do not match the parameter type")
    raw_keywords = item.get("keywords")
    keywords: tuple[Keyword, ...] | None = None
    if raw_keywords is not None:
        if type_name != "keyword" or not isinstance(raw_keywords, list):
            raise InvalidMetadata("parameter keywords are invalid")
        parsed: list[Keyword] = []
        texts: set[str] = set()
        for raw_keyword in raw_keywords:
            keyword = _mapping(raw_keyword, "parameter keyword")
            _keys(keyword, {"text", "value"}, "parameter keyword")
            keyword_text = _string(keyword.get("text"), "parameter keyword text")
            identity = keyword_text.lower()
            if identity in texts:
                raise InvalidMetadata("parameter keyword is duplicated")
            texts.add(identity)
            parsed.append(
                Keyword(
                    keyword_text,
                    _integer(
                        keyword.get("value"),
                        "parameter keyword value",
                        -(2**31),
                        2**31 - 1,
                    ),
                )
            )
        if not parsed:
            raise InvalidMetadata("parameter keywords are empty")
        keywords = tuple(parsed)
    return ConfigurationSemantics(unit, unit_adjusted, bounds_source, keywords)


def _raw_value(value: object, type_name: str, label: str) -> RawValue:
    item = _mapping(value, label)
    state = item.get("state")
    if state in {"null", "unavailable"}:
        if set(item) != {"state"}:
            raise InvalidMetadata(f"{label} has unexpected fields")
        return RawValue(state)
    if state != "value" or set(item) != {"state", "value"}:
        raise InvalidMetadata(f"{label} has an unsupported state")
    raw = item["value"]
    valid = False
    if type_name == "boolean":
        valid = isinstance(raw, bool)
    elif type_name in {"integer", "keyword"}:
        valid = (
            isinstance(raw, int)
            and not isinstance(raw, bool)
            and -(2**31) <= raw < 2**31
        )
    elif type_name == "bigint":
        valid = isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw < 2**64
    elif type_name == "float":
        valid = (
            isinstance(raw, (int, float))
            and not isinstance(raw, bool)
            and math.isfinite(raw)
            and abs(raw) <= 3.4028235e38
        )
    elif type_name == "string":
        valid = isinstance(raw, str) and not any(
            ord(char) < 32 or char in "\x7f\x85\u2028\u2029" for char in raw
        )
    elif type_name == "integer_list":
        valid = (
            isinstance(raw, list)
            and len(raw) <= 10_000
            and all(
                isinstance(item, int)
                and not isinstance(item, bool)
                and -(2**31) <= item < 2**31
                for item in raw
            )
        )
    elif type_name == "no_type":
        valid = False
    if not valid:
        raise InvalidMetadata(f"{label} is invalid for {type_name}")
    return RawValue("value", raw)


def parse_response(data: bytes, root: Path) -> MetadataCatalog:
    if not data or len(data) > MAX_RESPONSE_BYTES:
        raise InvalidMetadata("response size is invalid")
    try:
        payload = json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise InvalidMetadata(f"response is not valid UTF-8 JSON: {error}") from error
    top = _mapping(payload, "response")
    if top.get("protocol") != PROTOCOL:
        raise InvalidMetadata("unsupported helper protocol")
    status = top.get("status")
    if status == "unsupported":
        _keys(top, {"protocol", "status", "diagnostic"}, "response")
        diagnostic = _string(top.get("diagnostic"), "diagnostic")
        return MetadataCatalog(diagnostics=[diagnostic])
    if status != "supported":
        raise InvalidMetadata("response status is invalid")
    _keys(
        top,
        {
            "protocol",
            "status",
            "artifact",
            "compatibility",
            "provenance",
            "parameters",
        },
        "response",
    )

    artifact_data = _mapping(top.get("artifact"), "artifact")
    _keys(
        artifact_data,
        {"path", "sha256", "build_id", "role", "needed_by", "soname", "mode"},
        "artifact",
    )
    soname = _string(artifact_data.get("soname"), "artifact.soname")
    expected_library = (root / "lib" / soname).absolute()
    expected_server = (root / "bin/cub_server").absolute()
    path = Path(_string(artifact_data.get("path"), "artifact.path"))
    needed_by = Path(_string(artifact_data.get("needed_by"), "artifact.needed_by"))
    if path != expected_library or needed_by != expected_server:
        raise InvalidMetadata("artifact paths do not match the selected installation")
    sha256 = _string(artifact_data.get("sha256"), "artifact.sha256")
    build_id = _string(artifact_data.get("build_id"), "artifact.build_id")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256) or not re.fullmatch(
        r"[0-9a-f]{40}", build_id
    ):
        raise InvalidMetadata("artifact identity is malformed")
    role = _string(artifact_data.get("role"), "artifact.role")
    mode = _string(artifact_data.get("mode"), "artifact.mode")
    if role != "server" or mode not in {"debug", "release"}:
        raise InvalidMetadata("artifact role or mode is unsupported")
    artifact = ArtifactIdentity(path, sha256, build_id, role, needed_by, soname, mode)

    compatibility_data = _mapping(top.get("compatibility"), "compatibility")
    _keys(
        compatibility_data,
        {"layout", "evidence", "registry_size"},
        "compatibility",
    )
    compatibility = Compatibility(
        _string(compatibility_data.get("layout"), "compatibility.layout"),
        _string(compatibility_data.get("evidence"), "compatibility.evidence"),
        _integer(
            compatibility_data.get("registry_size"),
            "compatibility.registry_size",
            1,
            10_000_000,
        ),
    )
    provenance_data = _mapping(top.get("provenance"), "provenance")
    _keys(
        provenance_data,
        {"runtime_values_read", "cpu_derived"},
        "provenance",
    )
    if _boolean(
        provenance_data.get("runtime_values_read"),
        "provenance.runtime_values_read",
    ):
        raise InvalidMetadata("helper must not report runtime registry values")
    provenance = MetadataProvenance(
        artifact,
        compatibility,
        _string(provenance_data.get("cpu_derived"), "provenance.cpu_derived"),
    )

    raw_parameters = top.get("parameters")
    if (
        not isinstance(raw_parameters, list)
        or not 0 < len(raw_parameters) <= MAX_PARAMETERS
    ):
        raise InvalidMetadata("parameters must be a bounded nonempty array")
    parameters: dict[str, MetadataEntry] = {}
    for expected_id, raw_parameter in enumerate(raw_parameters):
        parameter = _mapping(raw_parameter, f"parameter {expected_id}")
        _keys(
            parameter,
            {
                "id",
                "name",
                "type",
                "hidden",
                "client",
                "server",
                "obsolete",
                "default",
                "lower",
                "upper",
                "has_custom_callbacks",
                "semantics",
            },
            f"parameter {expected_id}",
        )
        if (
            _integer(parameter.get("id"), "parameter.id", 0, MAX_PARAMETERS)
            != expected_id
        ):
            raise InvalidMetadata("parameter IDs are not consecutive")
        name = _string(parameter.get("name"), "parameter.name")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:::[A-Za-z][A-Za-z0-9_]*)?", name):
            raise InvalidMetadata(f"unsupported parameter name: {name}")
        identity = name.lower()
        if identity in parameters:
            raise InvalidMetadata(f"duplicate parameter: {name}")
        type_name = _string(parameter.get("type"), "parameter.type")
        if type_name not in PARAMETER_TYPES:
            raise InvalidMetadata(f"unsupported parameter type: {type_name}")
        entry = MetadataEntry(
            name=name,
            type_name=type_name,
            hidden=_boolean(parameter.get("hidden"), "parameter.hidden"),
            client=_boolean(parameter.get("client"), "parameter.client"),
            server=_boolean(parameter.get("server"), "parameter.server"),
            obsolete=_boolean(parameter.get("obsolete"), "parameter.obsolete"),
            default=_raw_value(
                parameter.get("default"), type_name, "parameter.default"
            ),
            lower=_raw_value(parameter.get("lower"), type_name, "parameter.lower"),
            upper=_raw_value(parameter.get("upper"), type_name, "parameter.upper"),
            has_custom_callbacks=_boolean(
                parameter.get("has_custom_callbacks"),
                "parameter.has_custom_callbacks",
            ),
            semantics=_semantics(parameter.get("semantics"), type_name),
            provenance=provenance,
        )
        parameters[identity] = entry
    if compatibility.registry_size != len(parameters) * 120:
        raise InvalidMetadata("registry size does not match the response")
    return MetadataCatalog(parameters=parameters, supported=True)


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    exceeded = False
    while True:
        chunk = await stream.read(65_536)
        if not chunk:
            return b"".join(chunks), exceeded
        remaining = limit - size
        if remaining > 0:
            chunks.append(chunk[:remaining])
        size += len(chunk)
        if size > limit:
            exceeded = True


async def discover_metadata(
    environment: Mapping[str, str],
    command: Sequence[str] | None = None,
    timeout: float = 10.0,
) -> MetadataCatalog:
    root = Path(environment["CUBRID"]).absolute()
    helper = (
        tuple(command)
        if command is not None
        else (
            sys.executable,
            "-m",
            "cubrid_conf_tui.metadata_helper",
        )
    )
    process: asyncio.subprocess.Process | None = None
    subprocess_tasks: list[asyncio.Task[object]] = []
    try:
        child_environment = dict(environment)
        library_paths = [str(root / "lib"), str(root / "cci/lib")]
        child_environment["LD_LIBRARY_PATH"] = os.pathsep.join(library_paths)
        process = await asyncio.create_subprocess_exec(
            *helper,
            str(root),
            env=child_environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_task = asyncio.create_task(
            _read_capped(process.stdout, MAX_RESPONSE_BYTES)
        )
        stderr_task = asyncio.create_task(
            _read_capped(process.stderr, MAX_DIAGNOSTIC_BYTES)
        )
        wait_task = asyncio.create_task(process.wait())
        subprocess_tasks = [stdout_task, stderr_task, wait_task]
        _, pending = await asyncio.wait(subprocess_tasks, timeout=timeout)
        if pending:
            return MetadataCatalog(diagnostics=["Offline catalog helper timed out."])
        stdout, stdout_exceeded = stdout_task.result()
        stderr, stderr_exceeded = stderr_task.result()
        if stdout_exceeded:
            return MetadataCatalog(
                diagnostics=["Offline catalog helper response exceeded the limit."]
            )
        if stderr_exceeded:
            return MetadataCatalog(
                diagnostics=["Offline catalog helper diagnostics exceeded the limit."]
            )
        if process.returncode:
            detail = stderr.decode("utf-8", errors="replace")[:2_000].strip()
            return MetadataCatalog(
                diagnostics=[
                    f"Offline catalog helper failed (exit {process.returncode})"
                    + (f": {detail}" if detail else ".")
                ]
            )
        try:
            return parse_response(stdout, root)
        except InvalidMetadata as error:
            return MetadataCatalog(
                diagnostics=[f"Offline catalog helper response rejected: {error}"]
            )
    except OSError as error:
        return MetadataCatalog(
            diagnostics=[f"Offline catalog helper unavailable: {error}"]
        )
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if subprocess_tasks:
                await asyncio.gather(*subprocess_tasks, return_exceptions=True)
            else:
                await process.wait()
