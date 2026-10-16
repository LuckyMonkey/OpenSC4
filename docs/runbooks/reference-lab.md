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
