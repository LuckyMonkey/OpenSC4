#!/usr/bin/env bash
set -euo pipefail

# Release gate: inspect tracked paths only. User-owned SC4 files may exist in
# the working tree, but they must never be committed to this repository.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mapfile -d '' tracked_files < <(git -C "$ROOT_DIR" ls-files -z)
violations=()

for path in "${tracked_files[@]}"; do
    case "$path" in
        *.dat|*.DAT|*.sc4|*.SC4|*.exe|*.EXE|*.dll|*.DLL|*.so|*.dylib|*.zip|*.7z|*.rar)
            violations+=("proprietary-or-binary extension: $path")
            ;;
        sc4-lab/reference/observations/*|sc4-lab/reference/manifests/*)
            case "$path" in
                */.gitkeep) ;;
                *) violations+=("reference output must remain local: $path") ;;
            esac
            ;;
    esac
done

if ((${#violations[@]} > 0)); then
    printf 'DATA BOUNDARY FAIL\n'
    printf '  %s\n' "${violations[@]}"
    exit 1
fi

printf 'DATA BOUNDARY PASS: tracked files checked=%d\n' "${#tracked_files[@]}"
