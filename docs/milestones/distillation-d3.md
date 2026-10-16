# Milestone: dynamic memory observatory D3

## Outcome

OpenSC4 now has a read-only dynamic memory observation layer for the next stage
of SC4 behavioral distillation.

## Delivered

- User-owned readable-region inspection.
- Typed `u32`, `i32`, `u64`, `i64`, `f32`, and `f64` value scanning.
- Hashed differential snapshots with no raw bytes persisted.
- Explicit-address sampling over time.
- Current-user and region-permission guardrails.
- A synthetic child-process self-test that validates scanning, changed values,
  and changed-region detection.
- [Memory observatory runbook](../runbooks/memory-observatory.md).

## Test evidence

```sh
python3 tools/memory_observatory.py self-test
```

Result: `MEMORY OBSERVATORY SELF-TEST PASS`.

The self-test is intentionally synthetic. No SC4 process was running and no
`.sc4` save was available in the workspace, so no SC4 address or value has been
claimed.

## Next experiment

Run the observatory against a disposable SC4 city under Wine, beginning with a
pause/control snapshot and a displayed treasury or simulation-date value. Keep
the candidate list, snapshots, and diff reports local; accept a field only
after repeated changes, pause behavior, reload behavior, and restart
rediscovery agree.
