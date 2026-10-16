# Reference observation schema

This schema describes data that an adapter may emit. It does not contain SC4
results. A missing or unobservable metric must be represented as `unsupported`,
not guessed.

## Manifest

```yaml
schema: sc4-lab.manifest.v1
test_id: POWER_001
scenario_sha256: <hash of synthetic scenario>
reference:
  executable_id: <local version/build identifier>
  install_path: local-only
  asset_files_tracked: false
  observation_method: <documented method>
run:
  started_utc: <timestamp>
  seed: unknown
  sampling_schedule: month_end
  uncertainty: <description>
status: draft
```

The install path is metadata only and must never be a repository fixture.

## Observation record

```yaml
schema: sc4-lab.observation.v1
test_id: POWER_001
sample:
  simulation_month: 1
  simulation_tick: unknown
metrics:
  generated_power: {status: unsupported, value: null, unit: unknown}
  electricity_demand: {status: unsupported, value: null, unit: unknown}
  operating_cost: {status: unsupported, value: null, unit: unknown}
  plant_condition: {status: unsupported, value: null, unit: unknown}
  pollution: {status: unsupported, value: null, unit: unknown}
```

Allowed metric statuses are `observed`, `unsupported`, `uncertain`, and
`not_applicable`. Observed values must include units and, when needed, a
confidence/uncertainty note.

Adapters may serialize the same record as JSON for the sidecar and verifier.
The JSON object shape is identical to the YAML examples above; the comparator
is `sc4-lab/verifier/compare.py` and its policy is kept separately from both
adapters.

## Candidate comparison

Candidate output uses the same metric names and adds `backend_id`. The verifier
must compare only metrics whose reference status permits comparison. It must
never promote `unsupported` to a passing value.
