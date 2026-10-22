class_name CitySim
extends Node

## Runs a loaded city on the OpenGlassBox candidate backend and draws it.
##
## - money: TAX_001 (verified SC4 rule) with placeholder taxable bases, plus
##   upkeep from the buildings' own SC4 exemplars;
## - pollution: OpenGlassBox Layer diffusion/decay fed by SC4 exemplar
##   "Pollution at centre" and radius -- candidate behavior, not SC4-verified;
## - traffic: OpenGlassBox commuter agents routed on the save's road graph --
##   candidate behavior, not SC4-verified.
##
## Keys: F6 pause/resume, F7 pollution overlay, F8 traffic overlay.

signal month_closed(budget : Dictionary)

const SIDECAR := "res://sc4-lab/adapters/openglassbox/openglassbox_sidecar.py"
const OVERLAY_LIFT := 0.6

@export var seconds_per_day : float = 0.5
@export var start_funds : int = 50000

var backend : OpenGlassBoxSidecarBackend
var city_model : Dictionary = {}
var running := false
var day := 0
var funds := 0
var last_budget : Dictionary = {}
var last_stats : Dictionary = {}
var pollution_total := 0
var busy_segments := 0
var simulation_date := "2000-01-01"
var failure := ""
var _generation := 0
var checkpoint_path := "user://city-simulation-checkpoint.json"
var _city : Node
# One worker thread owns the sidecar pipe while running (a game day of a large
# city takes seconds of OpenGlassBox time). Results reach the main thread via
# call_deferred only; nothing else is shared.
var _thread : Thread
var _stop_requested := false
var _heights : Array = []
var _hud : Label
var _pollution_mesh : MeshInstance3D
var _traffic_mesh : MeshInstance3D

func start(city : Node, savefile : DBPF, tiles_u : int, tiles_v : int, heights : Array = [], threaded : bool = true) -> bool:
    _stop_requested = false
    _generation += 1
    failure = ""
    _city = city
    _heights = heights
    var t0 := Time.get_ticks_msec()
    city_model = Sc4CityModel.build(savefile, tiles_u, tiles_v)
    var debug_path := OS.get_environment("OPENSC4_SIM_DUMP")
    if not debug_path.is_empty():
        var f := FileAccess.open(debug_path, FileAccess.WRITE)
        f.store_string(JSON.stringify(city_model))
        f.close()
    backend = OpenGlassBoxSidecarBackend.new()
    if not backend.start(SIDECAR):
        push_error("CitySim: OpenGlassBox sidecar did not start")
        return false
    var reply := backend.apply_command({"type": "city_init", "city": city_model, "funds": start_funds,
            "rates": [9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0], "mult": 1.0})
    if not bool(reply.get("accepted", false)):
        push_error("CitySim: city_init rejected: %s" % reply)
        backend.stop()
        return false
    funds = start_funds
    _build_views()
    running = threaded
    if threaded:
        _thread = Thread.new()
        _thread.start(_worker)
    Log.info("CitySim started in %d ms: %s" % [Time.get_ticks_msec() - t0, reply.get("city", {})])
    return true

func stop() -> void:
    running = false
    _generation += 1
    _stop_requested = true
    if _thread != null and _thread.is_started():
        _thread.wait_to_finish()
    _thread = null
    if backend != null:
        backend.stop()
        backend = null

func _exit_tree() -> void:
    stop()

## Synchronous step: advance, then fetch the pollution layer and traffic.
## Safe to call from the worker thread (touches only the backend).
func step_day() -> Dictionary:
    var reply := backend.apply_command({"type": "city_advance", "days": 1})
    if not bool(reply.get("accepted", false)):
        return {"error": str(backend.last_error)}
    var layer_reply := backend.apply_command({"type": "city_layer", "name": "AirPollution"})
    if not bool(layer_reply.get("accepted", false)):
        return {"error": str(backend.last_error)}
    var traffic_reply := backend.apply_command({"type": "city_traffic"})
    if not bool(traffic_reply.get("accepted", false)):
        return {"error": str(backend.last_error)}
    var layer : Dictionary = layer_reply.get("layer", {})
    var segments : Array = traffic_reply.get("traffic", {}).get("segments", [])
    return {"reply": reply, "layer": layer, "segments": segments}

## Main thread: fold one stepped day into state and redraw.
func apply_day(result : Dictionary, generation : int = -1) -> void:
    if generation >= 0 and generation != _generation:
        return
    if result.has("error"):
        failure = str(result.error)
        running = false
        _update_hud()
        return
    var reply : Dictionary = result.get("reply", {})
    day = int(reply.get("day", day + 1))
    simulation_date = str(reply.get("date", simulation_date))
    last_stats = reply.get("stats", {})
    funds = int(reply.get("funds", funds))
    for month in reply.get("months", []):
        last_budget = month
        month_closed.emit(month)
    var layer : Dictionary = result.get("layer", {})
    pollution_total = int(layer.get("total", 0))
    _draw_pollution(layer)
    _draw_traffic(result.get("segments", []))
    _update_hud()

func _worker() -> void:
    var generation := _generation
    while not _stop_requested:
        if not running:
            OS.delay_msec(100)
            continue
        var started := Time.get_ticks_msec()
        var result := step_day()
        call_deferred("apply_day", result, generation)
        if result.has("error"):
            running = false
        var spare := int(seconds_per_day * 1000.0) - (Time.get_ticks_msec() - started)
        if spare > 0:
            OS.delay_msec(spare)

func _unhandled_input(event : InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        match event.keycode:
            KEY_F6:
                if failure.is_empty():
                    running = not running
                _update_hud()
            KEY_F9: save_checkpoint()
            KEY_F10: restore_checkpoint()
            KEY_F7: if _pollution_mesh: _pollution_mesh.visible = not _pollution_mesh.visible
            KEY_F8: if _traffic_mesh: _traffic_mesh.visible = not _traffic_mesh.visible

# Join the sole pipe owner before checkpoint I/O. Deferred results from that
# worker are invalidated, then display state is refreshed from the backend.
func _join_worker() -> void:
    running = false
    _stop_requested = true
    if _thread != null and _thread.is_started():
        _thread.wait_to_finish()
    _thread = null
    _generation += 1

func _resume_worker() -> void:
    _stop_requested = false
    _thread = Thread.new()
    _thread.start(_worker)

func _refresh_checkpoint_view() -> void:
    var state := backend.snapshot()
    if state.is_empty():
        failure = str(backend.last_error)
        return
    day = int(state.get("elapsed_days", day))
    simulation_date = str(state.get("date", simulation_date))
    funds = int(state.get("funds", funds))
    var layer_reply := backend.apply_command({"type": "city_layer", "name": "AirPollution"})
    var traffic_reply := backend.apply_command({"type": "city_traffic"})
    if not bool(layer_reply.get("accepted", false)) or not bool(traffic_reply.get("accepted", false)):
        failure = str(backend.last_error)
        return
    var layer : Dictionary = layer_reply.get("layer", {})
    pollution_total = int(layer.get("total", 0))
    _draw_pollution(layer)
    _draw_traffic(traffic_reply.get("traffic", {}).get("segments", []))
    last_budget = {}
    last_stats = state

func save_checkpoint() -> bool:
    if backend == null:
        return false
    _join_worker()
    var state := backend.save_state()
    var success := false
    if not state.is_empty():
        var file := FileAccess.open(checkpoint_path + ".tmp", FileAccess.WRITE)
        if file != null:
            file.store_string(JSON.stringify(state, "", true, true))
            file.flush()
            var write_error := file.get_error()
            file.close()
            if write_error == OK:
                success = DirAccess.rename_absolute(ProjectSettings.globalize_path(checkpoint_path + ".tmp"),
                    ProjectSettings.globalize_path(checkpoint_path)) == OK
    failure = "" if success else "Checkpoint save failed: %s" % backend.last_error
    _refresh_checkpoint_view()
    _resume_worker()
    _update_hud()
    return success

func restore_checkpoint() -> bool:
    if backend == null:
        return false
    _join_worker()
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(checkpoint_path))
    var success := false
    if parsed is Dictionary:
        # A checkpoint belongs to this loaded city's geometry, not another map.
        var saved_city : Dictionary = parsed.get("initial", {}).get("city", {})
        var normalized_city : Dictionary = JSON.parse_string(JSON.stringify(city_model, "", true, true))
        if saved_city == normalized_city:
            if not backend.is_running():
                backend.start(SIDECAR)
            success = backend.load_state(parsed)
    failure = "" if success else "Checkpoint restore rejected: %s" % backend.last_error
    if success:
        _refresh_checkpoint_view()
    _resume_worker()
    _update_hud()
    return success

# -- views ---------------------------------------------------------------------

func _build_views() -> void:
    var canvas := CanvasLayer.new()
    canvas.layer = 5
    add_child(canvas)
    _hud = Label.new()
    # Top-right, clear of the city editor panel on the left.
    _hud.set_anchors_preset(Control.PRESET_TOP_RIGHT)
    _hud.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    _hud.grow_horizontal = Control.GROW_DIRECTION_BEGIN
    _hud.offset_right = -16
    _hud.offset_top = 16
    _hud.add_theme_color_override("font_color", Color(1, 1, 1))
    _hud.add_theme_color_override("font_outline_color", Color(0, 0, 0))
    _hud.add_theme_constant_override("outline_size", 6)
    canvas.add_child(_hud)
    _pollution_mesh = MeshInstance3D.new()
    _pollution_mesh.name = "PollutionOverlay"
    _traffic_mesh = MeshInstance3D.new()
    _traffic_mesh.name = "TrafficOverlay"
    var root : Node = _city.get_node_or_null("Node3D") if _city != null else null
    if root == null:
        root = self
    root.add_child(_pollution_mesh)
    root.add_child(_traffic_mesh)
    _update_hud()

func _height(x : float, z : float) -> float:
    if _heights.is_empty():
        return 0.0
    var j := clampi(int(z), 0, _heights.size() - 1)
    var i := clampi(int(x), 0, _heights[j].size() - 1)
    return float(_heights[j][i]) / 16.0

## One quad per polluted tile, colour by amount, draped just above the terrain.
func _draw_pollution(layer : Dictionary) -> void:
    var w := int(layer.get("w", 0))
    var data : Array = layer.get("data", [])
    if w == 0 or data.is_empty():
        _pollution_mesh.mesh = null
        return
    var peak := 0
    for v in data:
        peak = maxi(peak, int(v))
    if peak == 0:
        _pollution_mesh.mesh = null
        return
    var st := SurfaceTool.new()
    st.begin(Mesh.PRIMITIVE_TRIANGLES)
    for idx in data.size():
        var amount := int(data[idx])
        if amount <= 0:
            continue
        var u := idx % w
        var v := idx / w
        var t := clampf(float(amount) / float(peak), 0.0, 1.0)
        st.set_color(Color(0.55 + 0.45 * t, 0.45 * (1.0 - t), 0.1, 0.15 + 0.5 * t))
        var y := _height(u + 0.5, v + 0.5) + OVERLAY_LIFT
        var a := Vector3(u, y, v)
        var b := Vector3(u + 1, y, v)
        var c := Vector3(u + 1, y, v + 1)
        var d := Vector3(u, y, v + 1)
        st.add_vertex(a); st.add_vertex(b); st.add_vertex(c)
        st.add_vertex(a); st.add_vertex(c); st.add_vertex(d)
    var mat := StandardMaterial3D.new()
    mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    mat.vertex_color_use_as_albedo = true
    mat.cull_mode = BaseMaterial3D.CULL_DISABLED
    mat.no_depth_test = false
    var mesh := st.commit()
    mesh.surface_set_material(0, mat)
    _pollution_mesh.mesh = mesh

## Road segments coloured and sized by OpenGlassBox smoothed flow relative to
## the busiest link (green → yellow → red). Saturation stays tiny while one
## agent stands for many residents, so relative flow is the readable signal.
func _draw_traffic(segments : Array) -> void:
    busy_segments = 0
    var peak := 0.0
    for s in segments:
        peak = maxf(peak, float(s[4]))
    var st := SurfaceTool.new()
    st.begin(Mesh.PRIMITIVE_TRIANGLES)
    var any := false
    for s in segments:
        var flow := float(s[4])
        if flow <= 0.01:
            continue
        busy_segments += 1
        var rel := sqrt(flow / peak) if peak > 0.0 else 0.0
        if rel < 0.08:
            continue
        any = true
        st.set_color(Color(clampf(2.0 * rel, 0.0, 1.0), clampf(2.0 - 2.0 * rel, 0.0, 1.0), 0.05, 0.35 + 0.6 * rel))
        var p1 := Vector3(float(s[0]), 0.0, float(s[1]))
        var p2 := Vector3(float(s[2]), 0.0, float(s[3]))
        p1.y = _height(p1.x, p1.z) + OVERLAY_LIFT + 0.1
        p2.y = _height(p2.x, p2.z) + OVERLAY_LIFT + 0.1
        var side := (p2 - p1).cross(Vector3.UP).normalized() * (0.08 + 0.25 * rel)
        st.add_vertex(p1 - side); st.add_vertex(p1 + side); st.add_vertex(p2 + side)
        st.add_vertex(p1 - side); st.add_vertex(p2 + side); st.add_vertex(p2 - side)
    if not any:
        _traffic_mesh.mesh = null
        return
    var mat := StandardMaterial3D.new()
    mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    mat.vertex_color_use_as_albedo = true
    mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    mat.cull_mode = BaseMaterial3D.CULL_DISABLED
    var mesh := st.commit()
    mesh.surface_set_material(0, mat)
    _traffic_mesh.mesh = mesh

func _update_hud() -> void:
    if _hud == null:
        return
    var lines := PackedStringArray()
    lines.append("SIM %s   day %d   (F6 pause, F7 pollution, F8 traffic)" % ["RUNNING" if running else "PAUSED", day])
    lines.append("%s   F9 save checkpoint / F10 restore" % simulation_date)
    if not failure.is_empty():
        lines.append("SIM ERROR: %s" % failure)
    lines.append("Funds  §%s" % _thousands(funds))
    if not last_budget.is_empty():
        lines.append("Last month  tax §%s  upkeep §%s   [tax rule TAX_001 verified; bases placeholder]" % [
            _thousands(int(last_budget.get("tax_income", 0))), _thousands(int(last_budget.get("expenses", 0)))])
    lines.append("Commuters %s   busy road links %d   [OpenGlassBox candidate traffic]" % [
        str(int(last_stats.get("agents", 0))), busy_segments])
    lines.append("Air pollution total %d   [OpenGlassBox candidate diffusion]" % pollution_total)
    _hud.text = "\n".join(lines)

static func _thousands(value : int) -> String:
    var s := str(absi(value))
    var out := ""
    while s.length() > 3:
        out = "," + s.substr(s.length() - 3) + out
        s = s.substr(0, s.length() - 3)
    return ("-" if value < 0 else "") + s + out
