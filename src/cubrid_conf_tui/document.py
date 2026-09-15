"""Edit a conservative subset of CUBRID INI text without serializing the file."""

import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(Exception):
    """An actionable prerequisite, document, or save error."""


def editing_target(environment: Mapping[str, str]) -> Path:
    root_text = environment.get("CUBRID", "")
    if not root_text.strip():
        raise ConfigurationError("Set CUBRID to a usable installation directory.")
    root = Path(root_text).absolute()
    executable = root / "bin" / "cubrid"
    if (
        not root.is_dir()
        or not executable.is_file()
        or not os.access(executable, os.X_OK)
    ):
        raise ConfigurationError(f"Unusable CUBRID: expected executable {executable}.")
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            env=dict(environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigurationError(
            f"Unusable CUBRID: {executable} --version failed: {error}"
        ) from error
    if result.returncode or not re.search(
        rb"(?m)^CUBRID [0-9]+\.[0-9]+", result.stdout
    ):
        raise ConfigurationError(
            f"Unusable CUBRID: {executable} --version did not return a valid version "
            f"(exit {result.returncode}). Check installation libraries and environment."
        )
    return Path(
        environment.get("CUBRID_CONF_FILE") or root / "conf/cubrid.conf"
    ).absolute()


def validate_value(value: str) -> None:
    if any(
        ord(char) < 32 or char in "\x7f\x85\u2028\u2029" for char in value
    ) or value.rstrip().endswith("\\"):
        raise ConfigurationError(
            "Unsupported value: NULs, controls, line separators "
            "and continuations are forbidden."
        )


@dataclass(frozen=True)
class Assignment:
    name: str
    value: str
    line: int
    prefix: str
    suffix: str


@dataclass(frozen=True)
class Revision:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    size: int
    modified: int
    changed: int

    @classmethod
    def from_stat(cls, info: os.stat_result) -> "Revision":
        return cls(
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_uid,
            info.st_gid,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )


def inspect_path(path: Path) -> tuple[Revision, tuple[tuple[int, int], ...]]:
    """Reject indirection and remember ancestor identities without resolving aliases."""
    parents = []
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ConfigurationError(f"Unsupported target indirection: {parent}")
        parents.append((info.st_dev, info.st_ino))
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ConfigurationError(
            f"Unsupported target indirection or nonregular file: {path}"
        )
    return Revision.from_stat(info), tuple(parents)


def file_attributes(path: Path | int) -> dict[str, bytes]:
    return {name: os.getxattr(path, name) for name in os.listxattr(path)}


class ConfigurationDocument:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.requires_reload = False
        self.reload()

    def reload(self) -> None:
        self.revision, self.parents = inspect_path(self.path)
        self.original = self.path.read_bytes()
        self.attributes = file_attributes(self.path)
        self.check_conflict()
        if b"\r" in self.original.replace(b"\r\n", b""):
            raise ConfigurationError("Unsupported document: bare carriage return.")
        self.lines = self.original.decode("utf-8").splitlines(keepends=True)
        self.assignments: dict[str, Assignment] = {}
        section = ""
        sections: set[str] = set()
        keys: set[tuple[str, str]] = set()
        for index, line in enumerate(self.lines):
            body = line.removesuffix("\n").removesuffix("\r")
            if (
                len(line.encode("utf-8")) > 510
                or any(ord(char) < 32 and char != "\t" for char in body)
                or any(char in body for char in "\x7f\x85\u2028\u2029")
                or body.rstrip().endswith("\\")
            ):
                self.unsupported(index, "controls, long lines or continuation")
            stripped = body.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("["):
                match = re.fullmatch(r"\[([@%]?[A-Za-z0-9_.-]+)\]", stripped)
                if not match:
                    self.unsupported(index, "section syntax")
                assert match is not None
                section = match[1]
                if section in sections or (
                    not section.startswith("@") and section != section.lower()
                ):
                    self.unsupported(index, "duplicate or case-variant section")
                sections.add(section)
                continue
            match = re.fullmatch(r"([ \t]*([a-z][a-z0-9_]*)[ \t]*=[ \t]*)(.*)", body)
            if not match or not section:
                self.unsupported(index, "assignment syntax or case variant")
            assert match is not None
            prefix, name, tail = match.groups()
            identity = (section, name)
            if identity in keys:
                self.unsupported(index, "duplicate assignment")
            keys.add(identity)
            # Quoted values may contain comment characters. Keep their raw spelling.
            if tail.startswith(('"', "'")):
                end = tail.find(tail[0], 1)
                if end < 0:
                    self.unsupported(index, "unclosed quoted value")
                value = tail[: end + 1]
                suffix = tail[end + 1 :]
                if suffix.strip() and not suffix.lstrip().startswith(("#", ";")):
                    self.unsupported(index, "text after quoted value")
            else:
                comment = re.search(r"[#;]", tail)
                end = comment.start() if comment else len(tail)
                value = tail[:end].rstrip(" \t")
                suffix = tail[len(value) :]
            if section == "common":
                self.assignments[name] = Assignment(
                    name,
                    value,
                    index,
                    prefix,
                    suffix + line[len(body) :],
                )

    @staticmethod
    def unsupported(index: int, reason: str) -> None:
        raise ConfigurationError(f"Unsupported document at line {index + 1}: {reason}.")

    def check_conflict(self) -> None:
        try:
            revision, parents = inspect_path(self.path)
            same = (
                revision == self.revision
                and parents == self.parents
                and self.path.read_bytes() == self.original
                and file_attributes(self.path) == self.attributes
            )
        except (OSError, ConfigurationError) as error:
            raise ConfigurationError(
                "External-file conflict: reload before saving."
            ) from error
        if not same:
            raise ConfigurationError("External-file conflict: reload before saving.")

    def save(self, name: str, value: str) -> str:
        if self.requires_reload:
            raise ConfigurationError("Please reload before saving again.")
        validate_value(value)
        assignment = self.assignments[name]
        new_line = assignment.prefix + value + assignment.suffix
        if len(new_line.encode("utf-8")) > 510:
            raise ConfigurationError(
                "Unsupported value: resulting line exceeds 510 bytes."
            )
        # Ensure raw text remains one supported value, including quoted forms.
        if value.startswith(('"', "'")):
            if len(value) < 2 or value.find(value[0], 1) != len(value) - 1:
                raise ConfigurationError(
                    "Unsupported value: use one complete quoted value."
                )
        elif any(char in value for char in "#;\"'"):
            raise ConfigurationError(
                "Unsupported value: quote values containing "
                "comment or quote characters."
            )
        updated_lines = self.lines.copy()
        updated_lines[assignment.line] = new_line
        updated = "".join(updated_lines).encode("utf-8")
        backup = self.path.with_name(self.path.name + ".bak")
        temporary_paths: list[Path] = []
        replacement_attempted = False
        try:
            self.check_conflict()
            if backup.exists() or backup.is_symlink():
                inspect_path(backup)
            for content in (self.original, updated):
                fd, temporary = tempfile.mkstemp(
                    prefix=f".{self.path.name}.", dir=self.path.parent
                )
                temporary_paths.append(Path(temporary))
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    info = os.fstat(stream.fileno())
                    if (info.st_uid, info.st_gid) != (
                        self.revision.uid,
                        self.revision.gid,
                    ):
                        os.fchown(stream.fileno(), self.revision.uid, self.revision.gid)
                    os.fchmod(stream.fileno(), stat.S_IMODE(self.revision.mode))
                    inherited = file_attributes(stream.fileno())
                    for attribute in inherited.keys() - self.attributes.keys():
                        os.removexattr(stream.fileno(), attribute)
                    for attribute, data in self.attributes.items():
                        if inherited.get(attribute) != data:
                            os.setxattr(stream.fileno(), attribute, data)
                    if file_attributes(
                        stream.fileno()
                    ) != self.attributes or stat.S_IMODE(
                        os.fstat(stream.fileno()).st_mode
                    ) != stat.S_IMODE(self.revision.mode):
                        raise OSError(
                            "Could not preserve file permissions and attributes."
                        )
                    stream.flush()
                    os.fsync(stream.fileno())
            self.check_conflict()
            os.replace(temporary_paths[0], backup)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
                self.check_conflict()
                replacement_attempted = True
                os.replace(temporary_paths[1], self.path)
                os.fsync(directory)
            finally:
                os.close(directory)
            if self.path.read_bytes() != updated:
                raise ConfigurationError(
                    "Target changed after replacement; reload before saving."
                )
        except OSError as error:
            try:
                observed = self.path.read_bytes()
                if replacement_attempted and observed == updated:
                    outcome = (
                        "New file is present; "
                        "durability could not be confirmed. Reload."
                    )
                elif observed == self.original:
                    outcome = "Original file verified unchanged."
                else:
                    outcome = "Target changed; reload before saving."
            except OSError:
                outcome = "Save outcome unknown: target cannot be inspected. Reload."
            raise ConfigurationError(f"{outcome} {error}") from error
        finally:
            for temporary_path in temporary_paths:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    # A cleanup failure must not replace the verified save outcome.
                    pass
        try:
            self.reload()
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.requires_reload = True
            raise ConfigurationError(
                f"Saved file; reload failed: {error}. Please reopen the application."
            ) from error
        return (
            f"Saved file: {name} = {value}. Backup: {backup}. "
            "Activation requirements unavailable."
        )
