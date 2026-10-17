extends Node

# Headless city-simulation harness: loads a city like HeadlessCity, then runs
# the OpenGlassBox candidate simulation synchronously for N game days.
#   godot --headless --path . res://tools/SimCity.tscn -- <days> ["<region>" "<city>"]
# A clean run ends with "SIM DONE".

var dat_files = ["SimCity_1.dat", "SimCity_2.dat", "SimCity_3.dat", "SimCity_4.dat", "SimCity_5.dat", "EP1.dat"]

func _ready():
    var args = OS.get_cmdline_user_args()
    var days = int(args[0]) if args.size() >= 1 else 3
    var region = args[1] if args.size() >= 3 else "Timbuktu"
    var city_name = args[2] if args.size() >= 3 else "Big City Tutorial"
    if Core.game_dir == null:
        var config = INI.new("user://config.ini")
        Core.game_dir = config.sections["paths"]["sc4_files"] if config.sections.has("paths") else ProjectSettings.globalize_path("res://")
    for dat_file in dat_files:
        Core.add_dbpf(DBPF.new(Core.game_dir + "/" + dat_file))
    var region_dir = region if region.begins_with("/") else "%s/Regions/%s" % [Core.game_dir, region]
    var city_path = "%s/City - %s.sc4" % [region_dir, city_name]
    Boot.current_city = DBPF.new(city_path)
    Boot.current_city_name = city_name
    Boot.current_city_path = city_path
    Boot.current_region_name = region
    OS.set_environment("OPENSC4_SIM", "0")
    var city = load("res://CityView/CityScene/City.tscn").instantiate()
    add_child(city)
    var sim = CitySim.new()
    add_child(sim)
    if not sim.start(city, Boot.current_city, city.width - 1, city.height - 1, city.get_node("Node3D/Terrain").heightmap, false):
        push_error("SIM FAILED to start")
        get_tree().quit(1)
        return
    for d in range(days):
        var t = Time.get_ticks_msec()
        var stepped = sim.step_day()
        var t_step = Time.get_ticks_msec() - t
        sim.apply_day(stepped)
        print("SIM day %d  %d ms (step+IPC %d ms, apply/draw %d ms)  agents=%s  pollution=%d  busy_links=%d  funds=%d" % [sim.day, Time.get_ticks_msec() - t, t_step, Time.get_ticks_msec() - t - t_step,
            str(sim.last_stats.get("agents", "?")), sim.pollution_total, sim.busy_segments, sim.funds])
        if not sim.last_budget.is_empty() and sim.day % 30 == 0:
            print("SIM month: %s" % JSON.stringify(sim.last_budget))
    sim.stop()
    print("SIM DONE")
    get_tree().quit()
