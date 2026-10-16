# SC4 evidence-pack milestone v0.3

Status: achieved for static evidence organization; runtime correlation still
awaits a live user-owned SC4 process and controlled city.

## Delivered

- `tools/sc4_evidence_pack.py` combines the exact PE manifest and bounded
  static candidate ledger into a private JSON artifact plus an optional
  Markdown review.
- The pack records the target SHA-256, architecture, candidate categories,
  static references, verification sequences, REA evidence IDs, limitations,
  runtime prerequisites, and the no-raw-data boundary.
- The static scan now includes visible-value leads for `g_funds`,
  `g_population`, and `g_date`, plus named simulator and message types.
- Output is refused inside the repository, keeping local evidence separate
  from reviewable project code and documentation.

## Local result

Against the exact LAA backup:

- SHA-256: `f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153`
- Architecture: PE32/x86
- Static candidates: 185
- Retained leads: 57
- Key leads: `g_funds`, `g_population`, `g_date`, `g_power_consumed`,
  `SimulationClock`, `LoadCity`

The generated pack was written to `/tmp` and is intentionally not committed.

## Interpretation boundary

These are static candidates, not recovered SC4 source or verified simulation
fields. A string reference may be a publisher, UI label, cache, or unrelated
path. Static references do not prove function boundaries, runtime execution,
write authority, or algorithmic behavior.

## Next gate

Use a live SC4 session to scan one visible value at a time, then confirm the
candidate after save/reload and process restart. Promote only summarized
observations into the lab; keep saves, raw memory, executable bytes, and
extracted resources private.
