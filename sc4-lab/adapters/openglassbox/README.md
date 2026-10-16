# OpenGlassBox candidate adapter

Keep OpenGlassBox as an external, pinned dependency while the bridge contract
is designed. The preferred runtime integration is a small C++ GDExtension that
exposes simulation commands, snapshots, events, and lifecycle to OpenSC4.

Do not change the verifier or reference observations from candidate code.

The first candidate adapter should speak the shared JSON-line protocol in
[`../PROTOCOL.md`](../PROTOCOL.md). Map OpenGlassBox snapshots and commands to
plain data there; do not expose its object graph to GDScript. The adapter must
report its pinned upstream commit and backend fingerprint in `hello` without
including source snapshots or game assets.
