#!/usr/bin/env python3
"""Data-free adapter used to exercise the JSONL laboratory protocol.

This is a protocol fixture, not an SC4 implementation and not a reference
observation source. It mirrors the deliberately synthetic power equations used
by the OpenSC4 seam smoke backend.
"""

from __future__ import annotations

import json
import sys
from typing import Any


PROTOCOL = "opensc4.adapter.v1"
CONTRACT = "opensc4.simulation.v1"
SAVE_SCHEMA = "opensc4.synthetic-power.v1"
TICK_SECONDS = 1.0
TICKS_PER_MONTH = 30
EVENT_RETENTION = 256


class Backend:
    def __init__(self) -> None:
        self.tick = 0
        self.month = 0
        self.elapsed = 0.0
        self.demand = 0.0
        self.plants: list[dict[str, float]] = []
        self.metrics: dict[str, float] = {}
        self.sequence = 0
        self.events: list[dict[str, Any]] = []
        self._recompute()

    def capabilities(self) -> dict[str, Any]:
        return {
            "api_version": 1,
            "contract": CONTRACT,
            "backend_fingerprint": "synthetic-sidecar-v1-equations-1",
            "fixed_tick_seconds": TICK_SECONDS,
            "save_schema": SAVE_SCHEMA,
            "supports_commands": True,
            "supports_events": True,
            "supports_save_load": True,
            "event_retention": EVENT_RETENTION,
        }

    def reset(self, scenario: dict[str, Any]) -> None:
        self.tick = 0
        self.month = 0
        self.elapsed = 0.0
        self.sequence = 0
        self.events.clear()
        self.demand = max(0.0, float(scenario.get("demand", 0.0)))
        self.plants = []
        for spec in scenario.get("plants", []):
            self.add_plant(float(spec.get("capacity", 0.0)), float(spec.get("funding", 1.0)))
        self._recompute()
        self._emit("reset", {"plant_count": len(self.plants), "demand": self.demand})

    def add_plant(self, capacity: float, funding: float = 1.0) -> None:
        self.plants.append({
            "capacity": max(0.0, capacity),
            "funding": min(1.0, max(0.0, funding)),
            "condition": 1.0,
        })
        self._recompute()
        self._emit("plant_added", {"index": len(self.plants) - 1})

    def validate(self, command: Any) -> dict[str, Any]:
        if not isinstance(command, dict):
            return {"accepted": False, "error": "command_must_be_object"}
        kind = command.get("type")
        if kind == "set_demand":
            return {"accepted": True, "type": kind}
        if kind == "set_funding":
            index = int(command.get("index", -1))
            if index < 0 or index >= len(self.plants):
                return {"accepted": False, "error": "invalid_plant_index"}
            return {"accepted": True, "type": kind}
        if kind == "add_plant":
            return {"accepted": True, "type": kind}
        return {"accepted": False, "error": "unknown_command"}

    def command(self, command: dict[str, Any]) -> dict[str, Any]:
        validation = self.validate(command)
        if not validation["accepted"]:
            return validation
        kind = command["type"]
        if kind == "set_demand":
            self.demand = max(0.0, float(command.get("value", 0.0)))
            self._recompute()
            self._emit("demand_changed", {"value": self.demand})
        elif kind == "set_funding":
            index = int(command["index"])
            self.plants[index]["funding"] = min(1.0, max(0.0, float(command.get("value", 0.0))))
            self._recompute()
            self._emit("funding_changed", {"index": index, "value": self.plants[index]["funding"]})
        elif kind == "add_plant":
            self.add_plant(float(command.get("capacity", 0.0)), float(command.get("funding", 1.0)))
        return {"accepted": True, "snapshot": self.snapshot()}

    def advance(self, seconds: float) -> dict[str, Any]:
        if seconds < 0.0:
            return {"accepted": False, "error": "negative_time"}
        self.elapsed += seconds
        while self.elapsed >= TICK_SECONDS:
            self.elapsed -= TICK_SECONDS
            self.tick += 1
            if self.tick % TICKS_PER_MONTH == 0:
                self.month = self.tick // TICKS_PER_MONTH
                self._emit("month_advanced", {"month": self.month})
            self._recompute()
        return {"accepted": True, "snapshot": self.snapshot()}

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.metrics,
            "backend_id": "synthetic-sidecar-v1",
            "backend_fingerprint": "synthetic-sidecar-v1-equations-1",
            "contract": CONTRACT,
            "simulation_tick": self.tick,
            "simulation_month": self.month,
            "elapsed_seconds": self.elapsed,
            "demand": self.demand,
            "plants": [dict(plant) for plant in self.plants],
            "event_cursor": self.sequence,
        }

    def save(self) -> dict[str, Any]:
        return {
            "schema": SAVE_SCHEMA,
            "api_version": 1,
            "simulation_tick": self.tick,
            "simulation_month": self.month,
            "elapsed_seconds": self.elapsed,
            "demand": self.demand,
            "plants": [dict(plant) for plant in self.plants],
            "event_cursor": self.sequence,
        }

    def load(self, state: dict[str, Any]) -> bool:
        if state.get("schema") != SAVE_SCHEMA or int(state.get("api_version", -1)) != 1:
            return False
        self.tick = max(0, int(state.get("simulation_tick", 0)))
        self.month = max(0, int(state.get("simulation_month", 0)))
        self.elapsed = max(0.0, float(state.get("elapsed_seconds", 0.0)))
        self.sequence = max(0, int(state.get("event_cursor", 0)))
        self.demand = max(0.0, float(state.get("demand", 0.0)))
        self.plants = []
        for plant in state.get("plants", []):
            self.plants.append({
                "capacity": max(0.0, float(plant.get("capacity", 0.0))),
                "funding": min(1.0, max(0.0, float(plant.get("funding", 1.0)))),
                "condition": min(1.0, max(0.0, float(plant.get("condition", 1.0)))),
            })
        self.events.clear()
        self._recompute()
        self._emit("state_loaded", {"event_cursor": self.sequence})
        return True

    def events_since(self, cursor: int) -> list[dict[str, Any]]:
        if self.events and cursor < self.events[0]["sequence"] - 1:
            raise ValueError("event_history_gap")
        return [event for event in self.events if event["sequence"] > cursor]

    def _recompute(self) -> None:
        available = sum(plant["capacity"] * plant["funding"] * plant["condition"] for plant in self.plants)
        supplied = min(self.demand, available)
        self.metrics = {
            "available_power": available,
            "generated_power": available,
            "supplied_power": supplied,
            "unmet_demand": max(0.0, self.demand - supplied),
            "operating_cost": sum(plant["capacity"] * plant["funding"] * 0.1 for plant in self.plants),
            "pollution": available * 0.25,
        }

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        self.sequence += 1
        self.events.append({
            "sequence": self.sequence,
            "type": kind,
            "simulation_tick": self.tick,
            "simulation_month": self.month,
            "payload": payload,
        })
        del self.events[:-EVENT_RETENTION]


def response(request_id: Any, ok: bool, result: Any = None, error: dict[str, str] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"protocol": PROTOCOL, "request_id": request_id, "ok": ok}
    if ok:
        body["result"] = result
    else:
        body["error"] = error or {"code": "unknown", "message": "request failed"}
    return body


def main() -> int:
    backend = Backend()
    for line in sys.stdin:
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("request_id") if isinstance(request, dict) else None
            if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
                raise ValueError("invalid_protocol")
            operation = request.get("operation")
            payload = request.get("payload", {})
            before = backend.sequence
            if operation == "hello":
                result = {
                    "backend_id": "synthetic-sidecar-v1",
                    "backend_fingerprint": "synthetic-sidecar-v1-equations-1",
                    "contract": CONTRACT,
                    "capabilities": backend.capabilities(),
                    "save_schema": SAVE_SCHEMA,
                }
            elif operation == "reset":
                backend.reset(payload)
                result = {"snapshot": backend.snapshot(), "event_cursor": backend.sequence}
            elif operation == "validate_command":
                result = backend.validate(payload)
            elif operation == "command":
                result = backend.command(payload)
                result["events"] = backend.events_since(before)
            elif operation == "advance":
                result = backend.advance(float(payload.get("seconds", 0.0)))
                result["events"] = backend.events_since(before)
            elif operation == "snapshot":
                result = backend.snapshot()
            elif operation == "events":
                result = {"events": backend.events_since(int(payload.get("cursor", 0))), "event_cursor": backend.sequence}
            elif operation == "save":
                result = backend.save()
            elif operation == "load":
                result = {"accepted": backend.load(payload), "snapshot": backend.snapshot()}
            elif operation == "shutdown":
                print(json.dumps(response(request_id, True, {"shutdown": True})), flush=True)
                return 0
            else:
                raise ValueError("unknown_operation")
            print(json.dumps(response(request_id, True, result), separators=(",", ":")), flush=True)
        except Exception as exc:  # protocol errors must remain structured
            print(json.dumps(response(locals().get("request_id"), False, error={"code": str(exc), "message": str(exc)})), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
