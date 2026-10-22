# Future work and wishlist

This is the living backlog. A wishlist item is not a compatibility promise;
it becomes a milestone only when it has a test, measurement, specification, or
reviewable interface.

## P0 — required for a credible compatibility milestone

- [ ] Capture the real RTX/X11 profile at 3480x1080: startup, steady panning,
  zoom/rotation changes, repeated-view cache timing, and resident memory.
- [ ] Resolve or isolate the Godot shutdown leaks and llvmpipe double-free so
  harness exit status cannot obscure a completed capture.
- [ ] Expand the local city matrix: empty, dense, coastal, no-power-line,
  no-pipes, missing-model, and multiple city-size cases.
- [ ] Establish an allowed, repeatable SC4 reference observation path. Until
  then, leave reference metrics `unsupported`; never infer them from pixels.
- [x] Define fail-closed schema/engine mismatch behavior for separate candidate
  simulation checkpoints (`milestones/city-runtime-v0.2.md`).
- [ ] Add asynchronous checkpoint progress/cancellation and explicit migration
  policy before broadening persistent simulation state or modifying player saves.

## P1 — next implementation milestones

- [ ] Add the first held-in/held-out power observation corpus and independent
  comparator.
- [ ] Prototype an OpenGlassBox JSON sidecar, then replace it with a narrow
  GDExtension only after ownership, ticking, events, and shutdown are tested.
- [ ] Add visual invariants for camera/world coordinates, missing models, and
  UI anchoring at 16:9, 21:9, and 32:9.
- [ ] Add memory budgets and quality profiles for terrain, water, props, and
  view-batch caching.
- [ ] Make the baseline manifest include a stable renderer/driver identifier
  when the host exposes one, without recording proprietary game contents.

## P2 — wishlist

- Optional modern simulation mode alongside an SC4-compatible mode.
- Deterministic replay files containing commands and seeds, not game assets.
- Streaming/culling for large cities and a user-visible low-memory profile.
- In-game diagnostics overlay for frame time, loaded records, batch counts, and
  backend state.
- A local experiment dashboard that compares immutable observations against
  candidate reports.
- CI jobs that exercise all data-free fixtures without requiring SC4 files.

## Explicit non-goals

- Shipping EA executables, DLLs, DATs, original saves, extracted assets, or
  screenshots containing protected game content.
- Claiming 1:1 SC4 behavior from the synthetic backend or a visual match alone.
- Copying OpenGlassBox source wholesale into the Godot project.
- Changing verifier tolerances to make a candidate pass.

## Completion rule

For each item, record the command or experiment, the observed result, the
limitations, and the next unresolved edge case. Move an item to done only when
that evidence is committed with the implementation or specification.
