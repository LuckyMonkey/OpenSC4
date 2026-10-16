# Project status

Snapshot: 2026-10-16. This is a working status document, not a compatibility
claim.

## Verified today

| Area | State | Evidence |
| --- | --- | --- |
| Godot project import | Pass | `godot --headless --path . --import` |
| City asset loading | Pass | Tutorial city loads from a user-owned install |
| Terrain/building/prop rendering | Pass | Headless sweep reaches `SWEEP COMPLETE` |
| Zoom/rotation fallback paths | Pass | All fixed zooms, rotations, and free-rotation probes run |
| Region UI placement | Implemented, visual retest pending | Layout-derived legacy canvas is bottom-left anchored |
| Simulation seam | Contract + synthetic backend smoke test | No SC4 behavior has been measured or claimed |
| SC4 reference adapter | Not implemented | No reference observations are committed |
| OpenGlassBox bridge | Not implemented | External library builds; no Godot ABI boundary yet |
| Performance probe | Implemented | Windowed startup/pan/view timing tool |
| Parser fixture smoke | Implemented | Synthetic malformed-record and UI-bound tests |
| Spatial batching | Opt-in experiment | `OPENSC4_SPATIAL_BATCHES=1` |
| View-batch cache | Measured, opt-in | `OPENSC4_CACHE_VIEW_BATCHES=1`, two-view LRU |
| Baseline artifact manifest | Implemented | `opensc4.baseline.v1` in each run output |
| Data boundary gate | Implemented | `tools/check_data_boundary.sh` |
| Simulation events/protocol | Implemented | Event cursors + JSON-line adapter contract |
| Observation comparator | Implemented | `sc4-lab/verifier/compare.py`, policy separated |
| Local reference capture | Implemented, awaiting SC4 input | Save hashes/deltas + user-owned process metadata |
| Dynamic memory observatory | Implemented, awaiting SC4 input | Read-only scan/snapshot/watch tooling |
| REA integration | Connected, Ghidra healthy, bridge timeout | Codex MCP/skill aligned; native queries bounded |
| Static candidate ledger | Implemented, unverified | 185 named-string candidates + code references |
| Private SC4 evidence pack | Implemented, static-only | Target manifest + 57 categorized leads; runtime input pending |
| Live SC4 hashed capture | First runtime milestone | 859 launch regions, 913 city regions, 143 transition changes |
| SC4 tax path | First native distillation milestone | Proven rate storage/getter/setter and tax-income writer boundary; full taxable-base formula pending |

## Current strengths

- The project loads original SC4 DBPF data locally without tracking game files.
- The city loader has structured parsers for terrain, lots, networks, pipes,
  buildings, props, flora, foundations, retaining walls, power lines, and 2D
  sprite props.
- Props and flora use MultiMesh batching, with model and sprite caches.
- Headless and screenshot harnesses provide a repeatable rendering baseline.
- The compatibility-lab boundary separates reference observations from candidate
  implementation work.
- A renderer-independent backend contract and deterministic synthetic power
  backend now exercise clocking, supply/demand, snapshots, and save/load.
- Baseline outputs now carry reproducibility metadata without recording local
  game paths or game contents.
- The backend seam now supports validation, bounded event history, save schema,
  and backend fingerprints without coupling to OpenGlassBox.

## Known risks

- The city renderer still creates a large terrain and water mesh and performs
  substantial shader work at ultrawide resolutions.
- A fixed-iso view uses pre-rendered SC4 model variants; free orbit is an
  inspection mode, not a claim of SC4 visual equivalence.
- Missing or malformed DBPF records are handled unevenly; edge-case corpus
  coverage is still small.
- The current shutdown path reports substantial ObjectDB/resource leaks after
  the harness has completed. This is a cleanup issue, not currently a load
  failure, but it can hide future failures.
- There is no simulation state model, save migration policy, or adapter ABI.
- The reference observation adapter and independent verifier are still absent.
- Local capture tooling exists and has completed a live metadata-only SC4 run;
  no `.sc4` save or decoded city value has been added yet.
- REA is connected for Codex, but the current session needs a restart and a
  native provider (preferably Ghidra) before function-level SC4 analysis.
- Ghidra is now installed and healthy, but REA's native bridge times out on
  this legacy PE; the local candidate ledger preserves leads without claiming
  function boundaries or runtime authority.
- The evidence pack organizes those leads for runtime follow-up, but no field
  is verified until a live process survives controlled change, reload, and
  restart checks.
- A real Steam-launched city session now supplies metadata-only hashed
  snapshots and transition diffs. A separate local GDB investigation has now
  decoded the SC4 tax-rate object layout and the tax-income writer boundary;
  this is not a decoded treasury/date/power field.
- The live tax-rate setter was invoked only after its vtable target and bounds
  behavior were proven. All twelve rates were temporarily raised from `9.0`
  to `20.0` in process memory; no executable or save was changed. See
  `docs/milestones/sc4-tax-distillation-v0.1.md`.
- OpenGlassBox has its own simulation concepts and a dual GPL/commercial
  licensing policy; dependency review is required before distribution.

## Definition of progress

Every milestone must produce at least one of:

1. a deterministic regression test;
2. a benchmark with before/after measurements;
3. a documented edge case and expected fallback;
4. a written behavioral specification backed by observations; or
5. a reviewable adapter/interface that keeps rendering independent of simulation.

Do not use a single compatibility percentage. Report status by subsystem and
distinguish verified, approximate, unsupported, and unknown behavior.
