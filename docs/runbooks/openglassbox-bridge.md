# Runbook: OpenGlassBox integration investigation

## Current position

OpenGlassBox is an external C++17 simulation library with its own rules,
layers, buildings, agents, paths, fixed ticks, and save concepts. OpenSC4 is a
Godot/GDScript application. This is an interface-integration task, not a
source-tree merge.

## Pin and build

Keep the checkout outside OpenSC4 and record its exact commit:

```sh
git -C /tmp/OpenGlassBox-master rev-parse HEAD
make -C /tmp/OpenGlassBox-master -j2
```

The library should produce `build/libOpenGlassBox.a` and usually
`build/libOpenGlassBox.so`. The optional demo may require system GLFW/GLEW
headers; a demo failure does not invalidate a successful library build.

Run the upstream unit tests only when their GoogleTest dependencies are
available. Do not install packages as part of a normal OpenSC4 regression run.

## Adapter order

1. Write the plain-data OpenSC4 `SimulationBackend` contract.
2. Implement a tiny deterministic fake backend and tests against the contract.
3. Prototype OpenGlassBox in a standalone adapter or sidecar.
4. Define ownership, fixed-tick advancement, events, snapshots, errors, and
   save fingerprints.
5. Build a small GDExtension that exposes only the contract.
6. Add city rendering integration after lifecycle/shutdown tests pass.

Do not expose OpenGlassBox pointers or ruleset-specific classes to GDScript.
Do not let renderer code decide simulation update order.

## Licensing checkpoint

Preserve OpenSC4's AGPL notices. Review OpenGlassBox's GPL/commercial terms and
any bridge obligations before distributing a combined binary. This runbook is
not legal advice.
