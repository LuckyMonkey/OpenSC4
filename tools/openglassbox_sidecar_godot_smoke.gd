extends SceneTree

const BackendScript = preload("res://simulation/openglassbox_sidecar_backend.gd")

func _init() -> void:
    var backend = BackendScript.new()
    if not backend.start("res://sc4-lab/adapters/openglassbox/openglassbox_sidecar.py"):
        print("OPENGLASSBOX GODOT START FAILED")
        quit(2)
        return
    backend.reset({"roads": [{"x1": 0.0, "y1": 0.0, "x2": 30.0, "y2": 0.0}]})
    var accepted := backend.validate_command({"type": "add_road", "x1": 30.0, "y1": 0.0, "x2": 60.0, "y2": 0.0})
    if not bool(accepted.get("accepted", false)):
        print("OPENGLASSBOX GODOT VALIDATION FAILED %s" % accepted)
        backend.stop()
        quit(2)
        return
    backend.apply_command({"type": "add_road", "x1": 30.0, "y1": 0.0, "x2": 60.0, "y2": 0.0})
    backend.advance_seconds(2.0)
    var snapshot := backend.snapshot()
    var saved := backend.save_state()
    var loaded := backend.load_state(saved)
    backend.stop()
    if not loaded or int(snapshot.get("simulation_tick", -1)) != int(saved.get("simulation_tick", -2)):
        print("OPENGLASSBOX GODOT SMOKE FAILED snapshot=%s saved=%s loaded=%s" % [snapshot, saved, loaded])
        quit(2)
        return
    print("OPENGLASSBOX GODOT SMOKE PASS tick=%d nodes=%d segments=%d" % [
        int(snapshot.get("simulation_tick", -1)),
        int(snapshot.get("nodes", -1)),
        int(snapshot.get("segments", -1)),
    ])
    quit(0)
