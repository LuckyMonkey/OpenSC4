#!/usr/bin/env bash
set -euo pipefail

# Reproducible local baseline. This script reads the user's configured SC4
# installation but only writes logs/screenshots to the explicit output folder.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GODOT_BIN="${GODOT_BIN:-godot}"
OUT_DIR="${1:-/tmp/opensc4-baseline-$(date +%Y%m%d-%H%M%S)}"
REGION="${2:-Timbuktu}"
CITY="${3:-Big City Tutorial}"
SCREEN_WIDTH="${SC4_SCREEN_WIDTH:-1600}"
SCREEN_HEIGHT="${SC4_SCREEN_HEIGHT:-900}"
GIT_COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD)"
GIT_BRANCH="$(git -C "$ROOT_DIR" branch --show-current)"
GIT_DIRTY_FILES="$(git -C "$ROOT_DIR" status --porcelain | wc -l | tr -d ' ')"
GODOT_VERSION="$("$GODOT_BIN" --version 2>&1 | head -n 1)"
RENDERER_PROFILE="${SC4_RENDERER_PROFILE:-default}"
FAST_WATER="${OPENSC4_FAST_WATER:-0}"
SPATIAL_BATCHES="${OPENSC4_SPATIAL_BATCHES:-0}"
VIEW_BATCH_CACHE="${OPENSC4_CACHE_VIEW_BATCHES:-0}"

mkdir -p "$OUT_DIR"
printf 'schema=opensc4.baseline.v1\ncommit=%s\nbranch=%s\ngit_dirty_files=%s\n' \
    "$GIT_COMMIT" "$GIT_BRANCH" "$GIT_DIRTY_FILES" >"$OUT_DIR/manifest.txt"
printf 'godot_version=%s\nrenderer_profile=%s\nscreen=%sx%s\n' \
    "$GODOT_VERSION" "$RENDERER_PROFILE" "$SCREEN_WIDTH" "$SCREEN_HEIGHT" \
    >>"$OUT_DIR/manifest.txt"
printf 'fast_water=%s\nspatial_batches=%s\nview_batch_cache=%s\n' \
    "$FAST_WATER" "$SPATIAL_BATCHES" "$VIEW_BATCH_CACHE" >>"$OUT_DIR/manifest.txt"
printf 'region=%s\ncity=%s\nreference_data=local-only\noutput=%s\n' \
    "$REGION" "$CITY" "$OUT_DIR" | tee -a "$OUT_DIR/manifest.txt"

echo "[1/5] Godot import"
"$GODOT_BIN" --headless --path "$ROOT_DIR" --import \
    >"$OUT_DIR/import.log" 2>&1

echo "[2/5] Synthetic backend smoke"
"$GODOT_BIN" --headless --path "$ROOT_DIR" \
    res://tools/SyntheticBackendSmoke.tscn \
    >"$OUT_DIR/synthetic.log" 2>&1
grep -q "SYNTHETIC BACKEND PASS" "$OUT_DIR/synthetic.log"

echo "[3/5] Parser fixture smoke"
"$GODOT_BIN" --headless --path "$ROOT_DIR" \
    res://tools/ParserFixtureSmoke.tscn \
    >"$OUT_DIR/parser.log" 2>&1
grep -q "PARSER FIXTURE PASS" "$OUT_DIR/parser.log"

echo "[4/5] Headless city sweep"
timeout -k 5 180 "$GODOT_BIN" --headless --path "$ROOT_DIR" \
    res://tools/HeadlessCity.tscn -- "$REGION" "$CITY" \
    >"$OUT_DIR/city.log" 2>&1
grep -q "SWEEP COMPLETE" "$OUT_DIR/city.log"
if grep -Eq "SCRIPT ERROR|SHADER ERROR|Shader compilation failed" "$OUT_DIR/city.log"; then
    echo "City harness reported a script or shader error"
    exit 1
fi

if [ "${SC4_SKIP_SCREENSHOT:-0}" = "1" ]; then
    echo "[5/5] Screenshot harness skipped (SC4_SKIP_SCREENSHOT=1)" \
        | tee "$OUT_DIR/screenshot.log"
elif command -v xvfb-run >/dev/null 2>&1; then
    echo "[5/5] Screenshot harness"
    mkdir -p "$OUT_DIR/screenshots"
    run_screenshot_harness() {
        LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a \
            --server-args="-screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x24" \
            "$GODOT_BIN" --path "$ROOT_DIR" --rendering-driver opengl3 \
            --resolution "${SCREEN_WIDTH}x${SCREEN_HEIGHT}" \
            res://tools/ScreenshotCity.tscn -- "$OUT_DIR/screenshots" "$REGION" "$CITY"
    }

    screenshot_status=0
    run_screenshot_harness >"$OUT_DIR/screenshot.log" 2>&1 || screenshot_status=$?
    screenshot_status="${screenshot_status:-0}"
    if ! grep -q "SCREENSHOTS DONE" "$OUT_DIR/screenshot.log"; then
        echo "Screenshot harness did not complete (status $screenshot_status); retrying once" \
            >>"$OUT_DIR/screenshot.log"
        screenshot_status=0
        run_screenshot_harness >>"$OUT_DIR/screenshot.log" 2>&1 || screenshot_status=$?
    fi
    if ! grep -q "SCREENSHOTS DONE" "$OUT_DIR/screenshot.log"; then
        echo "Screenshot harness failed before completion (status $screenshot_status)"
        exit "${screenshot_status:-1}"
    fi
    if grep -Eq "SCRIPT ERROR|SHADER ERROR|Shader compilation failed" \
        "$OUT_DIR/screenshot.log"; then
        echo "Screenshot harness reported a script or shader error"
        exit 1
    fi
    if [ "$screenshot_status" -ne 0 ]; then
        echo "Screenshot completed; renderer exited with status $screenshot_status during shutdown"
    fi
else
    echo "[5/5] xvfb-run unavailable; screenshot harness skipped" \
        | tee "$OUT_DIR/screenshot.log"
fi

echo "BASELINE PASS: $OUT_DIR"
