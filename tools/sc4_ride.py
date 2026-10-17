#!/usr/bin/env python3
"""Long-running SC4 experiment: hold tax rates by memory write and record everything.

Each sample (default 0.5 s) records the clock plus budget telemetry. At every
month rollover it checks the v0.3 tax equation against the game's published
tax income, appends one row to ``months.jsonl``, re-asserts the held tax
rates, and takes a frozen full-memory dump compressed with zstd (skipped when
free disk falls under ``--min-free-gib``). All output stays outside Git.

    python3 tools/sc4_ride.py --pid PID --rates 20 --hours 2

Stop early with Ctrl-C or SIGTERM; the run finishes the current step cleanly.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

import sc4_budget_probe
import sc4_clock_probe
import sc4_dynamic


def mult_table(handle: int, budget: int, k: int) -> float:
    table = struct.unpack("<I", os.pread(handle, 4, budget + 0x814))[0]
    return struct.unpack("<f", os.pread(handle, 4, table + 4 * k))[0]


def difficulty(handle: int, budget: int) -> int:
    owner = struct.unpack("<I", os.pread(handle, 4, budget + 0x18))[0]
    return struct.unpack("<I", os.pread(handle, 4, owner + 0x28))[0]


def predict(metrics: dict, mult: float) -> float:
    return sum(b * r for b, r in zip(metrics["tax_category_totals"], metrics["tax_rates"])) * mult / 1200


def write_rates(pid: int, budget: int, rates: list[float]) -> list[float]:
    with sc4_dynamic.Frozen(pid):
        with open(f"/proc/{pid}/mem", "r+b", buffering=0) as mem:
            old = []
            for index, rate in enumerate(rates):
                address = budget + sc4_budget_probe.RATE_BASE + index * sc4_budget_probe.RECORD_STRIDE
                mem.seek(address)
                old.append(struct.unpack("<f", mem.read(4))[0])
                mem.seek(address)
                mem.write(struct.pack("<f", rate))
    return old


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--rates", type=float, nargs="+", required=True, help="one rate for all 12 categories, or 12 rates")
    ap.add_argument("--hours", type=float, default=2.0)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--dump-every", type=int, default=1, help="dump every N month rollovers (0 = never)")
    ap.add_argument("--min-free-gib", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=sc4_dynamic.DEFAULT_ROOT / time.strftime("ride-%Y%m%dT%H%M%S"))
    ap.add_argument("--image-name", default="SimCity 4.exe")
    args = ap.parse_args()

    rates = args.rates * 12 if len(args.rates) == 1 else args.rates
    if len(rates) != 12 or not all(0 <= r <= 100 for r in rates):
        raise SystemExit("give 1 or 12 rates in 0..100")
    out = sc4_dynamic.outside_repo(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stop = {"flag": False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.__setitem__("flag", True))

    base = sc4_budget_probe.image_base(args.pid, args.image_name)
    handle = os.open(f"/proc/{args.pid}/mem", os.O_RDONLY)
    budget = sc4_budget_probe.read_value(handle, base + sc4_budget_probe.BUDGET_GLOBAL_RVA, "<I")
    k = difficulty(handle, budget)
    mult = mult_table(handle, budget, k)
    original = write_rates(args.pid, budget, rates)
    meta = {"started": sc4_dynamic.utc_now(), "pid": args.pid, "held_rates": rates, "original_rates": original,
            "difficulty_index": k, "mult": mult, "interval": args.interval}
    (out / "ride.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"out": str(out), **meta}), flush=True)

    samples = open(out / "samples.jsonl", "a", buffering=1)
    months = open(out / "months.jsonl", "a", buffering=1)
    deadline = time.monotonic() + args.hours * 3600
    previous = None
    rollovers = 0
    compressors: list[subprocess.Popen] = []
    try:
        while not stop["flag"] and time.monotonic() < deadline:
            if not Path(f"/proc/{args.pid}").exists():
                print("SC4 process exited", flush=True)
                break
            try:
                metrics = dict(sc4_budget_probe.sample(handle, args.pid, base)["metrics"])
                metrics.update(sc4_clock_probe.sample(handle, args.pid, base)["metrics"])
            except Exception as exc:  # transient during load screens
                samples.write(json.dumps({"t": time.time(), "error": str(exc)}) + "\n")
                time.sleep(args.interval)
                continue
            samples.write(json.dumps({"t": round(time.time(), 3), **metrics}) + "\n")
            if previous and metrics["simulation_month"] != previous["simulation_month"]:
                rollovers += 1
                predicted = predict(metrics, mult)
                row = {
                    "date": f"{metrics['simulation_year']}-{metrics['simulation_month']:02d}",
                    "tax_income": metrics["tax_income"],
                    "predicted": round(predicted, 3),
                    "residual": metrics["tax_income"] - math.trunc(predicted),
                    "funds": metrics["funds_public"],
                    "funds_delta": metrics["funds_public"] - previous["funds_public"],
                    "expenses": metrics["tax_income"] - (metrics["funds_public"] - previous["funds_public"]),
                    "bases": metrics["tax_category_totals"],
                    "rates": metrics["tax_rates"],
                }
                if metrics["tax_rates"] != rates:
                    row["rates_drifted"] = metrics["tax_rates"]
                    write_rates(args.pid, budget, rates)
                if args.dump_every and rollovers % args.dump_every == 0:
                    free = shutil.disk_usage(out).free / 2**30
                    if free >= args.min_free_gib:
                        label = f"m{rollovers:03d}-{row['date']}"
                        subprocess.run([sys.executable, str(Path(__file__).with_name("sc4_dynamic.py")), "dump",
                                        "--pid", str(args.pid), "--root", str(out / "dumps"), "--label", label,
                                        "--note", f"ride rollover {row['date']}"], capture_output=True, check=False)
                        blob = out / "dumps" / label / "memory.bin"
                        if blob.exists():
                            compressors.append(subprocess.Popen(["zstd", "-1", "-q", "--rm", "-T2", str(blob)]))
                            row["dump"] = label
                    else:
                        row["dump_skipped_free_gib"] = round(free, 1)
                months.write(json.dumps(row) + "\n")
                print(json.dumps({k2: row[k2] for k2 in ("date", "tax_income", "predicted", "residual", "funds_delta", "expenses")}
                                 | {"base_sum": sum(row["bases"])}), flush=True)
            previous = metrics
            time.sleep(args.interval)
    finally:
        os.close(handle)
        for proc in compressors:
            proc.wait()
        meta["ended"] = sc4_dynamic.utc_now()
        meta["rollovers"] = rollovers
        (out / "ride.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"done": str(out), "rollovers": rollovers}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
