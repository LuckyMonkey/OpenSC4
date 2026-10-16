extends Node

## Windowed performance probe. It reports timings; it does not set acceptance
## thresholds because renderer and driver performance are machine-dependent.

const DEFAULT_REGION := "Timbuktu"
const DEFAULT_CITY := "Big City Tutorial"
const SAMPLE_FRAMES := 90

var dat_files = [
    "SimCity_1.dat",
    "SimCity_2.dat",
    "SimCity_3.dat",
    "SimCity_4.dat",
    "SimCity_5.dat",
    "EP1.dat",
]

func _ready() -> void:
    var user_args = OS.get_cmdline_user_args()
    var region = user_args[0] if user_args.size() >= 1 else DEFAULT_REGION
    var city_name = user_args[1] if user_args.size() >= 2 else DEFAULT_CITY
    if Core.game_dir == null:
        var config = INI.new("user://config.ini")
        if config.sections.has("paths"):
            Core.game_dir = config.sections["paths"]["sc4_files"]
    print("PERF environment: godot=%s renderer=%s fast_water=%s" % [
        Engine.get_version_info().string,
        RenderingServer.get_video_adapter_name(),
        Core.fast_water_enabled(),
    ])
    for dat_file in dat_files:
        Core.add_dbpf(DBPF.new(Core.game_dir + "/" + dat_file))

    var city_path = "%s/Regions/%s/City - %s.sc4" % [Core.game_dir, region, city_name]
    if not FileAccess.file_exists(city_path):
        push_error("No such city save: %s" % city_path)
        get_tree().quit(1)
        return
    Boot.current_city = DBPF.new(city_path)
    Boot.current_city_name = city_name
    Boot.current_city_path = city_path
    Boot.current_region_name = region

    var load_start = Time.get_ticks_usec()
    var city = load("res://CityView/CityScene/City.tscn").instantiate()
    add_child(city)
    var load_ms = _elapsed_ms(load_start)
    if not city.has_method("set_building_view"):
        push_error("City script not attached (compile error?)")
        get_tree().quit(1)
        return
    print("PERF startup_ms=%.2f" % load_ms)

    await get_tree().process_frame
    var camera = city.get_node("CameraHandler")
    var steady = await _sample_pan(camera)
    print("PERF steady_pan frames=%d elapsed_ms=%.2f ms_per_frame=%.3f" % [
        steady.frames, steady.elapsed_ms, steady.ms_per_frame])

    var view_times = []
    for zoom in range(1, 7):
        var view_start = Time.get_ticks_usec()
        city.set_building_view(zoom, 2)
        view_times.append({"zoom": zoom, "elapsed_ms": _elapsed_ms(view_start)})
    print("PERF view_changes=%s" % JSON.stringify(view_times))

    # Force a view change away and back so the optional cache has a measurable
    # revisit case. With the cache disabled this intentionally rebuilds.
    city.set_building_view(4, 2)
    var revisit_start = Time.get_ticks_usec()
    city.set_building_view(5, 2)
    print("PERF revisit_zoom5_ms=%.3f" % _elapsed_ms(revisit_start))

    var free_times = []
    for rot in range(4):
        var free_start = Time.get_ticks_usec()
        city.set_building_view(3, 2, rot)
        free_times.append({"rotation": rot, "elapsed_ms": _elapsed_ms(free_start)})
    print("PERF free_view_changes=%s" % JSON.stringify(free_times))
    print("PERF COMPLETE")
    get_tree().quit()

func _sample_pan(camera : Node) -> Dictionary:
    var start = Time.get_ticks_usec()
    var original = camera.position
    for i in range(SAMPLE_FRAMES):
        camera.position = original + Vector3(float(i) * 0.08, 0.0, 0.0)
        await get_tree().process_frame
    camera.position = original
    var elapsed_ms = _elapsed_ms(start)
    return {
        "frames": SAMPLE_FRAMES,
        "elapsed_ms": elapsed_ms,
        "ms_per_frame": elapsed_ms / float(SAMPLE_FRAMES),
    }

func _elapsed_ms(start_usec : int) -> float:
    return float(Time.get_ticks_usec() - start_usec) / 1000.0
