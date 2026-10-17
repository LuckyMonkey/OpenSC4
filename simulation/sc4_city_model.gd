class_name Sc4CityModel
extends RefCounted

## Builds the backend-neutral canonical city (opensc4.canonical-city.v1) from a
## loaded SC4 save plus the game's own exemplar data. Plain data only: this is
## what simulation backends and experiments consume.
##
## Attribute sources:
## - building/lot geometry, zoning and wealth: the city save's occupant subfiles;
## - pollution, upkeep, power, water and capacity: the building exemplar (and
##   its parent cohorts), read from the user's own SC4 install at runtime.
## Nothing here claims SC4 simulation semantics; it is input data.

const SCHEMA := "opensc4.canonical-city.v1"
const TILE_METRES := 16.0

# Exemplar property ids, checked against exemplar_types.dict.
const P_POLLUTION_AT_CENTRE := 0x27812851  # [air, water, garbage, radiation]
const P_POLLUTION_RADIUS := 0x68EE9764     # [air, water, garbage, radiation], tiles
# Monthly upkeep. exemplar_types.dict names this id "Budget Item: Line", but the
# values (e.g. [125] on a fire station, next to department and purpose ids in
# 0xEA54D283..85) show it is the cost.
const P_BUDGET_ITEM_COST := 0xEA54D286
const P_POWER_CONSUMED := 0x27812854
const P_POWER_GENERATED := 0x27812852
const P_WATER_CONSUMED := 0xC911EDA0
const P_CAPACITY_SATISFIED := 0x27812834   # [demand id, amount, ...]
const P_WEALTH := 0x27812832
const P_EXEMPLAR_NAME := 0x00000020

const BUILDING_SUBFILE := 0xa9bd882d
const LOT_SUBFILE := 0xc9bd5d4a
const NETWORK_SUBFILE := 0xc9c05c6e
const DRIVABLE := ["Road", "Street", "Avenue", "One-Way Road", "Dirt Road", "Maxis El Highway"]

var _exemplar_cache : Dictionary = {}

static func build(savefile : DBPF, tiles_u : int, tiles_v : int) -> Dictionary:
    var model := Sc4CityModel.new()
    return model._build(savefile, tiles_u, tiles_v)

func _build(savefile : DBPF, tiles_u : int, tiles_v : int) -> Dictionary:
    var lots := _lots(savefile)
    var entities : Array = []
    var unresolved := 0
    var index : Array = savefile.indices_by_type.get(BUILDING_SUBFILE, [])
    if not index.is_empty():
        var sub = savefile.get_subfile(index[0].type_id, index[0].group_id, index[0].instance_id, BuildingSubfile)
        for rec in sub.records:
            var tile_x := int(floor(rec.pos_x / TILE_METRES))
            var tile_z := int(floor(rec.pos_z / TILE_METRES))
            var attributes := _exemplar_attributes(rec.exemplar_tgi)
            if attributes.is_empty():
                unresolved += 1
            var lot = _lot_at(lots, tile_x, tile_z)
            var entity := {
                "id": "b%d" % entities.size(),
                "kind": "building",
                "exemplar": [rec.exemplar_tgi[1], rec.exemplar_tgi[2]],
                "position": {"x": tile_x, "y": tile_z},
                "attributes": attributes,
            }
            if lot != null:
                entity["footprint"] = {"min_x": lot.min_x, "min_y": lot.min_z, "max_x": lot.max_x, "max_y": lot.max_z}
                entity["attributes"]["zone_type"] = lot.zone_type
                entity["attributes"]["zone_wealth"] = lot.zone_wealth
            entity["attributes"]["class"] = _classify(entity["attributes"])
            entities.append(entity)
    return {
        "schema": SCHEMA,
        "dimensions": {"width": tiles_u, "height": tiles_v, "tile_metres": TILE_METRES},
        "entities": entities,
        "networks": {"road": _road_graph(savefile)},
        "provenance": {
            "save": savefile.path.get_file(),
            "exemplar_attributes": "runtime read from the local SC4 install",
            "unresolved_exemplars": unresolved,
        },
    }

# -- exemplars ---------------------------------------------------------------

func _exemplar(t : int, g : int, i : int) -> ExemplarSubfile:
    var key := "%08x%08x%08x" % [t, g, i]
    if _exemplar_cache.has(key):
        return _exemplar_cache[key]
    var ex : ExemplarSubfile = null
    if Core.subfile_indices.has(SubfileTGI.TGI2str(t, g, i)):
        ex = Core.subfile(t, g, i, ExemplarSubfile)
    _exemplar_cache[key] = ex
    return ex

## Property lookup that falls back through parent cohorts, as SC4 does.
func _prop(ex : ExemplarSubfile, key : int, depth : int = 0) -> Variant:
    if ex == null or depth > 8:
        return null
    if ex.properties.has(key):
        return ex.properties[key]
    var parent : Dictionary = ex.parent_cohort
    if parent.get("I", 0) == 0:
        return null
    return _prop(_exemplar(parent["T"], parent["G"], parent["I"]), key, depth + 1)

func _exemplar_attributes(tgi : Array) -> Dictionary:
    var ex := _exemplar(tgi[0], tgi[1], tgi[2])
    if ex == null:
        return {}
    var out := {}
    var name = _prop(ex, P_EXEMPLAR_NAME)
    if name is String:
        out["name"] = name
    var pollution = _prop(ex, P_POLLUTION_AT_CENTRE)
    if pollution is Array and pollution.size() >= 1:
        out["pollution"] = {"air": int(pollution[0]), "water": int(pollution[1]) if pollution.size() > 1 else 0,
                "garbage": int(pollution[2]) if pollution.size() > 2 else 0}
    var radius = _prop(ex, P_POLLUTION_RADIUS)
    if radius is Array and radius.size() >= 1:
        out["pollution_radius"] = {"air": float(radius[0]), "water": float(radius[1]) if radius.size() > 1 else 0.0,
                "garbage": float(radius[2]) if radius.size() > 2 else 0.0}
    for pair in [[P_BUDGET_ITEM_COST, "upkeep"], [P_POWER_CONSUMED, "power_consumed"],
            [P_POWER_GENERATED, "power_generated"], [P_WATER_CONSUMED, "water_consumed"], [P_WEALTH, "wealth"]]:
        var value = _prop(ex, pair[0])
        if value is Array:
            var total := 0.0
            for v in value:
                total += float(v)
            value = total
        if value != null and not (value is String) and not (value is bool):
            out[pair[1]] = value
    var capacity = _prop(ex, P_CAPACITY_SATISFIED)
    if capacity is Array and capacity.size() >= 2:
        var cap := {}
        for k in range(0, capacity.size() - 1, 2):
            cap["0x%04x" % int(capacity[k])] = int(capacity[k + 1])
        out["capacity"] = cap
    return out

## R/C/I from Capacity Satisfied demand ids (0x1xxx residential, 0x3xxx
## commercial, 0x4xxx industrial), else civic/utility by what the building does.
func _classify(attributes : Dictionary) -> String:
    var cap : Dictionary = attributes.get("capacity", {})
    for key in cap.keys():
        var demand : int = str(key).hex_to_int()
        match demand >> 12:
            1: return "residential"
            3: return "commercial"
            4: return "industrial"
    # Small values (1 on a fire station) are not generation; plants carry ~1000s.
    if float(attributes.get("power_generated", 0)) >= 100:
        return "power"
    if attributes.has("upkeep"):
        return "civic"
    return "other"

# -- lots and networks ---------------------------------------------------------

func _lots(savefile : DBPF) -> Array:
    var index : Array = savefile.indices_by_type.get(LOT_SUBFILE, [])
    if index.is_empty():
        return []
    var sub = savefile.get_subfile(index[0].type_id, index[0].group_id, index[0].instance_id, LotSubfile)
    return sub.records

func _lot_at(lots : Array, x : int, z : int) -> Variant:
    for lot in lots:
        if x >= lot.min_x and x <= lot.max_x and z >= lot.min_z and z <= lot.max_z:
            return lot
    return null

## Road graph: one node per drivable network tile, an edge between 4-adjacent
## drivable tiles. Adjacency is a candidate for SC4 connectivity (crossing
## flags are not yet used), sufficient for routing experiments.
func _road_graph(savefile : DBPF) -> Dictionary:
    var index : Array = savefile.indices_by_type.get(NETWORK_SUBFILE, [])
    var nodes : Array = []
    var edges : Array = []
    if index.is_empty():
        return {"nodes": nodes, "edges": edges}
    var sub = savefile.get_subfile(index[0].type_id, index[0].group_id, index[0].instance_id, NetworkSubfile)
    var by_tile := {}
    for tile in sub.tiles:
        var kind : String = NetworkSubfile.NETWORK_TYPE_NAMES[tile.network_type] if tile.network_type < NetworkSubfile.NETWORK_TYPE_NAMES.size() else ""
        if kind not in DRIVABLE:
            continue
        var key := Vector2i(tile.tile_x(), tile.tile_z())
        if by_tile.has(key):
            continue
        by_tile[key] = kind
        nodes.append({"id": "n%d_%d" % [key.x, key.y], "position": {"x": key.x, "y": key.y}, "kind": kind})
    for key in by_tile.keys():
        for step in [Vector2i(1, 0), Vector2i(0, 1)]:
            var other : Vector2i = key + step
            if by_tile.has(other):
                var kind : String = by_tile[key] if by_tile[key] == by_tile[other] else "Road"
                edges.append({"id": "e%d" % edges.size(), "from": "n%d_%d" % [key.x, key.y],
                        "to": "n%d_%d" % [other.x, other.y], "kind": kind})
    return {"nodes": nodes, "edges": edges}
