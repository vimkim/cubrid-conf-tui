# Offline catalog prototype verdict

## Result

Installed-only extraction succeeded without database initialization for the tested debug and release libraries. The prototype read the exported parameter registry in an isolated subprocess, with the local source root hidden, host files read-only, and networking isolated.

| Probe | Entries | Hidden | Obsolete |
| --- | ---: | ---: | ---: |
| Debug server library, installation 11.5.0.2585-c2492f8 | 393 | 157 | 12 |
| Debug client/server utility library | 393 | 157 | 12 |
| Debug standalone library | 393 | 157 | 12 |
| Release server library, installation 11.5.0.2546-481d26c | 386 | 155 | 12 |

These are registry counts, not counts of editable common-section parameters. Names, raw defaults, type tags, limits, and flags were extracted. All four processes exited successfully. Captured file/network traces show no network calls, write-mode opens, configuration/registry accesses, source reads, or database-volume opens. A rerun of the packaged debug runner also succeeded.

`enable_pgbuf_inspector` is hidden, server-side, boolean, and defaults to false in both installations. Debug `er_log_debug` defaults to true; release defaults to false.

## Consequences for the design

- Source and DWARF are not required at extraction time. The prototype itself was written using the inspected internal structure layout.
- Metadata must identify its library/mode. `max_connection_worker` is 40 with upper bound 80 in the tested server library, versus 2 with no upper bound in the client/standalone libraries. The installed `cub_server` links the tested server library.
- CPU-dependent initializers run when loading the library. The helper's environment may differ from a running server's environment.
- Extracted defaults are distinct from configured values and live values. The probe intentionally does not report uninitialized current values.
- Registry membership does not establish common-section editability. Obsolete entries, service-section names, and parameter-specific restrictions require handling.
- Keyword IDs, units, special sentinels, and cross-parameter constraints need interpretation before presenting a complete validation schema.
- This is an internal interface. Two successful builds establish feasibility, not universal compatibility. Structure-size and ID checks alone cannot safely authenticate an unknown layout.

## Preserved experiment

- Branch: `prototype/offline-catalog`
- Commit: `7ff8245`
- Local worktree: `.scratch/offline-catalog`
- Full method, limits, and source evidence: [.scratch/offline-catalog/prototypes/README.md](../.scratch/offline-catalog/prototypes/README.md)
- Raw captures and summaries: `.scratch/offline-catalog/prototypes/evidence/`
- Run from that worktree: `sh prototypes/run-probe.sh`

The script uses Python, readelf, bubblewrap, and strace as experiment tooling. Product runtime dependencies remain a separate implementation choice. The main branch contains design records only.

## Pending decision

Recommended: a subprocess metadata extractor for validated layouts, retaining installed-only operation and paramdump for runtime observations. For unsupported layouts, explicitly report offline catalog limitations and offer available configuration/live-dump information. That fallback policy is a proposal awaiting the user's decision, not an accepted reduction of offline scope.
