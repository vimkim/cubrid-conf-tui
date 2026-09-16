# Ticket 05: typed editing and conservative validation

Starting HEAD / review baseline:
`e39eaa06c1705659bcba1193c85d53e646c8343d`.
Spec: `.scratch/cubrid-conf-tui/issues/05-edit-with-typed-validation.md`.
Tests use the approved complete-Textual-app boundary.

## Behavior

Known booleans use a yes/no/default selector. Up/down changes the highlighted
value, Space toggles yes/no, Enter saves the selection, and Esc leaves the file
and backup untouched. An existing quoted boolean retains its single- or
double-quote style and inner edge whitespace. Other supported values use text
input. Typed validation interprets one complete surrounding quote pair and trims
its inner edge spaces/tabs like the supported CUBRID parser, while the writer
preserves the raw spelling on an unchanged save. The editor labels an absent
assignment, empty text, boolean false, numeric zero, the string/list `null`
sentinel, the universal `default` sentinel, and unavailable metadata as different
states.

The app validates configuration text before calling the unchanged protected
document writer. It supports representative integer, unsigned bigint, float,
string, comma-separated integer-list, keyword, size-unit and time-unit syntax.
The `default` sentinel remains an explicit assignment. Ctrl+R remains the only
operation that removes an override and restores inheritance.

Every saved result still says that validation is limited and does not prove
CUBRID startup acceptance. Unknown metadata continues through ticket 04's text
fallback. Callback and cross-parameter checks remain unavailable; their presence
does not prevent development edits.

## Authority boundary

The metadata protocol now carries a narrow configuration-semantics record:

| Evidence | Enforcement |
| --- | --- |
| Exact type plus static raw bounds with the same unit and exclusive artifact-role interpretation | Type and range are enforced. |
| Boolean type | The selector emits `yes`, `no`, or the explicit `default` sentinel. |
| Verified `error_log_level` table | Named keywords are enforced; its dual-role raw default is not presented as universal configuration text. |
| Size/time flags | Supported CUBRID unit spellings are parsed. |
| Client-only or shared-role bounds from the validated server artifact | Syntax is checked, but the bounds/default are displayed as role-limited rather than enforced as universal. |
| Adjusted-unit callbacks | Syntax is checked, but raw internal bounds are not enforced. |
| Known helper-CPU initializers | Integer syntax is checked, but helper-derived bounds/defaults are not treated as server-universal. |
| Unknown keyword table | Saving remains limited; raw numeric IDs are not presented as authoritative keyword spellings. |
| Custom callbacks / cross-parameter checks | Saving remains limited and explicitly says startup may reject the value. |

The established sentinel rules follow the two exact supported source revisions:
`default` is recognized before type conversion, while string and integer-list
values recognize `null`/`0`. Unknown types do not inherit these interpretations.
Injection controls, 510-byte line limits, conflict detection, backups, ACL/xattr
preservation, atomic replacement and post-write outcome checks remain in ticket
02's document writer.

Ticket 04's compatibility gate admits only the two exact server artifacts. This
ticket does not guess a client artifact layout or collapse the server registry's
client/shared flags into client metadata. Client compiled defaults and bounds
therefore remain explicitly unavailable; a role-limited boolean begins with no
concrete selection. Actual C/S runtime observations remain separate in the row and
are never replaced by the server artifact record. Adding client-library metadata
requires its own exact artifact/role compatibility evidence and a multi-role
protocol extension.

## Live and fallback behavior

Offline metadata and C/S observations still merge into one parameter row. A save
updates only configured text; the pre-save observations remain displayed until a
refresh. Metadata that completes after an editor opened is re-read at save time,
preserving ticket 04's obsolete/non-common restrictions and applying newly known
validation without replacing observations.

Malformed semantic fields reject the entire helper response before catalog
admission. Helper crashes, timeout, malformed output, unknown artifacts and
unsupported semantics preserve limited editing of existing assignments.

## Supported-artifact evidence

`docs/verification/probe_offline_catalog.py` was extended and run source-hidden,
read-only and network-isolated against both exact ticket 04 artifacts:

- debug `11.5.0.2585-c2492f8`, SHA-256
  `3cbce5364fe1e63f3b1ad889f58f8c8b15ab46bc43594fb255210df5babbe98c`;
- release `11.5.0.2546-481d26c`, SHA-256
  `0aeaeee76c0d977f85eb8d8adf014bb9f9a4a9ffb6714b08cbd4cde789ba27c0`.

Both returned the independently checked `error_log_level` keyword table, size
units for server-only `thread_stacksize` and client-only `ddl_audit_log_size`, and
a helper-CPU attribution for `max_connection_worker`. Their full apps enforced
the server-only `thread_stacksize` byte range, displayed but did not enforce the
client-only bounds from the server artifact, and saved
`enable_pgbuf_inspector=yes`, `error_log_level=warning`,
`thread_stacksize=1M`, `ddl_audit_log_size=9M`, and
`max_connection_worker=999`. The last save was permitted with an explicit warning
that the observed 80-CPU helper upper bound was not enforced. Tracing again
observed no network calls, writes, or configuration/source/database reads by
either extraction.

## Verification

- `uv run pytest -q`: **148 passed** (81.90 seconds).
- `uv run mypy`: strict typechecking passed.
- `uv run ruff check src tests docs/verification`: passed.
- `uv run ruff format --check src tests docs/verification`: passed.
- `uv lock --check` and `git diff --check`: passed.

## Review

Independent Standards and Spec agents reviewed the complete diff against the
captured starting HEAD. Their first pass found quoted-scalar spelling gaps,
unknown-keyword overvalidation, a missing boolean `default` path, incomplete
artifact-role authority, and a role-limited boolean default that could still
preselect a concrete value. Follow-up review also found that quoted inner edge
whitespace needed to follow CUBRID's trimming semantics. Each hard finding gained
full-app regression coverage and was fixed.

Final review summary: **Standards 0 residual findings; Spec 0 residual findings.**
