# SC4 system-identification runbook

This runbook turns verified SC4 memory telemetry into controlled response
measurements. It is for the local, user-owned reference installation only.
The capture tool is read-only; it does not write process memory, invoke game
functions, alter saves, or upload data.

## Current milestone

`tools/sc4_system_id.py` provides three operations:

- `plan`: create a factor plan without fabricating observations;
- `capture`: record a live budget series using the verified budget probe;
- `analyze`: pair two series by sample index and calculate finite-difference
  sensitivities, discrete response derivatives, and response area.

The current telemetry exposes funds, tax income, tax rates, and tax category
totals. It does not yet expose a verified simulation month or tick. Until that
field is recovered, wall-clock time is diagnostic only and no result may be
described as a month-by-month SC4 response.

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

## 2. Capture a read-only series

Find the live process without changing it:

```bash
pgrep -af 'SimCity 4.exe'
```

Capture a baseline and an intervention run separately. The intervention
metadata records what the operator changed through a valid game/native setter;
the capture itself does not apply the change.

```bash
python3 tools/sc4_system_id.py capture \
  --pid <PID> \
  --experiment-id TAX_COMMERCIAL_STEP_001 \
  --run-id baseline-9 \
  --phase baseline \
  --input-field commercial_tax_rate \
  --input-before 9 --input-after 9 --input-unit percent \
  --application native_setter \
  --duration 180 --interval 2 \
  --out /tmp/sc4-tax-baseline.jsonl
```

For a 10% run, use a new disposable copy of the same starting save and record
`--input-before 9 --input-after 10`. Keep the original save untouched.

The JSON Lines output contains no raw memory bytes. Each record retains process
identity, executable image base, budget-probe evidence, intervention metadata,
sample index, and structured metrics. Keep live reference output outside Git.

## 3. Analyze a paired response

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

## 4. Promotion rules

Do not promote a fitted curve or correlation to a behavioral rule until:

1. the reference and experiment start from the same save hash;
2. the input was applied through a verified setter or a separately validated
   memory intervention;
3. the simulation-time axis is recovered, or the result is explicitly kept as
   a wall-clock diagnostic;
4. the response repeats across independent runs;
5. a held-out input value distinguishes the proposed model from alternatives;
6. the normalized observation and executable identity are preserved privately;
7. an independently written OpenGlassBox implementation passes the held-out
   comparison without changing the reference or verifier policy.

## Current edge problems

- The budget probe has no verified simulation date/tick, so sample alignment
  can be affected by speed, pause state, and asynchronous accounting.
- Tax category totals are observed aggregates; the taxable-base formula is
  still unresolved.
- A native setter is stronger evidence than a direct field write because it
  may update caches and publish notifications. Direct writes remain disabled in
  this tool.
- A tax response may include city-state feedback. A paired run measures the
  response, but does not isolate a causal subsystem by itself.
- One process session is not enough to establish restart or save/reload
  stability.

## Next implementation milestones

1. Add the verified simulation-date/tick field to the budget observation schema.
2. Add save identity and starting-state hashes to the capture manifest without
   copying the save into the repository.
3. Add a native tax-setter operator behind an explicit, disposable-city command
   and an allowlist; keep capture read-only.
4. Add a multi-run aggregator that estimates mean response and variance.
5. Recover one non-budget output, preferably commercial demand, and extend the
   sensitivity matrix.
6. Add a held-out model ledger for linear, exponential, threshold, and
   piecewise candidates.
