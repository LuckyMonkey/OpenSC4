# SC4 budget telemetry v0.1

This milestone fixes the first live metric path that was being confused with a
UI cache. The probe reads only structured scalar fields from the user-owned
running process. It does not capture screenshots, raw memory, saves, or
executable bytes.

## Native budget paths

For the exact executable documented in the tax milestone, the live budget
object uses these vtable methods:

| Operation | Slot/target | Proven behavior |
| --- | --- | --- |
| funds getter | `+0x18` → `0x0068fd10` | returns signed 64-bit `this+0x28/+0x2c` |
| funds adder | `+0x1c` → `0x00690170` | adds signed 64-bit `(high:low)`, saturates, mirrors to `+0x30/+0x34`, and notifies |
| funds subtractor | `+0x20` → `0x00690200` | subtracts only when sufficient funds exist, then mirrors and notifies |
| tax income getter | `+0x4c` → `0x0068fd30` | returns signed 64-bit `this+0x670/+0x674` |
| tax-rate getter | `+0x90` → `0x0068fd50` | reads the twelve indexed rate fields |
| tax-rate setter | `+0x94` → `0x0068fd70` | stores a supplied rate for valid upper-bounded indices |
| category-total getter | `+0xe0` → `0x0068fde0` | reads signed 64-bit `this+0xe0+index*0x80` |

The funds adder is the correct reversible live cheat path because the native
method updates both balance copies and emits the game's funds-change event.
The probe itself never invokes it.

## Live recovery and stabilization

The read-only probe first found the city at §489,639, with tax income `660`
and live rates between `2.0` and `2.5`. A user-authorized native adjustment
then added §10,000,000 and restored all twelve rates to the normal `9.0`.
The immediate verified sample was:

```text
funds_public = 10,478,024
funds_working_candidate = 10,478,024
tax_income = 656
tax_rates = [9.0] * 12
tax_category_total_sum = 308,346
```

These are runtime observations, not committed reference fixtures.

## While-playing capture

`tools/sc4_budget_probe.py` followed the mapped image base to the budget global,
then emitted 45 structured samples over approximately 90 seconds. The probe
observed:

| Metric | First sample | Last sample |
| --- | ---: | ---: |
| funds | 10,470,504 | 10,466,637 |
| tax income | 2,682 | 2,599 |
| tax-category total sum | 298,050 | 288,842 |
| rates | 9.0 for all 12 | 9.0 for all 12 |

There was one observed funds transition and one tax transition in that window.
This proves the probe follows changing state; it does not yet establish the
monthly revenue formula or the exact simulation boundary that caused the
transition.

## Probe contract

Run a one-shot read:

```bash
python3 tools/sc4_budget_probe.py --pid <sc4-pid> --duration 0
```

Run a private while-playing capture:

```bash
python3 tools/sc4_budget_probe.py \
  --pid <sc4-pid> --duration 90 --interval 2 \
  --out /tmp/opensc4-budget-live.jsonl
```

The output schema is `sc4-lab.sc4-budget-observation.v1` and declares
`raw_bytes_recorded: false`. It omits the discovered heap pointer and stores
only the image base, the static global RVA, scalar metrics, and evidence text.

## Remaining work

1. Add an event/action marker to the JSONL capture so construction, pause, and
   budget-screen changes can be correlated with transitions.
2. Resolve the native monthly-income and monthly-expense getter dependencies
   into the same probe without invoking write-capable methods.
3. Pair a 9-to-20 rate change with the next confirmed tax-income transition.
4. Keep all live captures outside Git and add only normalized, independently
   authored observations after review.
