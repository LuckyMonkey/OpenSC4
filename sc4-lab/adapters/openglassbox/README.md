# OpenGlassBox candidate adapter

Keep OpenGlassBox as an external, pinned dependency while the bridge contract
is designed. The preferred runtime integration is a small C++ GDExtension that
exposes simulation commands, snapshots, events, and lifecycle to OpenSC4.

Do not change the verifier or reference observations from candidate code.
