# OpenGlassBox sidecar v0.1

Snapshot: 2026-10-17. This is an integration milestone, not an SC4
compatibility claim.

## What is now real

OpenSC4 now contains a small process bridge to the externally built
OpenGlassBox library:

```text
OpenSC4 protocol probe
        │ JSON lines
        ▼
openglassbox_sidecar.py
        │ plain text commands
        ▼
openglassbox_helper.cpp
        │ C++ API
        ▼
OpenGlassBox Simulation
```

The helper creates a real OpenGlassBox `Simulation`, city, road path, nodes,
and segments. The Python process owns the existing `opensc4.adapter.v1`
envelope and exports only plain JSON values. No OpenGlassBox pointers, Godot
objects, SC4 parser objects, saves, or proprietary assets cross the boundary.

## Build and run

The external checkout stays outside this repository:

```bash
make -C /tmp/OpenGlassBox-master -j2
./tools/build_openglassbox_adapter.sh

python3 tools/probe_adapter.py \
  --adapter python3 sc4-lab/adapters/openglassbox/openglassbox_sidecar.py \
  --scenario sc4-lab/reference/scenarios/openglassbox-bridge-v0.1.json \
  --trace /tmp/opensc4-ogb-trace.jsonl \
  --observation /tmp/opensc4-ogb-observation.json
```

Set `OPENSC4_OPENGLASSBOX_ROOT` when the library is checked out elsewhere.
The compiled helper defaults to `/tmp/opensc4-openglassbox-helper` and is not
tracked.

## Verified boundary

- protocol hello reports the pinned external OpenGlassBox commit;
- reset creates a real city and can add a real road;
- command adds another road through the shared protocol;
- advance moves the OpenGlassBox clock by fixed ticks;
- snapshot reports clock, city, path, node, and segment counts;
- save/load reconstructs the bridge's road-and-clock state;
- shutdown exits the helper cleanly.

This does not prove that OpenGlassBox matches SimCity 4. It proves that an
actual candidate simulation can now be exercised through the same adapter seam
as the synthetic backend, which enables later SC4-versus-candidate
comparisons.

## Deliberate limitations

- roads are straight segments and currently use a small bridge-specific model;
- the first sidecar exposes no OpenGlassBox script/ruleset or building import;
- the event endpoint retains a bounded 256-event ring buffer and reports history
  gaps explicitly;
- Godot has not yet selected this backend at runtime;
- the external library remains pinned outside the repository and its licensing
  terms must be reviewed before distribution.

## Next closure work

1. Add a Godot `SimulationBackend` client that launches this sidecar when
   configured and maps snapshots/events to plain Dictionaries.
2. Add building/resource commands only after the road lifecycle is stable.
3. Preserve the SC4 road writer as a separate compatibility path; this sidecar
   does not read or write `.sc4` files.
