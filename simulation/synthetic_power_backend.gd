class_name SyntheticPowerBackend
extends SimulationBackend

## A deliberately small deterministic backend used to test the simulation seam.
## Its equations are synthetic and must never be treated as SC4 observations.
const TICK_SECONDS := 1.0
const TICKS_PER_MONTH := 30

var simulation_tick := 0
var simulation_month := 0
var elapsed_seconds := 0.0
var demand := 0.0
var plants : Array[Dictionary] = []
var _last_metrics : Dictionary = {}

func reset(scenario : Dictionary) -> void:
    simulation_tick = 0
    simulation_month = 0
    elapsed_seconds = 0.0
    demand = max(0.0, float(scenario.get("demand", 0.0)))
    plants.clear()
    for spec in scenario.get("plants", []):
        add_plant(float(spec.get("capacity", 0.0)), float(spec.get("funding", 1.0)))
    _recompute_metrics()

func add_plant(capacity : float, funding : float = 1.0) -> int:
    plants.append({
        "capacity": max(0.0, capacity),
        "funding": clampf(funding, 0.0, 1.0),
        "condition": 1.0,
    })
    _recompute_metrics()
    return plants.size() - 1

func set_demand(value : float) -> void:
    demand = max(0.0, value)
    _recompute_metrics()

func set_funding(index : int, value : float) -> bool:
    if index < 0 or index >= plants.size():
        return false
    plants[index]["funding"] = clampf(value, 0.0, 1.0)
    _recompute_metrics()
    return true

func advance_seconds(seconds : float) -> Dictionary:
    if seconds < 0.0:
        return snapshot()
    elapsed_seconds += seconds
    while elapsed_seconds >= TICK_SECONDS:
        elapsed_seconds -= TICK_SECONDS
        simulation_tick += 1
        if simulation_tick % TICKS_PER_MONTH == 0:
            simulation_month = simulation_tick / TICKS_PER_MONTH
        _recompute_metrics()
    return snapshot()

func snapshot() -> Dictionary:
    var result = _last_metrics.duplicate(true)
    result["api_version"] = API_VERSION
    result["simulation_tick"] = simulation_tick
    result["simulation_month"] = simulation_month
    result["elapsed_seconds"] = elapsed_seconds
    result["demand"] = demand
    result["plants"] = plants.duplicate(true)
    return result

func save_state() -> Dictionary:
    return {
        "schema": "opensc4.synthetic-power.v1",
        "api_version": API_VERSION,
        "simulation_tick": simulation_tick,
        "simulation_month": simulation_month,
        "elapsed_seconds": elapsed_seconds,
        "demand": demand,
        "plants": plants.duplicate(true),
    }

func load_state(state : Dictionary) -> bool:
    if state.get("schema", "") != "opensc4.synthetic-power.v1":
        return false
    if int(state.get("api_version", -1)) != API_VERSION:
        return false
    simulation_tick = max(0, int(state.get("simulation_tick", 0)))
    simulation_month = max(0, int(state.get("simulation_month", 0)))
    elapsed_seconds = max(0.0, float(state.get("elapsed_seconds", 0.0)))
    demand = max(0.0, float(state.get("demand", 0.0)))
    plants.clear()
    for plant in state.get("plants", []):
        if typeof(plant) != TYPE_DICTIONARY:
            return false
        plants.append({
            "capacity": max(0.0, float(plant.get("capacity", 0.0))),
            "funding": clampf(float(plant.get("funding", 1.0)), 0.0, 1.0),
            "condition": clampf(float(plant.get("condition", 1.0)), 0.0, 1.0),
        })
    _recompute_metrics()
    return true

func _recompute_metrics() -> void:
    var available_power := 0.0
    var operating_cost := 0.0
    for plant in plants:
        var output = plant["capacity"] * plant["funding"] * plant["condition"]
        available_power += output
        operating_cost += plant["capacity"] * plant["funding"] * 0.1
    var supplied = min(demand, available_power)
    _last_metrics = {
        "available_power": available_power,
        "generated_power": available_power,
        "supplied_power": supplied,
        "unmet_demand": max(0.0, demand - supplied),
        "operating_cost": operating_cost,
        "pollution": available_power * 0.25,
    }
