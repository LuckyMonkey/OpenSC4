# Godot city road round-trip runbook

This is the first end-to-end city-edit milestone. It keeps the original SC4
save untouched, enters a loaded city, lets the Godot UI stage road tiles, and
exports a safe baseline copy plus a machine-readable edit journal.

## Current boundary

The Godot road tool is now functional as a staged editor:

- existing ground-network topology seeds the RUL drag solver;
- `Build road` enables world input, so UI clicks cannot start roads;
- a committed drag updates the Godot road mesh and terrain preview;
- committed tiles are stored as plain `{x, z, edges, network}` records;
- each staged tile also records the local terrain height used by the writer;
- the experimental writer can clone a simple Road record into a new empty tile,
  rebuild the structured network index, and write a new `.sc4`;
- export refuses to overwrite the source city;
- the exported `.sc4` is an unchanged baseline copy and the `.sc4.opensc4.json`
  sidecar contains the staged road edits.

The baseline sidecar is intentional. It is not presented as a valid SC4 patch.
The experimental road-save button now performs the narrow writer path, but it
has not yet been accepted as SC4-compatible until the manual game-load gate
below passes.

## Manual smoke path

1. Launch OpenSC4 and enter a city from the region view.
2. Click `Build road` in the top-left editor panel.
3. Drag across terrain. Release to commit the preview.
4. Confirm the panel reports a non-zero staged tile count.
5. For a safe control, choose `Export SC4 baseline + journal` and select a new
   filename. Never select the source `.sc4`.
6. For the experimental writer, choose `Experimental save road changes to
   SC4` and select another new filename. The first supported case is a straight
   Road into an empty network tile; edits overlapping an existing network are
   refused.
7. Open the experimental output in the real SimCity 4 installation. Keep the
   matching `.opensc4.json` beside it and treat the city as disposable until
   the manual load/re-save gate passes.

## Read-only save reconnaissance

Use a user-owned city save; this command only parses it:

```bash
godot --headless --path . res://tools/SC4SaveInspect.tscn -- \
  "/path/to/disposable-city.sc4"
```

Record the network entry's stored size, compression status, decoded tile count,
and the network-index reference count before attempting a writer change.

## Writer gate

Do not call a future export “SC4 road save” until all of these are true:

- a copy of the source opens in SC4;
- a single new road survives SC4 reload;
- the network subfile parses with zero layout failures;
- the network index reference count and tile references remain coherent;
- the city remains loadable after a second SC4 save;
- the source save hash is unchanged;
- the generated journal records the source, destination, and writer version.

The first writer implementation should target one disposable small city and one
straight road. It should preserve every untouched subfile byte where possible,
use a fresh output path, and fail closed when the network index format is not
known well enough to rebuild. The current writer has reached the parser gate:
the generated probe output reopens with 358 ground-network tiles, 562
network-index tiles, zero network layout failures, and a complete structured
index decode. A disposable candidate was also staged as a new city in a
separate region folder for the retail load gate; no retail acceptance claim has
been made yet. This is necessary but not sufficient evidence that retail SC4
will accept the file.
