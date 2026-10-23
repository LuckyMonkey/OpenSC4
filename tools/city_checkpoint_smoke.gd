extends Node

class SlowCheckpoint extends CitySim:
    func _checkpoint_io(operation : String, path : String, model : Dictionary) -> Dictionary:
        OS.delay_msec(200)
        return super._checkpoint_io(operation, path, model)

func await_checkpoint(sim : CitySim) -> int:
    var frames := 0
    var deadline := Time.get_ticks_msec() + 10000
    while not sim._checkpoint_operation.is_empty() and Time.get_ticks_msec() < deadline:
        await get_tree().process_frame
        frames += 1
    return frames if sim._checkpoint_operation.is_empty() else -1

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
    var sim := SlowCheckpoint.new()
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
    sim.running = true
    if not check(sim.request_checkpoint("save"), "async save accepted"):
        sim.stop()
        return
    if not check(not sim.request_checkpoint("restore") and not sim.save_checkpoint(), "concurrent requests rejected"):
        sim.stop()
        return
    var frames := await await_checkpoint(sim)
    if not check(frames > 2 and sim.failure.is_empty() and not sim.running, "save keeps rendering and finishes paused"):
        sim.stop()
        return
    var async_day := sim.day
    sim._join_worker()
    sim.apply_day(sim.step_day())
    sim._resume_worker()
    sim.request_checkpoint("restore")
    frames = await await_checkpoint(sim)
    if not check(frames > 2 and sim.failure.is_empty() and sim.day == async_day, "async restore refreshes state"):
        sim.stop()
        return
    for invalid in ["{broken", '{"initial": []}', '{"initial": {"city": {}}}']:
        var file := FileAccess.open(sim.checkpoint_path, FileAccess.WRITE)
        file.store_string(invalid)
        file.close()
        sim.request_checkpoint("restore")
        await await_checkpoint(sim)
        if not check(not sim.failure.is_empty() and sim.day == async_day and backend.is_running(), "malformed/foreign restore preserves city"):
            sim.stop()
            return
    sim.checkpoint_path += "/missing/checkpoint.json"
    sim.request_checkpoint("save")
    await await_checkpoint(sim)
    if not check(sim.failure.contains("temporary file") and sim.day == async_day, "file failure preserves diagnostic and state"):
        sim.stop()
        return
    sim.checkpoint_path = "/tmp/opensc4-checkpoint-smoke-%d.json" % OS.get_process_id()
    sim.stop()
    DirAccess.remove_absolute(sim.checkpoint_path)
    sim.queue_free()
    print("CITY CHECKPOINT GODOT PASS: large payload, calendar, JSON roundtrip, transactional rejection, worker join, stale results, exit recovery, responsive async save/restore, request exclusion, malformed/foreign/file failure")
    get_tree().quit(0)
