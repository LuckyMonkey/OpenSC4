#!/usr/bin/env python3
"""Safely invoke the already-verified SC4 tax-rate setter.

Default behavior is a read-only dry run. Applying a rate requires both
``--apply`` and ``--ack-runtime-write``. The operator resolves the current
image base and budget object every run, calls only the verified native setter,
and reads the twelve rate fields back. It never writes a raw memory location,
changes a save, or edits the executable.

This is intentionally a narrow experiment operator, not a general memory
writer. Category-to-index mapping remains an open research question; callers
must provide an explicit index from 0 through 11.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sc4_budget_probe
from memory_observatory import ObservatoryError, open_memory, process_identity


IMAGE_BASE_DEFAULT = 0x00400000
SETTER_RVA = 0x0068FD70 - IMAGE_BASE_DEFAULT
RATE_COUNT = 12
RATE_BASE = 0x70
RECORD_STRIDE = 0x80


class InterventionError(Exception):
    """Raised when the guarded intervention cannot proceed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_rates(pid: int, budget: int) -> list[float]:
    handle = open_memory(pid)
    try:
        return [
            sc4_budget_probe.read_value(handle, budget + RATE_BASE + index * RECORD_STRIDE, "<f")
            for index in range(RATE_COUNT)
        ]
    finally:
        os.close(handle)


def resolve(pid: int, image_name: str) -> tuple[dict[str, Any], int, int, list[float]]:
    identity = process_identity(pid)
    base = sc4_budget_probe.image_base(pid, image_name)
    handle = open_memory(pid)
    try:
        budget = sc4_budget_probe.read_value(
            handle, base + sc4_budget_probe.BUDGET_GLOBAL_RVA, "<I"
        )
    finally:
        os.close(handle)
    if budget < 0x10000:
        raise InterventionError(f"budget pointer is invalid: 0x{budget:x}")
    return identity, base, budget, read_rates(pid, budget)


def invoke_setter(pid: int, address: int, budget: int, index: int, value: float) -> str:
    expression = (
        f"call ((void (*)(void *, int, float))0x{address:x})"
        f"((void *)0x{budget:x}, {index}, {value:.9g}f)"
    )
    command = [
        "gdb",
        "-q",
        "-n",
        "-batch",
        "-p",
        str(pid),
        "-ex",
        "set pagination off",
        "-ex",
        expression,
        "-ex",
        "detach",
        "-ex",
        "quit",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise InterventionError(f"could not launch gdb: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise InterventionError(detail[-1] if detail else f"gdb exited with {result.returncode}")
    return expression


def write_output(path: Path | None, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(encoded, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
        print(f"SC4 TAX INTERVENTION PLAN: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--index", type=int, required=True, help="verified tax record index, 0 through 11")
    parser.add_argument("--value", type=float, required=True, help="tax rate percentage, restricted to 0 through 100")
    parser.add_argument("--image-name", default="SimCity 4.exe")
    parser.add_argument("--apply", action="store_true", help="invoke the native setter")
    parser.add_argument("--ack-runtime-write", action="store_true", help="acknowledge this changes the running process only")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    try:
        if not 0 <= args.index < RATE_COUNT:
            raise InterventionError("index must be between 0 and 11")
        if not 0 <= args.value <= 100:
            raise InterventionError("value must be between 0 and 100")
        if args.apply and not args.ack_runtime_write:
            raise InterventionError("--apply requires --ack-runtime-write")

        identity, base, budget, before = resolve(args.pid, args.image_name)
        setter_address = base + SETTER_RVA
        result: dict[str, Any] = {
            "schema": "sc4-lab.sc4-tax-intervention.v1",
            "created_utc": utc_now(),
            "operation": {
                "index": args.index,
                "requested_value": args.value,
                "setter_rva": f"0x{SETTER_RVA:x}",
                "setter_address": f"0x{setter_address:x}",
                "application": "native_setter" if args.apply else "dry_run",
            },
            "source": {
                "pid": args.pid,
                "process": identity,
                "image_base": f"0x{base:x}",
                "budget_global_rva": f"0x{sc4_budget_probe.BUDGET_GLOBAL_RVA:x}",
                "budget_pointer": f"0x{budget:x}",
                "raw_memory_written": False,
                "native_function_invoked": False,
                "save_modified": False,
                "category_mapping_status": "caller-supplied index; not yet independently mapped",
            },
            "rates_before": before,
            "rates_after": before,
            "interpretation": {
                "reference_claim": True,
                "equivalence_claim": False,
                "status": "dry_run" if not args.apply else "applied_runtime_only",
            },
        }
        if args.apply:
            result["source"]["native_function_invoked"] = True
            result["operation"]["gdb_expression"] = invoke_setter(
                args.pid, setter_address, budget, args.index, args.value
            )
            _, _, budget_after, after = resolve(args.pid, args.image_name)
            result["source"]["budget_pointer_after"] = f"0x{budget_after:x}"
            result["rates_after"] = after
        write_output(args.out, result)
        return 0
    except (OSError, ObservatoryError, InterventionError, ValueError) as exc:
        print(f"SC4 TAX INTERVENTION FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
