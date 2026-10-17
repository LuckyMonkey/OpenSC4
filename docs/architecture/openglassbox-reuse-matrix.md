# OpenGlassBox reuse matrix for SC4 behavioral compatibility

Audit date 2026-10-17. OpenGlassBox pinned at
[`fd7d918`](https://github.com/Lecrapouille/OpenGlassBox/commit/fd7d91891191ba3603723adccbba282fce74c846)
(upstream HEAD on that date; checkout at `/tmp/OpenGlassBox-master`). File
references are to that commit. The older local checkout `985db88` uses a
different API (`Unit`, `Map`) and is not used.

Principle: **reuse infrastructure, not unverified behavior.** A "reuse"
below means the machinery fits; it does not mean SC4 behaves like it.

## Matrix

| Component | Evidence (source) | Classification | Reasoning |
| --- | --- | --- | --- |
| `Simulation` lifecycle | `Simulation.hpp:104` ctor, `:199` `stepOneTick`, `:252` `setTicks` | **Reuse unchanged** | Deterministic manual stepping works headless (used by the sidecar). Drive with `stepOneTick`/`setTicks`, not wall-clock `update(dt)`. |
| `SimulationClock` | header: day/hour/minute, "days never wrap" | **Extend (adapter side)** | No months or years. SC4 work happens at Gregorian month rollovers, so the SC4 calendar lives in the adapter and maps month length → days of ticks. Done in `budgetMonth`. |
| `World` | `World.hpp`: one shared grid, tick order cities → layers | **Reuse unchanged (untested for SC4)** | Ordering is a reasonable start. SC4's own intra-month update order is unmeasured. |
| `City` | `City.hpp:204,235,243` buildings/zones, `getGlobals()` `:415` | **Reuse as container** | Hosts the TAX_001 state today. |
| `Resources` / city treasury | `Resource.hpp:144-146` `uint32_t` amount + capacity, excess lost | **Replace for SC4 money** | SC4 funds are signed 64-bit and go negative; bases are 64-bit. OK for small non-negative inventories, wrong for SC4 accounting. TAX_001 clamps funds and flags it; a real SC4 budget needs its own signed store. |
| Rule language (`Rule`, `RuleCommand`, `RuleValue`, `.ogs`) | `RuleCommand.hpp:33,73,121`: add / remove / test integer constants on local, global or layer values | **Extend (C++ module)** for Level A | Cannot express `Σ B·M·R / 1200` or any multiplication between values. SC4 scalar rules go in C++ next to the engine. An upstream "arithmetic command" is possible later. |
| `Ruleset` / `.ogs` scripts | `Ruleset.hpp`: parser chosen by file extension | **Configure** | Good for declaring resource, layer, building and zone *types* once SC4 types are known. |
| `Layer` (spatial fields) | `Layer.cpp:232-330` `spreadAndFade`: 4-neighbour diffusion with integer quarter shares, decay with a 1-unit minimum, `uint32` cells, chunked | **Configure; validate against SC4 (Priority D)** | A plausible substrate for pollution and land value, but SC4's kernel, period and saturation are unmeasured. Integer rounding behavior will matter for exact matches. |
| `Building` | `Building.hpp:84,113`: anchored to a road `Node`/`Segment`, or placed by position | **Extend** | SC4 lots are tile rectangles with occupants (`LotSubfile`, `BuildingSubfile` parsers already exist in OpenSC4). Needs lot footprint, wealth and occupancy mapping. |
| `Zone` growth | `Zone.hpp:85,225,236`: grow when rules pass, free cell near a road | **Evaluate (Priority E)** | Mechanism shape fits. SC4 growth (lot size, stage, wealth, demand caps) is unmeasured. Expect modification. |
| `Agent` transport | `Agent.hpp` header: one visible traveller per fired command, carrying resources | **Do not reuse for SC4 commute without evidence** | SC4's commute and traffic representation is unmeasured. Mapping it onto per-trip resource agents would force SC4 into GlassBox semantics. Keep for visual traffic only, if at all. |
| `Path` / `Node` / `Segment` | `Path.hpp`: graph, segment addresses, ids | **Reuse** | Generic road-graph infrastructure. OpenSC4's `CityView/ClassDefinitions/Net*.gd` stubs (125 lines in total) are redundant and should not grow. |
| `IRouter` / `DijkstraRouter` | `Router.hpp` interface; `DijkstraRouter.hpp` BPR travel-time costs; `DijkstraRouter.cpp:54` seeds from `std::random_device` | **Extend via `IRouter`** | The swap point SC4's path costs need. **Determinism trap:** call `setRandomSeed` or runs differ. |
| `CellsInRadius` / `CellRegion` / `RandomCells` | taxicab diamond radius; uniform cell sampling | **Reuse unchanged** | Generic. Whether SC4 influence radii are taxicab is unmeasured. |
| Save / serialization | `CitySave` lives in `demo/src/Save/`, not the library | **Replace (adapter-owned)** | The library has no persistence API. The sidecar already owns a versioned save schema. |
| Licence | `LICENSING.md`: GPL-3.0-or-later or commercial | **Review before distribution** | GPLv3 §13 permits combining with AGPLv3 code such as OpenSC4. The sidecar process boundary keeps the build separable. Not legal advice. |

## OpenSC4 side

| OpenSC4 piece | State | Decision |
| --- | --- | --- |
| `simulation/simulation_backend.gd` (57 lines) | Backend contract | Keep: the canonical seam. |
| `simulation/synthetic_power_backend.gd` | Deterministic test backend | Keep for contract tests. |
| `simulation/openglassbox_sidecar_backend.gd` | Godot client of the JSON sidecar | Keep. Next client for TAX_001 commands. |
| `sc4-lab/adapters/openglassbox/*` | Sidecar + C++ helper | **Primary candidate engine.** Hosts `sc4-tax-v0.3`. |
| `sc4-lab/verifier/compare.py` | Independent verifier | Reused unchanged by the TAX_001 pipeline. |
| `CityView/ClassDefinitions/Net*.gd` | Stubs | Redundant with OGB `Path`. Freeze. |
| `tools/sc4_*` instrumentation | Reference side | Keep. Produces reference observations only. |

## Answer: can OpenGlassBox be a faithful SC4 backend?

**Partly, by level:**

- **Level A (scalars, accounting): no, not natively.** Unsigned 32-bit
  resources and an add/remove/test rule language cannot hold SC4 money or
  express its arithmetic. These rules must be SC4-specific C++ modules that
  use OpenGlassBox for state hosting and time, as TAX_001 does now.
- **Level B (entities): with extension.** Building/Zone containers fit, but
  lot geometry, occupancy and wealth must be added.
- **Level C (spatial fields): likely, pending measurement.** `Layer`
  diffusion and decay is the right shape. Exactness depends on SC4's kernel
  and rounding.
- **Level D (networks): graph yes, behavior unknown.** Reuse `Path`, and
  plug SC4 costs in through `IRouter`. Do not adopt `Agent` as SC4's commute
  model without evidence.
- **Level E (RCI, growth, region): SC4-specific.** OpenGlassBox has no
  demand model. Zone growth hooks can host one once it is measured.

So the smallest path is a **hybrid**: OpenGlassBox for the clock, world,
grid, graph, entities and scripting; SC4-specific modules (C++, in or next
to the helper) for each verified rule. Each module is gated by a TAX_001-style
reference → candidate → verifier pipeline.
