extends Node

const SyntheticPowerBackendScript = preload("res://simulation/synthetic_power_backend.gd")

func _fail(message : String) -> void:
    push_error("SYNTHETIC BACKEND FAIL: %s" % message)
    get_tree().quit(1)

func _expect(condition : bool, message : String) -> bool:
    if not condition:
        _fail(message)
        return false
    return true

func _ready() -> void:
    var backend = SyntheticPowerBackendScript.new()
    backend.reset({
        "demand": 50.0,
        "plants": [{"capacity": 100.0, "funding": 1.0}],
    })
    var initial = backend.snapshot()
    if not _expect(is_equal_approx(initial["generated_power"], 100.0), "initial generation"):
        return
    if not _expect(is_equal_approx(initial["unmet_demand"], 0.0), "initial demand"):
        return

    backend.set_demand(150.0)
    var shortfall = backend.snapshot()
    if not _expect(is_equal_approx(shortfall["unmet_demand"], 50.0), "demand shortfall"):
        return

    backend.add_plant(50.0)
    var balanced = backend.snapshot()
    if not _expect(is_equal_approx(balanced["supplied_power"], 150.0), "second plant supply"):
        return

    backend.advance_seconds(30.0)
    if not _expect(backend.snapshot()["simulation_month"] == 1, "fixed month clock"):
        return

    var saved = backend.save_state()
    var restored = SyntheticPowerBackendScript.new()
    if not _expect(restored.load_state(saved), "save/load"):
        return
    if not _expect(
        is_equal_approx(restored.snapshot()["available_power"], backend.snapshot()["available_power"]),
        "restored metrics"):
        return

    print("SYNTHETIC BACKEND PASS")
    get_tree().quit()
