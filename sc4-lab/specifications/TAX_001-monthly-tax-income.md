# TAX_001 — monthly tax income

Status: **verified subsystem boundary** for executable SHA-256
`f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153`.
Independently written from observations; no SC4 code is reproduced.
Evidence: `docs/milestones/sc4-tax-distillation-v0.3.md`.

## Inputs (Level A scalars, all per city, all observable)

| Symbol | Meaning | Type |
| --- | --- | --- |
| `R[c]`, c = 0..11 | tax rate of category c, in percent | IEEE-754 binary32 |
| `B[c]` | annual taxable base of category c | integer ≥ 0 |
| `M` | multiplier selected by a 3-way city setting (observed 1.2 / 1.1 / 1.0) | binary32 |

## Rule

```text
T = trunc( Σ_c  B[c] · M · R[c] · K )         K = binary32(1/1200)
```

- Products are evaluated left to right in at least binary64 precision with
  `M`, `R[c]` and `K` taken at their exact binary32 values, then summed.
- `trunc` rounds toward zero once, on the sum (not per category).
- `T` is published once per month at the month rollover. It is the
  month's tax income; funds change by `T − expenses` at the same boundary.

## Scope and non-claims

- `B[c]` is an **input**. How SC4 builds it (from which buildings, with
  which factors) is not specified here.
- Expenses, demand response, abandonment and growth are not covered.
- Verified with M = 1.0 only. M = 1.2 / 1.1 and negative values are untested.
- Category names (which `c` is which zone/wealth class) are unassigned.

## Acceptance

`tax_income` must match the reference **exactly**
(`sc4-lab/verifier/tolerances.tax.v1.json`). Months used to derive the rule
are labelled `derivation` and excluded from the held-out score.
