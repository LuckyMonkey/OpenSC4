extends Node

# Read-only DBPF inspection helper. It deliberately does not write, decompress
# to disk, or alter the supplied city. Use it to choose a small disposable
# save for the road-writer experiments.

func _ready():
    var args = OS.get_cmdline_user_args()
    if args.is_empty():
        print("usage: godot --headless --path . --script tools/sc4_save_inspect.gd -- /path/to/city.sc4")
        get_tree().quit(2)
        return
    var path = args[0]
    if not FileAccess.file_exists(path):
        print("missing: %s" % path)
        get_tree().quit(2)
        return

    var city = DBPF.new(path)
    if not city.loaded:
        print("could not load DBPF: %s" % path)
        get_tree().quit(2)
        return

    print("SC4_SAVE path=%s" % path)
    print("INDEXES count=%d compressed_entries=%d" % [city.indices.size(), city.compressed_files.size()])
    for type_id in [0xc9c05c6e, 0x6a0f82b2, 0x49c05b9f, 0xca16374f]:
        for index in city.indices_by_type.get(type_id, []):
            var tgi = SubfileTGI.TGI2str(index.type_id, index.group_id, index.instance_id)
            var compressed = city.compressed_files.has(tgi)
            print("ENTRY tgi=%s offset=%d stored=%d compressed=%s" %
                [tgi, index.location, index.size, compressed])
            if type_id == 0xc9c05c6e:
                var network = city.get_subfile(index.type_id, index.group_id, index.instance_id, NetworkSubfile)
                print("NETWORK tiles=%d layout_failures=%d types=%s raw=%d" %
                    [network.tiles.size(), network.layout_failures, network.type_histogram(), network.raw_data.size()])
                for sample_i in range(min(2, network.tiles.size())):
                    var tile = network.tiles[sample_i]
                    print("NETWORK_TILE[%d] type=%d pos=%s mem=%d offsets=pos:%d verts:%d bbox:%d size=%d" %
                        [sample_i, tile.network_type, tile.position, tile.record_mem,
                         tile.position_offset, tile.vertices_offset, tile.bbox_offset,
                         tile.raw_record.size()])
            elif type_id == 0x6a0f82b2:
                var network_index = city.get_subfile(index.type_id, index.group_id, index.instance_id, NetworkIndexSubfile)
                print("NETWORK_INDEX city_tiles=%d declared_refs=%d recovered_refs=%d raw=%d" %
                    [network_index.city_tile_count, network_index.network_tile_count,
                     network_index.tile_refs.size(), network_index.raw_data.size()])
                print("NETWORK_INDEX_STRUCTURED ok=%s tiles=%d intersections=%d transit=%d y=%d" %
                    [network_index.structured_decode_ok, network_index.tiles.size(),
                     network_index.intersections.size(), network_index.transit_enabled_tiles.size(),
                     network_index.y_intersections.size()])
                for sample_i in range(min(3, network_index.tiles.size())):
                    var sample = network_index.tiles[sample_i]
                    print("NETWORK_INDEX_TILE[%d] number=%d pointer=%s blocks=%d automata=%d reps2=%d" %
                        [sample_i, sample["number"], sample["pointer"], sample["blocks"].size(),
                         sample["automata"].size(), sample["reps2"].size()])
                var pointer_types = {}
                for sample in network_index.tiles:
                    var key = "0x%08x" % sample["pointer"]["type"]
                    pointer_types[key] = pointer_types.get(key, 0) + 1
                print("NETWORK_INDEX_POINTER_TYPES %s" % pointer_types)
                for sample in network_index.tiles:
                    if sample["pointer"]["type"] == 0xc9c05c6e:
                        print("NETWORK_INDEX_GROUND_SAMPLE number=%d pointer=%s blocks=%s reps2=%s" %
                            [sample["number"], sample["pointer"], sample["blocks"], sample["reps2"]])
                        break
    city.file.close()
    get_tree().quit(0)
