# Supported configuration semantics

Ticket 02 extends the lossless writer with duplicate handling and Remove override.
The evidence baseline is CUBRID source commit
`c2492f886eeb2790c4887fbc95fb3c59c419d362` (11.5.0.2585-c2492f8).
This is a supported text subset, not a claim of compatibility with every CUBRID
release or of parameter-specific value validation.

## Primary evidence

Inspected the matching local checkout at
`/home/vimkim/gh/cb/CBRD-27398-pgbuf-inspector-contract`.

| Rule | Source at the evidence baseline |
| --- | --- |
| Keys are trimmed and lowercased, including assignments with empty values. | `src/base/ini_parser.c:533–565`, `ini_parse_line` |
| Section whitespace is trimmed; `@` sections retain case, other sections are lowercased. | `src/base/ini_parser.c:507–531` |
| Exact normalized `section:key` duplicates replace the stored value. Repeated sections do not clear existing assignments. | `src/base/ini_parser.c:298–309,651–657`, `ini_table_set` / `ini_parser_load` |
| Empty unquoted and quoted assignments are values; they are not absence. | `src/base/ini_parser.c:540–565` |
| Whole-line comments start with `#`; inline unquoted values stop at `;` or `#`. | `src/base/ini_parser.c:502–506,533–535` |
| Common loads first, then the selected `@database` section is matched with case sensitivity. | `src/base/system_parameter.c:6600–6616,6870–6874` |

The [upstream parser at the pinned revision](https://github.com/CUBRID/cubrid/blob/c2492f886eeb2790c4887fbc95fb3c59c419d362/src/base/ini_parser.c)
is the source reference; the files were read locally for this investigation.
The general `ini_getstr` utility lowercases its lookup argument, so it would not
establish database section matching by itself. The parameter loader above supplies
that evidence.

## Installed parser experiment

[probe_ini_parser.py](verification/probe_ini_parser.py) calls the actual installed
parser in a short-lived Python process, then reads the table using the matching
source header. This developer-only probe is pinned to that library's symbol names
and layout; it is not a production compatibility gate or runtime dependency.
Only parser load/free functions are invoked; no database initialization or open
function is called. The input is a temporary file.

Reproduce with the matching installation:

```sh
uv run python docs/verification/probe_ini_parser.py \
  /home/vimkim/.cub/install/CBRD-27398-pgbuf-inspector-contract/debug_gcc/lib/libcubrid.so.11.5
```

Observed library SHA-256:
`3cbce5364fe1e63f3b1ad889f58f8c8b15ab46bc43594fb255210df5babbe98c`.
The fixture combines repeated `[ Common ]` / `[COMMON]` headers, mixed-case keys,
CRLF lines, inline comments, empty values and an unterminated final line.
Its actual table contains:

```json
{
  "common:max_clients": "30",
  "@Demo:max_clients": "2",
  "@demo:max_clients": "3",
  "common:empty": "",
  "common:quoted": ""
}
```

## Writer behavior

- The last occurrence supplies the displayed configured text, including its key
  spelling. A normal edit changes only its value. Earlier duplicates stay intact.
- Remove override removes **all** common occurrences, across key case variants and
  repeated common sections. It never removes a database-specific assignment.
- The raw quoted spelling remains visible in the editor. An empty assignment is
  still explicit. The tool does not infer a compiled default or a runtime value.
- Unrelated bytes, section spelling/order, indentation, line endings, and comments
  remain. Removed assignments' inline `#` comments become standalone comments;
  `;` comments retain their text and receive a leading `#` to remain valid CUBRID
  syntax. Comment-free removed lines disappear. Empty sections remain.
- Editing retains an unterminated final line. Removing it leaves the preceding
  bytes unchanged, including any preceding newline.
- The query survives removal. With no catalog, a removed setting disappears from
  the list. Selection stays at the same index when possible, otherwise at the last
  remaining result; an empty result has no selection.

The writer deliberately rejects continuations, unsupported/malformed syntax,
control characters, bare CR, lines over 510 bytes, and non-ASCII key spellings.
It accepts simple section names with letters, digits, underscore, dot and hyphen,
optional `@`/`%`, and surrounding spaces/tabs. Other CUBRID section syntax remains
unsupported. It rejects indirection through symlinks or hardlinks and nonregular
files. It does not rewrite the document through a generic INI serializer.

## Recovery and conflicts

Both mutations use the same transaction: stage and sync the old and new files,
preserve ownership/mode/ACLs/attributes, replace and sync `.bak`, recheck the target,
replace the target atomically, then sync the directory. The application checks
observed identity/content/metadata changes and ancestor redirection. After replacing,
it checks the staged target identity and metadata before claiming success.

On failure it re-inspects the target and reports original intact, new present with
unconfirmed durability, changed/redirected, or unknown because inspection failed.
Input remains in the editor. Replacement attempts with an error require reopening
before another operation. An abrupt process termination cannot notify the user:
real process-exit checks verify old/new target bytes and the pre-edit backup on disk.
Staged files can survive such termination. These experiments do not simulate power
loss or prove hardware durability. Uncooperative writers can still race the final
checks and replacements; observed conflicts are detected, not globally excluded.
