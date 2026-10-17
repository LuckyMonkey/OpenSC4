#!/usr/bin/env python3
"""Record and analyze controlled SC4 response series.

The capture path is read-only and reuses the verified budget telemetry paths.
The analysis path operates on JSON Lines produced by this tool. It computes
paired deltas, finite-difference sensitivities, discrete derivatives, step
response summaries, and a small sensitivity matrix. It never changes the
reference process, reference observations, or acceptance policy.

Important boundary: the budget probe has no verified SC4 simulation tick.
Captures retain sample index and wall-clock elapsed time, and can optionally
include the native simulation-date candidate from ``sc4_clock_probe``. Those
date samples are useful for alignment, but are not yet month-level claims.
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
import sc4_clock_probe
import reference_capture
from memory_observatory import ObservatoryError, open_memory, process_identity


SERIES_SCHEMA = "sc4-lab.sc4-system-id-series.v1"
ANALYSIS_SCHEMA = "sc4-lab.sc4-system-id-analysis.v1"
PLAN_SCHEMA = "sc4-lab.sc4-system-id-plan.v1"
BOUNDARY_SCHEMA = "sc4-lab.sc4-system-id-boundaries.v1"
BOUNDARY_METRICS = ("funds_public", "funds_working_candidate", "tax_income", "tax_category_total_sum")


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
    starting_save = None
    if args.save is not None:
        try:
            starting_save = reference_capture.file_manifest(args.save, args.save_chunk_size)
        except reference_capture.CaptureError as exc:
            raise SystemIdError(str(exc)) from exc
    started = time.monotonic()
    deadline = started + args.duration
    records: list[dict[str, Any]] = []
    sample_index = 0
    try:
        while True:
            sample = sc4_budget_probe.sample(handle, args.pid, base)
            clock_sample = None
            clock_error = None
            try:
                clock_sample = sc4_clock_probe.sample(handle, args.pid, base)
            except sc4_clock_probe.ClockProbeError as exc:
                if args.with_clock:
                    raise SystemIdError(f"clock probe failed: {exc}") from exc
                clock_error = str(exc)
            metrics = dict(sample["metrics"])
            evidence = dict(sample["evidence"])
            source = {
                "tool": "tools/sc4_system_id.py",
                "budget_probe_schema": sample["schema"],
                "pid": args.pid,
                "process": identity,
                "image_base": sample["image_base"],
                "raw_bytes_recorded": False,
                "raw_memory_written": False,
                "starting_save": starting_save,
                "clock_probe": "enabled" if args.with_clock else "opportunistic",
            }
            if clock_sample is not None:
                metrics.update(clock_sample["metrics"])
                evidence.update({f"clock_{key}": value for key, value in clock_sample["evidence"].items()})
                source["clock_resolution"] = clock_sample["native_resolution"]
            elif clock_error is not None:
                source["clock_error"] = clock_error
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
                        "primary": "simulation_date_serial" if clock_sample is not None else "sample_index",
                        "simulation_time_status": "native-date-candidate" if clock_sample is not None else "unavailable",
                        "simulation_tick": "not recovered",
                        "wall_clock_seconds": "diagnostic_only",
                    },
                    "intervention": intervention,
                    "source": source,
                    "metrics": metrics,
                    "evidence": evidence,
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
    date_candidate_present = all(
        "simulation_date_serial" in item.get("metrics", {})
        for pair in pairs
        for item in pair
    )
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
            "simulation_time_status": (
                "native-date-candidate present; wall-clock axis remains diagnostic"
                if date_candidate_present
                else "unavailable; wall-clock axis is diagnostic only"
            ),
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


def read_analysis(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemIdError(f"cannot read analysis {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != ANALYSIS_SCHEMA:
        raise SystemIdError(f"unexpected analysis schema: {path}")
    return value


def sign_consistency(values: list[float]) -> str:
    signs = {1 if value > 0 else -1 if value < 0 else 0 for value in values}
    if not signs:
        return "no_values"
    if len(signs) == 1:
        return {1: "positive", -1: "negative", 0: "zero"}[next(iter(signs))]
    return "mixed"


def aggregate(args: argparse.Namespace) -> int:
    analyses = [read_analysis(path) for path in args.analysis]
    if len(analyses) < 2:
        raise SystemIdError("aggregate requires at least two analysis files")
    first_intervention = analyses[0].get("intervention", {})
    input_field = first_intervention.get("field")
    if any(item.get("intervention", {}).get("field") != input_field for item in analyses):
        raise SystemIdError("all analyses must use the same input field")
    metric_names = args.metric or sorted(
        {metric for item in analyses for metric in item.get("metrics", {})}
    )
    cases: dict[str, dict[str, Any]] = {}
    for item in analyses:
        intervention = item.get("intervention", {})
        value = intervention.get("after")
        if value is None:
            raise SystemIdError("every analysis needs an intervention after value")
        key = str(value)
        case = cases.setdefault(key, {"value": value, "analyses": []})
        case["analyses"].append(item)

    aggregated_metrics: dict[str, Any] = {}
    for metric in metric_names:
        metric_cases: list[dict[str, Any]] = []
        for case in cases.values():
            values: list[float] = []
            deltas: list[float] = []
            response_by_sample: dict[int, list[float]] = {}
            for item in case["analyses"]:
                metric_result = item.get("metrics", {}).get(metric)
                if not metric_result:
                    continue
                sensitivity = metric_result.get("finite_difference_sensitivity", [])
                paired_delta = metric_result.get("paired_delta", {})
                values.append(numeric(sensitivity[-1], f"{metric}.sensitivity")) if sensitivity else None
                if paired_delta.get("last") is not None:
                    deltas.append(numeric(paired_delta["last"], f"{metric}.paired_delta"))
                for index, value in enumerate(sensitivity):
                    response_by_sample.setdefault(index, []).append(numeric(value, f"{metric}.sensitivity"))
            sample_means = [
                {"sample_index": index, **summarize(sample_values)}
                for index, sample_values in sorted(response_by_sample.items())
            ]
            metric_cases.append(
                {
                    "input_after": case["value"],
                    "replicates": len(values),
                    "final_sensitivity": summarize(values),
                    "final_paired_delta": summarize(deltas),
                    "final_sensitivity_sign_consistency": sign_consistency(values),
                    "response_by_sample": sample_means,
                }
            )
        aggregated_metrics[metric] = sorted(metric_cases, key=lambda entry: float(entry["input_after"]))

    result = {
        "schema": "sc4-lab.sc4-system-id-aggregate.v1",
        "created_utc": utc_now(),
        "input": {
            "field": input_field,
            "unit": first_intervention.get("unit"),
            "analysis_files": [str(path) for path in args.analysis],
        },
        "metrics": aggregated_metrics,
        "interpretation": {
            "status": "replicate_summary",
            "reference_claim": True,
            "causation_claim": False,
            "equivalence_claim": False,
            "simulation_time_status": "unavailable; wall-clock axis remains diagnostic",
            "next_step": "use sign consistency and response variance to choose a held-out intervention",
        },
    }
    write_json(args.out, result)
    print(json.dumps({"out": str(args.out), "analyses": len(analyses), "metrics": list(aggregated_metrics)}))
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


def boundary_report(series: list[dict[str, Any]], metrics: list[str], pause_samples: int) -> dict[str, Any]:
    """Correlate native date-serial steps with budget-field changes in one series."""
    if len(series) < 2:
        raise SystemIdError("boundary analysis needs at least two samples")
    serials = []
    for item in series:
        value = item.get("metrics", {}).get("simulation_date_serial")
        if value is None:
            raise SystemIdError(f"sample {item.get('sample_index')} has no simulation_date_serial; capture with --with-clock")
        serials.append(int(value))

    date_steps: list[dict[str, Any]] = []
    metric_changes: list[dict[str, Any]] = []
    stationary_runs: list[dict[str, Any]] = []
    run_start = 0
    for index in range(1, len(series)):
        before, after = series[index - 1], series[index]
        step = serials[index] - serials[index - 1]
        if step != 0:
            old = sc4_clock_probe.decode_native_date(serials[index - 1])
            new = sc4_clock_probe.decode_native_date(serials[index])
            date_steps.append(
                {
                    "sample_index": after.get("sample_index", index),
                    "elapsed_seconds": after.get("elapsed_seconds"),
                    "serial_before": serials[index - 1],
                    "serial_after": serials[index],
                    "serial_step": step,
                    "date_before": old,
                    "date_after": new,
                    "month_rollover": (old["year"], old["month"]) != (new["year"], new["month"]),
                    "year_rollover": old["year"] != new["year"],
                }
            )
            if index - run_start >= pause_samples:
                stationary_runs.append(
                    {"first_sample": run_start, "last_sample": index - 1, "samples": index - run_start, "serial": serials[run_start]}
                )
            run_start = index
        for metric in metrics:
            left = before.get("metrics", {}).get(metric)
            right = after.get("metrics", {}).get(metric)
            if left is None or right is None or left == right:
                continue
            metric_changes.append(
                {
                    "sample_index": after.get("sample_index", index),
                    "metric": metric,
                    "before": left,
                    "after": right,
                    "delta": numeric(right, metric) - numeric(left, metric),
                    "coincides_with_date_step": step != 0,
                    "coincides_with_month_rollover": bool(step) and date_steps[-1]["month_rollover"],
                }
            )
    if len(series) - run_start >= pause_samples:
        stationary_runs.append(
            {"first_sample": run_start, "last_sample": len(series) - 1, "samples": len(series) - run_start, "serial": serials[run_start]}
        )

    backwards = [step for step in date_steps if step["serial_step"] < 0]
    per_metric: dict[str, Any] = {}
    for metric in metrics:
        changes = [item for item in metric_changes if item["metric"] == metric]
        per_metric[metric] = {
            "changes": len(changes),
            "on_date_step": sum(item["coincides_with_date_step"] for item in changes),
            "on_month_rollover": sum(item["coincides_with_month_rollover"] for item in changes),
            "off_boundary": sum(not item["coincides_with_date_step"] for item in changes),
        }
    month_rollovers = sum(step["month_rollover"] for step in date_steps)
    checks = {
        "serial_monotonic": not backwards,
        "pause_observed": bool(stationary_runs),
        "advance_observed": bool(date_steps),
        "month_rollover_observed": month_rollovers > 0,
        "budget_change_on_month_rollover": any(item["coincides_with_month_rollover"] for item in metric_changes),
    }
    return {
        "schema": BOUNDARY_SCHEMA,
        "created_utc": utc_now(),
        "experiment_id": series[0].get("experiment_id"),
        "run_id": series[0].get("run_id"),
        "samples": len(series),
        "serial_range": [min(serials), max(serials)],
        "date_steps": date_steps,
        "serial_step_sizes": sorted({step["serial_step"] for step in date_steps}),
        "month_rollovers": month_rollovers,
        "stationary_runs": stationary_runs,
        "metric_changes": metric_changes,
        "per_metric": per_metric,
        "gate_checks": checks,
        "interpretation": {
            "status": "boundary_correlation",
            "sampling_caveat": "changes are attributed to the sampling interval, not an exact tick",
            "tick_claim": False,
            "equivalence_claim": False,
        },
    }


def boundaries(args: argparse.Namespace) -> int:
    if args.pause_samples < 2:
        raise SystemIdError("--pause-samples must be at least 2")
    result = boundary_report(read_series(args.series), args.metric or list(BOUNDARY_METRICS), args.pause_samples)
    write_json(args.out, result)
    print(json.dumps({"out": str(args.out), "date_steps": len(result["date_steps"]), "gate_checks": result["gate_checks"]}))
    return 0


def boundary_self_test() -> int:
    base = sc4_clock_probe_serial_for_test()
    serials = [base, base, base, base + 1, base + 2, base + 2, base + 2, base + 3]
    funds = [100, 100, 100, 100, 250, 250, 240, 240]
    series = [
        {"experiment_id": "self-test", "run_id": "t", "sample_index": i, "elapsed_seconds": float(i),
         "metrics": {"simulation_date_serial": s, "funds_public": f}}
        for i, (s, f) in enumerate(zip(serials, funds))
    ]
    report = boundary_report(series, ["funds_public"], 3)
    assert report["serial_step_sizes"] == [1], report["serial_step_sizes"]
    assert len(report["stationary_runs"]) == 2, report["stationary_runs"]
    assert report["per_metric"]["funds_public"] == {"changes": 2, "on_date_step": 1, "on_month_rollover": 1, "off_boundary": 1}, report["per_metric"]
    assert all(report["gate_checks"].values()), report["gate_checks"]
    try:
        boundary_report(series[:1], ["funds_public"], 3)
    except SystemIdError:
        pass
    else:
        raise AssertionError("single-sample series accepted")
    print("SC4 SYSTEM ID BOUNDARY SELF-TEST PASSED")
    return 0


def sc4_clock_probe_serial_for_test() -> int:
    """Return a serial whose next value is the first day of a month."""
    serial = 0x25B6DB
    while sc4_clock_probe.decode_native_date(serial + 2)["day"] != 1:
        serial += 1
    return serial


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
    capture_parser.add_argument("--save", type=Path, help="optional starting save; only hash/chunk metadata is recorded")
    capture_parser.add_argument("--save-chunk-size", type=int, default=4096)
    capture_parser.add_argument("--duration", type=float, default=0.0)
    capture_parser.add_argument("--interval", type=float, default=2.0)
    capture_parser.add_argument("--image-name", default="SimCity 4.exe")
    capture_parser.add_argument(
        "--with-clock",
        action="store_true",
        help="require and include the native simulation-date candidate",
    )
    capture_parser.add_argument("--out", type=Path, required=True)

    analyze_parser = sub.add_parser("analyze", help="compare paired baseline and experiment series")
    analyze_parser.add_argument("--baseline", type=Path, required=True)
    analyze_parser.add_argument("--experiment", type=Path, required=True)
    analyze_parser.add_argument("--input-delta", type=float)
    analyze_parser.add_argument("--metric", action="append")
    analyze_parser.add_argument("--out", type=Path, required=True)

    aggregate_parser = sub.add_parser("aggregate", help="summarize repeated paired analyses")
    aggregate_parser.add_argument("--analysis", type=Path, nargs="+", required=True)
    aggregate_parser.add_argument("--metric", action="append")
    aggregate_parser.add_argument("--out", type=Path, required=True)

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

    boundary_parser = sub.add_parser("boundaries", help="correlate date-serial steps with budget changes")
    boundary_parser.add_argument("--series", type=Path, required=True)
    boundary_parser.add_argument("--metric", action="append")
    boundary_parser.add_argument("--pause-samples", type=int, default=3)
    boundary_parser.add_argument("--out", type=Path, required=True)

    sub.add_parser("self-test", help="run the synthetic boundary-analysis check")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "capture":
            return capture(args)
        if args.command == "analyze":
            return analyze(args)
        if args.command == "aggregate":
            return aggregate(args)
        if args.command == "boundaries":
            return boundaries(args)
        if args.command == "self-test":
            return boundary_self_test()
        return plan(args)
    except (OSError, ObservatoryError, SystemIdError, ValueError) as exc:
        print(f"SC4 SYSTEM ID FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
