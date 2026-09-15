# cubrid-conf-tui

A Linux terminal editor for existing CUBRID `[common]` assignments.
The application currently runs in **limited offline editing** mode. Defaults, types,
constraints, activation requirements, and runtime observations are unavailable.
A successful save changes the file only; it does not start a database or apply live values.

## Run

```sh
export CUBRID=/absolute/path/to/cubrid
uv run cubrid-conf-tui

# Install the CLI into an isolated tool environment
uv tool install .
cubrid-conf-tui
```

The selected installation must have a working `bin/cubrid --version` (five-second
prerequisite timeout). The application never substitutes a CUBRID executable from PATH.
A nonempty `CUBRID_CONF_FILE` selects an alternate target; otherwise the target is
`$CUBRID/conf/cubrid.conf`. Relative overrides are relative to the working directory.
The full target and common-only scope are displayed while browsing and editing.

Type a fuzzy query, press Enter to edit, or Tab to move to the results and use arrows
to select a row. Enter saves the text value; Ctrl+R in the editor removes the
common override; Esc cancels. Ctrl+Q quits. Saving and cancelling retain the query
and selection. Removal retains the query and selects the next remaining row (or
the previous row when removing the last result). After a conflict, exit and reopen to
reload the file; copy any entered text you want to keep first.

## Supported documents and save behavior

The writer accepts UTF-8 files with LF or CRLF lines and ordinary unambiguous
assignments. Parameter names and common-section names are case-insensitive.
Repeated common sections and duplicate assignments are supported: one row shows
the last common value, and editing changes only that last occurrence, retaining
its spelling. Ctrl+R removes every common occurrence of that parameter, allowing
inheritance; it does not write an explicit default. It retains
unrelated text, comments, database sections, line endings, permissions and ownership.
Quoted values retain their quote spelling. Enter quoted text for values containing
`#` or `;`. Unknown types always use text input, even when the old value is `yes` or `no`.

Continuation lines, malformed syntax,
control characters and lines longer than 510 bytes are rejected. Symlinks anywhere
in the editing path, hardlinks, and nonregular targets or backup files are rejected.
The file must already exist; adding parameters is not yet supported. Removal keeps
inline comments as standalone comments. A semicolon comment receives a leading
`#` because CUBRID rejects standalone semicolon comments. Empty assignments are
explicit overrides and can be removed. A missing final newline is preserved on
edits; removal leaves the remaining lines intact. See the
[parser evidence and supported semantics](docs/configuration-semantics.md).

Each save writes and syncs a previous-file backup at `<target>.bak`, then atomically
replaces the target with a synced file in the same directory and syncs the directory.
The next save replaces that backup with the immediately previous file. Observed
changes to file identity, content, permissions or ancestor identities stop a save.
These checks detect ordinary conflicts; they do not exclude a concurrent writer
between the final check and replacement. ACLs and extended attributes are copied and verified on both files; an inability
to preserve them stops replacement. Failures retain input and report the inspected
file outcome, including durability uncertainty after replacement. A target redirected after replacement
is reported as a conflict, and uncertain replacement outcomes require reopening.
An abruptly terminated process cannot display a notification; inspect the target
and `.bak` after reopening. Staged `.cubrid.conf.*` files can remain after such a
termination.

## Development checks

```sh
uv run mypy
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

Principal tests run the complete Textual application with keyboard input and real
temporary configuration and backup files, following the approved boundary in the
specification and [Textual's testing guide](https://textual.textualize.io/guide/testing/).
Filesystem faults are injected only at OS boundaries. CLI tests run actual uv
processes. Tests never edit an active developer configuration or start a database.

The [design](docs/design.md), [glossary](CONTEXT.md), and
[metadata ADR](docs/adr/0001-installed-library-metadata.md) describe subsequent slices.
Database selection, live discovery, metadata extraction and typed validation are
not implemented in this ticket. The pyelftools dependency reserves the accepted
stack; no native libraries are loaded by the application.
