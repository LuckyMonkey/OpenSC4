class_name SimulationBackend
extends RefCounted

## Renderer-independent simulation contract.
##
## Concrete backends must expose plain Dictionaries/Arrays only. Godot Nodes,
## OpenGlassBox pointers, and SC4 parser objects must not cross this boundary.
const API_VERSION := 1

func backend_id() -> String:
    return "abstract"

func capabilities() -> Dictionary:
    return {"api_version": API_VERSION}

func reset(_scenario : Dictionary) -> void:
    push_error("SimulationBackend.reset() is abstract")

func advance_seconds(_seconds : float) -> Dictionary:
    push_error("SimulationBackend.advance_seconds() is abstract")
    return {}

func apply_command(_command : Dictionary) -> Dictionary:
    push_error("SimulationBackend.apply_command() is abstract")
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
