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

For the real ultrawide desktop test, launch the main scene at the target size
and compare panning with the fast-water environment enabled and disabled:

```sh
OPENSC4_FAST_WATER=1 godot --path . --resolution 3480x1080
```

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
