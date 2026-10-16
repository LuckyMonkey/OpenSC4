# SC4 Behavioral Compatibility Lab

This document defines the experimental boundary for reconstructing observable
SimCity 4 behavior in OpenSC4. It is an engineering protocol, not a claim
that OpenSC4 currently matches the original simulation.

## Goals and boundaries

The lab uses a legitimately installed copy of SimCity 4 as a local reference
and OpenSC4 as the independently implemented candidate. It records inputs,
observable outputs, timing, and uncertainty. It does not copy EA source code,
executables, assets, save files, or extracted proprietary data into this
repository.

The first milestone is power generation and consumption under controlled
conditions. Transportation, zoning, growth, taxes, pollution, and municipal
accounting stay out of the acceptance set until the reference adapter and
comparator are working.

## Architecture

```text
scenario -> reference adapter -> normalized observation --+
                                                        +-> independent verifier
scenario -> candidate adapter -> normalized observation -+       |
                                                                  +-> report
```

The reference adapter runs locally against the user's installation. The
candidate adapter runs OpenSC4's selected simulation backend. Neither adapter
may write reference observations or alter verifier tolerances.

The long-term simulation boundary is:

```text
OpenSC4 renderer/UI
        |
   Simulation API
      /       \
SC4-compatible  modern backend
   backend      backend
```

OpenGlassBox should be integrated behind this boundary, not copied into the
Godot/GDScript tree. Its current C++ library is a reasonable experimental
backend, but it needs a narrow Godot bridge (preferably a GDExtension) for
state snapshots, commands, events, lifecycle, and save-versioning. A JSON
sidecar is acceptable for early experiments but should not become the runtime
architecture.

## Repository roles

The `sc4-lab/` directory is deliberately data-free:

```text
sc4-lab/
├── reference/
│   ├── scenarios/       # synthetic inputs and manifests only
│   ├── observations/    # immutable local outputs; never committed by default
│   └── manifests/       # executable/version/hash metadata
├── specifications/     # independently written behavioral claims
├── adapters/
│   ├── sc4/             # local reference runner; no shipped game files
│   └── openglassbox/    # candidate/backend adapter
├── verifier/            # comparison rules and fixed tolerances
├── reports/             # generated summaries
└── candidate/           # implementation work, separate from reference data
```

Reference observations must include the original executable version, scenario
hash, run timestamp, sampling schedule, and uncertainty. Once accepted, an
observation manifest is content-addressed and treated as read-only. New
experiments go into a held-out set before candidate changes are evaluated.

## Scenario contract

Scenarios describe only synthetic inputs and actions. They must not embed an
original `.sc4` save or extracted game resource. A minimal power experiment
will eventually look like this, with values filled by the reference adapter:

```yaml
schema: sc4-lab.scenario.v1
test_id: POWER_001
status: draft
initial_city:
  size: small
  population: 0
  buildings:
    - kind: coal_power_plant
actions:
  - run_months: 1
  - sample_metrics: true
  - run_months: 11
  - sample_metrics: true
metrics:
  - generated_power
  - electricity_demand
  - operating_cost
  - plant_condition
  - pollution
```

`status: draft` is intentional: this repository does not yet contain
reference results for this scenario.

## Comparison rules

The verifier must classify each metric as one of:

- `exact`: deterministic value or state transition;
- `tolerance`: numeric error with a fixed, predeclared bound;
- `distribution`: repeated-run comparison for stochastic behavior;
- `spatial`: normalized map or occupancy comparison.

The candidate is never allowed to change the acceptance rule for a failing
test. A matching population total is insufficient if the building transitions,
power state, or spatial result disagree.

Simulation time must be sampled at named events (for example, month-end) and
also record the candidate tick count. One SC4 month must not be assumed to
equal an arbitrary number of OpenGlassBox ticks.

## Work sequence

1. Define the adapter and observation schemas.
2. Identify a reliable, legal way to drive and observe the local SC4 reference.
3. Record a small deterministic power corpus; do not infer missing values.
4. Implement the candidate power model behind the simulation API.
5. Compare held-in and held-out scenarios with fixed tolerances.
6. Add experiments that distinguish competing formulas or update schedules.
7. Report verified, approximate, unsupported, and regressed behavior by subsystem.

The practical compatibility target is Level 2: equivalent behavior over
extended controlled scenarios and edge cases. Exact internal reconstruction is
not required unless an observable result depends on it.

## Legal and provenance rules

Run reference experiments locally using the user's own installation. Keep
proprietary assets and original saves outside version control. Publish only
synthetic scenarios, observations that do not contain protected game data, and
independently written specifications. Preserve OpenSC4's AGPL obligations and
review the dependency terms before distributing any OpenGlassBox bridge.
