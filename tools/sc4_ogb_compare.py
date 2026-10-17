#!/usr/bin/env python3
"""Replay a recorded SC4 ride through the OpenGlassBox sidecar and score it.

For every month in ``<ride>/samples.jsonl`` the SC4 state is read a few game
days after the rollover (after the funds write and the in-place base rebuild
have settled). Two comparisons run against the sidecar's ``sc4-tax-v0.3``
budget slice:

- tax (closed loop on inputs): the sidecar gets that month's SC4 rates and
  bases and must reproduce SC4's published tax income;
- funds (open loop): the sidecar is seeded with SC4 funds once, then carries
  its own balance forward with a fixed monthly expense. Drift exposes what the
  candidate does not model yet (expense changes, one-off costs, ...).

    python3 tools/sc4_ogb_compare.py ~/.cache/opensc4/dynamic/ride-tax20
"""

from __future__ import annotations

import argparse
import calendar
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SIDECAR = REPO / "sc4-lab" / "adapters" / "openglassbox" / "openglassbox_sidecar.py"
REPORT_SCHEMA = "sc4-lab.sc4-ogb-compare.v1"


class Sidecar:
    def __init__(self) -> None:
        self.proc = subprocess.Popen([sys.executable, str(SIDECAR)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, bufsize=1)
        self.request_id = 0
        self.hello = self.call("hello", {})

    def call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.request_id += 1
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps({"protocol": "opensc4.adapter.v1", "request_id": self.request_id,
                                          "operation": operation, "payload": payload}) + "\n")
        reply = json.loads(self.proc.stdout.readline())
        if not reply.get("ok"):
            raise RuntimeError(f"sidecar {operation} failed: {reply.get('error')}")
        return reply["result"]

    def close(self) -> None:
        try:
            self.call("shutdown", {})
        finally:
            self.proc.wait(timeout=5)


def settled_months(samples: list[dict[str, Any]], settle_days: int) -> list[dict[str, Any]]:
    """One SC4 state per month, taken settle_days after an observed rollover.

    The first month in a capture is dropped: its rollover was not observed, so
    inputs seen in it (for example a rate poked mid-month) may differ from the
    inputs that produced its published tax.
    """
    months: list[dict[str, Any]] = []
    current = None
    first_serial = None
    taken = True
    for row in samples:
        key = (row["simulation_year"], row["simulation_month"])
        if key != current:
            observed_rollover = current is not None
            current, first_serial, taken = key, row["simulation_date_serial"], not observed_rollover
            continue
        if not taken and row["simulation_date_serial"] - first_serial >= settle_days:
            months.append(row)
            taken = True
    return months


def days_in_previous_month(row: dict[str, Any]) -> int:
    year, month = row["simulation_year"], row["simulation_month"] - 1
    if month == 0:
        year, month = year - 1, 12
    return calendar.monthrange(year, month)[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ride", type=Path)
    ap.add_argument("--settle-days", type=int, default=3)
    ap.add_argument("--expenses", type=int, help="fixed monthly expense for the open-loop funds model (default: first clean month)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    meta = json.loads((args.ride / "ride.json").read_text())
    samples = [json.loads(line) for line in (args.ride / "samples.jsonl").read_text().splitlines()]
    samples = [row for row in samples if "error" not in row]
    months = settled_months(samples, args.settle_days)
    if len(months) < 2:
        raise SystemExit("need at least two settled months")
    mult = float(meta.get("mult", 1.0))
    expenses = args.expenses
    if expenses is None:
        expenses = months[1]["tax_income"] - (months[1]["funds_public"] - months[0]["funds_public"])

    sidecar = Sidecar()
    rows = []
    try:
        ogb_funds = months[0]["funds_public"]
        for previous, month in zip(months, months[1:]):
            # tax: SC4's own inputs for this month (rates/bases as settled after rollover)
            sidecar.call("command", {"type": "budget_set", "funds": ogb_funds, "expenses": expenses, "mult": mult,
                                     "rates": month["tax_rates"], "bases": month["tax_category_totals"]})
            budget = sidecar.call("command", {"type": "budget_month", "days": days_in_previous_month(month)})["budget"]
            ogb_funds = budget["funds"]
            sc4_expenses = month["tax_income"] - (month["funds_public"] - previous["funds_public"])
            rows.append({
                "date": f"{month['simulation_year']}-{month['simulation_month']:02d}",
                "sc4_tax": month["tax_income"], "ogb_tax": budget["tax"], "tax_residual": month["tax_income"] - budget["tax"],
                "sc4_funds": month["funds_public"], "ogb_funds": ogb_funds, "funds_drift": month["funds_public"] - ogb_funds,
                "sc4_expenses": sc4_expenses, "model_expenses": expenses,
                "base_sum": sum(month["tax_category_totals"]),
            })
    finally:
        sidecar.close()

    exact = sum(row["tax_residual"] == 0 for row in rows)
    report = {
        "schema": REPORT_SCHEMA,
        "ride": str(args.ride),
        "backend_fingerprint": sidecar.hello.get("backend_fingerprint"),
        "ruleset": "sc4-tax-v0.3",
        "settle_days": args.settle_days,
        "model_expenses": expenses,
        "months": len(rows),
        "tax_exact_months": exact,
        "tax_max_abs_residual": max(abs(row["tax_residual"]) for row in rows),
        "funds_final_drift": rows[-1]["funds_drift"],
        "funds_max_abs_drift": max(abs(row["funds_drift"]) for row in rows),
        "expense_changes": [row for row in rows if row["sc4_expenses"] != expenses],
        "rows": rows,
    }
    out = args.out or args.ride / "ogb-compare.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"OpenGlassBox {report['backend_fingerprint']}  ruleset {report['ruleset']}")
    print(f"months {len(rows)}  tax exact {exact}/{len(rows)}  max |tax residual| {report['tax_max_abs_residual']}")
    print(f"funds open-loop drift: final {report['funds_final_drift']}  max {report['funds_max_abs_drift']}  (model expenses {expenses}/month)")
    print(f"months where SC4 expenses differed from the model: {len(report['expense_changes'])}")
    for row in report["expense_changes"][:12]:
        print(f"  {row['date']}  sc4 expenses {row['sc4_expenses']}  tax {row['sc4_tax']}  funds {row['sc4_funds']}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
