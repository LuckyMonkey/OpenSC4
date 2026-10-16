# Milestone: reproducible lab baseline v0.2

## Outcome

OpenSC4 now has a repeatable, data-free development baseline that can be
committed and synchronized without treating a local SC4 installation as a
repository fixture.

## Delivered

- Baseline runs emit `opensc4.baseline.v1` manifests containing Git commit,
  branch, dirty-file count, Godot version, resolution, renderer profile, and
  opt-in experiment flags.
- `tools/check_data_boundary.sh` rejects tracked game archives, executables,
  binary libraries, and committed reference outputs.
- Backend and parser smoke fixtures execute without SC4 reference data.
- Performance probe and bounded view-cache measurements are recorded in the
  performance baseline.
- Reference schema, draft POWER_001 scenario, iteration runbook, and future
  work/wishlist define the next experimental boundary.

## Evidence

The following checks are the release gate for this milestone:

```sh
git diff --check
godot --headless --path . --import
godot --headless --path . res://tools/SyntheticBackendSmoke.tscn
godot --headless --path . res://tools/ParserFixtureSmoke.tscn
bash tools/check_data_boundary.sh
bash tools/run_baseline.sh /tmp/opensc4-baseline Timbuktu "Big City Tutorial"
```

The deterministic headless variant is:

```sh
SC4_SKIP_SCREENSHOT=1 bash tools/run_baseline.sh \
    /tmp/opensc4-baseline-headless Timbuktu "Big City Tutorial"
```

The deterministic checks pass. The city sweep reaches `SWEEP COMPLETE`.
Screenshot capture reaches `SCREENSHOTS DONE` when Xvfb starts successfully;
Godot may then exit 134 during llvmpipe cleanup, which is a known shutdown
issue and not a capture result.

## Not yet proven

- Real RTX/X11 performance at 3480x1080.
- Stable memory behavior for the two-view cache.
- SC4 reference observations or 1:1 simulation behavior.
- OpenGlassBox runtime integration.

## Next milestone

Resolve the reference-adapter capability question while running the real RTX
performance/memory profile in parallel. Keep all observations local until their
provenance and legal/data boundary are reviewed.
