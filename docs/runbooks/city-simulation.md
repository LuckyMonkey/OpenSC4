# City simulation in Godot (OpenGlassBox backend)

Loading a city now starts a simulation of it. The city is converted to the
canonical city model, handed to an unmodified OpenGlassBox library through the
JSON-line sidecar, and stepped one game day at a time on a worker thread.

```text
City.gd ─► Sc4CityModel (save + your SC4 exemplars)
        ─► CitySim ──JSON lines──► openglassbox_sidecar.py ──► helper (links libOpenGlassBox)
                                      │  sc4_city_ruleset.py generates the .ogs
        ◄─ HUD, pollution overlay, traffic overlay ◄───┘
```

## What is real, what is candidate

| System | Inputs | Behavior | Status |
| --- | --- | --- | --- |
| Buildings, lots, roads | city save | — | as saved |
| Per-building pollution, radius, upkeep, power, capacity | **your SC4 exemplars** (`Pollution at centre` 0x27812851, radius 0x68EE9764, upkeep 0xEA54D286, capacity 0x27812834) | — | real SC4 data |
| Monthly tax | rates, bases | **TAX_001** `trunc(Σ B·M·R/1200)` | rule verified; **bases are a placeholder** (100 per resident/job) until Priority A |
| Monthly upkeep | Σ exemplar upkeep | summed | unverified against SC4 expenses; road maintenance not included |
| Air pollution | exemplar values | OpenGlassBox `Layer` diffusion 20 % / decay 8 % per game hour | **candidate**, not SC4-verified |
| Traffic | residents/jobs, road graph | OpenGlassBox commuter agents, Dijkstra + BPR travel time | **candidate**, not SC4-verified |

Candidate parameters live in one place:
`sc4-lab/adapters/openglassbox/sc4_city_ruleset.py` (`PEOPLE_PER_UNIT`,
`AIR_DIFFUSION`, `AIR_DECAY`, `COMMUTER_SPEED`, `PLACEHOLDER_BASE_PER_CAPACITY`).
Replace each with a measured SC4 rule as the roadmap closes it.

## Run

```bash
bash tools/build_openglassbox_adapter.sh --root /path/to/OpenGlassBox   # fd7d918, or fd7d918 + 7d3ae8e (faster, see below)
godot --path .                     # open a city: the sim starts with it
OPENSC4_SIM=0 godot --path .       # same, without simulating
```

In the city: **F6** pause/resume, **F7** pollution overlay, **F8** traffic
overlay. The HUD (top right) shows day, funds, last month's tax and upkeep,
commuters, busy road links and total air pollution.

Headless and visual checks:

```bash
godot --headless --path . res://tools/SimCity.tscn -- 31        # ends with SIM DONE
godot --path . --resolution 1600x900 res://tools/ScreenshotCity.tscn -- /tmp/shots \
    Timbuktu "Big City Tutorial" sim=2 "64,64,2,2,overview"
godot --headless --path . res://tools/ExportCity.tscn -- /tmp/city.json   # canonical city only
```

## Measured (Big City Tutorial, 3,427 buildings, 3,436 road links)

- Model build + OpenGlassBox city init: about 5 s.
- One game day: ~0.67 s in Godot with the OpenGlassBox layer optimization
  below (~1.5 s on stock fd7d918; 4.8–5.7 s before any culls).
- Morning and evening commuter waves of ~110 agents (1 agent = 100 people);
  ~2,500–2,800 road links carry traffic.
- Air pollution approaches a steady state within ~10 days
  (30,876 → 48,801 total).

## Performance: what was culled and what was not

Profiled per game day (helper only, tutorial city):

| Component | Before | Share |
| --- | --- | --- |
| Commuter agents | ~4–6.5 s | ~85 % |
| Pollution emitter rules | ~0.9 s | ~15 % |
| Other OpenGlassBox work | 0.13 s | ~2 % |
| Layer/traffic dumps + JSON | ~20 ms | <1 % |
| Godot overlay redraw | 40–50 ms | <1 % |

Adopted (behavior kept; tests below):

- **Lost commuters give up after 2 game hours** (`agentGiveUpTicks` 2400 →
  120): 3.73 → 2.41 s/day; commute waves unchanged.
- **Commuters capped to job slots** (`commuting_share`): 2.41 → 1.32 s/day.
  256 home units competed for 145 job units, and the surplus searched the whole
  graph. Modelling choice: unemployed residents do not commute.

Rejected because they change results:

- Batched pollution emission (every 2 h ×2 / every 6 h ×6): 25–55 % faster,
  but steady-state pollution rises 16 % / 57 %. OpenGlassBox decay removes at
  least one unit per cell, so burst input settles higher.
- Faster commuters: no gain.

- **Straight road runs merged** (`compact_roads`): 3,436 tile links → 1,291
  segments; buildings attach at street addresses (`BUILDING_ON`). Topology and
  lengths unchanged; pollution identical. Small gain (~0.1–0.3 s/day), and a
  cheaper traffic overlay.

Rejected: dropping the 2,326 houses that emit 1 unit of air pollution saves
only 0.11 s/day but changes the pollution map by 23 % at the hotspots.

### Where the remaining time goes (clean run, s/day)

| full | no commuters | no emitters | neither |
| --- | --- | --- | --- |
| 1.24 | 1.09 | 0.31 | 0.10 |

Pollution emission is ~75 %. 87 % of the emitted cell work comes from the 980
industrial buildings, whose SC4 air-pollution radius is 13 or 16 tiles
(365–545 cells per hourly add, plus the capacity check over the same diamond).
These are real SC4 values, so the speedup had to come from inside OpenGlassBox.

### OpenGlassBox layer optimization (upstream candidate)

Rule commands on layers use distributed adds, which touch about one cell. But
before every add, the capacity check walks the whole diamond twice
(`sumInRadius` + `walkCellsInRadius`), one hash-map block lookup per cell.
Both results are order-independent, so OpenGlassBox commit `7d3ae8e`
(branch `perf/layer-radius-ops` on top of `fd7d918`, local, not yet proposed
upstream) walks the clipped diamond row by row: one block lookup per row
segment, plus a closed-form count. Adds and removes keep `CellsInRadius`
because their random start offset matters.

Verification:

- Same helper, same seed, stock vs patched library: grid, traffic and stats
  hashes **identical** on every one of 3 days; stock is deterministic run to run.
- 192,049 randomized brute-force checks of sum and count (radius 1–24,
  clipped/offset regions, negative cells, empty blocks): 0 mismatches on both
  libraries.
- 1.06 → 0.44 s per helper day (×2.4); ~1.5 → ~0.67 s per day in Godot.
- OpenGlassBox's own GoogleTest suite was not run here (`libgtest-dev` not
  installed).

Determinism fix in our helper: OpenGlassBox seeds `CellsInRadius`'s global RNG
from `std::random_device`, so runs differed. The helper now calls
`CellsInRadius::setSeed(seed)`, and the same city and seed reproduce exactly.

## Known limits

- One agent per 100 residents keeps the agent count affordable. Finer
  granularity costs roughly linearly in OpenGlassBox routing time.
- Road connectivity uses 4-adjacency of drivable tiles, not SC4's crossing
  flags, so some diagonal roads appear as staircases.
- Placeholder taxable bases make the money figures illustrative only. The tax
  arithmetic is exact; its inputs are not yet SC4's.
- The sidecar's helper log is `$TMPDIR/opensc4-openglassbox-helper.log`.
