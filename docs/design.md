# CUBRID configuration TUI design

Status: accepted by the user on 2026-09-15 after consolidated review, including Python with uv, Textual, and pyelftools. The design interview is complete. Production implementation has not started.

## Purpose and scope

A Linux terminal application for developers to find CUBRID parameters, inspect their values, and edit the common configuration. Distribute a Python CLI package managed by uv, with built-in fuzzy search and configuration editing. This supersedes the earlier native single-executable packaging choice. An installed CUBRID is sufficient; source and external debug tooling are optional.

Require a nonempty, usable `CUBRID` environment variable. Edit `[common]` in `$CUBRID/conf/cubrid.conf`, honoring a nonempty `CUBRID_CONF_FILE` override and displaying the full target path. Database-specific and other configuration sections are not editable in v1.

Saving changes the file and reports activation guidance. It does not restart a server or change live values.

## User flow

1. Accept `cubrid-conf-tui <db_name>`. When the name is omitted, offer a database picker. Database candidates do not imply that a server is running. Offline editing remains available when a live dump is unavailable.
2. Show one searchable row per parameter, including hidden parameters. Display configured value, default, and client/server differences without conflating an explicit assignment with a difference from default.
3. Enter opens an editor showing the existing common assignment, available client/server observations, defaults, and relevant metadata. Show database overrides that mask a common assignment. Missing metadata is explicitly unknown.
4. Boolean parameters use a yes/no selector: arrows or Space change the selection, Enter saves, Esc cancels. Other parameters use text input.
5. Offer **Remove override** separately from writing an explicit default value.
6. After a successful save, return to the same filtered list and selection. Report what was saved and known activation requirements. Runtime observations retain their observed values until refreshed; saving alone cannot establish activation.

The target path and common-section scope remain visible. Descriptions and source locations are shown when available. Environment-derived values must not be attributed to the configuration file, and the TUI's environment is not proof of the server's environment.

## Discovery and metadata

Use compiled metadata from validated installed-library layouts in a separate process. Preserve artifact and client/server/standalone distinctions; registry membership alone is not proof that an entry is editable in common. Exclude obsolete entries from the available-parameter catalog and handle known section restrictions.

For runtime observations, merge ordinary and hidden paramdump results while preserving C/S identity. For the inspected modern format, `*` compares displayed current and default values; it does not mean an explicit file override.

| Available capability | Behavior |
| --- | --- |
| Supported installed-library metadata and live dump | Catalog/metadata plus observed client/server values |
| Supported installed-library metadata, database unavailable | Offline catalog and configured values; runtime values unavailable |
| Unsupported metadata layout, live dump available | Discover from paramdump; mark unavailable metadata unknown |
| Unsupported metadata layout, no live dump | Clearly limited offline editing of existing settings; do not claim a complete catalog |

Source is optional enrichment. Debug information may locate a source candidate in debug or RelWithDebInfo builds, but a path or short revision alone does not prove the file contents match. Missing, stale, or incompatible source must not block installed-only operation. Unsupported library layouts must not be dereferenced based on guessed offsets.

The extractor does not initialize or open a database. Library loading can execute initializers, so isolate extraction and treat failure as unavailable metadata. CPU-derived defaults and limits describe the helper environment; they may differ from those observed by a running server.

## Validation and writing

- Reject input that can inject another line/setting and violations of reliably established parameter constraints.
- Unknown constraints permit saving with **limited validation** indicated. Raw keyword IDs, units, special sentinels, callback checks, and cross-parameter rules must be interpreted before claiming validation coverage.
- Report definite restart guidance only where supported by evidence. Otherwise state that activation requirements are unknown; do not infer a universal restart rule from one flag.
- Preserve unrelated text, comments, formatting, and file permissions. Resolve duplicate common assignments consistently; Remove override must not reveal an earlier duplicate assignment.
- Detect external file changes before saving and stop conflicting writes with a reload request.
- Write atomically and retain the previous file as a recovery backup. A failed save leaves the user's input available and reports the error.

## Implementation stack

The user selected **Python with uv**. Use Textual for the terminal UI and its built-in fuzzy matcher. Use pyelftools for ELF symbol inspection and optional DWARF source discovery. The metadata extractor uses Python ctypes in a separate process, preserving the successful prototype's isolation boundary. File editing uses a text-preserving writer rather than a serializer that rewrites the entire configuration.

Keep direct third-party runtime dependencies small: Textual and pyelftools. Their dependencies are managed by uv. External fzf, crudini, Java, gdb, readelf, strace, and bubblewrap are not required for ordinary product use; the last tools were used to investigate and trace the prototype. Native-library loading still requires the installed CUBRID's compatible system libraries.

Planned commands after implementation:

```sh
# Develop/run from this repository
uv run cubrid-conf-tui demodb

# Install this local package as a CLI tool
uv tool install .
cubrid-conf-tui demodb
```

uv documents [isolated tool installation](https://docs.astral.sh/uv/concepts/tools/). Textual provides [input widgets](https://textual.textualize.io/widgets/input/) and a [fuzzy matcher](https://textual.textualize.io/api/fuzzy_matcher/). [pyelftools](https://github.com/eliben/pyelftools) parses ELF and DWARF in pure Python. Exact Python/package versions and compatibility gates belong to implementation planning.

## Evidence and implementation verification

The [offline prototype report](offline-catalog-findings.md) records the successful experiments and their limits. [ADR 0001](adr/0001-installed-library-metadata.md) records the accepted integration trade-off. The [interview record](design-interview.md) preserves answers and source references; [CONTEXT.md](../CONTEXT.md) defines domain language.

Implementation must verify the complete flow against representative installed debug and release builds, plus unsupported metadata and stopped-database cases. Focused checks must cover hidden discovery, C/S differences, overrides, validation boundaries, boolean/text editing, duplicate assignments, comment preservation, external-edit conflicts, backups and failed writes, and activation messages. The prototype alone does not satisfy these implementation checks.
