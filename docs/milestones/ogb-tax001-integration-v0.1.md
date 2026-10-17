# Milestone: first verified SC4 rule running in OpenGlassBox (TAX_001 v0.1)

Date 2026-10-17. SC4 executable SHA-256 `f512a405…1153`. OpenGlassBox
`fd7d918`. Status: **verified for the conditions below; not complete.**

## Pipeline

```text
SC4 (live memory) ─► reference observations (local only: sc4-lab/reference/observations/TAX_001/)
                         │ split: derivation | held_out
            ┌────────────┴─────────────┐
            ▼                          ▼
 OpenGlassBox sidecar         AI-fitted hypothesis
 ruleset sc4-tax-v0.3         sc4-lab/candidate/sc4_tax_fit.py
 (spec constant)              (constant fitted on derivation months only)
            └────────────┬─────────────┘
                         ▼
     sc4-lab/verifier/compare.py + tolerances.tax.v1.json (exact)
                         ▼
               EXACT MATCH / FAIL per candidate
```

The spec (`sc4-lab/specifications/TAX_001-monthly-tax-income.md`) and the exact
policy were committed (`61ef38b`) before any candidate was scored.

## Reproduce

```bash
bash tools/build_openglassbox_adapter.sh --root /path/to/OpenGlassBox   # fd7d918
python3 tools/sc4_tax_pipeline.py verify sc4-lab/reference/observations/TAX_001/*.jsonl
# exit 0 = OpenGlassBox exact on every held-out month
```

Reference observations are **local only** (`tools/check_data_boundary.sh`
rejects them in Git). Regenerate them from your own captures first:

```bash
python3 tools/sc4_tax_pipeline.py extract ~/.cache/opensc4/dynamic --series ~/.cache/opensc4/dynamic/rate0-poke-series.jsonl \
    --split derivation --out sc4-lab/reference/observations/TAX_001/derivation-rate0-poke.jsonl
python3 tools/sc4_tax_pipeline.py extract ~/.cache/opensc4/dynamic/ride-tax20 \
    --split held_out --out sc4-lab/reference/observations/TAX_001/heldout-ride-tax20.jsonl
```

To add data from a new live run:
`python3 tools/sc4_tax_pipeline.py extract <ride-dir> --split held_out --out …`.

## Result

| Candidate | Derivation (4 months, 2 distinct values) | Held-out (102 months, 4 distinct values) |
| --- | --- | --- |
| OpenGlassBox `sc4-tax-v0.3` | 4/4 | **102/102 — EXACT MATCH** |
| AI fit | 4/4 | **95/102 — FAIL** |

E_model (AI − OGB) is non-zero in exactly the 7 months where the AI fit fails.

- The AI fit narrowed the constant to `1/k ∈ [1199.890, 1200.050]` from data
  alone. That interval contains 1200, but its midpoint is wrong at the
  7174/7175 boundary. The derivation set **underdetermines** the constant.
  This is reported as a failure; neither the policy nor the fit was adjusted.
- The fit initially rejected the derivation data outright. That exposed an
  extraction bug: the first month of a capture pairs post-poke inputs with a
  tax computed before the poke. The extractor now drops any month whose
  rollover was not observed (`settled_months` in `tools/sc4_ogb_compare.py`).

## Limitations

- **Low input diversity:** 102 held-out months contain 4 distinct tax values
  (rates held at 20%, bases nearly frozen). Exact matches over many months
  are not 102 independent tests.
- Only `M = 1.0` (one difficulty setting), one city, one executable.
- Bases are supplied from SC4. Their construction (Priority A) is open.
- Funds are not part of TAX_001. The open-loop replay drifts by §38 over 102
  months, entirely from SC4 expense changes (2,362 → 2,361 …).
- OpenGlassBox resources are `uint32`. The module clamps negative funds and
  flags `clamped=1`. SC4 accounting needs a signed store
  (see `docs/architecture/openglassbox-reuse-matrix.md`).
- The AI fit is one simple hypothesis family, not a general fitter.

## Next (not started; awaiting review)

1. Increase input diversity for TAX_001: vary rates per category, use a
   second city, and a different difficulty (`M = 1.2/1.1`).
2. Priority A: taxable-base construction for one category.
3. Run the pipeline live inside `sc4_ride.py` for per-month verdicts.
