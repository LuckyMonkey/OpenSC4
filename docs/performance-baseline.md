# Performance baseline

This is a machine-specific diagnostic snapshot, not an acceptance threshold.

## Measurement

- City: `Timbuktu / Big City Tutorial`
- Window: 800x600 under Xvfb
- Renderer: Godot OpenGL compatibility / Mesa llvmpipe
- Pan sample: 90 frames
- Scene contents: 3,427 buildings, 69,477 batched props/flora occupants
- Probe: `res://tools/PerformanceCity.tscn`

## Results

| Profile | Startup | Steady pan | View changes |
| --- | ---: | ---: | ---: |
| Normal water | 17.4 s | 627.5 ms/frame | 1.95–4.14 s |
| Fast water | 18.9 s | 545.2 ms/frame | 1.84–3.64 s |
| Spatial batches | 17.7 s | 672.7 ms/frame | 2.81–4.86 s |
| View-batch cache | 16.4 s | 460.8 ms/frame | revisit 79 ms |

Fast water improves this software-rendered panning sample by about 13%, but
does not remove the problem. The large remaining cost is consistent with the
current renderer drawing many city-wide MultiMesh batches and rebuilding them on
zoom/rotation changes. This does not yet prove the same percentages on the
user's RTX 3050; repeat the probe in the real X11 session before changing
defaults.

## Next experiment

Compare three batch layouts using the same camera sequence:

1. current model-only batches;
2. cached view batches for repeated zoom/rotation changes;
3. model-plus-spatial-chunk batches so off-screen occupants can be culled.

Measure frame time, node count, GPU memory, and visual completeness. Keep the
current path available until the spatial version passes the city sweep and
visual review.

The spatial profile produced 4,310 MultiMesh nodes versus 769 and was slower in
this software-rendered test, so it is not a default recommendation. The
view-batch cache's no-cache control revisit was 1,521 ms versus 79 ms cached.
Pan timings varied substantially between runs under llvmpipe, so the cache is
credited only with reducing repeated view rebuilds, not with improving panning.
