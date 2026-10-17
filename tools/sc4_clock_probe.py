#!/usr/bin/env python3
"""Read the native SC4 simulation-date candidate from a running process.

This probe is read-only.  It follows the executable image base to the native
clock service global, resolves the embedded date object, and reads the scalar
returned by that object's vtable method.  The integer calendar conversion is
implemented from the observed native helper at 0x00912789; it is not inferred
from screenshots or wall-clock time.

The field is a runtime candidate until it survives save/reload and process
restart checks.  The probe therefore labels semantic status explicitly and
never presents the result as complete SC4 clock equivalence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_observatory import ObservatoryError, open_memory, process_identity
import sc4_budget_probe


IMAGE_BASE_DEFAULT = 0x00400000
CLOCK_GLOBAL_VA = 0x00B43D5C
CLOCK_GLOBAL_RVA = CLOCK_GLOBAL_VA - IMAGE_BASE_DEFAULT
CLOCK_DATE_OBJECT_OFFSET = 0xF0
CLOCK_SERIAL_OFFSET = 0xEC
CLOCK_DATE_METHOD_OFFSET = 0x68
CLOCK_DATE_HELPER_VA = 0x00912789
CLOCK_DATE_HELPER_RVA = CLOCK_DATE_HELPER_VA - IMAGE_BASE_DEFAULT
DATE_EPOCH_BIAS = 0x1A431F
FOUR_HUNDRED_YEAR_DAYS = 0x23AB1
FOUR_YEAR_DAYS = 0x5B5
MONTH_CYCLE_DAYS = 0x99


class ClockProbeError(Exception):
    """Raised when the native clock candidate cannot be read safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_u32(handle: int, address: int) -> int:
    value = sc4_budget_probe.read_value(handle, address, "<I")
    return int(value)


def decode_native_date(serial: int) -> dict[str, int]:
    """Mirror the integer Gregorian conversion in the native date helper.

    The instruction sequence uses unsigned integer division and the constants
    below.  Negative/pre-epoch values are not promoted by this probe because
    their C unsigned semantics have not been observed in a live city.
    """

    days = serial - DATE_EPOCH_BIAS
    if days <= 0:
        raise ClockProbeError(f"date serial is before supported native epoch: {serial}")

    four_century_numerator = days * 4 - 1
    century, remainder = divmod(four_century_numerator, FOUR_HUNDRED_YEAR_DAYS)
    remainder = (remainder >> 2) << 2

    aligned_remainder = remainder
    year_in_century, _ = divmod(aligned_remainder + 3, FOUR_YEAR_DAYS)
    remainder = aligned_remainder - year_in_century * FOUR_YEAR_DAYS + 7
    day_in_four_year_cycle = remainder >> 2

    month_cycle = day_in_four_year_cycle * 5
    month_cycle_index, _ = divmod(month_cycle - 3, MONTH_CYCLE_DAYS)
    # The native helper stores the quotient directly.  It does not apply the
    # usual civil-calendar ``+1`` adjustment at this boundary.
    day, _ = divmod(month_cycle - month_cycle_index * MONTH_CYCLE_DAYS + 2, 5)

    year = century * 100 + year_in_century + month_cycle_index // 10
    month = month_cycle_index + 3 - 12 * (month_cycle_index // 10)
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ClockProbeError(
            f"native date conversion produced an invalid date: {year}-{month}-{day}"
        )
    return {"year": year, "month": month, "day": day}


def sample(handle: int, pid: int, base: int) -> dict[str, Any]:
    clock_global = base + CLOCK_GLOBAL_RVA
    clock_service = read_u32(handle, clock_global)
    if clock_service < 0x10000:
        raise ClockProbeError(f"clock service pointer is invalid: 0x{clock_service:x}")

    date_object = clock_service + CLOCK_DATE_OBJECT_OFFSET
    date_vtable = read_u32(handle, date_object)
    date_serial = read_u32(handle, clock_service + CLOCK_SERIAL_OFFSET)
    calendar_date = decode_native_date(date_serial)

    return {
        "schema": "sc4-lab.sc4-clock-observation.v1",
        "captured_utc": utc_now(),
        "metrics": {
            "simulation_date_serial": date_serial,
            "simulation_year": calendar_date["year"],
            "simulation_month": calendar_date["month"],
            "simulation_day": calendar_date["day"],
        },
        "native_resolution": {
            "clock_global": f"0x{clock_global:x}",
            "clock_service": f"0x{clock_service:x}",
            "date_object": f"0x{date_object:x}",
            "date_vtable": f"0x{date_vtable:x}",
            "date_serial_address": f"0x{clock_service + CLOCK_SERIAL_OFFSET:x}",
            "date_method_offset": f"0x{CLOCK_DATE_METHOD_OFFSET:x}",
            "date_helper_rva": f"0x{CLOCK_DATE_HELPER_RVA:x}",
        },
        "evidence": {
            "clock_global": "native code references ds:0xb43d5c as the clock service",
            "date_object": "clock vtable +0x1c returns the embedded object at this+0xf0",
            "date_serial": "embedded date vtable +0x68 targets 0x0091297e, which returns [this-4]",
            "calendar_conversion": "integer Gregorian conversion recovered from helper 0x00912789",
        },
        "provenance": {
            "observation_kind": "live-memory-native-date-candidate",
            "reference_claim": True,
            "equivalence_claim": False,
            "semantic_status": "runtime-candidate; restart/save validation pending",
            "raw_bytes_recorded": False,
            "raw_memory_written": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pid", type=int)
    result.add_argument("--duration", type=float, default=0.0)
    result.add_argument("--interval", type=float, default=2.0)
    result.add_argument("--image-name", default="SimCity 4.exe")
    result.add_argument("--out", type=Path)
    result.add_argument("--self-test", action="store_true")
    return result


def self_test() -> int:
    expected = {"year": 2055, "month": 1, "day": 10}
    actual = decode_native_date(0x25B6DB)
    if actual != expected:
        raise ClockProbeError(f"date conversion self-test produced {actual}, expected {expected}")
    print("SC4 CLOCK PROBE SELF-TEST PASS: 0x25b6db -> 2055-01-10")
    return 0


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        try:
            return self_test()
        except ClockProbeError as exc:
            print(f"sc4 clock probe failed: {exc}", file=sys.stderr)
            return 2
    if args.pid is None:
        print("--pid is required unless --self-test is used", file=sys.stderr)
        return 2
    if args.duration < 0 or args.interval <= 0:
        print("duration must be non-negative and interval must be positive", file=sys.stderr)
        return 2

    try:
        identity = process_identity(args.pid)
        base = sc4_budget_probe.image_base(args.pid, args.image_name)
        handle = open_memory(args.pid)
        records: list[dict[str, Any]] = []
        started = time.monotonic()
        deadline = started + args.duration
        sample_index = 0
        try:
            while True:
                record = sample(handle, args.pid, base)
                record["sample_index"] = sample_index
                record["elapsed_seconds"] = round(time.monotonic() - started, 6)
                record["time_axis"] = {
                    "primary": "simulation_date_serial",
                    "wall_clock_seconds": "diagnostic_only",
                    "simulation_tick": "not recovered",
                }
                record["source"] = {
                    "tool": "tools/sc4_clock_probe.py",
                    "pid": args.pid,
                    "process": identity,
                    "image_base": f"0x{base:x}",
                    "image_name": args.image_name,
                    "clock_global_rva": f"0x{CLOCK_GLOBAL_RVA:x}",
                }
                records.append(record)
                sample_index += 1
                if time.monotonic() >= deadline:
                    break
                time.sleep(args.interval)
        finally:
            os.close(handle)

        encoded = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(encoded, encoding="utf-8")
            print(json.dumps({"out": str(args.out), "samples": len(records)}))
        else:
            print(encoded, end="")
        return 0
    except (OSError, ObservatoryError, ClockProbeError, ValueError) as exc:
        print(f"sc4 clock probe failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
