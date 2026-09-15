# Configuration TUI design interview

Status: interviewing; implementation has not started.

## Requested behavior

- Require `CUBRID` in the current environment; error when absent.
- Search available parameters with an fzf-style interaction, including hidden parameters.
- Show values and differences from defaults, informed by paramdump markers.
- Enter opens value editing with default and previous value visible.
- Save on Enter and report success or failure.
- Provide safe validation where feasible and restart guidance where required.
- Prefer a standalone tool with few dependencies; crudini is an acceptable fallback if checked explicitly.

## Decision tree

1. Supported installations: installed binaries alone, or matching source required?
   - Determines metadata discovery, version compatibility, and validation options.
2. Save/activation scope: file editing with guidance, restart control, or live updates?
   - Determines runtime state and process-control requirements.
3. Configuration scope: common section, database-specific sections, or additional files?
   - Determines target selection and override handling.

### Accepted direction from round one

- Primary audience: developers. An installed CUBRID is sufficient; a source checkout is not required (explicit clarification after round two). Matching source is optional enrichment.
- Saving edits the configuration file and reports restart guidance. No restart action or live parameter updates.
- Edit only `[common]` in `cubrid.conf` (latest explicit Q3 choice). Database-specific sections remain relevant to interpreting effective values; they are not editable in v1.

### Accepted direction from round two

- Optionally inspect matching source for metadata; missing or unrecognized information remains unknown.
- Investigate debug symbols as a way to locate source, including RelWithDebInfo installations. A recorded source path is a candidate, not proof that the current source matches the binary.
- Accept a database name as a command argument; offer an interactive picker when omitted.
- Support editing before the database starts, including repairing settings that prevent startup. Mark unavailable runtime information clearly. Complete offline catalog discovery remains a research requirement.
- The earlier agreement to a section picker is superseded by the latest explicit common-only Q3 answer. Keep the editing target visible. How to present database overrides is part of the next display decision.

### Accepted direction from round three

- Honor nonempty `CUBRID_CONF_FILE`; prominently display the full editing path.
- One searchable row per parameter, with configured value, default, and C/S differences. The editor shows full details, including database overrides masking common assignments.
- Provide a distinct Remove override action that removes the common assignment. Explicitly setting the compiled default is an ordinary value edit.
- Block unsafe multiline input and reliably established type/range violations. Allow saving when constraints are unknown, with limited validation clearly indicated.

### Accepted direction from round four

- Linux first, with built-in fuzzy search and configuration editing. The original single-executable packaging choice is superseded by the later explicit Python-with-uv selection.
- Enter opens a boolean editor with yes/no choices; arrows or Space change the selection, Enter saves, Esc cancels. No immediate list-row toggle/save.
- After saving, return to the filtered list while preserving search and selection. Report the saved value and known activation requirements.
- Detect external file changes and stop a conflicting save, asking to reload. Preserve comments/formatting, write atomically, and retain the previous file as a recovery backup.

### Accepted compatibility policy (Q17)

- Use installed-library metadata for validated layouts. Fall back to paramdump where available; otherwise offer clearly limited offline editing of existing settings. Never guess an unknown library layout.
- See [ADR 0001](adr/0001-installed-library-metadata.md) for the trade-off.

### Next decision frontier

- Review the [consolidated design](design.md) and confirm shared understanding. The user selected Python with uv; Textual and pyelftools are the corresponding implementation proposal.

### Implementation language clarification

The user requested Python, then explicitly specified Python with uv. Adopt Python CLI package distribution through uv. This replaces the unaccepted Rust proposal and the earlier native single-executable packaging direction. Preserve minimal external-tool dependencies and the subprocess metadata boundary.

## Pending fact discovery

- Compatibility of the inspected output with other installed versions.
- Actual stopped-server failures and standalone database-opening effects.
- Authoritative activation rules and validation metadata beyond paramdump.
- Handling stripped/separate debug information and source/binary mismatch.
- Generalizing the successful installed-only catalog probe beyond its tested internal layout, and converting raw metadata to configuration semantics.

## Verified source findings

Inspected on 2026-09-15 in `/home/vimkim/gh/cb/CBRD-27398-pgbuf-inspector-contract`, HEAD `c2492f886eeb2790c4887fbc95fb3c59c419d362`. These are source findings for this checkout; no database commands were executed.

| Finding | Local source evidence |
| --- | --- |
| Ordinary dumps exclude hidden parameters; `--dump-flag=0x8` selects hidden parameters within the client/server roles. Discovering both sets requires combining these dumps. | `src/executables/util_cs.c:2375–2395,2442–2450`; `src/base/system_parameter.c:6152–6171` |
| Modern output contains current and default values: `[C*] name=current (default)`. The star compares their printed strings, not configuration-file presence. | `src/base/system_parameter.c:6174–6191` |
| C and S identify client and server snapshots; one parameter can have both. | `src/executables/util_cs.c:2439–2450`; `src/base/system_parameter.c:8489–8492` |
| The dump does not print types, bounds, or restart metadata. The source parameter structure contains types, bounds, and flags, but no single restart-required field. | `src/base/system_parameter.c:6174–6191`; `src/base/system_parameter.h:635–657,726–739` |
| Paramdump calls `db_restart` before dumping. Standalone mode must not be assumed to be a pure offline configuration parser. | `src/executables/util_cs.c:2404–2411`; `src/executables/util_admin.c:1181–1209`; `src/communication/network_interface_cl.c:9267–9292` |
| The example inspector parameter is hidden, server-side, boolean, defaults to false, and is checked at startup. | `src/base/system_parameter.c:5586–5594`; `src/storage/pgbuf_inspector.cpp:110–115` |

The local manual's `-b` description (`en/admin/admin_utils.rst:3470`) differs from this branch's modern output: the `both_flag` controls the legacy `--for-cm` path here. Compatibility needs actual version-specific evidence.

The CTP `ini.sh` wrapper delegates to Java and `cubridqa-common.jar`; using it would add those dependencies.

### Configuration targeting and database discovery

- Database sections are `[@database_name]`. `[common]` loads before the database section; matching database values override common values (`src/base/system_parameter.c:6870–6874`). Standalone mode also loads `[standalone]` afterward (`6877–6882`).
- Common-section matching is case-insensitive; database-section matching is case-sensitive (`src/base/system_parameter.c:6600–6616,6870–6874`).
- Some parameters have scope constraints: `stored_procedure_port` is rejected in `[common]` (`src/base/system_parameter.c:6827–6831`).
- Nonempty `CUBRID_CONF_FILE` selects an alternate configuration file when no explicit API path is supplied (`src/base/system_parameter.c:6363–6381`; environment prefix in `src/base/environment_variable.c:150–174`). HA configuration and later tuning can further affect effective values (`src/base/system_parameter.c:6398–6462`).
- Database candidates come from `$CUBRID_DATABASES/databases.txt`, or `databases.txt` in the working directory when that variable is absent/empty (`src/base/databases_file.c:222–242`). Registry presence does not establish server availability.

### Design implications to discuss

- Keep default difference separate from explicit configuration override.
- Preserve client/server distinctions when combining parameter listings.
- Show unknown validation and activation metadata honestly.
- Editing common values must expose applicable database overrides that mask the change.
- File targeting must account for CUBRID_CONF_FILE to avoid displaying values from one file while silently editing another.

### Debug information probe

Read-only inspection of the current installation found DWARF v5 in `bin/cubrid`, with `DW_AT_name` pointing to this checkout's `src/executables/util_service.c` and `DW_AT_comp_dir` to its `build_preset_debug_gcc` directory. `lib/libcubrid.so.11.5` also contains debug information and source paths. The executable advertises `11.5.0.2585-c2492f8`, consistent with the inspected checkout revision.

The local `release` preset chooses RelWithDebInfo (`CMakePresets.json:21–25`). This is evidence for the local presets, not a guarantee that every distributed release retains debug information. `WITH_SOURCES` can remap paths into the installation's `src` directory (`CMakeLists.txt:248–256`).

Source discovery through DWARF is therefore viable as optional enrichment. Paths may be stale or remapped; the embedded short commit (`CMakeLists.txt:160–167`) does not encode uncommitted edits. An ELF build ID identifies a binary, not the contents of a current source checkout. Missing debug tools/information must preserve installed-only operation.

### Offline discovery feasibility and parser findings

No database-free catalog CLI was found in the bounded caller search for this branch. `paramdump` requires a database name and calls `db_restart` before dumping (`src/executables/util_cs.c:2323–2332,2404–2411`). An environment-triggered dump exists only under `#if 0` (`src/base/system_parameter.c:6465–6471`).

The installed `libcubrid.so.11.5` exports `prm_Def`, `sysprm_dump_parameters`, and initialization functions, as observed with `nm -D`. The initial source investigation identified a plausible subprocess extractor and these risks: the registry structure is internal, its header is not installed publicly, initialization has substantial side effects, and client/server build differences matter (`src/base/system_parameter.h:726–739`; `src/base/system_parameter.c:1059,1065–1069,6298–6555`). The later prototype established extraction for tested artifacts without calling CUBRID initialization functions; it did not establish general compatibility.

Q17 explicitly accepted limited existing-setting editing for unsupported layouts when a live dump is also unavailable. A previously collected catalog could help repeat use, but cannot solve a first run against an unknown build by itself.

Individual `CUBRID_<UPPERCASE_PARAMETER_NAME>` environment variables can override file values (`src/base/system_parameter.c:7371–7396`). The TUI's environment is not proof of the running server's environment.

Exact duplicate `section:key` entries are last-value-wins in the parser (`src/base/ini_parser.c:298–309,655–657`). Removing only the last occurrence can reveal an earlier assignment. Case-variant behavior still requires checking before implementing the writer.

### Accepted prototype detour and outcome

Q16 accepted a bounded executable prototype of installed-library metadata extraction without database startup/opening. The probe succeeded for three debug libraries and an older release server library. See [offline-catalog-findings.md](offline-catalog-findings.md) for results, limitations, and the preserved prototype branch/commit. Installed-only feasibility is established for these artifacts; general layout compatibility and complete editable schema interpretation are not established.

## Interview checkpoint

Rounds one through four answered, Q16 prototype completed, Q17 compatibility policy accepted, Python with uv selected. Consolidated design is ready for final review. No production implementation has started.

## References supplied by the user

- `/home/vimkim/gh/ctp/run-sql/CTP/bin/ini.sh`
- `/home/vimkim/gh/cubrid-manual/en/admin/config.rst`
- `/home/vimkim/gh/cb/CBRD-27398-pgbuf-inspector-contract`

The inspector example is a branch-specific reference to verify, not a compatibility guarantee.
