# Architecture and seams

## Current runtime

```text
BootScreen
  -> DBPF index/parser registry (Core)
  -> Region or City scene
  -> terrain + networks + occupants + SC4 UI
```

`Core` owns the local DBPF index and resolves parser classes. `City.gd` turns
city-save subfiles into Godot terrain, meshes, sprites, and MultiMesh instances.
The renderer currently owns most city-loading decisions because simulation does
not exist yet.

## Target runtime

```text
Boot / Region / City UI
          |
       CityModel
          |
   SimulationBackend API
     /              \
SC4-compatible       modern
backend               backend
          |
       snapshots/events
```

The UI and renderer must consume normalized city state rather than reaching
into an OpenGlassBox object graph. A backend owns its clock, entities, rules,
serialization, and update ordering.

## Minimum backend contract

The first interface should answer only these questions:

- What simulation time and tick are we at?
- Which entities and resource stocks exist?
- Which commands were accepted, rejected, or deferred?
- What changed since the previous snapshot?
- Can the state be serialized and loaded with a version/fingerprint?
- What errors are recoverable versus fatal?

Keep commands and snapshots plain data. Do not expose Godot `Node` pointers,
OpenGlassBox C++ references, or proprietary SC4 parser objects across the seam.

## Bridge choices

1. **GDExtension** — preferred runtime path; a small C++ adapter owns the
   OpenGlassBox library and maps plain data to Godot types.
2. **JSON sidecar** — useful for early differential experiments; slower and
   more fragile, but keeps processes isolated.
3. **Direct GDScript port** — useful only for a tiny synthetic backend; not a
   substitute for a full OpenGlassBox bridge.

The bridge must define ownership, thread affinity, error propagation, fixed
tick advancement, and shutdown before it is used by the main scene.
