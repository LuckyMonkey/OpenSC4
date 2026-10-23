# City runtime v0.3 — responsive checkpoints and honest startup checks

Implemented 2026-10-23. Candidate simulation only; no SC4 compatibility claim.

## Checkpoint ownership and responsiveness

Interactive F9/F10 pause advancement, invalidate stale day callbacks and wait for
the current worker by polling `Thread.is_alive()` each frame. Once finished, a
checkpoint worker exclusively owns the backend pipe. It performs file I/O,
replay, snapshot and overlay data reads; only the main thread updates scene nodes.
Completion leaves the simulation paused and emits `checkpoint_finished`.
Elapsed-time status describes the phase, not a fabricated replay percentage.
Synchronous entry points remain for headless callers and reject concurrent work.

Malformed structure, foreign city, oversized input, missing file and write/rename
failures produce explicit diagnostics. A failed restore refreshes the retained
backend state, including any day completed while the request was pending. The
original failure is preserved even if subsequent refresh succeeds.

## Startup correctness

HeadlessCity now requires every archive and the selected save to load before
instantiating a city. Failure exits 1 without a sweep success marker. PlayCity
uses the same gates and displays a readable failure window.

## Evidence

- Godot 4.7.2 import: no script errors.
- `python3 tools/check_city_runtime.py`: all runtime/transport checks pass.
- `godot --headless --path . res://tools/CityCheckpointSmoke.tscn`: PASS.
  Includes frame progress during an injected 200 ms save/restore delay,
  duplicate/synchronous request exclusion, malformed and foreign checkpoints,
  file-write failure retention, real-helper replay and dead-sidecar recovery.
  The intentional integrity rejection logs one expected backend error.
- After reboot, real-city camera sweep completed. It exposed a pre-existing
  network-index structured-read overrun, now guarded by checked reads, bounded
  counts and failure-state clearing. The writer cannot accept truncated data;
  rendering retains scanned references for unsupported layouts. Parser fixtures
  cover all truncated prefixes of a valid empty v6 record, oversized counts,
  trailing data and successful decoding.
- Real tutorial city (3,427 buildings), three simulation days: asynchronous save
  1,067 ms / 111 frames; restore 2,407 ms / 339 frames. An extra day was advanced
  before restoring; day, funds and pollution matched the saved values.
  `REAL CITY CHECKPOINT PASS` and `SIM DONE`, exit 0. No script errors;
  pre-existing shutdown resource leaks remain.
- Windowed Vulkan/NVIDIA launch at 1600x900: tutorial terrain/buildings and both
  panels visible, no runtime errors. F6 keyboard pause verified at day 23;
  game left open paused. Screenshot retained locally at `/tmp/opensc4-live.png`.
  F9/F10 keyboard routing was not exercised; asynchronous operations were tested
  through the same request API in the integration harness.

## Limits

Replay cancellation and per-day replay progress are not implemented. Closing the
scene still waits for active work, bounded by transport deadlines. A responsive
UI does not shorten reconstruction time. Long-history replay and cancellation remain untested. No disk repair or proprietary game-file changes performed.

## Real-city reproduction

The helper in `/tmp` is removed by reboot; rebuild against the preserved external
library before launching simulation:

```sh
bash tools/build_openglassbox_adapter.sh --root /home/freezer/.local/src/OpenGlassBox-perf
godot --headless --path . res://tools/SimCity.tscn -- 3 Timbuktu "Big City Tutorial" checkpoint
godot --path . --resolution 1600x900 res://tools/PlayCity.tscn
```

The integration check writes only a PID-specific temporary checkpoint and removes
it on success. Retail saves and the user's normal checkpoint are untouched.
