#!/usr/bin/env python3
"""Compare normalized observation records without importing candidate code.

The comparator is deliberately boring: it reads JSON, applies a checked-in
policy, and writes a JSON report. It never executes an adapter and never edits
reference data or tolerances.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


OBSERVATION_SCHEMA = "sc4-lab.observation.v1"
TOLERANCE_SCHEMA = "sc4-lab.tolerances.v1"
ALLOWED_STATUSES = {"observed", "unsupported", "uncertain", "not_applicable"}


class VerificationError(Exception):
    """Input or policy error that must be visible in the report."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"top level must be an object: {path}")
    return value


def validate_observation(value: dict[str, Any], label: str) -> None:
    if value.get("schema") != OBSERVATION_SCHEMA:
        raise VerificationError(f"{label}: unsupported observation schema")
    if not isinstance(value.get("test_id"), str) or not value["test_id"]:
        raise VerificationError(f"{label}: missing test_id")
    metrics = value.get("metrics")
    if not isinstance(metrics, dict):
        raise VerificationError(f"{label}: metrics must be an object")
    for name, metric in metrics.items():
        if not isinstance(name, str) or not isinstance(metric, dict):
            raise VerificationError(f"{label}: malformed metric {name!r}")
        status = metric.get("status")
        if status not in ALLOWED_STATUSES:
            raise VerificationError(f"{label}: invalid status for {name}")
        if "value" not in metric:
            raise VerificationError(f"{label}: missing value for {name}")


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compare_metric(expected: Any, actual: Any, rule: dict[str, Any]) -> tuple[bool, str]:
    mode = rule.get("mode")
    if mode == "exact":
        return expected == actual, "exact equality"
    if mode == "tolerance":
        if not numeric(expected) or not numeric(actual):
            return False, "tolerance mode requires numeric values"
        absolute = float(rule.get("absolute", 0.0))
        relative = float(rule.get("relative", 0.0))
        if absolute < 0.0 or relative < 0.0:
            return False, "tolerances must be non-negative"
        error = abs(float(actual) - float(expected))
        limit = absolute + relative * abs(float(expected))
        return error <= limit, f"error={error:g}, limit={limit:g}"
    if mode in {"distribution", "spatial"}:
        return False, f"comparison mode not implemented: {mode}"
    return False, "missing or unknown comparison mode"


def compare(reference: dict[str, Any], candidate: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    validate_observation(reference, "reference")
    validate_observation(candidate, "candidate")
    if reference["test_id"] != candidate["test_id"]:
        raise VerificationError("reference and candidate test_id differ")
    if policy.get("schema") != TOLERANCE_SCHEMA:
        raise VerificationError("unsupported tolerance schema")
    policy_metrics = policy.get("metrics", {})
    if not isinstance(policy_metrics, dict):
        raise VerificationError("tolerance metrics must be an object")

    candidate_metrics = candidate["metrics"]
    results: list[dict[str, Any]] = []
    comparable = 0
    failed = 0
    skipped = 0
    for name, expected_entry in reference["metrics"].items():
        status = expected_entry["status"]
        if status != "observed":
            skipped += 1
            results.append({
                "metric": name,
                "status": "skipped",
                "reason": f"reference status is {status}",
            })
            continue

        comparable += 1
        actual_entry = candidate_metrics.get(name)
        if not isinstance(actual_entry, dict) or actual_entry.get("status") != "observed":
            failed += 1
            results.append({
                "metric": name,
                "status": "fail",
                "reason": "candidate metric is missing or not observed",
            })
            continue

        rule = policy_metrics.get(name, policy.get("default"))
        if not isinstance(rule, dict):
            failed += 1
            results.append({
                "metric": name,
                "status": "fail",
                "reason": "no fixed comparison rule",
            })
            continue

        passed, reason = compare_metric(expected_entry["value"], actual_entry["value"], rule)
        if not passed:
            failed += 1
        results.append({
            "metric": name,
            "status": "pass" if passed else "fail",
            "mode": rule.get("mode"),
            "reason": reason,
            "expected": expected_entry["value"],
            "actual": actual_entry["value"],
        })

    return {
        "schema": "sc4-lab.comparison.v1",
        "test_id": reference["test_id"],
        "passed": comparable > 0 and failed == 0,
        "summary": {
            "comparable": comparable,
            "failed": failed,
            "skipped": skipped,
        },
        "metrics": results,
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--tolerances", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        report = compare(
            read_json(args.reference),
            read_json(args.candidate),
            read_json(args.tolerances),
        )
    except VerificationError as exc:
        report = {
            "schema": "sc4-lab.comparison.v1",
            "passed": False,
            "error": str(exc),
        }
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"cannot write report {args.report}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("passed", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
