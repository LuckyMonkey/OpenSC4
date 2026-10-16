#!/usr/bin/env python3
"""Read authoritative SC4 budget fields from a running local process.

This is deliberately read-only. It follows the exact executable's image base
to the discovered budget global, then reads fields whose meanings were
established by native instruction tracing. It does not scan arbitrary memory,
write process memory, invoke game code, or persist raw bytes.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_observatory import ObservatoryError, open_memory, parse_maps, process_identity


IMAGE_BASE_DEFAULT = 0x00400000
BUDGET_GLOBAL_RVA = 0x00B43D64 - IMAGE_BASE_DEFAULT
RATE_COUNT = 12
RATE_BASE = 0x70
RECORD_STRIDE = 0x80
FUNDS_OFFSET = 0x28
FUNDS_WORKING_OFFSET = 0x30
TAX_INCOME_OFFSET = 0x670
TAX_CATEGORY_TOTAL_BASE = 0xE0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def image_base(pid: int, image_name: str) -> int:
    wanted = image_name.lower()
    for region in parse_maps(pid):
        if region["offset"] != 0 or "r" not in region["perms"]:
            continue
        if region["name"].lower() == wanted:
            return region["start"]
    raise ObservatoryError(f"could not find mapped image {image_name!r}")


def read_value(handle: int, address: int, fmt: str) -> Any:
    size = struct.calcsize(fmt)
    data = os.pread(handle, size, address)
    if len(data) != size:
        raise ObservatoryError(f"could not read {size} bytes from the live process")
    return struct.unpack(fmt, data)[0]


def sample(handle: int, pid: int, base: int) -> dict[str, Any]:
    budget_global = base + BUDGET_GLOBAL_RVA
    budget = read_value(handle, budget_global, "<I")
    if budget < 0x10000:
        raise ObservatoryError(f"budget pointer is invalid: 0x{budget:x}")

    rates = [
        read_value(handle, budget + RATE_BASE + index * RECORD_STRIDE, "<f")
        for index in range(RATE_COUNT)
    ]
    category_totals = [
        read_value(handle, budget + TAX_CATEGORY_TOTAL_BASE + index * RECORD_STRIDE, "<q")
        for index in range(RATE_COUNT)
    ]
    return {
        "schema": "sc4-lab.sc4-budget-observation.v1",
        "captured_utc": utc_now(),
        "process": process_identity(pid),
        "image_base": f"0x{base:x}",
        "budget_global_rva": f"0x{BUDGET_GLOBAL_RVA:x}",
        "raw_bytes_recorded": False,
        "metrics": {
            "funds_public": read_value(handle, budget + FUNDS_OFFSET, "<q"),
            "funds_working_candidate": read_value(handle, budget + FUNDS_WORKING_OFFSET, "<q"),
            "tax_income": read_value(handle, budget + TAX_INCOME_OFFSET, "<q"),
            "tax_rates": rates,
            "tax_category_totals": category_totals,
            "tax_category_total_sum": sum(category_totals),
        },
        "evidence": {
            "funds_public": "budget object +0x28/+0x2c via vtable +0x18",
            "funds_adjustment": "budget vtable +0x1c; not invoked by this tool",
            "tax_income": "budget object +0x670/+0x674 via vtable +0x4c",
            "tax_rates": "budget object +0x70 + index*0x80 via vtable +0x90",
            "tax_category_totals": "budget object +0xe0 + index*0x80 via vtable +0xe0",
            "working_balance": "candidate mirror used by the native update path",
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pid", type=int, required=True)
    result.add_argument("--duration", type=float, default=0.0)
    result.add_argument("--interval", type=float, default=2.0)
    result.add_argument("--image-name", default="SimCity 4.exe")
    result.add_argument("--out", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.duration < 0 or args.interval <= 0:
        print("duration must be non-negative and interval must be positive", file=sys.stderr)
        return 2
    try:
        identity = process_identity(args.pid)
        base = image_base(args.pid, args.image_name)
        handle = open_memory(args.pid)
        stream = args.out.open("w", encoding="utf-8") if args.out else sys.stdout
        try:
            deadline = time.monotonic() + args.duration
            first = True
            while first or time.monotonic() <= deadline:
                first = False
                stream.write(json.dumps(sample(handle, args.pid, base), sort_keys=True) + "\n")
                stream.flush()
                if time.monotonic() > deadline:
                    break
                time.sleep(args.interval)
        finally:
            os.close(handle)
            if args.out:
                stream.close()
        print(f"SC4 BUDGET PROBE PASS: {identity['command_basename']}", file=sys.stderr)
        return 0
    except (OSError, ObservatoryError, ValueError) as exc:
        print(f"sc4 budget probe failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
