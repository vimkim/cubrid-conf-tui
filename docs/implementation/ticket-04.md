# Ticket 04: supported offline catalog

Starting HEAD / review baseline:
`bc4d5616ee14503c4cb0f85f150562e993aabb20`.
Spec: `.scratch/cubrid-conf-tui/issues/04-browse-supported-offline-catalog.md`.
Tests use the approved complete-Textual-app boundary plus focused real-process
contracts.

## Behavior

The application starts a bounded Python helper for installed-library metadata.
Only the helper imports pyelftools and ctypes; the Textual process validates a
strict, size-limited JSON protocol and never loads or dereferences native registry
structures. Timeout, signal crash, oversized/malformed output, missing helper or
dependency, and unsupported layouts keep the existing-settings editor usable and
explicitly limited. Cancellation and exit kill the helper process group and drain
its pipes without unbounded buffering.

Supported metadata and ticket 03 live observations merge by normalized parameter
identity into one row. The editor displays hidden/ordinary classification,
client/server flags, typed raw defaults and bounds, callback presence, helper-CPU
attribution, and server artifact path, mode, SHA-256, build ID and compatibility
evidence. Raw values are not prefilled or treated as configuration text; saves
remain visibly limited validation. Uninitialized native current values are never
read or presented as configured/live state.

Obsolete entries are excluded from the available catalog. Existing obsolete
assignments remain inspectable/removable but cannot be resaved, including when an
editor was opened before metadata completed. Live discovery cannot reintroduce an
obsolete entry. Section-qualified parameters and `stored_procedure_port` remain
read-only for common insertion. Catalog edits and removals use ticket 02's
unchanged conflict, backup, metadata-preservation and atomic-replacement writer.

## Compatibility gate

Compatibility is exact, not inferred from table shape. Before native loading the
helper requires all of the following to agree:

- `cub_server` declares `libcubrid.so.11.5` as its server dependency;
- the library is a little-endian x86-64 shared ELF object;
- the full artifact SHA-256 and GNU build ID match a previously validated entry;
- the exported `prm_Def` object size matches that entry's inspected 120-byte
  layout and registry count.

The already-hashed open file descriptor is passed to `dlopen` through `/proc`, so
path replacement cannot swap in an unchecked artifact between proof and loading.
Consecutive IDs, names and types remain post-load sanity checks, not compatibility
proof. The child receives only the selected installation's `lib` and `cci/lib`
paths; an inherited foreign CUBRID `LD_LIBRARY_PATH` cannot satisfy a missing
dependency.

The exact supported server artifacts are:

| Mode | CUBRID build | SHA-256 | Build ID | Registry / hidden / obsolete |
| --- | --- | --- | --- | ---: |
| Debug | 11.5.0.2585-c2492f8 | `3cbce5364fe1e63f3b1ad889f58f8c8b15ab46bc43594fb255210df5babbe98c` | `e34e8dfb4134ce9df54ee63df56e74da39643e0e` | 393 / 157 / 12 |
| Release | 11.5.0.2546-481d26c | `0aeaeee76c0d977f85eb8d8adf014bb9f9a4a9ffb6714b08cbd4cde789ba27c0` | `bb5732f72c587c34b2f2f9388894fe8d93f362df` | 386 / 155 / 12 |

## Verification

`docs/verification/probe_offline_catalog.py` ran both artifact classes with the
source root hidden, host files read-only and networking isolated. Independent
expectations reference prototype commit `7ff8245`, source revision `c2492f8`,
`docs/offline-catalog-findings.md`, and the preserved prototype captures. The
captures record platform, architecture, Python, CPU count/affinity, installation,
library path and sandbox conditions.

- Both helpers returned the identities and counts above. Debug/release
  `enable_pgbuf_inspector` was hidden, server-side, boolean and raw false;
  `er_log_debug` was raw true/false respectively.
- Tracing observed zero network calls, write opens, or configuration, source and
  database reads for each extraction.
- Full-app real-process flows exposed 381 debug and 374 release non-obsolete rows,
  inspected provenance, and saved `enable_pgbuf_inspector=yes` only to temporary
  targets with recovery backups. No database was opened or started.
- Removing `libcascci.so.11.3` from an otherwise exact validated debug installation
  reached the loader and returned explicit unsupported fallback. A current
  unallowlisted debug artifact was rejected by SHA-256 before native loading.
- Controlled full-app subprocess cases cover actual SIGSEGV termination (with core
  creation disabled), timeout, excessive output, malformed JSON, wrong artifact
  role, unsupported compatibility and quit-time child cleanup.

Final checks:

- `uv run pytest -q`: **116 passed** (54.06 seconds).
- `uv run mypy`: strict typechecking passed.
- `uv run ruff check src tests docs/verification`: passed.
- `uv run ruff format --check src tests docs/verification`: passed.
- `uv lock --check` and `git diff --cached --check`: passed.

## Review

Independent Standards and Spec agents reviewed the staged snapshot against the
captured starting HEAD. The first passes found one duplicated ELF check and three
spec gaps: stale editability after async metadata, obsolete live reintroduction,
and incomplete crash/dependency failure evidence. Re-review then found missing
verification-environment provenance and foreign inherited library-path mixing.
All findings received regressions or evidence checks and were fixed.

Final review summary: **Standards 0 residual findings; Spec 0 residual findings.**

## Limits

Compatibility is intentionally limited to the two exact artifacts above; similar
versions, architectures and registry sizes degrade rather than guess. Raw keyword
IDs, units, sentinels, callback semantics and CPU-sensitive bounds do not yet
drive typed controls or authoritative range validation; that work belongs to
ticket 05. Source enrichment and activation guidance remain later slices.
Bubblewrap and strace are verification-only tools, not runtime dependencies.
