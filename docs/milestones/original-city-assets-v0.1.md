# Original city assets v0.1

Implemented 2026-10-23 against the user's local Deluxe installation. Assets stay
in the user's DAT archives; the repository contains only code and resource IDs.

## Inventory

`tools/sc4_asset_inventory.py` merges the six core/expansion archive indices in
load order and inventories PNG/FSH groups, UI layouts, button-image references,
source archives and PNG dimensions. Optional original PNG exports and the JSON
manifest must be outside the repository. The group containing networks also
contains model textures; its count must not be reported as a road-texture count.

Observed local resources after TGI overrides:

| Category | Resources |
| --- | ---: |
| UI images | 810 |
| Tool icons | 39 |
| Terrain | 182 |
| Lot ground | 1,453 |
| Shared network/model textures | 37,131 |
| UI layouts | 281 |

## Runtime use

`Sc4CityControls.gd` uses 12 original PNG resources: camera panel, zoom/rotation,
pause/speed states, toolbar toggle, transportation and return-to-region icons.
Camera button identifiers/rectangles/images are read from layout
`00000000-96a006b0-c973b411`; SC4 rectangles are interpreted as left/top/right/bottom.
PNG magenta color keys become transparent in a runtime copy, preserving source
images. Button atlas rows are cropped to the layout's frame height, rather than
stretching two-row images. Missing resources retain text controls/editor fallback.

Original graphics now control the actual camera, simulation and road staging;
they do not imply unimplemented retail behaviors. Speed choices control wall-clock
pacing of the candidate backend, not SC4's native clock. The static sample map in
the original camera panel is covered with this city's height/network minimap.
The large editor/export panel starts collapsed under Tools & export. Simulation
diagnostics are collapsed behind F11; checkpoint failures remain visible. Original
art stays pixel-sized and bottom-left anchored instead of stretching ultrawide.

## Validation

`CityUISmoke.tscn` loads the actual tutorial and verifies 12 textures, all nine
camera-panel controls, color-key alpha, tools visibility, road-tool state,
pause/speed, zoom/rotation, and bounds at 1280x720, 1600x900 and 3440x1440.
Success marker: `CITY UI PASS`. Minimap dimensions are also asserted to prevent
texture minimum sizes overflowing the original panel. No SCRIPT ERRORs. Existing shutdown resource leaks
remain. The Vulkan screenshot harness writes its image, then encounters the
pre-existing shutdown double-free (exit 134); it is not a clean process exit.
Final live-window screenshot `/tmp/opensc4-original-final.png` confirms the
corrected minimap fits the panel, original controls render, and the compact HUD
remains readable over the city. Screenshots remain local and are never committed. Screenshot output now
creates its directory and checks write errors before announcing success.

## Next asset integration work

1. **Terrain:** audit original terrain parameter tables against shader slope,
   elevation, shoreline and cliff blending; validate a coastal and mountain city
   at every zoom before adding terraforming edits.
2. **Roads:** audit saved orientation/wealth/crossing variants and RUL-driven drag
   connectivity; distinguish intersections, diagonals, bridges and elevated
   networks. Finish structured index decoding before broadening native saves.
3. **UI:** import transportation/zoning submenus and exemplar-referenced tool
   icons alongside implemented tools; integrate original budget/data panels as
   their underlying behavior becomes available. Correct legacy region rectangle
   semantics separately with screenshot coverage.
4. **Fonts/audio:** resolve local font definitions and button-sound references;
   current controls use Godot's font and do not claim original audio behavior.

## Commands

```sh
python3 tools/sc4_asset_inventory.py '/path/to/SimCity 4 Deluxe' /tmp/sc4-assets --export-ui
godot --headless --path . res://tools/CityUISmoke.tscn
godot --path . res://tools/PlayCity.tscn
```

The inventory is a discovery aid. Resource availability is not implementation
coverage, and visual similarity is not simulation compatibility.
