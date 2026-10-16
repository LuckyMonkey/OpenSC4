# Runbook: reference experiment lifecycle

## Safety and provenance

Use only a legitimately obtained local SC4 installation. Keep the executable,
DLLs, original saves, DBPF archives, extracted assets, and screenshots that
contain protected game content outside Git. Do not bypass DRM or authentication.

The lab records behavior, not copied implementation. If an observation cannot
be obtained through an allowed, repeatable path, record `unsupported` and the
reason.

## Scenario lifecycle

1. Create a synthetic scenario manifest with `status: draft`.
2. Hash the manifest and record the local game-version identifier.
3. Run the reference adapter with a named sampling schedule.
4. Store raw observations outside the candidate tree; normalize into a
   data-only observation format.
5. Review uncertainty and mark the observation immutable.
6. Put a new case into the held-out set before exposing its result to a model
   or implementation agent.
7. Run the candidate adapter and independent verifier.
8. Publish a report stating exact, tolerance, distribution, spatial, or
   unsupported comparison status.

## Start with the data-free protocol fixture

Before a local SC4 adapter exists, exercise the transport and recorder with
the synthetic sidecar:

```sh
python3 tools/probe_adapter.py \
    --adapter python3 sc4-lab/adapters/mock/synthetic_sidecar.py \
    --scenario sc4-lab/adapters/mock/protocol_smoke.json \
    --trace /tmp/opensc4-protocol-trace.jsonl \
    --observation /tmp/opensc4-protocol-observation.json
```

This proves only JSON envelopes, command validation, event cursors,
save/load, and observation recording. It does not run SC4 or create reference
results.

## Capture a local SC4 save transition

Use the metadata capture tool around one controlled action, such as changing a
budget slider and saving. It records hashes and changed fixed-size chunk ranges,
never the original save bytes:

```sh
python3 tools/reference_capture.py snapshot \
    --save "/path/to/user-owned/Regions/Region/City - Test.sc4" \
    --phase before-action --out /tmp/sc4-before.json

# Perform exactly one action in SC4, save, and close/save again.

python3 tools/reference_capture.py snapshot \
    --save "/path/to/user-owned/Regions/Region/City - Test.sc4" \
    --phase after-action --out /tmp/sc4-after.json
python3 tools/reference_capture.py diff \
    --before /tmp/sc4-before.json --after /tmp/sc4-after.json \
    --out /tmp/sc4-save-diff.json
```

For a live user-owned process, add `--pid PID --include-maps` to capture
process status and mapped-region metadata. This tool deliberately does not
read `/proc/PID/mem` or create a raw memory dump. Escalate to OS core-dump
tooling only as a separately reviewed, local-only experiment.

To watch for saves during a short manual experiment:

```sh
python3 tools/reference_capture.py watch \
    --save "/path/to/user-owned/Regions/Region/City - Test.sc4" \
    --duration 120 --interval 1 --out /tmp/sc4-watch.jsonl
```

Treat changed ranges as leads, not decoded game logic. Correlate them with
structured parser observations and repeated controlled actions before writing a
behavioral specification.

## First power corpus

The minimum useful sequence is:

1. one plant and near-zero demand;
2. one plant with demand changed at a known month;
3. funding changed while demand is held constant;
4. two plants with different funding or operating conditions;
5. repeated runs with the same and different seeds, if controllable.

Capture generated power, demand, cost, condition, pollution, simulation time,
and any uncertainty. Do not infer hidden values from a screenshot.

## Acceptance discipline

Reference observations, tolerances, and verifier code are separate from the
candidate implementation. A candidate failure may cause a new experiment or a
new specification; it may not silently relax the acceptance rule.
