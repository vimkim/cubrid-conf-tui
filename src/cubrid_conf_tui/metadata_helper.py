"""Isolated native extractor for exact, previously validated CUBRID artifacts.

This module is launched as a child process.  Compatibility checks complete before
``ctypes`` loads a library or dereferences the private parameter registry.
"""

import ctypes
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, cast

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

LAYOUT = "c2492f8-x86_64-120-byte"
SERVER_SONAME = "libcubrid.so.11.5"
PARAMETER_TYPES = (
    "integer",
    "float",
    "boolean",
    "keyword",
    "bigint",
    "string",
    "integer_list",
    "no_type",
)
PRM_SIZE_UNIT = 0x00001000
PRM_TIME_UNIT = 0x00002000
PRM_DIFFER_UNIT = 0x00004000
# These CPU-derived initializers were checked in both exact supported revisions.
HELPER_CPU_BOUNDS = {
    "max_request_worker",
    "max_request_concurrency",
    "max_connection_worker",
    "min_connection_worker",
    "auto_scaling_window_size",
}
# These configuration spellings were also checked in both exact revisions. Unknown
# keyword tables intentionally stay absent rather than exposing raw numeric IDs.
KEYWORD_TABLES = {
    "error_log_level": (
        ("fatal", 0),
        ("error", 1),
        ("syntax", 2),
        ("warning", 3),
        ("notification", 4),
    )
}


@dataclass(frozen=True)
class SupportedArtifact:
    mode: str
    build_id: str
    registry_count: int


# These exact artifacts were inspected against the c2492f8 definition and then
# exercised source-hidden in the preserved prototype.  Shape checks below are
# defense in depth; only an exact identity reaches ctypes.
SUPPORTED_ARTIFACTS = {
    (
        "3cbce5364fe1e63f3b1ad889f58f8c8b15ab46bc43594fb255210df5babbe98c"
    ): SupportedArtifact("debug", "e34e8dfb4134ce9df54ee63df56e74da39643e0e", 393),
    (
        "0aeaeee76c0d977f85eb8d8adf014bb9f9a4a9ffb6714b08cbd4cde789ba27c0"
    ): SupportedArtifact("release", "bb5732f72c587c34b2f2f9388894fe8d93f362df", 386),
}


class UnsupportedArtifact(ValueError):
    pass


class Value(ctypes.Union):
    _fields_ = [
        ("integer", ctypes.c_int),
        ("boolean", ctypes.c_bool),
        ("float", ctypes.c_float),
        ("string", ctypes.c_char_p),
        ("integer_list", ctypes.POINTER(ctypes.c_int)),
        ("bigint", ctypes.c_uint64),
    ]


class ParameterValue(ctypes.Structure):
    _fields_ = [("is_null", ctypes.c_bool), ("value", Value)]


class NativeParameter(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_int),
        ("name", ctypes.c_char_p),
        ("flags", ctypes.c_uint),
        ("type", ctypes.c_int),
        ("dynamic_flags", ctypes.c_uint),
        ("default", ParameterValue),
        ("current", ParameterValue),
        ("upper", ParameterValue),
        ("lower", ParameterValue),
        ("force", ctypes.c_void_p),
        ("set_dup", ctypes.c_void_p),
        ("get_dup", ctypes.c_void_p),
    ]


def _elf_contract(path: Path) -> tuple[Any, BinaryIO]:
    # Callers keep the stream open while using the returned ELFFile.
    stream = path.open("rb")
    try:
        return _elf_from_stream(stream), stream
    except Exception:
        stream.close()
        raise


def _elf_from_stream(stream: BinaryIO) -> Any:
    stream.seek(0)
    elf = cast(Any, ELFFile(stream))  # type: ignore[no-untyped-call]
    if (
        elf.elfclass != 64
        or not elf.little_endian
        or elf.header["e_machine"] != "EM_X86_64"
    ):
        raise UnsupportedArtifact("expected little-endian x86-64 ELF")
    return elf


def _needed_server_library(server: Path) -> str:
    elf, stream = _elf_contract(server)
    try:
        dynamic = elf.get_section_by_name(".dynamic")
        if dynamic is None:
            raise UnsupportedArtifact("cub_server has no dynamic dependency table")
        matches = [
            tag.needed
            for tag in dynamic.iter_tags("DT_NEEDED")
            if tag.needed.startswith("libcubrid.so.")
        ]
        if matches != [SERVER_SONAME]:
            raise UnsupportedArtifact(
                "cub_server does not identify the validated server library role"
            )
        return cast(str, matches[0])
    finally:
        stream.close()


def _build_id(elf: Any) -> str:
    for section in elf.iter_sections():
        if section.header["sh_type"] != "SHT_NOTE":
            continue
        for note in section.iter_notes():
            if note["n_name"] == "GNU" and note["n_type"] == "NT_GNU_BUILD_ID":
                descriptor = note["n_desc"]
                if isinstance(descriptor, bytes):
                    return descriptor.hex()
                if isinstance(descriptor, str):
                    return descriptor.lower()
    raise UnsupportedArtifact("library has no GNU build identity")


def _registry_symbol_size(elf: Any) -> int:
    dynamic_symbols = elf.get_section_by_name(".dynsym")
    if not isinstance(dynamic_symbols, SymbolTableSection):
        raise UnsupportedArtifact("library has no dynamic symbol table")
    symbols = cast(Any, dynamic_symbols)
    matches = [symbol for symbol in symbols.iter_symbols() if symbol.name == "prm_Def"]
    if len(matches) != 1 or matches[0]["st_info"]["type"] != "STT_OBJECT":
        raise UnsupportedArtifact("library has no unambiguous parameter registry")
    return int(matches[0]["st_size"])


def _sha256(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    stream.seek(0)
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def inspect_artifact(
    root: Path,
) -> tuple[Path, str, SupportedArtifact, int, BinaryIO]:
    server = root / "bin/cub_server"
    if not server.is_file():
        raise UnsupportedArtifact(f"missing server executable: {server}")
    soname = _needed_server_library(server)
    library = root / "lib" / soname
    if not library.is_file():
        raise UnsupportedArtifact(f"missing server library: {library}")
    resolved_library = library.resolve(strict=True)
    if resolved_library.parent != (root / "lib").resolve(strict=True):
        raise UnsupportedArtifact("server library resolves outside the installation")

    stream = resolved_library.open("rb")
    try:
        digest = _sha256(stream)
        supported = SUPPORTED_ARTIFACTS.get(digest)
        if supported is None:
            raise UnsupportedArtifact(
                f"unknown artifact SHA-256 {digest}; private layout access refused"
            )
        elf = _elf_from_stream(stream)
        if elf.header["e_type"] != "ET_DYN":
            raise UnsupportedArtifact("server library is not a shared ELF object")
        build_id = _build_id(elf)
        symbol_size = _registry_symbol_size(elf)
        if build_id != supported.build_id:
            raise UnsupportedArtifact(
                "artifact build identity does not match its digest"
            )
        expected_size = supported.registry_count * ctypes.sizeof(NativeParameter)
        if ctypes.sizeof(NativeParameter) != 120 or symbol_size != expected_size:
            raise UnsupportedArtifact(
                "validated registry layout contract does not match"
            )
    except Exception:
        stream.close()
        raise
    return library.absolute(), digest, supported, symbol_size, stream


def _raw(value: ParameterValue, type_id: int) -> dict[str, object]:
    if type_id == 7:
        return {"state": "unavailable"}
    if value.is_null:
        return {"state": "null"}
    union = value.value
    raw: object
    if type_id in {0, 3}:
        raw = union.integer
    elif type_id == 1:
        raw = union.float
    elif type_id == 2:
        raw = union.boolean
    elif type_id == 4:
        raw = union.bigint
    elif type_id == 5:
        if union.string is None:
            return {"state": "unavailable"}
        raw = union.string.decode("utf-8")
    elif type_id == 6:
        if not union.integer_list:
            return {"state": "unavailable"}
        count = union.integer_list[0]
        if not 0 <= count <= 10_000:
            raise UnsupportedArtifact("integer-list count is invalid")
        raw = [union.integer_list[index] for index in range(1, count + 1)]
    else:
        raise UnsupportedArtifact("parameter type is invalid")
    return {"state": "value", "value": raw}


def _semantics(name: str, flags: int) -> dict[str, object]:
    unit = "none"
    if flags & PRM_SIZE_UNIT:
        unit = "size"
    elif flags & PRM_TIME_UNIT:
        unit = "time"
    keywords = KEYWORD_TABLES.get(name)
    return {
        "unit": unit,
        "unit_adjusted": bool(flags & PRM_DIFFER_UNIT),
        "bounds_source": "helper_cpu" if name in HELPER_CPU_BOUNDS else "static",
        "keywords": (
            [{"text": keyword, "value": value} for keyword, value in keywords]
            if keywords
            else None
        ),
    }


def extract(root: Path) -> dict[str, object]:
    library, digest, supported, symbol_size, artifact_stream = inspect_artifact(root)
    # No native object is loaded until every exact-identity and ELF check above passes.
    try:
        native_library = ctypes.CDLL(f"/proc/self/fd/{artifact_stream.fileno()}")
        registry = (NativeParameter * supported.registry_count).in_dll(
            native_library, "prm_Def"
        )
        parameters: list[dict[str, object]] = []
        names: set[str] = set()
        for expected_id, parameter in enumerate(registry):
            if parameter.id != expected_id or not parameter.name:
                raise UnsupportedArtifact("registry ID/name sanity check failed")
            name = parameter.name.decode("utf-8")
            if not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_]*(?:::[A-Za-z][A-Za-z0-9_]*)?", name
            ):
                raise UnsupportedArtifact("registry parameter name is invalid")
            if name.lower() in names or not 0 <= parameter.type < len(PARAMETER_TYPES):
                raise UnsupportedArtifact(
                    "registry uniqueness/type sanity check failed"
                )
            names.add(name.lower())
            parameters.append(
                {
                    "id": expected_id,
                    "name": name,
                    "type": PARAMETER_TYPES[parameter.type],
                    "hidden": bool(parameter.flags & 0x8),
                    "client": bool(parameter.flags & 0x2),
                    "server": bool(parameter.flags & 0x4),
                    "obsolete": bool(parameter.flags & 0x80000000),
                    "default": _raw(parameter.default, parameter.type),
                    "lower": _raw(parameter.lower, parameter.type),
                    "upper": _raw(parameter.upper, parameter.type),
                    "has_custom_callbacks": bool(
                        parameter.set_dup or parameter.get_dup
                    ),
                    "semantics": _semantics(name, parameter.flags),
                }
            )
    finally:
        artifact_stream.close()
    return {
        "protocol": 1,
        "status": "supported",
        "artifact": {
            "path": str(library),
            "sha256": digest,
            "build_id": supported.build_id,
            "role": "server",
            "needed_by": str((root / "bin/cub_server").absolute()),
            "soname": SERVER_SONAME,
            "mode": supported.mode,
        },
        "compatibility": {
            "layout": LAYOUT,
            "evidence": (
                "exact SHA-256 allowlist plus ELF/build-id/server-role contract"
            ),
            "registry_size": symbol_size,
        },
        "provenance": {
            "runtime_values_read": False,
            "cpu_derived": (
                "CPU-derived metadata reflects the helper process environment"
            ),
        },
        "parameters": parameters,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m cubrid_conf_tui.metadata_helper CUBRID")
    root = Path(sys.argv[1]).absolute()
    try:
        payload = extract(root)
    except (OSError, UnicodeError, ELFError, UnsupportedArtifact) as error:
        payload = {
            "protocol": 1,
            "status": "unsupported",
            "diagnostic": (
                "Artifact is not a supported ELF server library; native access was "
                f"refused: {error}"
            ),
        }
    print(json.dumps(payload, allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
