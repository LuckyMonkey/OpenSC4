# City runtime v0.2 — five substantive milestones

Implemented 2026-10-22. Candidate OpenGlassBox runtime features, not new claims
of SC4 simulation equivalence. No retail game or proprietary save was modified.

## 1. Validated, deterministic native input

`city_contract.py` validates city schema, dimensions, finite numeric inputs,
building attributes and footprints, node identity, edge references, duplicate
edges, supported network kinds, tax arrays, and bounded advancement. Command
validation and execution share this validator. Legacy mutations are rejected
in city mode. Road compaction uses sorted traversal so Python hash randomization
cannot change native insertion order. Failed city initialization uses a disposable
helper and preserves the active backend.

Evidence: malformed graph and numeric rejection, protocol-level failed init
preserves state, ruleset/load-plan equality across three Python hash seeds.

## 2. Calendar-based accounting

City initialization accepts `start_date` (default `2000-01-01`; this is not the
save's recovered native date). Advancement steps individual days and closes a
budget period on entry into the next Gregorian month. Replies contain elapsed
days, ISO date, and dated month records. Leap years and year transitions use the
standard library calendar. City mode rejects generic time advancement that could
bypass accounting. Taxes still use placeholder bases and upkeep is unverified.

Evidence: February 2000 leap-day close, December/January close, batched stepping
and restored continuation match native observations.

## 3. Transactional city checkpoints

`opensc4.city-checkpoint.v1` stores the canonical city/initial inputs, seed,
elapsed days, retained event history, engine identity, and integrity/observation
digests. Identity covers helper binary, loaded Linux OpenGlassBox shared library,
and adapter/rules/validation source. JSON numeric normalization and full-precision
Godot serialization preserve integrity across the boundary.

Load creates a fresh helper, replays the saved days, compares stats, pollution,
traffic, date and funds, restores event cursors, and only then swaps backends.
Schema/identity/integrity mismatches and replay divergence leave the current
backend intact. Replay is capped at 3,660 days. This is reconstruction, not a
native heap snapshot; the comparison cannot prove equality of every hidden field.
The digest detects accidental corruption, not malicious modification.

Evidence: real-helper checkpoint reconstruction and subsequent continuation;
event preservation; corrupted, foreign-engine and divergent saves rejected;
Godot JSON and file round-trips. No migration across code/engine versions.

## 4. Bounded process communication

Native helper transport uses nonblocking binary pipes, partial-write handling,
30-second exchange deadlines, a 32 MiB reply limit, EOF/UTF-8 checks and forced
cleanup on transport failure. Linux helper children receive a parent-death kill
signal. Godot uses nonblocking reads and atomic Linux pipe writes (at most 4096
bytes), 32 MiB request/reply bounds and a 120-second request deadline. Requests
check reply identity and protocol. Transport failure retains a diagnostic.

Evidence: timeout, oversized output, EOF, sidecar-death cleanup and a 200 KB
Godot city request. Linux is the validated platform; the atomic write assumption
and parent-death cleanup are not portable guarantees. Long replay may exceed the
Godot request deadline and require recovery from a shorter checkpoint.

## 5. Godot worker ownership and recovery

F9 saves `user://city-simulation-checkpoint.json` through a temporary file and
rename; F10 restores it. Both join the sole pipe-owning worker, invalidate stale
deferred results and leave the simulation paused (F6 resumes). Restore checks
that the checkpoint belongs to the currently loaded canonical city. A dead
sidecar can be restarted and restored. Failed steps do not increment the HUD day
or replace the last displayed state. The HUD shows date and failure details.

Evidence: controller save/restore, joining an active worker, stale-result
rejection, failed-step day retention and recovery after sidecar exit, all in a
headless scene. Keyboard input and visual layout still need manual review.
Checkpoint work currently runs synchronously after the worker joins; large
replays can pause the UI. No `.sc4` save writer is involved.

## Reproduce

Requires the already-built external helper (or build using the existing bridge
runbook). All fixtures are synthetic and contain no game assets.

```sh
python3 tools/check_city_runtime.py
godot --headless --path . res://tools/CityCheckpointSmoke.tscn
godot --headless --path . --script tools/openglassbox_sidecar_godot_smoke.gd
```

The checkpoint scene intentionally submits one corrupt checkpoint: its logged
`checkpoint integrity mismatch` is expected. Success ends with
`CITY CHECKPOINT GODOT PASS`. The fixture checkpoint is a PID-specific `/tmp`
file and is removed on success. Implementation of the first four milestones
preceded the first test batch; controller checks followed integration.

Next: asynchronous checkpoint progress/cancellation for large cities; explicitly
versioned simulation mutations with a replay command journal; native SC4 date
and taxable-base inputs after independent measurement. Do not broaden candidate
traffic/pollution compatibility claims from these runtime tests.
