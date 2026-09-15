# Ticket 02: remove overrides and preserve files

Implemented on 2026-09-15 from task baseline `c5e34c5`.
Local ticket: `.scratch/cubrid-conf-tui/issues/02-remove-overrides-and-preserve-files.md`.
Parent: `.scratch/cubrid-conf-tui/spec.md`. Work item: 163.
Implementation commit: `2bb08c0`.

## Delivered

- Ctrl+R in the value editor removes every common occurrence of the selected
  parameter, including case variants and duplicates across repeated sections.
  This restores file inheritance without assigning a compiled default.
- Browsing displays one row using the last common assignment. Normal edits change
  that occurrence while preserving its spelling and earlier duplicates.
- Both actions retain unrelated document bytes, comments, database sections,
  permissions, ownership, ACLs and extended attributes. Removal leaves inline
  comments as valid standalone comments. Empty values and missing final newlines
  are covered. The filtered query and a valid remaining selection survive removal.
- Both actions share the existing backup and atomic-replacement transaction.
  Post-replacement inspection now checks target identity and metadata, as well as
  contents. Redirected targets cannot be reported as verified successful saves.
  Failed/uncertain replacement attempts retain input and require reopening.

[Supported semantics and primary evidence](../configuration-semantics.md) records
source locations, the pinned installed-parser experiment, and recovery boundaries.

## Verification

- Full-app keyboard flows use real temporary configuration/backup files. Tests
  cover repeated sections, mixed key case, comments, empty assignments, final-line
  removal, filtered-list selection, content conflicts and ancestor redirection.
- Caught filesystem interruptions cover old/new staging, backup replacement and
  directory sync, target replacement and sync, a rename that succeeds before an
  error is returned, unreadable outcomes, and external post-replacement changes.
  Exact target and backup bytes and user-visible messages are checked for edit
  and removal.
- Four actual process-exit cases terminate the complete app at the target rename
  boundary, before and after replacement, for both actions. They verify intact
  old/new target bytes and the pre-edit recovery backup without running cleanup.
- The pinned installed CUBRID parser confirms normalized duplicate handling,
  database-section case preservation and explicit empty values. The reproducible
  probe is developer evidence only and is not part of application startup.
- A complete headless app removal flow using the actual selected installation
  passed with a temporary configuration. No active configuration was edited and
  no database was started.

Final checks:

- `uv run pytest -q`: **80 passed** (27.20 seconds).
- `uv run mypy`: strict typechecking passed.
- `uv run ruff check src tests docs/verification`: passed.
- `uv run ruff format --check src tests docs/verification`: passed.
- `git diff --check`: passed.

## Standards

Independent Standards review of `git diff c5e34c5...2bb08c0` found no hard violations
and no actionable judgment calls. Changes follow the domain vocabulary and
application boundary. Tests operate the keyboard and actual files and inject
faults at filesystem boundaries. The shared transaction centralizes edit/removal
behavior, and the native probe is separated from runtime use.

## Spec

Independent Spec review found no missing or partial ticket-02 requirements, no
material scope creep, and no concrete defect in duplicate/case handling,
preservation, filtered-list return or filesystem outcome reporting. It checked the
ticket, parent specification, glossary and pinned parser/parameter-loader source.
The reviewer inspected tests; execution evidence is from the main implementation
session. Catalog editability controls remain in ticket 04 as specified.

Review summary: **Standards 0 findings; Spec 0 findings.**

## Limits

Supported text syntax and target restrictions remain documented in the README.
Observed conflicts are detected, but uncooperative writers can race final checks
and replacement. Process-exit tests do not simulate power loss. Abrupt termination
cannot display a notification and may leave staged dotfiles; inspect the target
and `.bak` on recovery. Full platform/manual terminal acceptance remains part of
ticket 08. Native-library compatibility beyond the pinned evidence is not claimed.
