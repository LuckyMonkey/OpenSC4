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
import tempfile

import sc4_city_ruleset
from typing import Any

PROTOCOL = "opensc4.adapter.v1"
CONTRACT = "opensc4.simulation.v1"
SAVE_SCHEMA = "opensc4.openglassbox-sidecar.v1"
DEFAULT_HELPER = "/tmp/opensc4-openglassbox-helper"


class BridgeError(Exception):
    pass


class Backend:
    def __init__(self, helper: str) -> None:
        # Engine diagnostics go to a log file, never to an inherited stderr the
        # host may have closed (a closed pipe would SIGPIPE the helper).
        log_path = os.environ.get("OPENSC4_OPENGLASSBOX_LOG",
                                  os.path.join(tempfile.gettempdir(), "opensc4-openglassbox-helper.log"))
        self.log = open(log_path, "a")
        self.process = subprocess.Popen(
            [helper],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
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

    def budget_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        rates = [float(value) for value in payload["rates"]]
        bases = [int(value) for value in payload["bases"]]
        if len(rates) != 12 or len(bases) != 12:
            raise BridgeError("budget_needs_12_rates_and_bases")
        line = " ".join(
            ["BUDGET_SET", str(int(payload["funds"])), str(int(payload.get("expenses", 0))),
             repr(float(payload.get("mult", 1.0)))] + [repr(rate) for rate in rates] + [str(base) for base in bases]
        )
        self._command(line)
        return self.emit("budget_set", {"funds": int(payload["funds"])})

    def budget_month(self, days: int) -> dict[str, Any]:
        values = self._command(f"BUDGET_MONTH {int(days)}")
        self.emit("budget_month", values)
        return values

    # --- SC4 city mode -------------------------------------------------------
    TICKS_PER_MINUTE = 1

    def city_init(self, payload: dict[str, Any]) -> dict[str, Any]:
        city = payload["city"]
        script, commands, meta = sc4_city_ruleset.build(city)
        handle = tempfile.NamedTemporaryFile("w", suffix=".ogs", prefix="opensc4-city-", delete=False)
        handle.write(script)
        handle.close()
        dims = city["dimensions"]
        self._command(f"CITY_NEW {dims['width']} {dims['height']} 1.0 {self.TICKS_PER_MINUTE} "
                      f"{int(payload.get('seed', 1))} {handle.name}")
        anchored = 0
        for line in commands:
            values = self._command(line)
            anchored += int(values.get("anchored", 0))
        self.city = city
        self.month_days = 0
        self.funds = int(payload.get("funds", 50000))
        self.rates = [float(r) for r in payload.get("rates", [9.0] * 12)]
        self.mult = float(payload.get("mult", 1.0))
        meta.update({"script": handle.name, "anchored_buildings": anchored, "funds": self.funds})
        meta.update(self._command("CITY_STATS"))
        self.emit("city_init", {"buildings": meta["buildings"]})
        return meta

    def city_advance(self, days: int) -> dict[str, Any]:
        ticks = int(days) * 24 * 60 * self.TICKS_PER_MINUTE
        stats = self._command(f"STEP {ticks}")
        months = []
        self.month_days += int(days)
        while self.month_days >= 30:
            self.month_days -= 30
            budget = sc4_city_ruleset.monthly_budget(self.city, self.rates, self.mult)
            self.funds += budget["tax_income"] - budget["expenses"]
            budget["funds"] = self.funds
            months.append(budget)
            self.emit("month", {"funds": self.funds})
        return {"stats": stats, "months": months, "funds": self.funds}

    def city_layer(self, name: str) -> dict[str, Any]:
        line = self._raw(f"LAYER {name}")
        fields = dict(item.split("=", 1) for item in line.split()[1:])
        return {"w": int(fields["w"]), "h": int(fields["h"]), "total": int(fields["total"]),
                "data": [int(v) for v in fields["data"].split(",")] if fields["data"] else []}

    def city_traffic(self) -> dict[str, Any]:
        line = self._raw("TRAFFIC")
        data = line.split("data=", 1)[1] if "data=" in line else ""
        segments = []
        for item in data.split(";") if data else []:
            x1, y1, x2, y2, flow, sat = item.split(":")
            segments.append([float(x1), float(y1), float(x2), float(y2), float(flow), float(sat)])
        return {"segments": segments}

    def _raw(self, command: str) -> str:
        if self.process.stdin is None or self.process.stdout is None:
            raise BridgeError("helper pipes unavailable")
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline().strip()
        if not line or line.startswith("ERR"):
            raise BridgeError("helper rejected command: " + line)
        return line

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
                            "commands": ["add_road", "budget_set", "budget_month",
                                         "city_init", "city_advance", "city_layer", "city_traffic"],
                            "rulesets": ["sc4-tax-v0.3"],
                        },
                        "save_schema": SAVE_SCHEMA,
                    }
                elif operation == "reset":
                    events = backend.reset(payload if isinstance(payload, dict) else {})
                    result = {"snapshot": backend.snapshot(), "event_cursor": backend.sequence, "events": events}
                elif operation == "validate_command":
                    kind = payload.get("type") if isinstance(payload, dict) else None
                    accepted = kind in {"add_road", "budget_set", "budget_month"}
                    result = {"accepted": accepted, "type": kind} if accepted else {"accepted": False, "error": "unknown_command"}
                elif operation == "command":
                    kind = payload.get("type") if isinstance(payload, dict) else None
                    if kind == "add_road":
                        event = backend.add_road(payload)
                        result = {"accepted": True, "snapshot": backend.snapshot(), "events": [event]}
                    elif kind == "budget_set":
                        event = backend.budget_set(payload)
                        result = {"accepted": True, "events": [event]}
                    elif kind == "city_init":
                        result = {"accepted": True, "city": backend.city_init(payload)}
                    elif kind == "city_advance":
                        result = {"accepted": True, **backend.city_advance(int(payload.get("days", 1)))}
                    elif kind == "city_layer":
                        result = {"accepted": True, "layer": backend.city_layer(str(payload.get("name", "AirPollution")))}
                    elif kind == "city_traffic":
                        result = {"accepted": True, "traffic": backend.city_traffic()}
                    elif kind == "budget_month":
                        result = {"accepted": True, "budget": backend.budget_month(int(payload.get("days", 30)))}
                    else:
                        raise BridgeError("unknown_command")
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
            except (BridgeError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                print(json.dumps(response(request_id, False, error=str(exc)), sort_keys=True), flush=True)
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
