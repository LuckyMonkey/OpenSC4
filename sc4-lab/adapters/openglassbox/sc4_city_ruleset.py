"""Generate an OpenGlassBox ruleset (.ogs) and load plan for a canonical SC4 city.

The canonical city (opensc4.canonical-city.v1, see simulation/sc4_city_model.gd)
supplies SC4 inputs read from the user's own install: per-building pollution
at centre and radius, capacity (residents/jobs), upkeep. The behavior that
consumes them -- diffusion/decay of the pollution layer, commuter agents on
the road graph, BPR congestion -- is OpenGlassBox's own and is labelled
``candidate`` everywhere: it has not been compared against SC4 yet.

Money is different: the monthly tax step is the verified TAX_001 rule. Its
taxable bases are a declared placeholder until base construction (roadmap
Priority A) is recovered.
"""

from __future__ import annotations

import math
from typing import Any

# --- candidate parameters (OpenGlassBox-style, NOT measured from SC4) --------
PEOPLE_PER_UNIT = 100         # residents/jobs represented by one People unit
AIR_DIFFUSION = 20            # % of a cell's amount spread to 4 neighbours per period
AIR_DECAY = 8                 # % lost per period
AIR_CAPACITY = 2000
COMMUTER_SPEED = 30
# Placeholder taxable base per resident/job, until Priority A recovers the rule.
PLACEHOLDER_BASE_PER_CAPACITY = 100

SEGMENTS = {
    "Street": "speed 15 capacity 8 beta 4",
    "Road": "speed 30 capacity 20 beta 4",
    "One-Way Road": "speed 30 capacity 20 beta 4",
    "Dirt Road": "speed 10 capacity 4 beta 4",
    "Avenue": "speed 45 capacity 50 beta 4",
    "Maxis El Highway": "speed 70 capacity 120 beta 4",
}


def _seg_name(kind: str) -> str:
    return "N" + "".join(ch for ch in kind if ch.isalnum())


def _capacity(entity: dict[str, Any]) -> int:
    return sum(int(v) for v in entity["attributes"].get("capacity", {}).values())


def compact_roads(roads: dict[str, Any]) -> list[tuple[tuple[float, float], tuple[float, float], str]]:
    """Merge straight runs of road tiles into single segments.

    A tile node is kept when it is a junction or dead end (degree != 2), where
    the road kind changes, or at a bend. Everything else is a mid-run node whose
    removal keeps topology and path lengths identical. Returns segments as
    ((x1, y1), (x2, y2), kind) in tile-centre coordinates.
    """
    pos = {n["id"]: (n["position"]["x"] + 0.5, n["position"]["y"] + 0.5) for n in roads["nodes"]}
    adj: dict[str, list[tuple[str, str]]] = {node: [] for node in pos}
    for edge in roads["edges"]:
        adj[edge["from"]].append((edge["to"], edge["kind"]))
        adj[edge["to"]].append((edge["from"], edge["kind"]))

    def kept(node: str) -> bool:
        links = adj[node]
        if len(links) != 2 or links[0][1] != links[1][1]:
            return True
        (a, _), (b, _) = links
        x, y = pos[node]
        return (pos[a][0] - x, pos[a][1] - y) != (x - pos[b][0], y - pos[b][1])

    keep = {node for node in pos if kept(node)}
    seen: set[frozenset[str]] = set()
    segments = []
    for start in keep:
        for first, kind in adj[start]:
            if frozenset((start, first)) in seen:
                continue
            seen.add(frozenset((start, first)))
            previous, current = start, first
            while current not in keep:
                nxt = next(n for n, _ in adj[current] if n != previous)
                seen.add(frozenset((current, nxt)))
                previous, current = current, nxt
            segments.append((pos[start], pos[current], kind))
    return segments


def _anchor(segments_by_tile: dict[tuple[int, int], list[int]], segments: list, x: float, y: float,
            reach: float) -> tuple[int, float] | None:
    """Nearest segment within reach (tiles) of point (x, y) and the offset along it."""
    best = None
    r = int(math.ceil(reach))
    for tx in range(int(x) - r, int(x) + r + 1):
        for ty in range(int(y) - r, int(y) + r + 1):
            for index in segments_by_tile.get((tx, ty), ()):
                (x1, y1), (x2, y2), _ = segments[index]
                dx, dy = x2 - x1, y2 - y1
                length2 = dx * dx + dy * dy
                t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
                d = math.hypot(x1 + t * dx - x, y1 + t * dy - y)
                if d <= reach and (best is None or d < best[0]):
                    best = (d, index, t)
    return None if best is None else (best[1], best[2])


def build(city: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    """Return (ogs script text, helper commands after CITY_NEW, metadata)."""
    emit_levels: set[int] = set()
    types: dict[str, str] = {}
    placements: list[tuple[str, float, float]] = []
    cell = 1.0  # helper coordinates are tiles; cellSize is 1 tile
    summary = {"residential": 0, "commercial": 0, "industrial": 0, "other": 0}

    # Only as many residents commute as there are jobs (candidate rule): with
    # more workers than job slots the surplus would search the whole graph and
    # never arrive, which dominated the step cost.
    residents = sum(_capacity(e) for e in city["entities"] if e["attributes"].get("class") == "residential")
    jobs = sum(_capacity(e) for e in city["entities"] if e["attributes"].get("class") in ("commercial", "industrial"))
    commuting_share = min(1.0, jobs / residents) if residents else 0.0
    carry = {"home": 0.0, "job": 0.0}
    for entity in city["entities"]:
        attrs = entity["attributes"]
        klass = attrs.get("class", "other")
        air = max(0, int(attrs.get("pollution", {}).get("air", 0)))
        radius = max(0, int(math.ceil(attrs.get("pollution_radius", {}).get("air", 0.0))))
        # Whole People units per building; fractions carry over in file order so
        # the city total matches capacity / PEOPLE_PER_UNIT (deterministic).
        pool = "home" if klass == "residential" else "job"
        share = commuting_share if pool == "home" else 1.0
        carry[pool] += _capacity(entity) * share / PEOPLE_PER_UNIT
        units = int(carry[pool])
        carry[pool] -= units
        rules = []
        if air > 0:
            emit_levels.add(air)
            rules.append(f"Emit{air}")
        if klass == "residential":
            rules.insert(0, "GoToWork")
            target, caps, resources = "Home", f"People {units}", f"People {units}"
        elif klass in ("commercial", "industrial"):
            rules.insert(0, "GoHome")
            target, caps, resources = "Job", f"People {units}", ""
        else:
            target, caps, resources = "Civic", "", ""
        summary[klass if klass in summary else "other"] += 1
        name = f"B_{klass[:3]}_{units}_{air}_{radius}"
        if name not in types:
            types[name] = (f"\tbuilding {name} color 0x888888 layerRadius {radius} rules [ {' '.join(rules)} ] "
                           f"targets [ {target} ] caps [ {caps} ] resources [ {resources} ]")
        foot = entity.get("footprint")
        if foot:
            x = (foot["min_x"] + foot["max_x"] + 1) / 2.0
            y = (foot["min_y"] + foot["max_y"] + 1) / 2.0
        else:
            x, y = entity["position"]["x"] + 0.5, entity["position"]["y"] + 0.5
        placements.append((name, x * cell, y * cell))

    roads = city["networks"].get("road", {"nodes": [], "edges": []})
    positions = {n["id"]: (n["position"]["x"] + 0.5, n["position"]["y"] + 0.5) for n in roads["nodes"]}
    kinds = sorted({e["kind"] for e in roads["edges"]} | {"Road"})

    lines = ["resources", "\tresource People", "\tresource AirPollution", "end",
             "paths", "\tpath Road color 0xAAAAAA", "end", "segments"]
    lines += [f"\tsegment {_seg_name(k)} color 0xAAAAAA {SEGMENTS.get(k, SEGMENTS['Road'])}" for k in kinds]
    lines += ["end", "agents", f"\tagent Commuter color 0xFFFF00 speed {COMMUTER_SPEED}", "end", "rules",
              "\tbuildingRule GoToWork", "\t\trate 20 minutes", "\t\thour between 6 10",
              "\t\tlocal People greater 0", "\t\tlocal People remove 1",
              "\t\tagent Commuter to Job add [ People 1 ]", "\tend",
              "\tbuildingRule GoHome", "\t\trate 20 minutes", "\t\thour between 16 20",
              "\t\tlocal People greater 0", "\t\tlocal People remove 1",
              "\t\tagent Commuter to Home add [ People 1 ]", "\tend"]
    for level in sorted(emit_levels):
        lines += [f"\tbuildingRule Emit{level}", "\t\trate 1 hour", f"\t\tlayer AirPollution add {level}", "\tend"]
    lines += ["end", "buildings"] + list(types.values()) + ["end", "layers",
              f"\tlayer AirPollution color 0x885522 capacity {AIR_CAPACITY} diffusion {AIR_DIFFUSION} "
              f"decay {AIR_DECAY} rate 1 hours rules [ ]", "end", ""]

    segments = compact_roads(roads)
    by_tile: dict[tuple[int, int], list[int]] = {}
    commands = []
    for index, ((x1, y1), (x2, y2), kind) in enumerate(segments):
        commands.append(f"ROAD Road {_seg_name(kind)} {x1} {y1} {x2} {y2}")
        steps = int(max(abs(x2 - x1), abs(y2 - y1))) + 1
        for k in range(steps + 1):
            t = k / steps
            by_tile.setdefault((int(x1 + t * (x2 - x1)), int(y1 + t * (y2 - y1))), []).append(index)
    on_segment = 0
    for name, x, y in placements:
        hit = _anchor(by_tile, segments, x, y, 4.0)
        if hit is None:
            commands.append(f"BUILDING {name} {x} {y} 4")
            continue
        (x1, y1), (x2, y2), _ = segments[hit[0]]
        commands.append(f"BUILDING_ON {name} {x1} {y1} {x2} {y2} {hit[1]:.4f}")
        on_segment += 1

    meta = {
        "building_types": len(types),
        "buildings": len(placements),
        "road_edges": len(roads["edges"]),
        "road_segments_compacted": len(segments),
        "buildings_on_segments": on_segment,
        "classes": summary,
        "commuting_share": round(commuting_share, 4),
        "candidate_parameters": {
            "people_per_unit": PEOPLE_PER_UNIT, "air_diffusion_pct": AIR_DIFFUSION, "air_decay_pct": AIR_DECAY,
            "commuter_speed": COMMUTER_SPEED, "commuters_capped_to_jobs": True, "agent_give_up_game_hours": 2, "placeholder_base_per_capacity": PLACEHOLDER_BASE_PER_CAPACITY,
        },
    }
    return "\n".join(lines), commands, meta


def monthly_budget(city: dict[str, Any], rates: list[float], mult: float) -> dict[str, Any]:
    """TAX_001 (verified rule) with placeholder bases; upkeep from exemplars."""
    bases = [0] * 12
    slot = {"residential": 0, "commercial": 3, "industrial": 6}
    for entity in city["entities"]:
        klass = entity["attributes"].get("class")
        if klass in slot:
            bases[slot[klass]] += _capacity(entity) * PLACEHOLDER_BASE_PER_CAPACITY
    total = sum(b * mult * r for b, r in zip(bases, rates)) / 1200.0
    upkeep = sum(float(e["attributes"].get("upkeep", 0)) for e in city["entities"])
    return {"tax_income": math.trunc(total), "expenses": int(round(upkeep)), "bases": bases,
            "tax_rule": "TAX_001 (verified)", "bases_status": "placeholder (Priority A open)",
            "expenses_status": "sum of exemplar Budget Item Cost (unverified vs SC4)"}
