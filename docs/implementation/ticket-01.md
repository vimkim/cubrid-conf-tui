# Ticket 01: existing common settings

Completed 2026-09-15 against accepted design baseline `849a27a`.
Local tracker: `.scratch/cubrid-conf-tui/issues/01-edit-existing-common-settings.md`.
Parent: `.scratch/cubrid-conf-tui/spec.md`. Work item: 162.

## Delivered

- Installable Python/uv/Textual CLI; explicitly limited offline editing.
- Selected installation validation using its own `bin/cubrid --version`, requiring
  recognizable version output as well as successful exit. Nonempty configuration
  override is honored, with the full path and common-only scope always displayed.
- Fuzzy search, text editor, previous assignment and unavailable metadata, cancel,
  and save with retained query/selection.
- Conservative lossless document edits, injection rejection, ordinary external
  conflict detection, atomic replacement and previous-file `.bak` backup.
- Ownership, mode bits, named ACLs and extended attributes preserved and verified.
  Errors retain text and report inspected outcomes, including post-replacement
  durability uncertainty and a verified save followed by a reload failure.

Implementation commits: `169e57e`, `a1cfa95`, `7c3f2cd`.

## Verification

- `uv run pytest`: **46 passed**, full app/Pilot flows plus real uv process checks.
- `uv run mypy`: passed in strict mode.
- `uv run ruff check src tests`: passed.
- `uv run ruff format --check src tests`: passed.
- `git diff --check`: passed.
- Isolated `uv tool install .` and installed `cubrid-conf-tui --help`: passed.
- Real pseudo-terminal launch, rendering, Ctrl+Q exit and terminal attribute
  restoration: passed; included in the suite.
- Installed CUBRID prerequisite and full-app save using a temporary configuration:
  passed against `/home/vimkim/.cub/install/CBRD-27398-pgbuf-inspector-contract/debug_gcc`,
  reporting CUBRID 11.5.0.2585-c2492f8. No active configuration was edited and no
  database was started. This establishes the prerequisite/offline workflow only,
  not native catalog compatibility.

The approved principal test boundary remained the complete Textual app with real
files. Fault injection was confined to filesystem operations. Each correctness
repair had a failing application regression before the fix.

## Standards review

No documented-standard violations or actionable heuristic findings. Independent
review covered domain vocabulary, module responsibilities and approved test seams.

## Spec review

Three findings were reproduced and fixed:

1. Named ACL permissions disappeared on replacement: preserve and verify attributes
   on backup and replacement, including handling inherited directory ACLs.
2. Post-commit reload failures showed only the raw error: report the verified save
   and failed reload, retain text, and require reopening before another save.
3. Buffered writes could clear restored special permissions: flush content before
   restoring ownership, permissions and attributes; sync afterward.

Regression cases verify each fix through the complete app. Independent follow-up
review at `7c3f2cd` confirmed all findings resolved and no remaining concrete
ticket-01 spec findings or scope creep.

Final review summary: Standards 0 open findings; Spec 0 open findings.

## Limits and follow-up

Ticket 01 accepts only supported unambiguous existing assignments. Duplicates,
case variants, continuations, indirect targets and unsupported syntax fail before
writing; the inheritance slice broadens those semantics. The checks detect
observed conflicts but cannot exclude unrelated writers in the final check/replace
window. A conflict requires reopening the application to reload.

Metadata, live discovery, database selection, new assignments, removal and typed
validation belong to subsequent tickets. The real PTY check is automated; a human
visual terminal acceptance review and broader platform/package verification remain
part of final integration ticket 08.
