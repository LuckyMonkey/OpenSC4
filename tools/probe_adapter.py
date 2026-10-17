#!/usr/bin/env python3
"""Drive an adapter sidecar and record a data-free protocol trace.

The probe is intentionally adapter-neutral. Its output is useful for testing
the laboratory transport and candidate adapters; it must not be used to label
synthetic output as an SC4 reference observation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROTOCOL = "opensc4.adapter.v1"


class ProbeError(Exception):
    pass


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProbeError(f"scenario must be an object: {path}")
    return value


def request(process: subprocess.Popen[str], operation: str, payload: Any, request_id: int) -> dict[str, Any]:
    envelope = {
        "protocol": PROTOCOL,
        "request_id": request_id,
        "operation": operation,
        "payload": payload,
    }
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(envelope) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise ProbeError(f"adapter exited while handling {operation}")
    try:
        response = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"adapter returned invalid JSON for {operation}: {line!r}") from exc
    if response.get("protocol") != PROTOCOL or response.get("request_id") != request_id:
        raise ProbeError(f"adapter envelope mismatch for {operation}: {response!r}")
    if not response.get("ok", False):
        raise ProbeError(f"adapter rejected {operation}: {response.get('error')}")
    return response


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", nargs="+", required=True, help="adapter command and arguments")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    scenario = read_json(args.scenario)
    process = subprocess.Popen(
        args.adapter,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    trace: list[dict[str, Any]] = []
    request_id = 0

    def call(operation: str, payload: Any) -> dict[str, Any]:
        nonlocal request_id
        request_id += 1
        envelope = {
            "request": {
                "protocol": PROTOCOL,
                "request_id": request_id,
                "operation": operation,
                "payload": payload,
            }
        }
        result = request(process, operation, payload, request_id)
        envelope["response"] = result
        trace.append(envelope)
        return result

    try:
        hello = call("hello", {})["result"]
        reset = call("reset", scenario.get("reset", {}))["result"]
        cursor = int(reset["event_cursor"])
        command = scenario.get("command", {"type": "set_demand", "value": 0.0})
        call("validate_command", command)
        command_result = call("command", command)["result"]
        cursor = int(command_result["snapshot"]["event_cursor"])
        advance = call("advance", {"seconds": float(scenario.get("advance_seconds", 0.0))})["result"]
        events = call("events", {"cursor": cursor})["result"]
        saved = call("save", {})["result"]
        call("load", saved)
        call("snapshot", {})
        call("shutdown", {})
    except (ProbeError, BrokenPipeError) as exc:
        process.kill()
        raise SystemExit(f"probe failed: {exc}") from exc
    finally:
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    stderr = process.stderr.read() if process.stderr is not None else ""
    if stderr:
        print(stderr, file=sys.stderr, end="")

    final_snapshot = advance["snapshot"]
    metric_names = scenario.get("metrics", [])
    backend_id = str(hello.get("backend_id", "unknown"))
    if backend_id.startswith("openglassbox-"):
        provenance_kind = "candidate-openglassbox"
        metric_unit = "backend"
    elif backend_id.startswith("synthetic-"):
        provenance_kind = "synthetic-protocol-fixture"
        metric_unit = "synthetic"
    else:
        provenance_kind = "candidate-protocol-adapter"
        metric_unit = "backend"
    metrics: dict[str, dict[str, Any]] = {}
    for name in metric_names:
        if name in final_snapshot:
            metrics[name] = {"status": "observed", "value": final_snapshot[name], "unit": metric_unit}
        else:
            metrics[name] = {"status": "unsupported", "value": None, "unit": "unknown"}

    observation = {
        "schema": "sc4-lab.observation.v1",
        "test_id": scenario["test_id"],
        "sample": {
            "simulation_month": final_snapshot.get("simulation_month"),
            "simulation_tick": final_snapshot.get("simulation_tick"),
            "event_cursor": final_snapshot.get("event_cursor"),
        },
        "backend_id": backend_id,
        "metrics": metrics,
        "provenance": {
            "kind": provenance_kind,
            "reference_claim": False,
        },
        "events_observed": len(events.get("events", [])),
    }
    args.trace.parent.mkdir(parents=True, exist_ok=True)
    args.trace.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in trace), encoding="utf-8")
    args.observation.parent.mkdir(parents=True, exist_ok=True)
    args.observation.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"trace": str(args.trace), "observation": str(args.observation), "backend_id": hello.get("backend_id")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
