# Why the 2026-09-15 live probe reached the host CUBRID master

Report date: 2026-09-17

Incident date: 2026-09-15 (KST)

Audience: `cubrid-conf-tui` and CUBRID maintainers

Status: post-incident explanation; no real CUBRID process was started for this report

## Executive answer

Yes: a correctly configured private `CUBRID_TMP` would have prevented the
specific pathname-socket crossover that connected `tui_probe` to the long-lived
host `cub_master`.

The important qualification is that **a private `CUBRID_TMP` is sufficient to
prevent this specific pathname crossover, but is not by itself a complete
safety boundary**. It is effective only when it names a unique, private,
absolute directory; every participating CUBRID process inherits it before its
first master-endpoint lookup; and startup fails closed if the expected endpoint
already exists or is not owned by the master that the probe just launched.
`CUBRID_TMP` does not isolate the master TCP port, prove that a new master
started successfully, clean up processes, repair a failed `execv()`, or limit
how many tasks a defect can create. A genuinely private `/tmp` mount would also
have prevented this pathname crossover, which is why `CUBRID_TMP` is the chosen
direct control rather than the only possible control.

The incident required three distinct layers:

1. **Trigger — endpoint crossover.** The probe ran with a private copied
   installation but without `CUBRID_TMP` and without a private
   `cubrid_port_id`. CUBRID therefore selected the pathname socket
   `/tmp/CUBRID1523`. The namespace recipe still exposed the host-mounted
   `/tmp`, so `tui_probe` registered with the existing host master.
2. **Amplifier — failed-revival defect.** Once the temporary server executable
   disappeared, the host master tried to revive it. The revival child called
   `execv()`, but on failure returned into the copied master control flow rather
   than terminating. Each resulting master could repeat the revival, producing
   a recursive fork storm.
3. **Containment gaps.** The probe did not verify which master owned its
   endpoint, retained no reliable process lifecycle for all startup paths, and
   ran without a strict process-count boundary. The later unscoped
   `pkill cub_master` raced ongoing creation; it was an attempted mitigation,
   not the trigger.

This is best understood as a systems failure, not an individual failure. The
private installation and several Linux namespaces made the run look isolated,
but a pathname Unix socket follows filesystem visibility, which those particular
controls did not make private. A separate engine defect then magnified a single
wrong registration into thousands of processes. Either a private endpoint or a
safe failed-`execv()` path would have broken the causal chain; robust protection
requires both, plus bounded containment.

## What happened

### Factual timeline

| Time (KST) | Observed fact | Meaning |
| --- | --- | --- |
| 17:53:44 | The `cub_master` that later owned the runaway subtree started as part of a normal database start attempt. | A long-lived host master predated the probe by hours. |
| 21:20:15 | The agent session began the documented `unshare --user --map-root-user --net --ipc --pid --fork --mount-proc` probe sequence. Its first attempt failed while copying existing socket files and did not cause the later registration. | The session record identifies the exact workflow and shows that isolation was intended. |
| 21:20:24–21:20:27 | A follow-up probe execution used `cubrid server start tui_probe`. At 21:20:27.748 the host master logged a new `tui_probe` entry with PID 7. | PID 7 was meaningful inside the probe's PID namespace. Its appearance in the host master's registry proves that registration crossed the intended boundary. |
| 21:21:12.584 | The host master logged that it was waiting for a revived `tui_probe` at host PID 3765041. One millisecond later it logged “Failed to fork server process” and requeued revival. | Source inspection shows that the fork actually succeeded; `execv()` of the vanished temporary executable failed in the child. The log message describes the returned `-1` imprecisely. |
| 21:21–21:30 | Atop recorded 6,072 new UID-1000 `cub_master` processes. At 21:30 there were 6,083 masters and 14,253 total tasks. | This is the process storm. The observed parent chain matches repeated children returning as masters. |
| 21:35:45.360 | `pkill cub_master` began and did not complete. Descendants continued logging revival failures through at least 21:36:42. | The storm had already run for more than 14 minutes. The command could add exit/core-handling load and affect unrelated masters, but could not have initiated the event. |
| 21:55:54–21:58:39 | Kdump captured a vmcore, followed by a new kernel boot. | A kernel crash and reboot are established. The exact panic trigger is not available in the unprivileged evidence. |

The incident-time script must not be confused with the later pre-fix snapshot.
The session record at line 117 shows that the run which registered at 21:20:27
called `run("server", "start", "tui_probe")`. The version preserved as the
parent of commit `4d9d1c0` had subsequently evolved to launch copied
`cub_master` and `cub_server` binaries directly. Both versions omitted
`CUBRID_TMP` and retained the default port, but they had different startup
paths. The later snapshot is useful evidence of the unresolved design flaw; it
is not a byte-for-byte record of the triggering run.

### Causal chain

```text
probe starts with a copied CUBRID installation
  + no CUBRID_TMP
  + no private cubrid_port_id
  + host-mounted /tmp still visible
        |
        v
CUBRID resolves the master pathname to /tmp/CUBRID1523
        |
        v
tui_probe reaches and registers with the long-lived host master
  (host log records namespace-local PID 7 and a temporary cub_server path)
        |
        v
probe startup times out/exits; temporary executable path disappears
        |
        v
host master tries to revive tui_probe
        |
        v
fork succeeds; child execv(temporary cub_server) fails
        |
        v
child returns to master logic instead of _exit()
        |
        v
recursive master/revival loop creates thousands of cub_master processes
        |
        v
unbounded host task growth; later broad pkill races creation
        |
        v
host becomes unresponsive; kernel later crashes and kdump runs
```

The first arrow is the probe isolation defect. The recursive portion is the
CUBRID engine defect. The host-wide severity reflects the missing process-count
containment. Keeping these roles separate is important: fixing only the engine
would make this particular failure less explosive but would not make cross-talk
with a host master acceptable; fixing only the probe protects this workflow but
does not make the engine's failed-revival path safe for other callers.

## Why the endpoint became `/tmp/CUBRID1523`

The derivation is direct in current CUBRID source:

1. The environment prefix constant is `CUBRID`.
2. `envvar_name()` concatenates the prefix, `_`, and the requested name.
   `envvar_get("TMP")` therefore calls `getenv("CUBRID_TMP")`; it does **not**
   read ordinary `TMP` or `TMPDIR`.
3. `css_get_master_domain_path()` reads `envvar_get("TMP")`. If it is unset or
   empty, the function substitutes `/tmp`.
4. It formats the path as `"%s/%s%d"`: temporary directory, prefix, and master
   port.
5. `cubrid_port_id` defaults to 1523. Its configured range in source is 1 through
   `USHRT_MAX` (normally 65535).

Therefore:

```text
unset CUBRID_TMP
  -> temporary directory = /tmp

unset cubrid_port_id
  -> master port = 1523

master pathname
  = <temporary directory>/<prefix><master port>
  = /tmp/CUBRID1523
```

See the immutable upstream source for
[`envvar_name()` and `envvar_get()`](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/base/environment_variable.c#L142-L190),
[`css_get_master_domain_path()`](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/connection/tcp.c#L139-L156),
and the
[`cubrid_port_id` default and limits](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/base/system_parameter.c#L1562-L1572).
The path is cached after its first computation in each process, so changing
`CUBRID_TMP` later is not reliable; it must be present in the environment before
the process starts and before any endpoint lookup.

The CUBRID manual independently documents that `CUBRID_TMP` controls the
directory used for Unix domain sockets, defaults to `/tmp` when unset, and must
be an absolute path within the platform's pathname-length limit. See the pinned
manual section on
[`CUBRID_TMP`](https://github.com/CUBRID/cubrid-manual/blob/3b6ae97bfbdc664b010ffa933ded5a05b291ae03/en/env.rst#L24-L66).

The later direct-`Popen` pre-fix version carried an additional risk. During
master startup, CUBRID checks whether the pathname exists; if it is a socket, it
unlinks it before binding its own Unix socket. That behavior is visible in
[`css_tcp_master_open()`](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/connection/tcp.c#L740-L766).
Thus a shared `CUBRID_TMP` was not merely a risk of connecting to the wrong
master. A newly launched master could also remove the host master's directory
entry and replace it. This is why the repaired probe rejects any pre-existing
endpoint before starting a process rather than treating “the socket exists” as
readiness.

## Why the namespace command did not isolate `/tmp`

The command created user, network, IPC, PID, and—because of `--mount-proc`—mount
namespaces. Each isolates a particular class of kernel resources:

- A **user namespace** changes the process's view of user/group IDs and
  capabilities.
- A **network namespace** separates network devices, protocol stacks, and TCP/UDP
  ports.
- An **IPC namespace** separates System V IPC objects and POSIX message queues.
- A **PID namespace** gives processes a separate PID numbering hierarchy.
- `--mount-proc` mounts a procfs appropriate to the new PID namespace and implies
  a mount namespace.

A pathname Unix socket is different: its name is a filesystem object. A new
mount namespace begins with a copy of the caller's mount list. It separates
later mount/unmount operations, but does not automatically copy or hide the
contents of every inherited mount. `--mount-proc` privately remounted `/proc`;
it did not mount a private tmpfs or bind mount over `/tmp`. Both sides therefore
saw the same backing `/tmp/CUBRID1523` directory entry. The distinction follows
the Linux namespace resource table and mount-namespace semantics; see
[`namespaces(7)`](https://man7.org/linux/man-pages/man7/namespaces.7.html),
[`mount_namespaces(7)`](https://man7.org/linux/man-pages/man7/mount_namespaces.7.html),
and [`unix(7)`](https://man7.org/linux/man-pages/man7/unix.7.html).

The raw incident log did not record the pathname used for the escaped
connection, so it would be too strong to say the log alone proves the filename.
The later conclusion combines independent evidence:

- the executed environment omitted `CUBRID_TMP`;
- the executed configuration omitted `cubrid_port_id`;
- CUBRID source deterministically maps those defaults to `/tmp/CUBRID1523`;
- the host master recorded the namespace-local PID 7 for `tui_probe`; and
- a harmless toy Unix-socket check reproduced visibility of a host pathname
  socket under the same namespace recipe.

Together these establish the pathname crossover with high confidence while
keeping the evidence boundary honest.

## Why ordinary concurrent databases and `pkill` were not the cause

Multiple ordinary database servers were already running before this incident.
CUBRID's master normally manages named server entries; merely having several
differently named non-HA databases does not create a recursive chain of
`cub_master` processes. The abnormal transition was narrower and timestamped:
the existing host master accepted the temporary `tui_probe` registration, then
began repeated revival immediately when that one temporary executable became
unavailable. Source and logs agree on the same name, time, PID transition, and
retry path. No comparable evidence connects the other normal database servers
to the first runaway child.

This is also normal documented operation: CUBRID's service configuration can
list multiple database servers, and the manual's status example shows multiple
named servers under one service. See
[`server=demodb,testdb`](https://github.com/CUBRID/cubrid-manual/blob/3b6ae97bfbdc664b010ffa933ded5a05b291ae03/en/admin/control.rst#L207-L228)
and the corresponding
[`cubrid service status` example](https://github.com/CUBRID/cubrid-manual/blob/3b6ae97bfbdc664b010ffa933ded5a05b291ae03/en/admin/control.rst#L379-L390).

`pkill cub_master` is also excluded as the trigger by ordering. The first failed
revival was at 21:21:12; 6,072 new masters existed by 21:30; `pkill` began at
21:35:45. The broad command likely made recovery harder because it signalled
unrelated masters as well as the runaway tree, while newly forked descendants
could appear after its process scan. It may have increased simultaneous
exit/core-handling work, but it occurred more than fourteen minutes after the
storm began.

For recurrence, the safer response is to contain the known cgroup or exact
process tree. A name-wide `pkill` is neither precise nor atomic with respect to
continuous process creation.

## What `CUBRID_TMP` prevents—and what it does not

### It prevents this pathname crossover when all conditions hold

Suppose a run creates a directory such as:

```text
<unique-run-root>/installation/tmp
```

and launches the master, server, and all control utilities with:

```text
CUBRID_TMP=<absolute-unique-run-root>/installation/tmp
```

With master port `P`, those processes derive:

```text
<absolute-unique-run-root>/installation/tmp/CUBRID<P>
```

They will no longer look up `/tmp/CUBRID1523`, so the specific host pathname
cannot be selected. This conclusion depends on all of the following:

1. The directory is absolute, unique per run, owned by the run, and not a
   symlink or shared alias to a host runtime directory.
2. It exists before any CUBRID process starts and remains present until every
   process has stopped and unregistered.
3. The master, server, `cubrid` utility, `cub_commdb`, `paramdump`, and any other
   participant receive the same explicit environment. No participant falls back
   to an inherited or default environment.
4. `CUBRID_TMP` is set before process execution. Because the path is cached on
   first use, changing it in a running process is too late.
5. Startup checks that the expected endpoint does not already exist, waits for
   the new master to remain alive, and verifies that the new master's PID owns
   the socket before starting the server.

The endpoint pre-check is part of the safety contract, not just tidiness. It
protects against accidental reuse, stale files, symlink mistakes, and CUBRID's
startup behavior of unlinking an existing socket pathname.

### It does not provide these protections

| Risk | Why `CUBRID_TMP` is insufficient | Additional control |
| --- | --- | --- |
| TCP port collision | It changes a pathname, not `cubrid_port_id` or the network namespace. | Select a private per-run port and/or use a verified private network namespace; handle bind races and failure. |
| Wrong or failed master | A private path does not prove the launched process survived or bound it. | Retain the `Popen` handle, poll for early exit, and verify PID-to-socket ownership. |
| Stale or pre-existing endpoint | A directory can contain an old or foreign socket; CUBRID may unlink an existing socket on startup. | Reject the endpoint before spawn and reject any unexpected owner or non-socket. |
| Cleanup leaks | Environment selection does not unregister a server or reap/terminate children. | Explicit unregister/stop, bounded waits, terminate, then kill and reap. |
| Temporary executable deletion | `CUBRID_TMP` does not keep a copied installation alive until all registered processes are gone. | Stop and unregister the server, stop the master, verify termination, then let the temporary directory be removed. |
| Revival `execv()` failure | It does not fix the engine child-return bug. | Repair the CUBRID engine so a failed child `execv()` calls `_exit()`; add bounded retry/circuit breaking separately. |
| Unbounded task creation | A private socket limits cross-talk, not the blast radius of another fork defect. | Run real-process probes in a disposable VM/container under a strict PID limit. |
| Other CUBRID resources | `CUBRID_TMP` is not a universal relocation setting for every port, shared-memory key, registry, data path, PID file, log, or optional socket. | Isolate the complete runtime resource bundle and use a private installation/registry/storage root. |

In short: `CUBRID_TMP` answers “where is this family of pathname sockets?” It
does not answer “is every resource private?”, “did the right process create the
socket?”, or “what happens if cleanup fails?”

## The failed-revival amplifier

The engine source explains why a registration mistake became a fork storm.
`server_monitor::try_revive_server()` calls `fork()`. In the child branch it
directly returns the result of `execv()`. Successful `execv()` never returns, but
a missing executable returns `-1`. The child therefore returns to caller logic
that treats `-1` as a fork failure, logs the misleading message, and enqueues
another `REVIVE_SERVER` job. The original parent also continues its monitor
flow. A failed child remains a `cub_master` capable of repeating the operation.

The immutable source links show both the
[`try_revive_server()` child path](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/executables/master_server_monitor.cpp#L261-L279)
and the
[`-1` requeue path](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/executables/master_server_monitor.cpp#L181-L199).
This mechanism matches the first child PID in the master log and the observed
deep parent chain. It is sufficient to explain the process storm. It does not,
by itself, establish which kernel condition caused the later panic.

The engine repair remains intentionally separate from commit `4d9d1c0`. Probe
isolation must not rely on a server bug being harmless, and the engine must not
rely on every caller having perfect isolation.

## Layered controls added in commit `4d9d1c0`

Commit `4d9d1c0b9e554db8d5ccbb78d53a9942854b998c` (“Make live probe
isolate CUBRID master”) changed the probe and its operating guidance as follows:

| Control | Current behavior | Evidence |
| --- | --- | --- |
| Unique runtime directory | Every run uses a new `TemporaryDirectory`; the copied installation has its own `tmp`, `var`, `log`, configuration, and database registry. | [`probe_live_dump.py`](../verification/probe_live_dump.py), lines 109–145 |
| Explicit private `CUBRID_TMP` | Every child receives the copied installation's private `tmp` directory. | `probe_live_dump.py`, lines 130–145 |
| Per-run master port | The probe asks the OS for an ephemeral loopback port and writes it as `cubrid_port_id` before starting CUBRID. | `probe_live_dump.py`, lines 122–129 |
| Fail-closed endpoint checks | It rejects `/tmp/CUBRID1523`, paths outside the private directory, and any pre-existing filesystem entry, both before database creation and before master spawn. | `probe_live_dump.py`, lines 56–65 and 159–167 |
| Master readiness and ownership | It keeps the master handle, detects early exit, requires a Unix socket, and correlates the socket inode in `/proc/net/unix` with the launched PID's file descriptors. The server starts only afterward. | `probe_live_dump.py`, lines 67–106 and 168–185 |
| Explicit process ownership | Both master and server `Popen` handles remain available through normal and exceptional paths. | `probe_live_dump.py`, lines 168–185 and 250–256 |
| Unregister before teardown | Cleanup first invokes `cubrid server stop tui_probe`, even when the directly tracked server has already exited, so the master can remove its entry while the executable still exists. | `probe_live_dump.py`, lines 30–53 and 250–256 |
| Bounded termination | Cleanup uses bounded waits, escalates from terminate to kill, and reaps both processes. | `probe_live_dump.py`, lines 19–53 |
| Host-execution warning | The script says it is for a disposable, PID-limited VM/container and refuses ordinary non-PID-1 invocation. Ticket 03 no longer advertises the old namespace command as sufficient. | `probe_live_dump.py`, lines 1 and 259–265; [`ticket-03.md`](../implementation/ticket-03.md), lines 44–69 |

These controls are deliberately redundant. A unique path prevents accidental
selection; the pre-check catches configuration mistakes; ownership verification
catches wrong-master startup; retained handles make cleanup possible; bounded
termination makes cleanup finish; and an external PID limit contains defects
that survive all earlier checks.

One modest limitation should remain visible: choosing an ephemeral TCP port by
binding and then closing a reservation has a race before `cub_master` binds it.
The correct response to a collision is fail-closed startup, not an assumption
that the number is permanently reserved. This does not weaken the private Unix
pathname guarantee, but it is another reason not to treat a port choice as a
complete isolation boundary.

## Regression evidence

The ten tests in [`tests/test_live_probe.py`](../../tests/test_live_probe.py)
exercise the safety contracts without starting CUBRID or reproducing the fork
storm:

1. The first process spawn sees a private master pathname rather than the
   historical host endpoint (lines 57–85).
2. The configuration contains a non-default in-range master port before the
   first spawn (lines 88–110).
3. An injected post-server failure cleans the server and master in order (lines
   113–176).
4. A harmless pre-bound private Unix socket prevents all process spawning (lines
   179–211).
5. An early master exit prevents server startup (lines 214–242).
6. A live master that never creates the expected socket prevents server startup
   (lines 245–282).
7. A socket not owned by the spawned master prevents server startup (lines
   285–330).
8. An already-exited server is still unregistered before master cleanup (lines
   333–395).
9. Stop timeouts and stubborn processes exercise bounded terminate/kill/reap
   escalation (lines 398–475).
10. A failure preserves the caller's working directory (lines 478–495).

The recorded verification for commit `4d9d1c0` is 158 passing tests, including
10 focused probe-safety tests, plus passing strict mypy, Ruff lint/format, and
whitespace checks. These tests are strong evidence for configuration selection,
fail-closed startup, and cleanup control flow. They are synthetic: subprocesses
are faked and any Unix sockets are harmless, private test sockets.

The repaired real-process probe was intentionally **not** run on the shared host.
That is a safety decision, not missing routine verification. Its next end-to-end
execution belongs in a disposable VM or container with a strict PID limit and an
independently checked private endpoint.

## Remaining limits and confidence

| Finding | Confidence | Boundary |
| --- | --- | --- |
| `tui_probe` registered with the long-lived host master | High | Direct host master log: database name, timestamp, and namespace-local PID 7. |
| The selected pathname was `/tmp/CUBRID1523` | High | Derived from the recorded missing environment/configuration, deterministic CUBRID source, escaped registration, and later harmless namespace/socket check. The raw master log did not print the pathname. |
| Failed `execv()` children recursively continued as masters | High | Source control flow, first child PID, repeated log pairs, and observed parent topology agree. |
| Multiple normal databases initiated the storm | Rejected | The abnormal chain is specifically tied to `tui_probe` registration and revival. |
| `pkill cub_master` initiated the storm | Rejected | It began over fourteen minutes after the first runaway revival. It may have aggravated recovery. |
| Exact kernel panic trigger | Unknown | Kdump and reboot are proven, but the root-readable `vmcore-dmesg.txt` was unavailable; hard-lockup, another panic source, and the contribution of mass exit/core handling cannot be distinguished. |
| Repaired probe works end to end with real CUBRID | Not yet established | The host run was deliberately withheld. Synthetic regression tests validate the new safety seams; disposable-environment execution remains future work. |

## Operator checklist

Before any real-process probe:

- Use a disposable VM/container with a strict `pids.max` or equivalent task
  limit. PID 1 inside a namespace is not itself a PID limit.
- Create a unique absolute runtime directory and export the same `CUBRID_TMP` to
  the master, server, utility commands, and application subprocesses before they
  start.
- Set a private `cubrid_port_id`; do not assume a private pathname isolates TCP.
- Assert that the derived endpoint is inside the run root and does not exist.
- Start the master, retain its process handle, and prove that it owns the expected
  Unix socket before starting the server.
- Keep executable and runtime paths present until the server is unregistered and
  every owned process has been reaped.
- On every failure path: attempt unregister, wait with a deadline, terminate,
  escalate to kill if required, and reap.
- Never use an unscoped `pkill cub_master` as the first containment action. Stop
  the exact cgroup or verified process tree.
- Treat missing visibility or uncertain ownership as a refusal to run, not as an
  available resource.

For developers:

- Keep the synthetic safety suite mandatory for changes to the probe lifecycle.
- Run an end-to-end probe only in the disposable, PID-limited environment above.
- Track the engine `_exit()`/bounded-revival correction separately; do not weaken
  probe isolation after that defense is added.
- Document the incident-time implementation separately from later snapshots so
  timelines remain reproducible.

## Source and evidence map

### Incident artifacts

- `/tmp/cubrid-conf-tui-fork-storm-handoff.md:7-23,38-54` — consolidated
  post-incident endpoint finding, safe toy-socket result, and required repair
  scope.
- `/home/vimkim/temp/cubrid-dev2-server-failures/reports/2026-09-15-2140-hang.md:18-58,72-105,124-148,150-179`
  — incident conclusion, timeline, alternatives, unknowns, and corrective
  actions.
- `/home/vimkim/temp/cubrid-dev2-server-failures/evidence/2026-09-15-2140-hang/derived/source-mechanism.txt:4-54`
  — probe behavior and failed-`execv()` source derivation.
- `/home/vimkim/temp/cubrid-dev2-server-failures/evidence/2026-09-15-2140-hang/derived/command-and-master-log.txt:5-38`
  — command chronology, host master registration/revival records, repeated-log
  counts, and post-`pkill` continuation.
- `/home/vimkim/.codex/sessions/2026/09/15/rollout-2026-09-15T21-13-56-01a0a4fc-f4ae-7a43-bf02-02a42a5ac806.jsonl:117,119,146,170`
  — recorded probe commands and outcomes. Only incident-relevant signal was used;
  no credentials or unrelated session content is reproduced here.

### Probe repair

- Git commit `4d9d1c0b9e554db8d5ccbb78d53a9942854b998c` — implementation and
  regression-test change, separate from ticket 05.
- `git show 4d9d1c0^:docs/verification/probe_live_dump.py:18-150` — later unsafe
  pre-fix snapshot; missing `CUBRID_TMP`, default port, discarded master handle,
  no endpoint-owner check, and incomplete cleanup.
- [`docs/verification/probe_live_dump.py`](../verification/probe_live_dump.py)
  — repaired probe.
- [`tests/test_live_probe.py`](../../tests/test_live_probe.py) — synthetic safety
  and cleanup regression tests.
- [`docs/implementation/ticket-03.md`](../implementation/ticket-03.md), lines
  40–69 — corrected operating guidance and recorded verification.

### CUBRID and Linux primary sources

All CUBRID links below are pinned to upstream commit
`9aabaa22610af3588a337394b40df719d29c845c`, verified as the exact local
`/home/vimkim/gh/cb/develop` commit and present on the canonical
`https://github.com/CUBRID/CUBRID` remote when this report was prepared.

- [Environment prefix constant](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/base/environment_variable.c#L38-L41)
- [`envvar_prefix()`](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/base/environment_variable.c#L92-L125)
- [`envvar_name()` and `envvar_get()`](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/base/environment_variable.c#L142-L190)
- [Master pathname construction](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/connection/tcp.c#L139-L156)
- [Existing-socket unlink before master bind](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/connection/tcp.c#L740-L799)
- [`cubrid_port_id` default and range](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/base/system_parameter.c#L1562-L1572)
- [Revival decision and retry queue](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/executables/master_server_monitor.cpp#L181-L199)
- [Fork/`execv()` implementation](https://github.com/CUBRID/CUBRID/blob/9aabaa22610af3588a337394b40df719d29c845c/src/executables/master_server_monitor.cpp#L261-L279)
- [CUBRID manual: `CUBRID_TMP`](https://github.com/CUBRID/cubrid-manual/blob/3b6ae97bfbdc664b010ffa933ded5a05b291ae03/en/env.rst#L24-L66)
- [CUBRID manual: multiple database servers](https://github.com/CUBRID/cubrid-manual/blob/3b6ae97bfbdc664b010ffa933ded5a05b291ae03/en/admin/control.rst#L207-L228)
- [Linux namespace overview](https://man7.org/linux/man-pages/man7/namespaces.7.html)
- [Linux mount namespace semantics](https://man7.org/linux/man-pages/man7/mount_namespaces.7.html)
- [Linux pathname Unix socket semantics](https://man7.org/linux/man-pages/man7/unix.7.html)

### Corroborating local design research

- `/home/vimkim/gh/my-cubrid-docs/research/cubrid-worktree-instance-isolation_8459255_codex.md:31-41,55-79,83-113`
  — independent inventory showing that per-instance CUBRID isolation is a
  resource bundle, not a single environment variable or port.

No relevant additional ticket context was found in
`/home/vimkim/gh/my-cubrid-jira`.
