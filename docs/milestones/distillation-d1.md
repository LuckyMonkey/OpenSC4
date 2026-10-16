# Milestone: distillation machinery D1

## Outcome

The behavioral-distillation laboratory now has an executable, data-free path
from adapter protocol to normalized observation and independent comparison.
This validates the machinery only; it is not an SC4 observation or a claim of
simulation equivalence.

## Delivered

- Canonical [behavioral distillation protocol](../distillation.md).
- JSON-line adapter envelope with request IDs and structured errors.
- Synthetic sidecar implementing reset, validation, commands, advancement,
  snapshots, event cursors, save/load, and shutdown.
- Generic adapter probe that records a JSONL trace and normalized observation.
- Independent comparator with a separate fixed policy file.
- Explicit provenance marker: `reference_claim: false`.

## Test evidence

Positive protocol/comparator path:

```sh
python3 tools/probe_adapter.py \
    --adapter python3 sc4-lab/adapters/mock/synthetic_sidecar.py \
    --scenario sc4-lab/adapters/mock/protocol_smoke.json \
    --trace /tmp/opensc4-protocol-trace.jsonl \
    --observation /tmp/opensc4-protocol-observation.json
python3 sc4-lab/verifier/compare.py \
    --reference /tmp/opensc4-protocol-observation.json \
    --candidate /tmp/opensc4-protocol-observation.json \
    --tolerances sc4-lab/verifier/tolerances.v1.json \
    --report /tmp/opensc4-protocol-report.json
```

The comparator reported three exact metrics passing and two explicitly
unsupported. An intentional `generated_power` mismatch returned exit 1.
The Python adapters compiled and the existing synthetic backend/parser smoke
scenes passed.

## Boundary

The sidecar is synthetic and its output is not reference data. The SC4 adapter
is still unimplemented. The next real distillation task is a capability
inventory for controlled input and structured observation against the local
installation, followed by the first provenance-complete POWER_001 observation.
