# Data-free protocol fixtures

`synthetic_sidecar.py` exercises the adapter envelope with a deliberately
synthetic power backend. It is a transport and recording fixture only. Its
output is explicitly marked `reference_claim: false` and must never be used as
SC4 evidence.

The generic driver is `tools/probe_adapter.py`. Replace the mock command with
an eventual OpenGlassBox or local SC4 adapter only after its provenance and
data boundary are documented.
