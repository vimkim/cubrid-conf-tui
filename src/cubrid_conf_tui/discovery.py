"""Bounded client/server utility discovery; no standalone or lifecycle commands."""

import asyncio
import os
import re
import signal
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Observation:
    value: str
    default: str
    differs: bool


@dataclass
class Parameter:
    name: str
    observations: dict[str, Observation] = field(default_factory=dict)

    @property
    def common_supported(self) -> bool:
        # system_parameter.c rejects this parameter in common (see discovery docs).
        return "::" not in self.name and self.name.lower() != "stored_procedure_port"


@dataclass
class Discovery:
    parameters: dict[str, Parameter] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)

    def admit(self, output: str, kind: str) -> None:
        count = 0
        for number, line in enumerate(output.splitlines(), 1):
            if (
                not line.strip()
                or line.startswith("#")
                or line == "System parameters to be used by the client program."
                or re.fullmatch(r"System parameters loaded by the server '[^']+'", line)
            ):
                continue
            match = re.fullmatch(
                r"\[([CS])([ *])\] ([A-Za-z][A-Za-z0-9_]*(?:::[A-Za-z][A-Za-z0-9_]*)?)="
                r'("[^"\r\n]*"|[^"\r\n]*?) \(("[^"\r\n]*"|[^"\r\n]*)\)',
                line,
            )
            if match is None:
                self.diagnostics.append(
                    f"{kind} line {number}: unsupported record: {line[:160]}"
                )
                continue
            role, marker, name, value, default = match.groups()
            parameter = self.parameters.setdefault(name.lower(), Parameter(name))
            observation = Observation(value, default, marker == "*")
            if (
                role in parameter.observations
                and parameter.observations[role] != observation
            ):
                self.diagnostics.append(
                    f"{kind} line {number}: conflicting {role} record for {name}"
                )
                continue
            parameter.observations[role] = observation
            count += 1
        if not count:
            self.diagnostics.append(f"{kind}: no supported parameter records")


async def discover(environment: Mapping[str, str], database: str) -> Discovery:
    result = Discovery()
    executable = str(Path(environment["CUBRID"]).absolute() / "bin/cubrid")
    for kind, flags in (("ordinary", []), ("hidden", ["--dump-flag=0x8"])):
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                "paramdump",
                "--CS-mode",
                *flags,
                database,
                env=dict(environment),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
            result.admit(stdout.decode("utf-8"), kind)
            if process.returncode or stderr.strip():
                result.diagnostics.append(
                    f"{kind}: exit {process.returncode}: "
                    f"{stderr.decode('utf-8', errors='replace')[:2000]}"
                )
        except (OSError, UnicodeError, TimeoutError) as error:
            result.diagnostics.append(f"{kind}: {type(error).__name__}: {error}")
        finally:
            if process is not None:
                # Also remove descendants retaining pipe descriptors after utility exit.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
    return result


def registry_candidates(environment: Mapping[str, str]) -> tuple[list[str], str]:
    path = Path(environment.get("CUBRID_DATABASES") or ".") / "databases.txt"
    candidates: list[str] = []
    diagnostics = []
    try:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            fields = line.split("#", 1)[0].split()
            if not fields:
                continue
            if len(fields) < 4 or not re.fullmatch(
                r"[A-Za-z0-9_][A-Za-z0-9_.-]*", fields[0]
            ):
                diagnostics.append(f"Registry line {number}: unsupported entry")
            elif fields[0] not in candidates:
                candidates.append(fields[0])
    except (OSError, UnicodeError) as error:
        diagnostics.append(f"Registry unavailable: {path.absolute()}: {error}")
    return candidates, "\n".join(diagnostics) or f"Registry: {path.absolute()}"
