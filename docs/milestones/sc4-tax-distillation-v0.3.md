# SC4 tax distillation v0.3: monthly tax-income equation

Date: 2026-10-17. Executable SHA-256
`f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153`
(Steam SimCity 4 Deluxe, `Apps/SimCity 4.exe`). All addresses are image
virtual addresses for this binary only.

## Result

```text
k                = difficulty_object(+0x28)          ; getter 0x60fb80, observed 2
monthly_tax      = trunc( Σ_cat base[cat] * mult[k] * rate[cat] * (1/1200) )
base[cat]        = int64 at budget + 0xE0 + cat*0x80 ; "tax_category_totals"
rate[cat]        = float at budget + 0x70 + cat*0x80 ; percent
mult             = float[3] at *(budget + 0x814)     ; observed [1.2, 1.1, 1.0]
default_rate     = float[3] at *(budget + 0x820)     ; observed [9, 9, 9]
```

`1/1200` is percent → fraction (÷100) times one month of an annual amount
(÷12): the bases are annual taxable values, charged monthly.

## Evidence

### Observational fit (three months, one city, k = 2)

| Month | Σ rate×base | ÷1200 | observed `tax_income` |
| --- | --- | --- | --- |
| 2006-09 | 2,934,287 | 2445.24 | 2445 |
| 2006-10 | 3,001,291 | 2501.08 | 2501 |
| 2006-11 | 3,000,724 | 2500.60 | 2500 |

Truncating each category before summing gives 2498 for November, not 2500,
so the published value is one truncation of the floating-point total.

### Static confirmation

- `1/1200f` exists once in `.rdata` (`0x00ab08b8`) and is used by exactly two
  instructions:
  - `0x006904c0` — per-category monthly tax:
    `ftol((double)base[cat] * mult[k] * rate[cat] * (1/1200))`, `thiscall`
    on the budget object, category as the only stack argument.
  - `0x00692054` — the tail of the base-building loop at `0x00691e20`
    (see v0.2). Per record it adds the **pre-rate** integer to `base[cat]`
    and adds `value * mult[k] * rate * (1/1200)` to a floating accumulator.
    This corrects v0.2 step 9: `+0xE0` holds the untaxed base.
- `0x00690490` copies `default_rate[k]` into all twelve rate slots.
- `0x0060fb80` is `return this->[+0x28]`; its owner is `budget->[+0x18]`.
- The three tables having exactly three entries matches SC4's three
  difficulty levels. That `k` *is* difficulty is a candidate, not verified.

### Causal test

`tools/sc4_dynamic.py poke` wrote `rate[0] = 14.0` (was 7.0) directly into
the live budget object on 2006-11-07; nothing else was changed. A 0.25 s
read-only series then covered four month ends:

| Month | base[0] | predicted | observed |
| --- | --- | --- | --- |
| 2006-12 | 261,748 | 4028.17 | 4028 |
| 2007-01 | 265,216 | 4068.60 | 4068 |
| 2007-02 | 265,216 | 4068.60 | 4068 |
| 2007-03 | 265,216 | 4068.60 | 4068 |

- A raw write to the rate field is enough: no cache or setter notification is
  needed for the monthly pass to use it.
- Monthly funds change = tax − 2,362 in both the control month (+139) and
  every perturbed month (+1,706): expenses do not depend on the tax rate.
- Within four months base[0] did not shrink in response to the doubled rate
  (it grew). Any demand response is slower than this window, or acts
  elsewhere (desirability → future growth), and is the next experiment.

## Open

- What the base-building loop's record inputs are (which lots/buildings,
  which virtual methods) and the role of the `+0x7f8` table
  (observed `[1.0, 0.75, 0.5]`, indexed by a derived value, not `k`).
- The 12 category indices' names (expected: R/C/I × wealth, plus others).
- Verify `k` against a city started on a different difficulty.

## Method note

Found with `tools/sc4_dynamic.py` (frozen dumps, typed diffs, journaled
pokes) and a constant search in a local `objdump` disassembly. Raw dumps
and disassembly stay in `~/.cache/opensc4/` and the session scratchpad.
