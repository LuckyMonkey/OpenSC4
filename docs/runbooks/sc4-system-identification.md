# SC4 system-identification runbook

This runbook turns verified SC4 memory telemetry into controlled response
measurements. It is for the local, user-owned reference installation only.
The capture tool is read-only; it does not write process memory, invoke game
functions, alter saves, or upload data.

## Current milestone

`tools/sc4_system_id.py` provides five operations (plus `self-test`):

- `plan`: create a factor plan without fabricating observations;
- `capture`: record a live budget series using the verified budget probe;
  pass `--with-clock` to require and include the native date candidate;
- `analyze`: pair two series by sample index and calculate finite-difference
  sensitivities, discrete response derivatives, and response area;
- `aggregate`: combine repeated paired analyses by intervention value and
  report replicate variance and sign consistency;
- `boundaries`: on one `--with-clock` series, list date-serial steps, month
  and year rollovers, paused (stationary) runs, and whether each budget-field
  change landed on a date step, a month rollover, or off-boundary.

The current telemetry exposes funds, tax income, tax rates, and tax category
totals. `tools/sc4_clock_probe.py` now exposes a native simulation-date
candidate and its recovered integer calendar conversion. The date candidate is
not yet promoted to shared budget timing: no simulation tick/update counter or
budget-boundary equivalence has been verified. Wall-clock time remains
diagnostic only.

## 1. Make a plan

```bash
python3 tools/sc4_system_id.py plan \
  --experiment-id TAX_COMMERCIAL_STEP_001 \
  --question "Does a commercial tax step change tax income immediately?" \
  --input-field commercial_tax_rate \
  --input-unit percent \
  --baseline-value 9 \
  --values 8 9 10 12 \
  --duration 180 \
  --interval 2 \
  --metric tax_income \
  --metric tax_category_total_sum \
  --out /tmp/sc4-tax-plan.json
```

The plan is metadata only. Every run must begin from the same disposable save
snapshot. Restoring a tax rate after a run does not restore the city state.

## 2. Capture the native date candidate

Use the clock probe alongside the budget probe. It reads the clock service and
embedded date object through a version-specific, read-only native path:

```bash
pid=$(pgrep -n -f 'S:\\steamapps\\common\\SimCity 4 Deluxe\\Apps\\SimCity 4.exe')
python3 tools/sc4_clock_probe.py \
  --pid "$pid" \
  --duration 180 \
  --interval 2 \
  --out /tmp/sc4-clock-series.jsonl
```

The result records `simulation_date_serial`, `simulation_year`,
`simulation_month`, and `simulation_day`, plus native resolution evidence.
It does not write memory, call a game function, or read screenshots. Treat the
date as `runtime-candidate` until it survives save/reload, process restart,
and one observed transition. See
`docs/milestones/sc4-clock-distillation-v0.1.md` for the exact native path.

## 3. Capture a read-only series

Find the live process without changing it:

```bash
pgrep -af 'SimCity 4.exe'
```

Capture a baseline and an intervention run separately. The intervention
metadata records what the operator changed through a valid game/native setter;
the capture itself does not apply the change.

For a controlled tax-rate step, first inspect the current fields with the
guarded operator in dry-run mode:

```bash
python3 tools/sc4_tax_intervention.py \
  --pid <PID> --index <0-11> --value 10 \
  --out /tmp/sc4-tax-intervention-plan.json
```

The operator resolves the current budget pointer and setter address on every
run. It refuses out-of-range indices/rates and refuses to invoke GDB unless
both `--apply` and `--ack-runtime-write` are present. Applying it changes only
the running process; it does not save the city. The category mapping is not
assumed, so an index must not be called “commercial” until separately proven.

```bash
python3 tools/sc4_system_id.py capture \
  --pid <PID> \
  --experiment-id TAX_COMMERCIAL_STEP_001 \
  --run-id baseline-9 \
  --phase baseline \
  --input-field commercial_tax_rate \
  --input-before 9 --input-after 9 --input-unit percent \
  --application native_setter \
  --save /path/to/disposable-city.sc4 \
  --duration 180 --interval 2 \
  --out /tmp/sc4-tax-baseline.jsonl
```

For a 10% run, use a new disposable copy of the same starting save and record
`--input-before 9 --input-after 10`. Keep the original save untouched.

The JSON Lines output contains no raw memory bytes. Each record retains process
identity, executable image base, budget-probe evidence, intervention metadata,
sample index, structured metrics, and (when `--save` is supplied) only the
starting save's hash/chunk metadata. Keep live reference output outside Git.

For a timing-aware capture, add `--with-clock`. This merges the native date
candidate into each structured sample and fails closed if the clock path cannot
be resolved:

```bash
python3 tools/sc4_system_id.py capture \
  --pid <PID> \
  --experiment-id CLOCK_BUDGET_ALIGNMENT_001 \
  --phase baseline \
  --with-clock \
  --duration 60 --interval 2 \
  --out /tmp/sc4-clock-budget-series.jsonl
```

## 4. Analyze a paired response

```bash
python3 tools/sc4_system_id.py analyze \
  --baseline /tmp/sc4-tax-baseline.jsonl \
  --experiment /tmp/sc4-tax-10.jsonl \
  --metric tax_income \
  --metric tax_category_total_sum \
  --out /tmp/sc4-tax-10-analysis.json
```

For each metric, the report contains:

- paired experiment-minus-control deltas;
- finite-difference sensitivity `Δoutput / Δinput`;
- a discrete derivative over the diagnostic wall-clock axis;
- trapezoidal area under the paired response;
- first observed nonzero paired delta;
- baseline and experiment summary statistics.

These are measurements, not recovered SC4 source formulas. A derivative is a
description of the sampled response, not proof that SC4 uses calculus or a
continuous function internally.

## 5. Aggregate repeated runs

Repeat the same paired experiment from independent copies of the same starting
save, then aggregate the private analysis outputs:

```bash
python3 tools/sc4_system_id.py aggregate \
  --analysis /tmp/tax-10-run-a.json \
  --analysis /tmp/tax-10-run-b.json \
  --analysis /tmp/tax-12-run-a.json \
  --metric tax_income \
  --metric tax_category_total_sum \
  --out /tmp/sc4-tax-replicates.json
```

The aggregate groups by intervention value and reports final sensitivity,
paired delta, response-by-sample summaries, replicate count, and whether the
direction was consistent. Mixed signs or high variance are evidence to design
another experiment, not permission to fit a stronger formula.

## 6. Promotion rules

Do not promote a fitted curve or correlation to a behavioral rule until:

1. the reference and experiment start from the same save hash;
2. the input was applied through a verified setter or a separately validated
   memory intervention;
3. the native date candidate is present for alignment, or the result is
   explicitly kept as a wall-clock diagnostic;
4. the response repeats across independent runs;
5. a held-out input value distinguishes the proposed model from alternatives;
6. the normalized observation and executable identity are preserved privately;
7. an independently written OpenGlassBox implementation passes the held-out
   comparison without changing the reference or verifier policy.

## Current edge problems

- The clock probe has a native date candidate but no verified simulation tick,
  so sample alignment can still be affected by speed, pause state, and
  asynchronous accounting.
- Tax category totals are observed aggregates; the taxable-base formula is
  still unresolved.
- A native setter is stronger evidence than a direct field write because it
  may update caches and publish notifications. Direct writes remain disabled in
  this tool.
- A tax response may include city-state feedback. A paired run measures the
  response, but does not isolate a causal subsystem by itself.
- One process session is not enough to establish restart or save/reload
  stability.

## Date-boundary promotion run

Covers promotion-gate items 1 (pause → run → pause) and 4 (date transition
correlated with the budget probe) from `docs/milestones/sc4-clock-distillation-v0.1.md`.
Use a disposable city. Start the capture paused, unpause at fastest speed for
at least two in-game month ends, then pause again before the capture ends:

```bash
pid=$(pgrep -n -f 'SimCity 4.exe')
python3 tools/sc4_system_id.py capture --pid "$pid" --with-clock \
  --experiment-id date-boundary --phase baseline \
  --duration 240 --interval 0.5 --out /tmp/opensc4-date-boundary.jsonl
python3 tools/sc4_system_id.py boundaries \
  --series /tmp/opensc4-date-boundary.jsonl --out /tmp/opensc4-date-boundary.json
```

The summary prints `gate_checks`. All five should be `true`; the
`per_metric` block then shows whether `funds_public`/`tax_income` change only
on month rollovers (expected monthly budget pass) or also off-boundary.
Check the analysis with `python3 tools/sc4_system_id.py self-test`.

## Next implementation milestones

1. Validate the native date candidate across pause/run, save/reload, and
   process restart; keep the tick field separate until it is found.
2. Add save identity and starting-state hashes to the capture manifest without
   copying the save into the repository.
3. Add a native tax-setter operator behind an explicit, disposable-city command
   and an allowlist; keep capture read-only.
4. Add a multi-run aggregator that estimates mean response and variance.
5. Recover one non-budget output, preferably commercial demand, and extend the
   sensitivity matrix.
6. Add a held-out model ledger for linear, exponential, threshold, and
   piecewise candidates.
