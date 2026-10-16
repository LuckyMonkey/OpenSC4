# REA native candidate milestone v0.2

Status: partial — provider healthy, native bridge timeout recorded, static
candidate ledger available.

## Observed

- REA doctor reports Ghidra 12.1.4 and Temurin JDK 21.0.12 as healthy on Linux
  x64.
- REA native `analyze`, `search`, and focused `function` requests against the
  LAA SC4 PE all reached the 330-second provider timeout. The failure occurred
  during Ghidra analysis/bridge startup at the same unresolved legacy callback;
  it is not a conclusion about SC4 behavior.
- Independent static inspection of the same executable found named strings for
  `SimulationClock`, `GetSimulationDate`, `EnableSimulation`, `LoadCity`,
  `SaveCity`, power counters, water counters, and city population counters.
- Static code references place a cluster of power-counter key emissions in a
  routine beginning near `0x00421030`. The routine repeatedly converts integer
  results to floating point and passes them with named keys such as
  `g_power_plant_count` and per-type plant-count keys.

## Interpretation boundary

The `0x00421030` cluster is a strong telemetry/statistics candidate, not yet a
simulation writer. It may read cached aggregates or publish UI/debug values.
No runtime execution, memory write, save correlation, or REA function dossier
has verified it.

## Added capability

`tools/sc4_static_candidates.py` creates a private JSON ledger from `strings`
and `objdump`. It records target identity, selected string offsets/addresses,
and static references while refusing to persist raw executable bytes.

## Next step

Use the candidate ledger to avoid broad REA enumeration: investigate the
smallest relevant caller/callee around `0x00421030`, then correlate one named
metric with a live SC4 process and a before/after save. If the REA bridge still
times out, retain the exact failure and use a separately reviewed direct
Ghidra script only for address discovery.
