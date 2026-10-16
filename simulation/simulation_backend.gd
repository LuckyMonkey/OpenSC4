class_name SimulationBackend
extends RefCounted

## Renderer-independent simulation contract.
##
## Concrete backends must expose plain Dictionaries/Arrays only. Godot Nodes,
## OpenGlassBox pointers, and SC4 parser objects must not cross this boundary.
const API_VERSION := 1
const CONTRACT_ID := "opensc4.simulation.v1"

func backend_id() -> String:
    return "abstract"

func contract_id() -> String:
    return CONTRACT_ID

func backend_fingerprint() -> String:
    return backend_id()

func save_schema() -> String:
    return ""

func capabilities() -> Dictionary:
    return {"api_version": API_VERSION, "contract": CONTRACT_ID}

func reset(_scenario : Dictionary) -> void:
    push_error("SimulationBackend.reset() is abstract")

func advance_seconds(_seconds : float) -> Dictionary:
    push_error("SimulationBackend.advance_seconds() is abstract")
    return {}

func apply_command(_command : Dictionary) -> Dictionary:
    push_error("SimulationBackend.apply_command() is abstract")
    return {"accepted": false, "error": "unsupported_backend"}

func validate_command(_command : Dictionary) -> Dictionary:
    push_error("SimulationBackend.validate_command() is abstract")
    return {"accepted": false, "error": "unsupported_backend"}

func snapshot() -> Dictionary:
    push_error("SimulationBackend.snapshot() is abstract")
    return {}

func save_state() -> Dictionary:
    push_error("SimulationBackend.save_state() is abstract")
    return {}

func load_state(_state : Dictionary) -> bool:
    push_error("SimulationBackend.load_state() is abstract")
    return false

func event_cursor() -> int:
    return 0

func events_since(_cursor : int) -> Array:
    return []
