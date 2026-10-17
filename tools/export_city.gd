extends Node

# Export a city save as the canonical city JSON (simulation/sc4_city_model.gd).
#   godot --headless --path . res://tools/ExportCity.tscn -- <out.json> ["<region>" "<city name>"]
# Region/city default to Timbuktu / Big City Tutorial. A region may also be an
# absolute Regions directory (for profile saves outside the install).

var dat_files = ["SimCity_1.dat", "SimCity_2.dat", "SimCity_3.dat", "SimCity_4.dat", "SimCity_5.dat", "EP1.dat"]

func _ready():
    var args = OS.get_cmdline_user_args()
    if args.is_empty():
        push_error("usage: -- <out.json> [region city]")
        get_tree().quit(2)
        return
    var out_path : String = args[0]
    var region = args[1] if args.size() >= 3 else "Timbuktu"
    var city_name = args[2] if args.size() >= 3 else "Big City Tutorial"
    if Core.game_dir == null:
        var config = INI.new("user://config.ini")
        Core.game_dir = config.sections["paths"]["sc4_files"] if config.sections.has("paths") else ProjectSettings.globalize_path("res://")
    for dat_file in dat_files:
        Core.add_dbpf(DBPF.new(Core.game_dir + "/" + dat_file))
    var region_dir = region if region.begins_with("/") else "%s/Regions/%s" % [Core.game_dir, region]
    var city_path = "%s/City - %s.sc4" % [region_dir, city_name]
    if not FileAccess.file_exists(city_path):
        push_error("No such city save: %s" % city_path)
        get_tree().quit(1)
        return
    var save = DBPF.new(city_path)
    var info = save.get_subfile(0xca027edb, 0xca027ee1, 0, SC4ReadRegionalCity)
    var model = Sc4CityModel.build(save, info.size[0] * 64, info.size[1] * 64)
    var file = FileAccess.open(out_path, FileAccess.WRITE)
    file.store_string(JSON.stringify(model, "  "))
    file.close()
    var classes = {}
    for e in model["entities"]:
        var c = e["attributes"]["class"]
        classes[c] = classes.get(c, 0) + 1
    print("EXPORT DONE %s entities=%d classes=%s road_nodes=%d road_edges=%d unresolved=%d" % [out_path,
        model["entities"].size(), classes, model["networks"]["road"]["nodes"].size(),
        model["networks"]["road"]["edges"].size(), model["provenance"]["unresolved_exemplars"]])
    get_tree().quit()
