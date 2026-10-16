# SC4 lab data boundary

This directory contains the data-free layout for the behavioral compatibility
lab. Do not place SimCity 4 executables, DLLs, `.dat` archives, original city
saves, extracted assets, or unreviewed reference dumps here.

Reference observations are generated locally by an adapter and are immutable
after acceptance. See [`../docs/simulation-lab.md`](../docs/simulation-lab.md)
for the protocol and scenario contract.

The full behavioral method, hypothesis discipline, provenance rules, and
distillation milestones are in [`../docs/distillation.md`](../docs/distillation.md).

Adapter processes use the plain-data envelope in
[`adapters/PROTOCOL.md`](adapters/PROTOCOL.md). Candidate/reference outputs
are compared by [`verifier/compare.py`](verifier/compare.py) with a separate
policy file; neither component may rewrite the other's inputs.
