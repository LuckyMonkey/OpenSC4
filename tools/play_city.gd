extends Node

# Dev launcher: boot straight into a city with the live simulation running.
#   godot --path . res://tools/PlayCity.tscn [-- "<region>" "<city>"]
# Default Timbuktu / Big City Tutorial. F6 pause, F7 pollution, F8 traffic.

var dat_files = ["SimCity_1.dat", "SimCity_2.dat", "SimCity_3.dat", "SimCity_4.dat", "SimCity_5.dat", "EP1.dat"]

func _ready():
    var args = OS.get_cmdline_user_args()
    var region = args[0] if args.size() >= 2 else "Timbuktu"
    var city_name = args[1] if args.size() >= 2 else "Big City Tutorial"
    if Core.game_dir == null:
        var config = INI.new("user://config.ini")
        Core.game_dir = config.sections["paths"]["sc4_files"] if config.sections.has("paths") else ProjectSettings.globalize_path("res://")
    for dat_file in dat_files:
        var archive := DBPF.new(Core.game_dir + "/" + dat_file)
        if not archive.loaded:
            _show_load_error("Cannot read game archive: " + dat_file)
            return
        Core.add_dbpf(archive)
    var region_dir = region if region.begins_with("/") else "%s/Regions/%s" % [Core.game_dir, region]
    Boot.current_city = DBPF.new("%s/City - %s.sc4" % [region_dir, city_name])
    if not Boot.current_city.loaded:
        _show_load_error("Cannot read city save: " + city_name)
        return
    Boot.current_city_name = city_name
    Boot.current_city_path = "%s/City - %s.sc4" % [region_dir, city_name]
    Boot.current_region_name = region
    add_child(load("res://CityView/CityScene/City.tscn").instantiate())

func _show_load_error(message : String) -> void:
    push_error(message)
    var label := Label.new()
    label.text = "OpenSC4 — city could not load\n\n%s\n\nGame folder: %s\n\nCheck that the game drive is readable, then relaunch." % [message, Core.game_dir]
    label.position = Vector2(32, 32)
    label.add_theme_font_size_override("font_size", 22)
    add_child(label)
