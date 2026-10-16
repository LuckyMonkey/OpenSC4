class_name SyntheticPowerBackend
extends SimulationBackend

## A deliberately small deterministic backend used to test the simulation seam.
## Its equations are synthetic and must never be treated as SC4 observations.
const TICK_SECONDS := 1.0
const TICKS_PER_MONTH := 30
const EVENT_RETENTION := 256

var simulation_tick := 0
var simulation_month := 0
var elapsed_seconds := 0.0
var demand := 0.0
var plants : Array[Dictionary] = []
var _last_metrics : Dictionary = {}
var _event_sequence := 0
var _events : Array[Dictionary] = []

func backend_id() -> String:
    return "synthetic-power-v1"

func contract_id() -> String:
    return CONTRACT_ID

func backend_fingerprint() -> String:
    return "synthetic-power-v1-equations-1"

func save_schema() -> String:
    return "opensc4.synthetic-power.v1"

func capabilities() -> Dictionary:
    return {
        "api_version": API_VERSION,
        "contract": CONTRACT_ID,
        "backend_fingerprint": backend_fingerprint(),
        "fixed_tick_seconds": TICK_SECONDS,
        "save_schema": save_schema(),
        "supports_commands": true,
        "supports_events": true,
        "supports_save_load": true,
        "event_retention": EVENT_RETENTION,
    }

func reset(scenario : Dictionary) -> void:
    simulation_tick = 0
    simulation_month = 0
    elapsed_seconds = 0.0
    _event_sequence = 0
    _events.clear()
    demand = max(0.0, float(scenario.get("demand", 0.0)))
    plants.clear()
    for spec in scenario.get("plants", []):
        add_plant(float(spec.get("capacity", 0.0)), float(spec.get("funding", 1.0)))
    _recompute_metrics()
    _emit_event("reset", {"plant_count": plants.size(), "demand": demand})

func add_plant(capacity : float, funding : float = 1.0) -> int:
    plants.append({
        "capacity": max(0.0, capacity),
        "funding": clampf(funding, 0.0, 1.0),
        "condition": 1.0,
    })
    _recompute_metrics()
    _emit_event("plant_added", {"index": plants.size() - 1})
    return plants.size() - 1

func set_demand(value : float) -> void:
    demand = max(0.0, value)
    _recompute_metrics()
    _emit_event("demand_changed", {"value": demand})

func set_funding(index : int, value : float) -> bool:
    if index < 0 or index >= plants.size():
        return false
    plants[index]["funding"] = clampf(value, 0.0, 1.0)
    _recompute_metrics()
    _emit_event("funding_changed", {"index": index, "value": plants[index]["funding"]})
    return true

func validate_command(command : Dictionary) -> Dictionary:
    var kind = command.get("type", "")
    match kind:
        "set_demand":
            return {"accepted": true, "type": kind}
        "set_funding":
            var index = int(command.get("index", -1))
            if index < 0 or index >= plants.size():
                return {"accepted": false, "error": "invalid_plant_index", "command": command}
            return {"accepted": true, "type": kind}
        "add_plant":
            return {"accepted": true, "type": kind}
        _:
            return {"accepted": false, "error": "unknown_command", "command": command}

func apply_command(command : Dictionary) -> Dictionary:
    var validation = validate_command(command)
    if not validation.get("accepted", false):
        return validation
    var kind = command.get("type", "")
    match kind:
        "set_demand":
            set_demand(float(command.get("value", 0.0)))
        "set_funding":
            set_funding(int(command.get("index", -1)), float(command.get("value", 0.0)))
        "add_plant":
            add_plant(float(command.get("capacity", 0.0)), float(command.get("funding", 1.0)))
    return {"accepted": true, "command": command, "snapshot": snapshot()}

func advance_seconds(seconds : float) -> Dictionary:
    if seconds < 0.0:
        return snapshot()
    elapsed_seconds += seconds
    while elapsed_seconds >= TICK_SECONDS:
        elapsed_seconds -= TICK_SECONDS
        simulation_tick += 1
        if simulation_tick % TICKS_PER_MONTH == 0:
            simulation_month = simulation_tick / TICKS_PER_MONTH
            _emit_event("month_advanced", {"month": simulation_month})
        _recompute_metrics()
    return snapshot()

func snapshot() -> Dictionary:
    var result = _last_metrics.duplicate(true)
    result["backend_id"] = backend_id()
    result["api_version"] = API_VERSION
    result["simulation_tick"] = simulation_tick
    result["simulation_month"] = simulation_month
    result["elapsed_seconds"] = elapsed_seconds
    result["demand"] = demand
    result["plants"] = plants.duplicate(true)
    result["event_cursor"] = event_cursor()
    return result

func save_state() -> Dictionary:
    return {
        "schema": save_schema(),
        "api_version": API_VERSION,
        "simulation_tick": simulation_tick,
        "simulation_month": simulation_month,
        "elapsed_seconds": elapsed_seconds,
        "demand": demand,
        "plants": plants.duplicate(true),
        "event_cursor": event_cursor(),
    }

func load_state(state : Dictionary) -> bool:
    if state.get("schema", "") != save_schema():
        return false
    if int(state.get("api_version", -1)) != API_VERSION:
        return false
    simulation_tick = max(0, int(state.get("simulation_tick", 0)))
    simulation_month = max(0, int(state.get("simulation_month", 0)))
    elapsed_seconds = max(0.0, float(state.get("elapsed_seconds", 0.0)))
    _event_sequence = max(0, int(state.get("event_cursor", 0)))
    _events.clear()
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
    _emit_event("state_loaded", {"event_cursor": _event_sequence})
    return true

func event_cursor() -> int:
    return _event_sequence

func events_since(cursor : int) -> Array:
    var result : Array = []
    for event in _events:
        if int(event.get("sequence", 0)) > cursor:
            result.append(event.duplicate(true))
    return result

func _emit_event(kind : String, payload : Dictionary) -> void:
    _event_sequence += 1
    _events.append({
        "sequence": _event_sequence,
        "type": kind,
        "simulation_tick": simulation_tick,
        "simulation_month": simulation_month,
        "payload": payload.duplicate(true),
    })
    while _events.size() > EVENT_RETENTION:
        _events.pop_front()

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
