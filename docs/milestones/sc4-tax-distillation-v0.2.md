# SC4 tax-path distillation v0.2

Snapshot: 2026-10-17. This is static native evidence for the exact local
SimCity 4 executable identified by the v0.1 note. It is not a complete tax
formula and it is not an implementation claim.

## Target identity

- executable: `SimCity 4.exe` under the user-owned Steam/Proton install;
- architecture: PE32/x86;
- target SHA-256: `f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153`;
- primary calculation boundary: virtual address `0x00691e20`;
- conversion helper: virtual address `0x009eef04`.

All addresses are image virtual addresses for this executable and must be
rediscovered for another binary or version.

## Newly confirmed operations

The routine at `0x00691e20` performs these operations in the observed order:

1. Clears twelve 64-bit values at `budget + 0xe0 + index * 0x80`.
2. Initializes a floating-point accumulator and walks a budget-owned record
   container through its iterator/vtable methods.
3. For each eligible record, resolves a signed 16-bit category index through a
   table rooted near `0x00ab0840`; `0xffff` skips the record.
4. Calls the rate getter at the budget vtable slot `+0x90` with that category
   index.
5. Reads a category factor at `budget + 0x7c8 + index * 4`.
6. Calls record/object virtual methods to obtain the record's taxable inputs and
   derived indices. One lookup uses a table rooted near `budget + 0x7f8`.
7. Builds a 64-bit intermediate value from the record inputs and fixed-point
   adjustments, converts it to an integer through `0x009eef04`, and retains the
   returned `EDX:EAX` pair.
8. Converts that integer back to x87 floating point, multiplies by another
   index-selected table rooted at `budget + 0x814`, and multiplies by the tax
   rate returned in step 4.
9. Converts/accumulates the result into the category total at `+0xe0` and a
   floating-point total accumulator. A global constant near `0x00ab08b8` also
   participates in the per-record path.
10. After iteration, converts the floating category accumulators back to twelve
    64-bit values and returns the total pair consumed by the tax-income writer.

The rate-bearing portion is therefore better represented as:

```text
category = lookup(record)
rate = get_rate(budget, category)
base_i64 = convert_x87_to_i64(record_inputs, fixed_point_adjustments)
indexed_base = float(base_i64) * factor_7f8(derived_index)
indexed_base = indexed_base * factor_7c8(category)
amount = indexed_base * factor_814(second_derived_index) * rate
category_total[category] += convert(amount)
```

This pseudocode names only operations visible in the instruction trace. It does
not assign economic meanings to the three factor tables or the virtual methods.

## Conversion helper boundary

`0x009eef04` accepts an x87 value and returns a signed 64-bit result in
`EDX:EAX`. The trace shows an x87 `fistp` into a temporary 64-bit slot, reloads
that integer with `fild`, compares the residual against the original stored
single-precision value, and applies a sign-aware correction path. Exact behavior
for negative values, overflow, NaNs, and the process x87 rounding mode remains
unverified; the lab must not replace it with a language default cast without a
held-out numeric probe.

## What this rules out

- The category total is not simply `taxable_base * rate`.
- The published `tax_income` field is not the calculation entry point.
- A screenshot-derived tax graph cannot identify the table factors or the
  record-level virtual methods.
- The static trace alone does not reveal the table contents or the runtime
  category mapping.

## Next discriminating run

The next live capture should hold the city state constant, alter exactly one
validated rate, and sample at the first confirmed writer boundary. Record:

- all twelve rates;
- all twelve category totals at `budget + 0xe0 + index * 0x80`;
- the total at `budget + 0x670`;
- the process image base and budget pointer for that session;
- the candidate simulation/date field, if available.

The first model to implement independently should reproduce only the observed
rate multiplier while leaving `base_i64` and factor tables as explicit unknown
inputs. Do not promote a full tax equation until the 8%, 9%, 10%, and 12%
held-out runs distinguish the candidate factors and update boundary.
