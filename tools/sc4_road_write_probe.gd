extends Node

# Writes one synthetic straight Road tile to a new path, using the same narrow
# writer as the city UI. This is an operator probe, not a production save
# command; it never overwrites an existing destination.

func _ready():
    var args = OS.get_cmdline_user_args()
    if args.size() < 2:
        print("usage: godot --headless --path . res://tools/SC4RoadWriteProbe.tscn -- source.sc4 destination.sc4")
        get_tree().quit(2)
        return
    var source = args[0]
    var destination = args[1]
    var dbpf = DBPF.new(source)
    if not dbpf.loaded:
        print("SOURCE_LOAD_FAILED")
        get_tree().quit(2)
        return
    var nindex = dbpf.indices_by_type.get(0xc9c05c6e, [])
    var iindex = dbpf.indices_by_type.get(0x6a0f82b2, [])
    if nindex.size() != 1 or iindex.size() != 1:
        print("UNSUPPORTED_SUBFILE_SHAPE")
        get_tree().quit(2)
        return
    var network : NetworkSubfile = dbpf.get_subfile(
        nindex[0].type_id, nindex[0].group_id, nindex[0].instance_id, NetworkSubfile)
    var network_map : NetworkIndexSubfile = dbpf.get_subfile(
        iindex[0].type_id, iindex[0].group_id, iindex[0].instance_id, NetworkIndexSubfile)
    var occupied = {}
    for tile in network.tiles:
        if tile.is_present():
            occupied[Vector2i(tile.tile_x(), tile.tile_z())] = true
    var city_size = int(sqrt(float(network_map.city_tile_count)))
    var location = Vector2i(-1, -1)
    for z in range(city_size):
        for x in range(city_size):
            if not occupied.has(Vector2i(x, z)):
                location = Vector2i(x, z)
                break
        if location.x >= 0:
            break
    if location.x < 0:
        print("NO_EMPTY_NETWORK_TILE")
        get_tree().quit(2)
        return
    var template = network.tiles[0]
    for tile in network.tiles:
        if tile.is_present() and tile.network_type == 0 and tile.crossings.size() == 1:
            template = tile
            break
    var edit = {
        "x": location.x,
        "z": location.y,
        "y_m": template.position.y,
        "edges": [2, 0, 2, 0],
        "network": "Road",
    }
    var result = SC4RoadWriter.export(dbpf, [edit], destination)
    print("ROAD_WRITE_RESULT %s" % result)
    get_tree().quit(0 if not result.has("error") else 1)
