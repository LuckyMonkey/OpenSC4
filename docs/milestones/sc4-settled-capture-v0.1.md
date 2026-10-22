# Settled SC4 capture and replay v0.1

Implemented 2026-10-22; live validation pending.

## Milestone 1: coherent, delayed ride observations

`tools/sc4_ride.py` freezes the process while reading budget, clock, and the
current multiplier. It waits `--settle-days` game days (default 3) after an
observed consecutive month transition before emitting a month row. The first
partial month is omitted. Funds deltas compare consecutive settled observations,
not the last sample before rollover. The first settled row has null funds delta
and expenses; these are also null after a sampling discontinuity.

Samples retain their multiplier, and ride metadata identifies the sampling
schema and frozen reads. Existing rate interventions and optional dumps remain
part of this tool; running it changes the live game's rates.

## Milestone 2: shared, gap-aware replay

`tools/sc4_month_sampling.py` supplies selection to capture and offline replay.
It handles December/January, emits once per month, and starts a new segment on
skipped months or a backwards date. Replay rejects nonconsecutive settled
months and segment changes before starting the sidecar, so an open-loop funds
comparison cannot silently treat several months as one. New samples supply
their own multiplier; historical samples fall back to ride metadata.

## Verification and limits

After both implementations were complete, synthetic checks passed for delay,
year rollover, duplicate suppression, skipped months, same-month rewind,
error rows, and invalid delay. Python compilation and `git diff --check` passed.
No retail game, Godot, or OpenGlassBox process was launched for this change.

A freeze prevents reads from interleaving with writes; it can still stop an
update halfway through. The settling delay reduces that risk but is not proof
of an atomic budget publication. Same-date reloads are not detectable from
calendar telemetry. Expenses derived from funds still include one-off spending
or other income. Historical unfrozen samples cannot be made coherent retroactively.

For a manual live check, capture at least three month transitions in a disposable
city with no spending, then compare the ride's settled rows with offline replay:

```bash
python3 tools/sc4_ride.py --pid PID --rates 9 --hours 0.1 --dump-every 0 --settle-days 3
python3 tools/sc4_ogb_compare.py /path/to/ride --settle-days 3
```

Expected: one row per settled observed month, initial null funds delta, subsequent
consecutive settled-month deltas, and no rollover-only zero-delta artifacts.
Tax agreement and expense stability still require live evidence.
