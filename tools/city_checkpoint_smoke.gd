extends Node

func _ready() -> void:
    call_deferred("run")

func check(condition : bool, label : String) -> bool:
    if not condition:
        push_error("CHECKPOINT FAIL: " + label)
        get_tree().quit(2)
    return condition

func run() -> void:
    var backend := OpenGlassBoxSidecarBackend.new()
    backend.request_timeout_ms = 5000
    if not check(backend.start("res://sc4-lab/adapters/openglassbox/openglassbox_sidecar.py"), "start"):
        return
    var city := {"schema": "opensc4.canonical-city.v1", "dimensions": {"width": 8, "height": 8},
        "entities": [], "networks": {"road": {"nodes": [], "edges": []}},
        "provenance": {"large_request": "x".repeat(200000)}}
    var init := backend.apply_command({"type": "city_init", "city": city, "start_date": "2000-02-28"})
    if not check(bool(init.get("accepted", false)), "large city init"):
        backend.stop()
        return
    var result := backend.apply_command({"type": "city_advance", "days": 2})
    if not check(result.get("date") == "2000-03-01", "calendar"):
        backend.stop()
        return
    var saved := backend.save_state()
    # Exercise Godot's parse/stringify numeric conversion on checkpoint hashes.
    var roundtrip : Dictionary = JSON.parse_string(JSON.stringify(saved, "", true, true))
    if not check(backend.load_state(roundtrip), "JSON checkpoint restore"):
        backend.stop()
        return
    var before := backend.snapshot()
    roundtrip["elapsed_days"] = 99
    if not check(not backend.load_state(roundtrip), "reject corrupted checkpoint"):
        backend.stop()
        return
    if not check(backend.snapshot() == before, "restore failure preserves state"):
        backend.stop()
        return
    var sim := CitySim.new()
    add_child(sim)
    sim.backend = backend
    sim.city_model = city
    sim.checkpoint_path = "/tmp/opensc4-checkpoint-smoke-%d.json" % OS.get_process_id()
    sim._build_views()
    sim.apply_day(sim.step_day())
    var saved_day := sim.day
    if not check(sim.save_checkpoint(), "controller checkpoint write"):
        sim.stop()
        return
    sim.apply_day(sim.step_day())
    if not check(sim.restore_checkpoint() and sim.day == saved_day, "controller restore"):
        sim.stop()
        return
    sim.running = true
    await get_tree().create_timer(0.65).timeout
    if not check(sim.save_checkpoint() and sim.day > saved_day, "join active worker before save"):
        sim.stop()
        return
    var stable_day := sim.day
    sim.apply_day({"reply": {"day": 999}}, sim._generation - 1)
    if not check(sim.day == stable_day, "stale deferred result ignored"):
        sim.stop()
        return
    sim.apply_day({"error": "injected helper failure"})
    if not check(sim.day == stable_day and not sim.running, "failure preserves displayed day"):
        sim.stop()
        return
    backend.stop()
    if not check(sim.restore_checkpoint() and sim.failure.is_empty(), "recover after sidecar exit"):
        sim.stop()
        return
    sim.stop()
    DirAccess.remove_absolute(sim.checkpoint_path)
    sim.queue_free()
    print("CITY CHECKPOINT GODOT PASS: large payload, calendar, JSON roundtrip, transactional rejection, worker join, stale results, exit recovery")
    get_tree().quit(0)
