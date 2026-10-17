# City road round-trip milestone v0.1

Date: 2026-10-17

## Achieved

- City entry now creates a developer editor panel.
- Existing SC4 ground-network records seed the interactive road topology map.
- Road input is opt-in and does not begin from UI clicks.
- Road commits update the Godot mesh/terrain path and emit plain staged data.
- A safe baseline exporter copies the original save without overwriting it.
- Network records preserve their source bytes and variable-layout offsets.
- The network-index parser now decodes the full structured layout used by the
  open-source SC4 savegame implementation, while retaining the old reference
  scan as a cross-check.
- An experimental writer clones a simple saved Road record, patches location,
  geometry, WNES edges, CRC, and memory pointer, adds a matching network-index
  tile, and rewrites a new DBPF while preserving untouched stored entries.

## Evidence

Against a user-owned `City - Back Bay.sc4`:

- source: 357 ground-network tiles, 561 network-index tiles;
- generated output: 358 ground-network tiles, 562 network-index tiles;
- both generated subfiles parse with zero network layout failures;
- structured network-index decode consumes the complete record;
- source remains the input path and the output is a separate file.

The generated file has not yet been accepted as a retail SimCity 4 save. The
next manual gate is to load it in the real game, confirm the new road exists,
save it from SC4, and re-open the SC4-saved result in OpenSC4.

## Known limits

- only new empty tiles are supported by writer v0;
- only simple Road records with one crossing are used as templates;
- modified entries are written uncompressed, so output size/layout changes;
- no avenue, street, rail, bridge, pipe, tunnel, or complex intersection edit;
- the city simulation has not yet been reconciled with the new network;
- the original save must never be used as the writer destination.
