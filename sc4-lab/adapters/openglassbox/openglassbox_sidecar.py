#!/usr/bin/env python3
"""JSON-line adapter backed by a real external OpenGlassBox Simulation.

The C++ helper owns OpenGlassBox objects. This process owns the OpenSC4 adapter
protocol and converts only plain JSON data across the boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

PROTOCOL = "opensc4.adapter.v1"
CONTRACT = "opensc4.simulation.v1"
SAVE_SCHEMA = "opensc4.openglassbox-sidecar.v1"
DEFAULT_HELPER = "/tmp/opensc4-openglassbox-helper"


class BridgeError(Exception):
    pass


class Backend:
    def __init__(self, helper: str) -> None:
        self.process = subprocess.Popen(
            [helper],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
        )
        self.roads: list[dict[str, float]] = []
        self.sequence = 0
        self.events: list[dict[str, Any]] = []
        self.commit = "unknown"
        self._command("RESET")
        version = self._command("VERSION")
        self.commit = version.get("commit", "unknown")

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self._command("QUIT")
            except BridgeError:
                self.process.kill()
        self.process.wait(timeout=2)

    def _command(self, command: str) -> dict[str, Any]:
        if self.process.stdin is None or self.process.stdout is None:
            raise BridgeError("helper pipes unavailable")
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise BridgeError("OpenGlassBox helper exited")
        fields = line.strip().split()
        if not fields or fields[0] == "ERR":
            raise BridgeError("helper rejected command: " + line.strip())
        values: dict[str, Any] = {}
        for field in fields[1:]:
            key, separator, value = field.partition("=")
            if not separator:
                continue
            try:
                values[key] = int(value)
            except ValueError:
                try:
                    values[key] = float(value)
                except ValueError:
                    values[key] = value
        return values

    def snapshot(self) -> dict[str, Any]:
        values = self._command("SNAPSHOT")
        values.update(
            {
                "backend_id": "openglassbox-sidecar-v1",
                "backend_fingerprint": f"openglassbox-sidecar-v1-{self.commit}",
                "contract": CONTRACT,
                "event_cursor": self.sequence,
                "simulation_tick": values.get("tick", 0),
                "simulation_day": values.get("day", 0),
                "simulation_hour": values.get("hour", 0),
                "simulation_minute": values.get("minute", 0),
                "roads": [dict(road) for road in self.roads],
            }
        )
        return values

    def emit(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.sequence += 1
        event = {
            "sequence": self.sequence,
            "type": event_type,
            "simulation_tick": self.snapshot().get("tick", 0),
            "payload": payload,
        }
        self.events.append(event)
        del self.events[:-256]
        return event

    def events_since(self, cursor: int) -> list[dict[str, Any]]:
        if self.events and cursor < self.events[0]["sequence"] - 1:
            raise BridgeError("event_history_gap")
        return [event for event in self.events if event["sequence"] > cursor]

    def reset(self, scenario: dict[str, Any]) -> list[dict[str, Any]]:
        self._command("RESET")
        self.roads = []
        self.sequence = 0
        self.events = []
        events = [self.emit("reset", {})]
        for road in scenario.get("roads", []):
            self.add_road(road)
        return events

    def add_road(self, road: dict[str, Any]) -> dict[str, Any]:
        x1 = float(road.get("x1", road.get("from_x", 0.0)))
        y1 = float(road.get("y1", road.get("from_y", 0.0)))
        x2 = float(road.get("x2", road.get("to_x", 0.0)))
        y2 = float(road.get("y2", road.get("to_y", 0.0)))
        self._command(f"ADD_ROAD {x1} {y1} {x2} {y2}")
        stored = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        self.roads.append(stored)
        return self.emit("road_added", stored)

    def advance(self, seconds: float) -> list[dict[str, Any]]:
        before = self.snapshot().get("tick", 0)
        self._command(f"ADVANCE {seconds}")
        after = self.snapshot().get("tick", 0)
        return [self.emit("advanced", {"seconds": seconds, "from_tick": before, "to_tick": after})]

    def save(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "schema": SAVE_SCHEMA,
            "api_version": 1,
            "simulation_tick": snapshot.get("tick", 0),
            "roads": [dict(road) for road in self.roads],
        }

    def load(self, state: dict[str, Any]) -> bool:
        if state.get("schema") != SAVE_SCHEMA or int(state.get("api_version", -1)) != 1:
            return False
        self._command("RESET")
        self.roads = []
        self.sequence = 0
        self.events = []
        for road in state.get("roads", []):
            self.add_road(road)
        self._command(f"SET_TICK {max(0, int(state.get('simulation_tick', 0)))}")
        self.emit("state_loaded", {"simulation_tick": int(state.get("simulation_tick", 0))})
        return True


def response(request_id: Any, ok: bool, result: Any = None, error: str = "") -> dict[str, Any]:
    value: dict[str, Any] = {"protocol": PROTOCOL, "request_id": request_id, "ok": ok}
    if ok:
        value["result"] = result
    else:
        value["error"] = {"code": "bridge_error", "message": error}
    return value


def main() -> int:
    helper = os.environ.get("OPENSC4_OPENGLASSBOX_HELPER", DEFAULT_HELPER)
    backend = Backend(helper)
    try:
        for line in sys.stdin:
            request_id: Any = None
            try:
                request = json.loads(line)
                request_id = request.get("request_id")
                if request.get("protocol") != PROTOCOL:
                    raise BridgeError("invalid_protocol")
                operation = request.get("operation")
                payload = request.get("payload", {})
                if operation == "hello":
                    result = {
                        "backend_id": "openglassbox-sidecar-v1",
                        "backend_fingerprint": f"openglassbox-sidecar-v1-{backend.commit}",
                        "contract": CONTRACT,
                        "capabilities": {
                            "api_version": 1,
                            "contract": CONTRACT,
                            "supports_commands": True,
                            "supports_events": True,
                            "supports_save_load": True,
                            "fixed_tick_seconds": 0.05,
                            "external_commit": backend.commit,
                        },
                        "save_schema": SAVE_SCHEMA,
                    }
                elif operation == "reset":
                    events = backend.reset(payload if isinstance(payload, dict) else {})
                    result = {"snapshot": backend.snapshot(), "event_cursor": backend.sequence, "events": events}
                elif operation == "validate_command":
                    kind = payload.get("type") if isinstance(payload, dict) else None
                    accepted = kind in {"add_road"}
                    result = {"accepted": accepted, "type": kind} if accepted else {"accepted": False, "error": "unknown_command"}
                elif operation == "command":
                    if not isinstance(payload, dict) or payload.get("type") != "add_road":
                        raise BridgeError("unknown_command")
                    event = backend.add_road(payload)
                    result = {"accepted": True, "snapshot": backend.snapshot(), "events": [event]}
                elif operation == "advance":
                    seconds = float(payload.get("seconds", 0.0))
                    if seconds < 0.0:
                        raise BridgeError("negative_time")
                    events = backend.advance(seconds)
                    result = {"accepted": True, "snapshot": backend.snapshot(), "events": events}
                elif operation == "snapshot":
                    result = backend.snapshot()
                elif operation == "events":
                    result = {
                        "events": backend.events_since(int(payload.get("cursor", 0))),
                        "event_cursor": backend.sequence,
                    }
                elif operation == "save":
                    result = backend.save()
                elif operation == "load":
                    accepted = backend.load(payload if isinstance(payload, dict) else {})
                    result = {"accepted": accepted, "snapshot": backend.snapshot()}
                elif operation == "shutdown":
                    result = {"accepted": True}
                    print(json.dumps(response(request_id, True, result), sort_keys=True), flush=True)
                    return 0
                else:
                    raise BridgeError("unknown_operation")
                print(json.dumps(response(request_id, True, result), sort_keys=True), flush=True)
            except (BridgeError, ValueError, TypeError, json.JSONDecodeError) as exc:
                print(json.dumps(response(request_id, False, error=str(exc)), sort_keys=True), flush=True)
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
