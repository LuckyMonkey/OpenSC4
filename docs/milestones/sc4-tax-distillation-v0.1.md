# SC4 tax-path distillation v0.1

This milestone records a local, memory-and-instruction-based investigation of
the user-owned SimCity 4 Deluxe executable. It does not use screenshots to
infer arithmetic and it does not copy executable bytes, saves, or raw memory
into the repository.

## Target and evidence boundary

| Field | Value |
| --- | --- |
| executable | `SimCity 4.exe` under the Steam Proton install |
| SHA-256 | `f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153` |
| format | PE32/x86; image base `0x00400000` |
| static tools | `strings`, `objdump` |
| runtime tool | read-only GDB inspection, plus one user-authorized live setter call |
| raw data retained | none |

Static addresses in this note are virtual addresses for this exact executable
and are not portable pointers. A live pointer must be rediscovered from the
process each session.

## Proven tax-rate storage and accessors

The statistics publisher at `0x00413a10` calls the live budget object through
its vtable. The rate loop passes indices `0..11` to the virtual slot at `+0x90`
and publishes the returned float directly to the named tax-rate statistics.
There is no percentage scaling in this publisher.

Runtime vtable resolution for the exact target found:

| Operation | Slot | Target | Instruction-derived behavior |
| --- | ---: | ---: | --- |
| tax income getter | `+0x4c` | `0x0068fd30` | returns the 64-bit field at `this+0x670` |
| tax-rate getter | `+0x90` | `0x0068fd50` | returns `float(this+0x70+index*0x80)` for `index < 12` |
| tax-rate setter | `+0x94` | `0x0068fd70` | stores the supplied float at that same indexed field |

The getter and setter disassembly is equivalent to:

```text
get_rate(this, index):
    if index >= 12:
        return *(float*)0x00a81054
    return *(float*)(this + 0x70 + index * 0x80)

set_rate(this, index, value):
    if index < 12:
        *(float*)(this + 0x70 + index * 0x80) = value
```

The setter has no lower-bound check. The lab must only issue indices `0..11`;
negative indices would be an out-of-bounds write and are forbidden.

## Live authorized cheat

Before the change, all twelve live rate fields read exactly `9.0`. The setter
was invoked for each valid category with `20.0`, then every field was read back:

```text
rate[0..11] = 20.0
```

This changed only the running process. The executable and city save were not
modified. Reloading or restarting the city is expected to restore the saved
rates unless the change is later made through the in-game budget UI and saved.

## Tax-income calculation boundary

The getter is only a published result, not the calculation. A writer at
`0x00692510` calls `0x00691e20` and stores its returned 64-bit value into
`this+0x670/0x674`. The calculation routine performs these proven operations:

1. Clear twelve 64-bit per-category accumulators at
   `this+0xe0 + index*0x80`.
2. Iterate the budget/tax records owned by the object.
3. Resolve each record to a category index through a static lookup table.
4. Read the category tax rate through the virtual getter at `+0x90`.
5. Read a category factor from `this+0x7c8 + index*4` and a second
   derived-index factor from the table at `this+0x7f8`.
6. Build a taxable amount using record/object virtual methods and fixed-point
   values, then convert it to an integer amount.
7. Multiply the amount by the derived-index factor, category factor, and
   retrieved tax rate.
8. Convert and accumulate the result into the per-category and total values.

The exact rate-bearing portion is therefore established as a real operation,
not a visual hypothesis:

```text
category_amount = integer_convert(
    taxable_base(record, budget_state)
    * table_factor[derived_index]
    * factor[index]
    * get_rate(budget, index)
)
```

The taxable-base subroutine is not yet fully named. Its dependencies include
virtual methods on the record and budget objects, lookup data near
`0x00ab0840`, factor data near `this+0x7c8` and `this+0x7f8`, and the
fixed-point conversion helper at `0x009eef04`. These are the next static
tracing targets.

## Runtime result and interpretation

After the live cheat, the tax-income field read `1024` (low word `0x400`, high
word zero) in two samples separated by 15 seconds. That unchanged value does
not disprove the change: the writer is on a simulation/budget schedule and the
current session was not shown to cross that update boundary through memory
evidence. No screenshot-derived number is used as a result here.

## Next discriminating work

1. Capture `this+0x670/0x674`, all twelve per-category totals at `+0xe0`, and
   the simulation-date candidate before and after a confirmed budget update.
2. Resolve the writer's call to `0x00691e20` and the helper at `0x009eef04`.
3. Map the category lookup and factor tables without exporting their raw bytes.
4. Run a controlled 9-to-20 and 20-to-9 experiment across one complete budget
   update, recording only normalized scalar observations.
5. Recreate the independently written rate-times-base rule in the SC4
   compatibility backend only after the held-out observation exists.

This milestone proves the rate storage, getter, setter, result field, and
rate-bearing multiplication boundary. It does not yet claim a complete tax
formula or budget equivalence.
