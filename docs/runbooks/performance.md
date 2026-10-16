# Runbook: performance and panning investigation

## Principle

Separate startup cost, first-frame cost, steady-state panning, view changes,
and shader cost. GPU utilization alone is not proof of a bottleneck: a single
thread, synchronization, shader compilation, or driver stall can leave the GPU
underutilized.

## Capture the environment

```sh
date
godot --version
lscpu
lspci | rg -i 'vga|3d|nvidia|amd|intel'
nvidia-smi
```

Record the renderer and display size with every comparison. Use the same city,
camera pose, zoom, and rotation.

## Baseline and fast-water comparison

Normal path:

```sh
bash tools/run_baseline.sh /tmp/opensc4-normal Timbuktu "Big City Tutorial"
```

Opt-in simplified water path:

```sh
OPENSC4_FAST_WATER=1 bash tools/run_baseline.sh \
    /tmp/opensc4-fast-water Timbuktu "Big City Tutorial"
```

The fast path removes animated noise, water-depth reconstruction, and wave
highlight work while retaining the water texture. It is a diagnostic/performance
profile, not the default appearance.

Opt-in spatial batches split props/flora into 32x32-tile chunks:

```sh
OPENSC4_SPATIAL_BATCHES=1 bash tools/run_baseline.sh \
    /tmp/opensc4-spatial Timbuktu "Big City Tutorial"
```

Combine it with fast water when isolating culling behavior:

```sh
OPENSC4_FAST_WATER=1 OPENSC4_SPATIAL_BATCHES=1 \
    godot --path . --resolution 3480x1080
```

This profile may increase MultiMesh node count at whole-city zooms. Compare
both frame time and node count; do not assume more culling is automatically
faster.

Opt-in view-batch caching keeps the two most recently built zoom/rotation batch
sets alive, which targets back-and-forth view changes:

```sh
OPENSC4_CACHE_VIEW_BATCHES=1 godot --path . --resolution 3480x1080
```

It trades memory for reduced rebuild work. Measure resident memory and visual
correctness before combining it with spatial batches.

For the real ultrawide desktop test, launch the main scene at the target size
and compare panning with the fast-water environment enabled and disabled:

```sh
OPENSC4_FAST_WATER=1 godot --path . --resolution 3480x1080
```

For repeatable timing output under a windowed X11 session:

```sh
godot --path . --resolution 1600x900 res://tools/PerformanceCity.tscn -- \
    Timbuktu "Big City Tutorial"
```

For an unattended software-rendered probe:

```sh
xvfb-run -a --server-args="-screen 0 1600x900x24" godot --path . \
    --rendering-driver opengl3 --resolution 1600x900 \
    res://tools/PerformanceCity.tscn -- Timbuktu "Big City Tutorial"
```

The probe reports startup, steady-state panning, fixed-view changes, and free
view changes. Treat its numbers as a baseline for the same machine/driver, not
as a universal pass threshold.

The current measured software-rendered comparison is in
[`../performance-baseline.md`](../performance-baseline.md). It indicates that
water is only part of the cost; do not make the simplified water path the
default until a real RTX/X11 comparison is captured.

## What to measure next

- frame time while holding an arrow key for ten seconds;
- frame time during each zoom step;
- frame time during each quarter-turn;
- first view after loading versus a repeated view;
- memory after loading and after repeated view changes;
- whether the visual change during panning is water animation, terrain
  precision, model popping, or an actual dropped-frame stall.

Do not optimize the MultiMesh cache until these measurements identify whether
view changes or ordinary panning are the expensive path.
