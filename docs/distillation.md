# Behavioral distillation protocol

## Purpose

Behavioral distillation reconstructs observable SimCity 4 behavior from
controlled experiments against a legitimately obtained local reference. It is
not source extraction, asset conversion, or a claim that an AI model exists
inside the original game. The target is an independently written simulation
that predicts observable outcomes under unseen inputs.

The practical target is Level 2 equivalence:

1. **Observable equivalence** — matching reported values, transitions, and
   spatial outcomes for controlled cases.
2. **Behavioral equivalence** — continuing to match interactions, failures,
   timing boundaries, and edge cases across extended runs.
3. **Internal equivalence** — only pursued when an internal detail is required
   to explain an observable result. It is not the default goal.

## What is being reconstructed

SC4 is treated as a conventional simulation with hidden state, update order,
fixed or semi-fixed schedules, data tables, rules, and randomness. We infer
behavior from:

- controlled inputs and named simulation times;
- structured statistics and state transitions;
- spatial maps or normalized occupancy where available;
- repeated runs and distributions when randomness is present;
- save-state deltas only when they can be observed without shipping original
  saves or extracted content.

Screenshots are useful for visual review, but they are weak evidence for exact
arithmetic. A screenshot-only claim is always marked approximate or unsupported.

## Observation depth ladder

Use the least invasive source that can answer the question:

1. structured game/UI output and controlled input logs;
2. save-file metadata, hashes, and changed chunk ranges;
3. existing parser-visible subfile values from a user-owned local save;
4. process status and mapped-region metadata for a user-owned process;
5. raw memory/core analysis only as a separately reviewed local experiment.

The repository may contain the tool and methodology for these levels, but not
raw saves, memory dumps, or extracted proprietary bytes. Save deltas identify
where to investigate; they do not establish the meaning of a field by
themselves.

## Roles and separation

The lab keeps four responsibilities separate:

| Role | May change | Must not change |
| --- | --- | --- |
| Reference adapter | local input/observation code | candidate code, verifier policy |
| Candidate adapter | OpenSC4/OpenGlassBox implementation | reference observations, tolerances |
| Verifier | comparison report | expected values or acceptance rules during a run |
| Challenger | held-out scenarios and edge probes | implementation and reference results |

An agent may propose hypotheses and experiments, but an implementation cannot
declare itself correct. The verifier consumes immutable observations and a
predeclared policy.

## Experiment lifecycle

```text
synthetic scenario
       |
       v
reference adapter -----> normalized observation ----+
       |                                             |
       +---- action/timing log ----------------------+
                                                     v
candidate adapter -----> normalized observation -> verifier -> report
                                                     |
                                                     v
                                      challenger creates held-out cases
```

Every experiment follows this order:

1. **Question** — state one behavior to distinguish, such as whether power
   output is capped before or after funding is applied.
2. **Scenario** — vary only the inputs needed to answer that question.
3. **Schedule** — name the exact sampling points: initial, month-end, event,
   or fixed tick count. Never equate an SC4 month with a candidate tick count
   without evidence.
4. **Reference run** — record version, local executable identity, actions,
   timing, seed status, observations, and uncertainty.
5. **Normalization** — convert both adapters to the same plain-data schema.
6. **Hypothesis** — write an independently worded rule with its assumptions.
7. **Candidate implementation** — implement only what the evidence supports.
8. **Verification** — compare held-in cases with fixed rules.
9. **Challenge** — run held-out boundary and interaction cases designed to
   falsify the hypothesis.
10. **Report** — classify behavior as verified, approximate, unsupported,
    contradicted, or still unknown.

## Experiment design

Start with the smallest discriminating matrix. For a power subsystem that
means one plant, then controlled demand, funding, multiple plants, and month
boundaries. Use boundary values such as zero, just below capacity, equal to
capacity, just above capacity, and maximum funding.

When two candidate formulas fit the same observations, choose the next test
that produces the largest difference between their predictions. This is active
experimental design, not blind test volume. Keep a hypothesis ledger:

```yaml
hypothesis_id: POWER_H001
question: funding scales available power before demand is capped
predictions:
  low_funding: <candidate prediction>
  over_capacity: <candidate prediction>
discriminating_scenario: POWER_002
status: proposed
```

For randomness, repeat the exact scenario with controlled and uncontrolled
seeds where possible. Compare exact values only when replay is deterministic;
otherwise compare distributions with a fixed statistical rule declared before
the candidate run.

## Provenance and data boundary

Each accepted observation needs:

- schema and test ID;
- scenario hash;
- original executable/build identifier;
- observation method and adapter version;
- sampling schedule and seed status;
- timestamp and uncertainty;
- a content hash of the normalized observation.

The repository may contain synthetic scenarios, schemas, specifications,
verifier code, and data-free protocol fixtures. It must not contain EA
executables, DLLs, DATs, original `.sc4` saves, extracted assets, or screenshots
that retain protected game content. Local reference outputs stay outside Git
unless separately reviewed and proven safe to publish.

## Acceptance language

Use precise labels:

- **verified** — matched an immutable observation under a declared rule;
- **approximate** — visually or numerically close, but not proven equivalent;
- **unsupported** — the reference metric cannot currently be observed reliably;
- **contradicted** — a held-out observation disproved the implementation;
- **unknown** — not yet investigated.

Never summarize the project with one compatibility percentage. Report status by
subsystem and retain failed experiments as useful evidence.

## Current distillation milestones

- **D0 complete:** plain-data backend seam, event cursors, save schemas, and
  JSON-line adapter protocol.
- **D1 complete:** data-free protocol adapter, recorder, and comparator
  fixtures. These prove the laboratory machinery only; they are not SC4 data.
- **D2 tooling complete:** local save/process capture tooling is ready; the
  capability inventory and first real SC4 capture remain open because no live
  process or `.sc4` save is currently available in the workspace.
- **D3 later:** POWER_001 through POWER_004 reference corpus, then held-out
  candidate evaluation.

The implementation must remain honest about this boundary: synthetic protocol
success demonstrates transport and comparison correctness, not SC4 equivalence.
