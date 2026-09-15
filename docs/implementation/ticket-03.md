# Ticket 03: database selection and live discovery

Starting HEAD / review baseline: `767253c439843a82791b108bc79e45df5fdff09d`.
Spec: `.scratch/cubrid-conf-tui/issues/03-discover-live-and-hidden-parameters.md`.
Work item: 164. Tests use the previously approved full-app boundary.

## Behavior

Optional CLI database selection and registry picker feed asynchronous ordinary and
hidden client/server dumps from the selected installation. Offline editing remains
available on absent registry, connection failure, malformed data or cancellation.
Missing role values remain unavailable. Supported records combine by normalized
identity with original spelling and role-specific observations/default differences.
Database-section overrides and local environment information are read-only context.

Discovered supported settings enter the existing writer through an explicit insert
capability. Insertions use the last common section, or append one when absent;
line endings and unrelated sections remain. Editing/removal retain ticket 02's
shared conflict/backup/atomic-replacement transaction without changes to it.
Scope restrictions block `stored_procedure_port` and section-qualified names.
Unknown types, constraints and activation remain unavailable; printed NULL/keyword
values are observations, never automatically converted into an editable default.

## Source and installed-output evidence

Local source: `/home/vimkim/gh/cb/CBRD-27398-pgbuf-inspector-contract`,
commit `c2492f886eeb2790c4887fbc95fb3c59c419d362`.

- `src/executables/util_cs.c:2375–2450`: ordinary excludes hidden; `0x8`
  requests hidden; modern output includes C and S. Explicit `--CS-mode` avoids
  standalone opening. No lifecycle or live-update commands exist in the app.
- `src/base/system_parameter.c:6140–6191`: comments, role/default marker format,
  obsolete entries omitted. Marker compares printed current/default strings.
- `src/base/system_parameter.c:532–534,6827–6831`: qualified service parameter
  names and rejection of `stored_procedure_port` in common.
- `src/base/databases_file.c:222–242`: registry environment and CWD fallback.
- [Configuration semantics](../configuration-semantics.md) documents case-sensitive
  database-section matching and normalized common assignments.

The checked-in captures under `tests/fixtures/live/` come from a private copied
installation and isolated `tui_probe` database. Temporary absolute paths are
redacted. They are artifact-specific captures, not a universal parameter count.

Reproduce the real-process contract from the repository root on Linux with
unprivileged namespaces enabled (requires `unshare` and `ip` for this developer
experiment only):

```sh
unshare --user --map-root-user --net --ipc --pid --fork --mount-proc \
  sh -c 'ip link set lo up && exec .venv/bin/python \
    docs/verification/probe_live_dump.py "$CUBRID" tests/fixtures/live'
```

The probe refuses execution unless it is PID 1, copies installation artifacts,
uses private configuration/registry/storage and namespaces, starts only its isolated
test database, runs the complete app against it, then verifies stopped-server
fallback. Exiting the PID namespace removes residual test processes. Normal tests
use preserved captures and controlled executable responses; they never start a DB.

## Validation

Final combined suite: `uv run pytest -q` — **99 passed** (44.25 seconds).

- Full-app discovery coverage includes ordinary/hidden merge, overlapping roles,
  explicit defaults, absent/empty values, quoted parentheses, hidden insertion and
  removal, insertion with absent/repeated sections and line-ending preservation,
  conflict retention, read-only scope, database overrides, local environment,
  missing registry/connection failure, malformed/conflicting records, refresh,
  and responsive cancellation/exit with actual utility-process cleanup.
- All 78 existing application tests pass after changes, including ticket 02's
  filesystem fault injection and real process-interruption cases.
- The isolated installed contract passed on `11.5.0.2585-c2492f8`, 64-bit debug
  Linux: **380 rows**, `max_clients` server current/default `100`, and stopped-server
  offline editing. Client library SHA-256:
  `3cbce5364fe1e63f3b1ad889f58f8c8b15ab46bc43594fb255210df5babbe98c`.
- The PTY CLI check confirms terminal attributes are restored on exit.
- Strict mypy, Ruff lint/format, and diff whitespace checks pass.

## Standards

Independent review found no hard violations. Three maintainability suggestions
were addressed: bounded displayed-state waits replace fixed discovery sleeps;
the editor represents an absent assignment directly; catalog variables use the
parameter vocabulary. Re-review: **0 residual findings**.

## Spec

Independent review found one P2: host-qualified `Demo@localhost` hid `[@Demo]`.
A full-app regression reproduced it; section lookup now strips the host suffix and
uses basename, matching `system_parameter.c:6343–6348`, while preserving the full
utility connection argument. Re-review confirmed the fix and preserved save
protections: **0 residual findings**.

Review used the staged snapshot against the captured starting HEAD because the
user requested review before committing. No commits preceded the review.

Review summary: Standards 0 residual findings; Spec 0 residual findings.

## Limits

Modern dump syntax is supported; older/unknown formats degrade explicitly. Dump
strings supply no reliable type/range/restart metadata. Native catalog extraction
remains a later ticket. A syntactically valid truncated dump cannot always be
identified because this format has no terminal count/checksum; malformed records,
empty output, duplicate conflicts, failed processes and stderr are diagnosed.
