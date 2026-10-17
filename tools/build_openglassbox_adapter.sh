#!/usr/bin/env bash
set -euo pipefail

# Build the small OpenGlassBox process bridge without vendoring that external
# project into OpenSC4. The output defaults to /tmp so no generated binary is
# accidentally committed with the Godot project.

ogb_root="${OPENSC4_OPENGLASSBOX_ROOT:-/tmp/OpenGlassBox-master}"
output="${OPENSC4_OPENGLASSBOX_HELPER:-/tmp/opensc4-openglassbox-helper}"

if [[ "${1:-}" == "--root" ]]; then
    ogb_root="${2:?--root requires a path}"
    shift 2
fi
if [[ "${1:-}" == "--output" ]]; then
    output="${2:?--output requires a path}"
    shift 2
fi
if [[ $# -ne 0 ]]; then
    echo "usage: $0 [--root /path/to/OpenGlassBox] [--output /path/to/helper]" >&2
    exit 2
fi

if [[ ! -f "$ogb_root/include/OpenGlassBox/Simulation.hpp" || ! -f "$ogb_root/build/libOpenGlassBox.so" ]]; then
    echo "OpenGlassBox build not found at $ogb_root" >&2
    echo "Build it first with: make -C $ogb_root -j2" >&2
    exit 2
fi

commit="$(git -C "$ogb_root" rev-parse HEAD)"
mkdir -p "$(dirname "$output")"
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic \
    -I"$ogb_root/include" \
    -DOPENSC4_OGB_COMMIT=\"$commit\" \
    sc4-lab/adapters/openglassbox/openglassbox_helper.cpp \
    -L"$ogb_root/build" -Wl,-rpath,"$ogb_root/build" \
    -lOpenGlassBox -o "$output"

echo "built $output"
echo "OpenGlassBox commit $commit"
