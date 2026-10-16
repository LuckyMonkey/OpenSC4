# Roadmap and milestone plan

The project should move in parallel. Rendering, reproducibility, reference
measurement, and simulation integration have different failure modes, so one
track must not block the others.

## Track A — reproducible baseline

### A1: baseline command (done)

Run import, city loading, the full view sweep, and optional screenshots from one
command. Preserve logs and output paths.

### A2: deterministic artifact manifest (done)

Record Git commit, Godot version, renderer, display size, GPU driver, SC4 game
directory hash metadata (not game files), city name, and elapsed times. Never
hash or copy proprietary data into the repository.

The baseline now writes `opensc4.baseline.v1` metadata and the data-boundary
gate rejects tracked game archives and reference outputs. Host GPU-driver
identification remains a follow-up because it must not capture game contents.

### A3: held-out rendering corpus

Add synthetic camera poses and user-provided local city names to the local test
matrix. Only commit image dimensions, hashes, and review notes unless the image
contains no protected game content.

## Track B — performance and edge rendering

### B1: water cost switch (done)

`OPENSC4_FAST_WATER=1` disables animated water noise/depth effects for a clean
performance comparison. The default visual path is unchanged.

### B2: frame-time probe (done)

Measure startup, first city frame, steady-state panning, zoom/rotation changes,
and free-camera transitions separately. Report CPU/GPU frame time rather than
GPU utilization alone.

The first software-rendered comparison is recorded in
`docs/performance-baseline.md`.

### B3: batch-view reuse (done, opt-in)

Profile the MultiMesh rebuild on view changes. Replace destructive rebuilds with
reusable per-view data only if memory and visual results are measured first.

The bounded two-view cache reduces a measured revisit from about 1.52 seconds
to 79 ms under the software-rendered probe. It remains opt-in pending real GPU
memory testing.

### B4: terrain/water level-of-detail (later)

Evaluate tile mesh density, depth prepass cost, and water coverage. Keep a
high-fidelity path for visual comparison and a documented fast path for weak
hardware.

## Track C — data and rendering correctness

### C1: malformed/missing record corpus (next)

Create synthetic parser fixtures for truncated records, missing referenced TGIs,
empty subfiles, bad dimensions, and out-of-range sprite rectangles.

### C2: save diversity (next)

Test empty cities, cities with no power lines/pipes, dense prop cities, coastal
cities, and different city sizes using locally supplied saves.

### C3: visual invariants (next)

Assert that camera rotation does not change world coordinates, missing models do
not crash loading, and UI remains visible at 16:9, 21:9, and 32:9 sizes.

## Track D — reference laboratory

### D1: schema and provenance (done)

The data-free `sc4-lab/` layout and scenario contract exist.

### D2: reference observation path (capture tooling done; live input needed)

Identify an allowed, repeatable way to apply controlled inputs and observe
structured power metrics in the local SC4 installation. If a metric cannot be
observed reliably, mark it unsupported instead of estimating it from pixels.

Local save/process metadata capture and changed-range reports are implemented;
the first real run still needs a user-owned `.sc4` save and live process.

The read-only dynamic memory observatory is also ready for candidate scanning,
hashed snapshots, and address sampling. It has only been tested against a
synthetic child process so far.

### D3: dynamic memory observatory (tooling done; live input needed)

Typed scans, hashed snapshots, and address sampling are ready. No SC4 address
is verified until a live process is captured and validated across restarts.

### D3.5: REA artifact preflight (done; native provider pending)

REA 6.5.0 is connected to Codex through a user-owned MCP registration and its
reverse-engineering skill is aligned. The provider-free PE resource inspection
completed against the available SC4 backups and confirmed stable PE32/x86
artifact identities. This is provenance only; it does not establish simulation
logic. Restart Codex, configure Ghidra or another explicitly approved native
provider, then open the exact manifest-selected executable.

### D3.6: first native candidate ledger (partial)

Use REA to identify a save/load path, simulation-tick candidate, and one
visible city-statistic path. Record addresses, callers, constants, evidence
IDs, confidence, and unknowns. Correlate only one candidate at a time with the
existing read-only memory and save-capture tools.

The provider is healthy, but three REA native operations currently hit the
330-second Ghidra bridge timeout on the legacy PE. The bounded fallback ledger
now records 178 named-string candidates and static references. Strong leads are
`g_power_plant_count` at `0x0042107d`, `g_power_consumed` at `0x00422152`,
`SimulationClock` at `0x005c9f42`, `GetSimulationDate` at `0x007032ce`, and
`LoadCity` at `0x007b217f`. These remain unverified until a function dossier or
runtime/save correlation exists.

### D4: power corpus (next after D3)

Run one plant, altered demand, funding changes, and two-plant cases. Record
month-end state plus the actual sampling schedule and uncertainty.

The independent JSON comparator and fixed policy file are now ready for those
observations; no reference values have been added yet.

### D5: candidate power model (later)

Implement only behavior supported by observations, then evaluate held-out cases.

## Track E — simulation backend

### E1: backend-neutral API (done)

Define commands, snapshots, event cursors, clock semantics, and save-versioning
in OpenSC4 without choosing OpenGlassBox-specific types. The JSON-line adapter
envelope and independent comparator now make the seam usable outside Godot.

### E2: synthetic backend (done)

Add a tiny deterministic backend for API tests: buildings, resource stocks,
power supply/demand, monthly ticks, and serialization. This tests the seam
without pretending to match SC4.

### E3: OpenGlassBox adapter (next)

Pin an external OpenGlassBox commit and expose it through a narrow C++ bridge.
The first implementation should speak the sidecar protocol before a GDExtension
is attempted. Do not vendor a large source snapshot into the Godot project.

### E4: SC4-compatible backend (later)

Add compatibility behavior behind the same interface only after reference
observations exist.

## Track F — project hygiene

### F1: reproducible milestone package (done)

Baseline manifests, a tracked-data boundary check, an iteration/sync runbook,
and a future-work wishlist are committed in
`docs/milestones/lab-baseline-v0.2.md`.

### F2: held-out experiment reporting (next)

Add immutable local manifests and a comparator report format without committing
original saves, extracted assets, or unreviewed reference dumps.

## Edge-problem exit criteria

Before calling the project stable, it must have documented behavior for:

- missing installation/configuration and partial DAT sets;
- missing/corrupt city saves and missing subfile references;
- cities with no buildings, props, flora, networks, water, or power lines;
- unsupported model, texture, sprite, and UI records;
- display resize, ultrawide anchoring, input focus, and fullscreen transitions;
- renderer changes and low-memory/low-GPU fallback modes;
- deterministic versus stochastic simulation outputs;
- save versions and backend migration failures.
