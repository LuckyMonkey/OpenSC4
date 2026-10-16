# SC4 system identification v0.1

Status: tooling complete; first paired live experiment pending.

## What is complete

- A read-only capture wrapper reuses the verified budget memory paths.
- Captures retain intervention metadata and a stable sample index.
- Raw process bytes and memory writes are explicitly disabled.
- Paired analysis calculates finite-difference sensitivity, discrete response
  derivative, response area, and first response sample.
- A plan command creates baseline/control/intervention run metadata without
  inventing reference observations.
- An aggregate command summarizes repeated paired analyses by intervention
  value, including variance and sign consistency.
- Optional starting-save metadata records hashes and chunk hashes only, never
  the save bytes.
- A guarded tax intervention operator can dry-run or explicitly invoke the
  already-verified native setter; it does not provide a category mapping and
  was not applied to the active city for this milestone.

## Evidence boundary

This milestone establishes a measurement instrument, not a recovered tax
function. The instrument currently observes authoritative budget fields already
documented in `sc4-budget-telemetry-v0.1.md`. It does not observe a verified
SC4 simulation month or tick, so current response curves are indexed by sample
and diagnostic wall-clock seconds.

The analysis deliberately reports `causation_claim: false` and
`equivalence_claim: false`. A tax intervention can be causally associated with
the paired response only after repeated same-state runs and held-out checks.

## Live baseline spot check

On the current Steam/Wine SC4 session, a read-only capture produced 16 samples
over approximately 30 seconds. All twelve rate fields remained `9.0`; funds
remained `10,466,637`; tax income remained `2,599`; and the category-total sum
remained `288,842`. This is a stability observation from the authoritative
budget paths, not a tax-response experiment. The capture is private at
`/tmp/opensc4-live-baseline-long.jsonl` and is not committed.

## First real experiment

Use a disposable copy of one city and run the planned 8%, 9%, 10%, and 12%
commercial-tax conditions. Record at least one baseline and one intervention
series with the native setter metadata. Do not alter the user's active city
without a recoverable save first.

The first acceptance target is narrower than “recover the tax formula”:

> Reproduce the direction, timing boundary, and magnitude range of one budget
> response on a held-out tax value while preserving the original reference
> observation.

## Known limitations

- The tax setter's rate field is verified, but the full taxable-base dependency
  is not.
- The capture process cannot infer simulation months from wall time.
- A single paired series is not enough to distinguish a direct tax effect from
  city-state feedback.
- Aggregation reduces run noise but does not create causation or recover the
  underlying implementation formula.
- The repository must not contain raw save files, executable bytes, memory
  dumps, or extracted proprietary assets.
