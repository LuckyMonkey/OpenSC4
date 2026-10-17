#!/usr/bin/env python3
"""TAX_001 three-way pipeline: SC4 reference vs OpenGlassBox vs AI-fitted model.

    extract  ride dir -> reference observations (one settled record per month)
    verify   reference observations -> independent verifier, exact match or fail

Reference records are scalar measurements (rates, bases, multiplier, published
tax income) taken from the live game; no raw memory or game data. Each record
is labelled ``derivation`` (used to find the rule) or ``held_out``. The AI model
is fitted on derivation records only; both candidates are scored on held-out
records by ``sc4-lab/verifier/compare.py`` with the fixed exact policy.

    python3 tools/sc4_tax_pipeline.py extract ~/.cache/opensc4/dynamic/ride-tax20 \
        --split held_out --out sc4-lab/reference/observations/TAX_001/ride-tax20.jsonl
    python3 tools/sc4_tax_pipeline.py verify sc4-lab/reference/observations/TAX_001/*.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sc4-lab" / "verifier"))
sys.path.insert(0, str(REPO / "sc4-lab" / "candidate"))
sys.path.insert(0, str(REPO / "tools"))

import compare as verifier  # noqa: E402
from sc4_ogb_compare import Sidecar, days_in_previous_month, settled_months  # noqa: E402
from sc4_tax_fit import TaxFit  # noqa: E402

EXE_SHA256 = "f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153"
POLICY = REPO / "sc4-lab" / "verifier" / "tolerances.tax.v1.json"


def observation(test_id: str, value: int, extra: dict[str, Any]) -> dict[str, Any]:
    return {"schema": verifier.OBSERVATION_SCHEMA, "test_id": test_id,
            "metrics": {"tax_income": {"status": "observed", "value": int(value), "unit": "simoleons/month"}}, **extra}


def extract(args: argparse.Namespace) -> int:
    meta = json.loads((args.ride / "ride.json").read_text()) if (args.ride / "ride.json").exists() else {}
    rows = []
    for name in ("samples.jsonl",) if (args.ride / "samples.jsonl").exists() else ():
        rows = [json.loads(line) for line in (args.ride / name).read_text().splitlines()]
    if args.series:
        rows = [json.loads(line) for line in args.series.read_text().splitlines()]
        rows = [{**row.get("metrics", {}), **row} for row in rows]
    rows = [row for row in rows if "error" not in row and "simulation_date_serial" in row]
    months = settled_months(rows, args.settle_days)
    mult = float(meta.get("mult", args.mult))
    records = []
    for row in months:
        records.append(observation("TAX_001", row["tax_income"], {
            "sample": {"simulation_year": row["simulation_year"], "simulation_month": row["simulation_month"],
                       "simulation_date_serial": row["simulation_date_serial"], "simulation_tick": "unknown",
                       "settled_days_after_rollover": args.settle_days},
            "inputs": {"rates": row["tax_rates"], "bases": row["tax_category_totals"], "mult": mult},
            "split": args.split,
            "provenance": {"executable_sha256": EXE_SHA256, "method": "live memory, sc4_budget_probe paths",
                           "source": args.label or args.ride.name, "raw_bytes_recorded": False},
        }))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    print(json.dumps({"out": str(args.out), "records": len(records), "split": args.split}))
    return 0


def verify(args: argparse.Namespace) -> int:
    policy = json.loads(POLICY.read_text())
    records = [json.loads(line) for path in args.reference for line in path.read_text().splitlines() if line.strip()]
    derivation = [r for r in records if r["split"] == "derivation"]
    held_out = [r for r in records if r["split"] == "held_out"]
    fit = TaxFit(derivation)

    sidecar = Sidecar()
    results = []
    try:
        for record in records:
            inputs = record["inputs"]
            sidecar.call("command", {"type": "budget_set", "funds": 0, "expenses": 0, "mult": inputs["mult"],
                                     "rates": inputs["rates"], "bases": inputs["bases"]})
            ogb = sidecar.call("command", {"type": "budget_month",
                                           "days": days_in_previous_month(record["sample"])})["budget"]["tax"]
            ai = fit.predict(inputs)
            fingerprint = {"backend_id": sidecar.hello.get("backend_fingerprint")}
            verdict_ogb = verifier.compare(record, observation("TAX_001", ogb, fingerprint), policy)
            verdict_ai = verifier.compare(record, observation("TAX_001", ai, {"backend_id": "ai-fit"}), policy)
            verdict_model = verifier.compare(observation("TAX_001", ai, {}), observation("TAX_001", ogb, {}), policy)
            sc4 = record["metrics"]["tax_income"]["value"]
            results.append({
                "date": f"{record['sample']['simulation_year']}-{record['sample']['simulation_month']:02d}",
                "split": record["split"], "sc4": sc4, "ogb": ogb, "ai": ai,
                "E_ogb": sc4 - ogb, "E_ai": sc4 - ai, "E_model": ai - ogb,
                "ogb_pass": verdict_ogb["passed"], "ai_pass": verdict_ai["passed"], "model_agree": verdict_model["passed"],
            })
    finally:
        sidecar.close()

    def score(split: str) -> dict[str, Any]:
        rows = [r for r in results if r["split"] == split]
        return {"months": len(rows),
                "ogb_exact": sum(r["ogb_pass"] for r in rows), "ai_exact": sum(r["ai_pass"] for r in rows),
                "models_agree": sum(r["model_agree"] for r in rows),
                "distinct_tax_values": len(Counter(r["sc4"] for r in rows))}

    report = {
        "schema": "sc4-lab.tax001-three-way.v1",
        "spec": "sc4-lab/specifications/TAX_001-monthly-tax-income.md",
        "policy": str(POLICY.relative_to(REPO)),
        "executable_sha256": EXE_SHA256,
        "ogb_backend": sidecar.hello.get("backend_fingerprint"),
        "ai_model": fit.describe(),
        "derivation": score("derivation"),
        "held_out": score("held_out"),
        "failures": [r for r in results if not (r["ogb_pass"] and r["ai_pass"])],
        "rows": results,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    held = report["held_out"]
    ogb_passed = held["months"] > 0 and held["ogb_exact"] == held["months"]
    ai_passed = held["months"] > 0 and held["ai_exact"] == held["months"]
    report["verdict"] = {"openglassbox": "EXACT MATCH" if ogb_passed else "FAIL",
                         "ai_fit": "EXACT MATCH" if ai_passed else "FAIL"}
    print(f"OpenGlassBox backend : {report['ogb_backend']}")
    print(f"AI model             : 1/k in [{report['ai_model']['one_over_k_interval'][0]:.6f}, "
          f"{report['ai_model']['one_over_k_interval'][1]:.6f}] from {fit.months} derivation months")
    for split in ("derivation", "held_out"):
        s = report[split]
        print(f"{split:<11}: {s['months']:>4} months ({s['distinct_tax_values']} distinct tax values)  "
              f"OGB exact {s['ogb_exact']}/{s['months']}  AI exact {s['ai_exact']}/{s['months']}  "
              f"AI==OGB {s['models_agree']}/{s['months']}")
    for row in report["failures"][:10]:
        print(f"  FAIL {row['date']} [{row['split']}] sc4={row['sc4']} ogb={row['ogb']} ai={row['ai']}")
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"TAX_001 HELD-OUT  OpenGlassBox: {report['verdict']['openglassbox']}   AI fit: {report['verdict']['ai_fit']}")
    print(f"report: {args.report}")
    # Exit status tracks the implementation under test; the AI fit is a hypothesis.
    return 0 if ogb_passed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    e = sub.add_parser("extract")
    e.add_argument("ride", type=Path, help="ride dir with samples.jsonl (or any dir with --series)")
    e.add_argument("--series", type=Path, help="sc4_system_id capture series instead of a ride")
    e.add_argument("--split", choices=("derivation", "held_out"), required=True)
    e.add_argument("--settle-days", type=int, default=3)
    e.add_argument("--mult", type=float, default=1.0)
    e.add_argument("--label")
    e.add_argument("--out", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("reference", type=Path, nargs="+")
    v.add_argument("--report", type=Path, default=Path("/tmp/opensc4-tax001-three-way.json"))
    args = ap.parse_args()
    return extract(args) if args.command == "extract" else verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
