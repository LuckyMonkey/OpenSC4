#!/usr/bin/env python3
"""Build a metadata-only static candidate ledger for a local SC4 PE.

This is a bounded fallback when the REA/Ghidra bridge cannot finish a legacy
PE analysis. It records selected printable strings, their file/virtual
addresses, and code instructions that reference those virtual addresses. It
never writes executable bytes, disassembly, or extracted resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_PATTERNS = (
    r"^g_power_",
    r"^g_water_",
    r"^g_city_",
    r"^g_(funds|population|date)$",
    r"^cSC4(BudgetSimulator|PowerSimulator|WaterPathFinder)$",
    r"^kMessage.*(Power|Water|Simulation|City)",
    r"^SimulationClock$",
    r"^GetSimulationDate$",
    r"^EnableSimulation$",
    r"^LoadCity$",
    r"^SaveCity",
    r"^kCommandID_",
)
SECTION_RE = re.compile(r"^\s*\d+\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)")
STRING_RE = re.compile(r"^\s*([0-9a-fA-F]+)\s+(.*)$")
INSTRUCTION_RE = re.compile(r"^\s*([0-9a-fA-F]+):\s+(.*)$")


def run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise RuntimeError(f"command failed: {' '.join(command)}\n{detail.strip()}") from exc
    return result.stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sections(path: Path) -> list[dict[str, int | str]]:
    result: list[dict[str, int | str]] = []
    for line in run(["objdump", "-h", str(path)]).splitlines():
        match = SECTION_RE.match(line)
        if not match:
            continue
        name, size, vma, _lma, file_offset = match.groups()
        result.append(
            {
                "name": name,
                "size": int(size, 16),
                "vma": int(vma, 16),
                "file_offset": int(file_offset, 16),
            }
        )
    if not result:
        raise RuntimeError("objdump returned no sections")
    return result


def virtual_address(file_offset: int, section_list: list[dict[str, int | str]]) -> int | None:
    for section in section_list:
        start = int(section["file_offset"])
        end = start + int(section["size"])
        if start <= file_offset < end:
            return int(section["vma"]) + file_offset - start
    return None


def selected_strings(path: Path, section_list: list[dict[str, int | str]], patterns: list[re.Pattern[str]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for line in run(["strings", "-a", "-t", "x", "-n", "4", str(path)]).splitlines():
        match = STRING_RE.match(line)
        if not match:
            continue
        file_offset = int(match.group(1), 16)
        value = match.group(2)
        if not any(pattern.search(value) for pattern in patterns):
            continue
        address = virtual_address(file_offset, section_list)
        section_name = next(
            (
                section["name"]
                for section in section_list
                if int(section["file_offset"]) <= file_offset < int(section["file_offset"]) + int(section["size"])
            ),
            None,
        )
        selected.append(
            {
                "value": value,
                "file_offset": f"0x{file_offset:x}",
                "virtual_address": f"0x{address:08x}" if address is not None else None,
                "section": section_name,
                "status": "candidate_unverified",
            }
        )
    return selected


def code_references(path: Path, candidates: list[dict[str, Any]]) -> None:
    address_map = {
        int(candidate["virtual_address"], 16): candidate
        for candidate in candidates
        if candidate["virtual_address"]
    }
    if not address_map:
        return
    for line in run(["objdump", "-d", "--no-show-raw-insn", str(path)]).splitlines():
        instruction = INSTRUCTION_RE.match(line)
        if not instruction:
            continue
        instruction_address = int(instruction.group(1), 16)
        operands = instruction.group(2)
        referenced = {int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]+)", operands)}
        for address in referenced & address_map.keys():
            address_map[address].setdefault("code_references", []).append(
                {
                    "instruction_address": f"0x{instruction_address:08x}",
                    "instruction": operands,
                }
            )
    for candidate in candidates:
        candidate.setdefault("code_references", [])


def build(path: Path, pattern_strings: list[str]) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    section_list = sections(path)
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in pattern_strings]
    candidates = selected_strings(path, section_list, patterns)
    code_references(path, candidates)
    return {
        "schema": "opensc4.static-candidates.v1",
        "target": {
            "basename": path.name,
            "absolute_path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        },
        "method": {
            "tools": ["strings", "objdump"],
            "read_policy": "metadata_only; output_is_local_and_must_not_be_committed",
            "patterns": pattern_strings,
            "limitations": [
                "String presence does not prove authoritative state or runtime use.",
                "Code references are static address matches, not dynamic execution traces.",
                "No function boundary, calling convention, or write authority is established.",
            ],
        },
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--pattern", action="append", dest="patterns", help="case-insensitive regex; repeatable")
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args()
    try:
        manifest = build(args.target, args.patterns or list(DEFAULT_PATTERNS))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().resolve().write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
