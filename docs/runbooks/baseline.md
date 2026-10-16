# Runbook: baseline verification

## Purpose

Establish whether a change broke project import, local SC4 data loading, city
construction, or the known rendering view paths.

## Quick run

From the OpenSC4 repository:

```sh
bash tools/run_baseline.sh
```

Specify an output directory and local city when needed:

```sh
bash tools/run_baseline.sh /tmp/opensc4-baseline Timbuktu "Big City Tutorial"
```

The command writes logs and optional screenshots under the requested output
directory. It never copies SC4 files there.

## Expected results

- import exits zero;
- the synthetic backend log contains `SYNTHETIC BACKEND PASS`;
- the city log contains `SWEEP COMPLETE`;
- if Xvfb is installed, the screenshot log contains `SCREENSHOTS DONE`;
- `SCRIPT ERROR` is absent from the logs.

The current harness can still report ObjectDB/resource leak warnings during
Godot shutdown after a successful sweep. Track those separately from load
failures.

## Triage

1. Check the recorded `game_dir` and verify the user-owned install is complete.
2. Re-run only the failing city name with a fresh temporary output directory.
3. Search the log for the first `SCRIPT ERROR`, not the final cascade.
4. If only screenshots differ, compare renderer, resolution, GPU driver, and
   camera pose before changing code.
5. Keep failing logs outside the repository unless they contain no game data.
