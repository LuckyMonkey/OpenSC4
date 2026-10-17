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

    commands = []
    for edge in roads["edges"]:
        a, b = positions[edge["from"]], positions[edge["to"]]
        commands.append(f"ROAD Road {_seg_name(edge['kind'])} {a[0]} {a[1]} {b[0]} {b[1]}")
    for name, x, y in placements:
        commands.append(f"BUILDING {name} {x} {y} 4")

    meta = {
        "building_types": len(types),
        "buildings": len(placements),
        "road_edges": len(roads["edges"]),
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
