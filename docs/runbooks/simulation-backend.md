# Runbook: simulation backend seam

## Contract

Backends implement `SimulationBackend` and exchange plain Dictionaries/Arrays.
The contract exposes:

- backend and contract identity;
- capabilities and fixed-tick metadata;
- reset, command validation, command application, and time advancement;
- snapshots and versioned save/load;
- event cursors and bounded event history.

Godot nodes, OpenGlassBox C++ objects, SC4 parser objects, and asset paths stay
outside the seam.

## Lifecycle

```text
construct -> hello/capabilities -> reset -> validate -> command/advance
                                      ^                    |
                                      +--- snapshot/events-+
                         save/load may occur between commands
```

The caller stores an event cursor and requests only events after that cursor.
Backends may bound retention; a stale cursor must produce an explicit history
gap error in a production adapter rather than silently pretending continuity.

## Local synthetic backend

The synthetic power backend is a seam exercise, not an SC4 model. It provides
fixed one-second ticks, a 30-tick synthetic month, command validation, events,
snapshots, and save/load. Use it to develop UI/adapter plumbing before a real
simulation is available.

## Sidecar integration order

1. Implement the JSON-line envelope in an isolated process.
2. Exercise `hello`, reset, command validation, snapshots, events, and save/load.
3. Add timeout, process-exit, malformed-response, and history-gap handling.
4. Map the sidecar to the same plain-data contract as an in-process backend.
5. Only then prototype a GDExtension for lower overhead.

See [`../../sc4-lab/adapters/PROTOCOL.md`](../../sc4-lab/adapters/PROTOCOL.md)
for the wire format and
[`openglassbox-bridge.md`](openglassbox-bridge.md) for dependency boundaries.

## Failure policy

Recoverable command rejection stays in the response. Invalid save schema,
backend identity mismatch, event-history gaps, process crashes, and unknown
contract versions are hard adapter errors. The renderer should retain the last
known snapshot and show a recoverable diagnostic rather than mutating state.
