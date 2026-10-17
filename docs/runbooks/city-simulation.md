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
bash tools/build_openglassbox_adapter.sh --root /path/to/OpenGlassBox   # pinned fd7d918
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
- One game day: 1.6–2.0 s in Godot (was 4.8–5.7 s before the culls below).
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

Next candidates, not yet done: collapse chains of degree-2 road tiles into
single segments (fewer router nodes, same topology); only rebuild overlays
when values change.

## Known limits

- One agent per 100 residents keeps the agent count affordable. Finer
  granularity costs roughly linearly in OpenGlassBox routing time.
- Road connectivity uses 4-adjacency of drivable tiles, not SC4's crossing
  flags, so some diagonal roads appear as staircases.
- Placeholder taxable bases make the money figures illustrative only. The tax
  arithmetic is exact; its inputs are not yet SC4's.
- The sidecar's helper log is `$TMPDIR/opensc4-openglassbox-helper.log`.
