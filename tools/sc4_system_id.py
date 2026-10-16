#!/usr/bin/env python3
"""Record and analyze controlled SC4 response series.

The capture path is read-only and reuses the verified budget telemetry paths.
The analysis path operates on JSON Lines produced by this tool. It computes
paired deltas, finite-difference sensitivities, discrete derivatives, step
response summaries, and a small sensitivity matrix. It never changes the
reference process, reference observations, or acceptance policy.

Important boundary: the current budget probe has no verified SC4 simulation
month/tick field. Captures therefore retain sample index and wall-clock
elapsed time, while explicitly marking the simulation-time axis unavailable.
These are useful response measurements, but they are not month-level claims.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import sc4_budget_probe
from memory_observatory import ObservatoryError, open_memory, process_identity


SERIES_SCHEMA = "sc4-lab.sc4-system-id-series.v1"
ANALYSIS_SCHEMA = "sc4-lab.sc4-system-id-analysis.v1"
PLAN_SCHEMA = "sc4-lab.sc4-system-id-plan.v1"


class SystemIdError(Exception):
    """Raised for invalid or incomplete system-identification data."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, sort_keys=True) + "\n")


def read_series(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SystemIdError(f"cannot read series {path}: {exc}") from exc
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemIdError(f"invalid JSON at {path}:{line_number}") from exc
        if not isinstance(value, dict) or value.get("schema") != SERIES_SCHEMA:
            raise SystemIdError(f"unexpected series schema at {path}:{line_number}")
        values.append(value)
    if not values:
        raise SystemIdError(f"series is empty: {path}")
    return values


def numeric(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SystemIdError(f"metric {label!r} is not numeric: {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise SystemIdError(f"metric {label!r} is not finite")
    return result


def intervention_payload(args: argparse.Namespace) -> dict[str, Any]:
    before = args.input_before
    after = args.input_after
    delta = None if before is None or after is None else after - before
    return {
        "field": args.input_field,
        "before": before,
        "after": after,
        "delta": delta,
        "unit": args.input_unit,
        "application": args.application,
    }


def capture(args: argparse.Namespace) -> int:
    if args.duration < 0 or args.interval <= 0:
        raise SystemIdError("duration must be non-negative and interval must be positive")
    identity = process_identity(args.pid)
    base = sc4_budget_probe.image_base(args.pid, args.image_name)
    handle = open_memory(args.pid)
    run_id = args.run_id or uuid.uuid4().hex
    intervention = intervention_payload(args)
    started = time.monotonic()
    deadline = started + args.duration
    records: list[dict[str, Any]] = []
    sample_index = 0
    try:
        while True:
            sample = sc4_budget_probe.sample(handle, args.pid, base)
            records.append(
                {
                    "schema": SERIES_SCHEMA,
                    "captured_utc": sample["captured_utc"],
                    "experiment_id": args.experiment_id,
                    "run_id": run_id,
                    "phase": args.phase,
                    "sample_index": sample_index,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "time_axis": {
                        "primary": "sample_index",
                        "simulation_time_status": "unavailable",
                        "wall_clock_seconds": "diagnostic_only",
                    },
                    "intervention": intervention,
                    "source": {
                        "tool": "tools/sc4_system_id.py",
                        "budget_probe_schema": sample["schema"],
                        "pid": args.pid,
                        "process": identity,
                        "image_base": sample["image_base"],
                        "raw_bytes_recorded": False,
                        "raw_memory_written": False,
                    },
                    "metrics": sample["metrics"],
                    "evidence": sample["evidence"],
                    "provenance": {
                        "observation_kind": "live-memory-authoritative",
                        "reference_claim": True,
                        "equivalence_claim": False,
                    },
                }
            )
            sample_index += 1
            if time.monotonic() >= deadline:
                break
            time.sleep(args.interval)
    finally:
        os.close(handle)
    write_jsonl(args.out, records)
    print(json.dumps({"out": str(args.out), "run_id": run_id, "samples": len(records)}))
    return 0


def pair_by_index(baseline: list[dict[str, Any]], experiment: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    baseline_by_index = {int(item["sample_index"]): item for item in baseline}
    experiment_by_index = {int(item["sample_index"]): item for item in experiment}
    shared = sorted(set(baseline_by_index) & set(experiment_by_index))
    if not shared:
        raise SystemIdError("baseline and experiment have no shared sample indices")
    return [(baseline_by_index[index], experiment_by_index[index]) for index in shared]


def derivative(values: list[float], axis: list[float]) -> list[float | None]:
    """Return a finite-difference derivative with one-sided endpoints."""
    if len(values) != len(axis):
        raise SystemIdError("values and axis lengths differ")
    if len(values) == 1:
        return [None]
    result: list[float | None] = []
    for index in range(len(values)):
        if index == 0:
            left, right = 0, 1
        elif index == len(values) - 1:
            left, right = index - 1, index
        else:
            left, right = index - 1, index + 1
        dx = axis[right] - axis[left]
        result.append(None if dx == 0 else (values[right] - values[left]) / dx)
    return result


def trapezoid(values: list[float], axis: list[float]) -> float | None:
    if len(values) < 2:
        return None
    total = 0.0
    for left, right in zip(range(len(values) - 1), range(1, len(values))):
        total += (values[left] + values[right]) * (axis[right] - axis[left]) / 2.0
    return total


def summarize(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "first": None, "last": None, "min": None, "max": None, "mean": None, "stdev": None}
    return {
        "count": len(values),
        "first": values[0],
        "last": values[-1],
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def analyze(args: argparse.Namespace) -> int:
    baseline = read_series(args.baseline)
    experiment = read_series(args.experiment)
    pairs = pair_by_index(baseline, experiment)
    metrics = args.metric or ["funds_public", "tax_income", "tax_category_total_sum"]
    first_intervention = experiment[0].get("intervention", {})
    input_delta = args.input_delta
    if input_delta is None:
        input_delta = first_intervention.get("delta")
    if input_delta is None or float(input_delta) == 0:
        raise SystemIdError("provide a non-zero --input-delta or capture intervention metadata with before/after")
    input_delta = float(input_delta)

    response: dict[str, Any] = {}
    sensitivity_matrix: list[dict[str, Any]] = []
    for metric in metrics:
        baseline_values = [numeric(left.get("metrics", {}).get(metric), metric) for left, _ in pairs]
        experiment_values = [numeric(right.get("metrics", {}).get(metric), metric) for _, right in pairs]
        axes = [float(right["elapsed_seconds"]) for _, right in pairs]
        paired_delta = [right - left for left, right in zip(baseline_values, experiment_values)]
        sensitivities = [value / input_delta for value in paired_delta]
        response[metric] = {
            "baseline": summarize(baseline_values),
            "experiment": summarize(experiment_values),
            "paired_delta": summarize(paired_delta),
            "finite_difference_sensitivity": sensitivities,
            "response_derivative_per_wall_second": derivative(paired_delta, axes),
            "response_auc_delta_wall_seconds": trapezoid(paired_delta, axes),
            "first_nonzero_delta_sample": next(
                (index for index, value in enumerate(paired_delta) if value != 0), None
            ),
        }
        sensitivity_matrix.extend(
            {
                "input_field": first_intervention.get("field"),
                "output_metric": metric,
                "sample_index": index,
                "sensitivity": value,
            }
            for index, value in enumerate(sensitivities)
        )

    result = {
        "schema": ANALYSIS_SCHEMA,
        "created_utc": utc_now(),
        "experiment_id": experiment[0].get("experiment_id"),
        "baseline": {"path": str(args.baseline), "run_id": baseline[0].get("run_id"), "samples": len(baseline)},
        "experiment": {"path": str(args.experiment), "run_id": experiment[0].get("run_id"), "samples": len(experiment)},
        "intervention": {
            **first_intervention,
            "delta_used_for_sensitivity": input_delta,
        },
        "pairing": {
            "method": "sample_index_exact_match",
            "paired_samples": len(pairs),
            "baseline_only_samples": len(baseline) - len(pairs),
            "experiment_only_samples": len(experiment) - len(pairs),
            "simulation_time_status": "unavailable; wall-clock axis is diagnostic only",
        },
        "metrics": response,
        "sensitivity_matrix": sensitivity_matrix,
        "interpretation": {
            "status": "measurement_summary",
            "causation_claim": False,
            "equivalence_claim": False,
            "next_step": "repeat from an identical saved state and compare the response curve",
        },
    }
    write_json(args.out, result)
    print(json.dumps({"out": str(args.out), "paired_samples": len(pairs), "metrics": list(response)}))
    return 0


def plan(args: argparse.Namespace) -> int:
    values = [float(value) for value in args.values]
    if not values:
        raise SystemIdError("at least one intervention value is required")
    runs = []
    for value in values:
        runs.append({
            "run_id": f"{args.experiment_id}-{value:g}",
            "phase": "experiment" if value != args.baseline_value else "baseline",
            "input": {"field": args.input_field, "value": value, "unit": args.input_unit},
            "required_start_state": "same disposable save snapshot",
            "sampling": {
                "duration_seconds": args.duration,
                "interval_seconds": args.interval,
                "simulation_time": "required before acceptance; current probe does not provide it",
            },
        })
    result = {
        "schema": PLAN_SCHEMA,
        "created_utc": utc_now(),
        "experiment_id": args.experiment_id,
        "question": args.question,
        "input": {"field": args.input_field, "unit": args.input_unit, "baseline": args.baseline_value},
        "values": values,
        "runs": runs,
        "metrics": args.metric or ["funds_public", "tax_income", "tax_category_total_sum"],
        "controls": [
            "same save snapshot for every run",
            "same game speed and pause state",
            "same sampling interval",
            "record executable identity and target hash",
            "keep reference outputs private and immutable",
        ],
        "status": "plan_only; no reference observation is fabricated",
    }
    write_json(args.out, result)
    print(json.dumps({"out": str(args.out), "runs": len(runs)}))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    capture_parser = sub.add_parser("capture", help="record read-only live budget telemetry")
    capture_parser.add_argument("--pid", type=int, required=True)
    capture_parser.add_argument("--experiment-id", required=True)
    capture_parser.add_argument("--run-id")
    capture_parser.add_argument("--phase", choices=("baseline", "control", "experiment", "recovery"), default="experiment")
    capture_parser.add_argument("--input-field", default="unspecified")
    capture_parser.add_argument("--input-before", type=float)
    capture_parser.add_argument("--input-after", type=float)
    capture_parser.add_argument("--input-unit", default="unknown")
    capture_parser.add_argument("--application", choices=("native_setter", "ui", "memory_write", "none"), default="none")
    capture_parser.add_argument("--duration", type=float, default=0.0)
    capture_parser.add_argument("--interval", type=float, default=2.0)
    capture_parser.add_argument("--image-name", default="SimCity 4.exe")
    capture_parser.add_argument("--out", type=Path, required=True)

    analyze_parser = sub.add_parser("analyze", help="compare paired baseline and experiment series")
    analyze_parser.add_argument("--baseline", type=Path, required=True)
    analyze_parser.add_argument("--experiment", type=Path, required=True)
    analyze_parser.add_argument("--input-delta", type=float)
    analyze_parser.add_argument("--metric", action="append")
    analyze_parser.add_argument("--out", type=Path, required=True)

    plan_parser = sub.add_parser("plan", help="write a controlled intervention plan")
    plan_parser.add_argument("--experiment-id", required=True)
    plan_parser.add_argument("--question", required=True)
    plan_parser.add_argument("--input-field", required=True)
    plan_parser.add_argument("--input-unit", default="unknown")
    plan_parser.add_argument("--baseline-value", type=float, required=True)
    plan_parser.add_argument("--values", nargs="+", required=True)
    plan_parser.add_argument("--duration", type=float, default=0.0)
    plan_parser.add_argument("--interval", type=float, default=2.0)
    plan_parser.add_argument("--metric", action="append")
    plan_parser.add_argument("--out", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "capture":
            return capture(args)
        if args.command == "analyze":
            return analyze(args)
        return plan(args)
    except (OSError, ObservatoryError, SystemIdError, ValueError) as exc:
        print(f"SC4 SYSTEM ID FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
