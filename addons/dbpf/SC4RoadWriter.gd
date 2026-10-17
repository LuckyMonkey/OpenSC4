extends RefCounted

class_name SC4RoadWriter

# Experimental, deliberately narrow writer for the first Godot -> SC4 road
# round-trip. It clones a known-good saved Road record, patches its position,
# geometry, crossing edges and pointer, then rewrites the DBPF with modified
# entries uncompressed while preserving untouched stored bytes. The writer
# refuses unsupported edits instead of emitting a plausible-looking corrupt
# city.

const NETWORK_TYPE : int = 0xc9c05c6e
const NETWORK_INDEX_TYPE : int = 0x6a0f82b2
const DBDF_TYPE : int = 0xe86b1eef
const DBDF_TGI : Array = [0xe86b1eef, 0xe86b1eef, 0x286b1f03]
const MAX_CRC_BYTES : int = 250000
const CRC_POLY : int = 0x04c11db7

static func export(dbpf : DBPF, edits : Array, destination : String) -> Dictionary:
    if dbpf == null or not dbpf.loaded:
        return {"error": "The source DBPF is not loaded"}
    if edits.is_empty():
        return {"error": "There are no staged road edits"}
    if destination.simplify_path() == dbpf.path.simplify_path():
        return {"error": "Refusing to overwrite the source city"}
    if FileAccess.file_exists(destination):
        return {"error": "Destination already exists; choose a new SC4 filename"}

    var network_indices = dbpf.indices_by_type.get(NETWORK_TYPE, [])
    var index_indices = dbpf.indices_by_type.get(NETWORK_INDEX_TYPE, [])
    if network_indices.size() != 1 or index_indices.size() != 1:
        return {"error": "Writer requires exactly one ground-network and one network-index subfile"}

    var network_index = network_indices[0]
    var index_index = index_indices[0]
    var network : NetworkSubfile = dbpf.get_subfile(
        network_index.type_id, network_index.group_id, network_index.instance_id, NetworkSubfile)
    var network_map : NetworkIndexSubfile = dbpf.get_subfile(
        index_index.type_id, index_index.group_id, index_index.instance_id, NetworkIndexSubfile)
    if network.layout_failures != 0 or not network_map.structured_decode_ok:
        return {"error": "Source network data is not fully decoded; writer stopped safely"}

    var city_size = int(sqrt(float(network_map.city_tile_count)))
    var existing = {}
    var max_mem : int = 0
    for tile in network.tiles:
        if tile.is_present():
            existing[Vector2i(tile.tile_x(), tile.tile_z())] = true
        max_mem = max(max_mem, tile.record_mem)
    var index_template = null
    for tile in network_map.tiles:
        if tile["pointer"]["type"] == NETWORK_TYPE:
            index_template = tile
            break
    if index_template == null:
        return {"error": "No ground-network index tile is available as a safe template"}

    var record_template = null
    for tile in network.tiles:
        if tile.is_present() and tile.network_type == 0 and tile.crossings.size() == 1:
            record_template = tile
            break
    if record_template == null:
        return {"error": "No simple saved Road record is available as a safe template"}

    var changed_network = network.raw_data.duplicate()
    var changed_index_tiles = network_map.tiles.duplicate(true)
    var used = {}
    var record_count = 0
    for edit in edits:
        var location = Vector2i(int(edit.get("x", -1)), int(edit.get("z", -1)))
        if location.x < 0 or location.y < 0 or location.x >= city_size or location.y >= city_size:
            return {"error": "Road edit %s is outside the city" % location}
        if existing.has(location) or used.has(location):
            return {"error": "Writer v0 only supports new empty tiles; edit overlaps %s" % location}
        if edit.get("network", "Road") != "Road":
            return {"error": "Writer v0 only supports Road edits"}
        var edges = edit.get("edges", [])
        if edges.size() != 4:
            return {"error": "Road edit %s has invalid WNES edges" % location}

        max_mem += 1
        var record = _clone_record(record_template, location, edges, max_mem,
            float(edit.get("y_m", record_template.position.y)))
        if record.is_empty():
            return {"error": "Could not patch the Road record template"}
        changed_network.append_array(record)

        var index_tile = index_template.duplicate(true)
        index_tile["number"] = location.y * city_size + location.x
        index_tile["x"] = location.x
        index_tile["z"] = location.y
        index_tile["pointer"] = {"mem": max_mem, "type": NETWORK_TYPE}
        changed_index_tiles.append(index_tile)
        used[location] = true
        record_count += 1

    var changed_index = _serialize_network_index(network_map, changed_index_tiles)
    if changed_index.is_empty():
        return {"error": "Could not serialize the network index"}

    var replacements = {
        SubfileTGI.TGI2str(network_index.type_id, network_index.group_id, network_index.instance_id): changed_network,
        SubfileTGI.TGI2str(index_index.type_id, index_index.group_id, index_index.instance_id): changed_index,
    }
    var result = _rewrite_dbpf(dbpf, replacements, destination)
    if result.has("error"):
        return result
    result["road_records"] = record_count
    result["network_index_tiles"] = changed_index_tiles.size()
    return result

static func _clone_record(template, location : Vector2i, edges : Array, mem : int, y_m : float) -> PackedByteArray:
    var record : PackedByteArray = template.raw_record.duplicate()
    if record.is_empty():
        return PackedByteArray()
    record.encode_u32(8, mem)
    record[19] = record[19] | NetworkSubfile.APPEARANCE_PRESENT
    var target = Vector3(location.x * 16.0 + 8.0, y_m, location.y * 16.0 + 8.0)
    var delta = target - template.position
    record.encode_float(template.position_offset + 0, target.x)
    record.encode_float(template.position_offset + 4, target.y)
    record.encode_float(template.position_offset + 8, target.z)
    for vertex_i in range(4):
        var offset = template.vertices_offset + vertex_i * 24
        var source = template.vertices[vertex_i].position + delta
        record.encode_float(offset + 0, source.x)
        record.encode_float(offset + 4, source.y)
        record.encode_float(offset + 8, source.z)
    record[template.crossings_offset] = 0
    record[template.crossings_offset + 1] = 0
    record[template.crossings_offset + 2] = int(edges[0]) & 0xff
    record[template.crossings_offset + 3] = int(edges[1]) & 0xff
    record[template.crossings_offset + 4] = int(edges[2]) & 0xff
    record[template.crossings_offset + 5] = int(edges[3]) & 0xff
    var bbox = template.bbox
    var min_corner = bbox.position + delta
    var max_corner = bbox.position + bbox.size + delta
    record.encode_float(template.bbox_offset + 0, min_corner.x)
    record.encode_float(template.bbox_offset + 4, max_corner.x)
    record.encode_float(template.bbox_offset + 8, min_corner.y)
    record.encode_float(template.bbox_offset + 12, max_corner.y)
    record.encode_float(template.bbox_offset + 16, min_corner.z)
    record.encode_float(template.bbox_offset + 20, max_corner.z)
    # SC4 record CRC is calculated over the payload after size+CRC.
    record.encode_u32(4, _crc32(record, 8))
    return record

static func _serialize_network_index(network_map : NetworkIndexSubfile, tiles : Array) -> PackedByteArray:
    var body = PackedByteArray()
    _append_u32(body, _u32(network_map.raw_data, 8))
    _append_u16(body, network_map.major)
    _append_u32(body, network_map.city_tile_count)
    _append_u32(body, tiles.size())
    for tile in tiles:
        _append_u32(body, tile["number"])
        _append_pointer(body, tile["pointer"])
        _append_u32(body, tile["blocks"].size())
        for block in tile["blocks"]:
            _append_u32(body, block["number"])
            _append_u32(body, block["bytes"].size())
            for bytes in block["bytes"]:
                body.append_array(bytes)
        _append_u32(body, tile["automata"].size())
        for pointer in tile["automata"]:
            _append_pointer(body, pointer)
        _append_u8(body, tile["unknown"]["byte"])
        for value in tile["unknown"]["dwords"]:
            _append_u32(body, value)
        for bytes in tile["reps"]:
            body.append_array(bytes)
        _append_u16(body, tile["reps_unknown"])
        _append_u32(body, tile["reps2"].size())
        for item in tile["reps2"]:
            _append_u32(body, item["number"])
            body.append_array(item["bytes"])

    _append_u32(body, network_map.intersections.size())
    for intersection in network_map.intersections:
        _append_pointer(body, intersection["pointer"])
        _append_u8(body, intersection["unknown_byte"])
        _append_u32(body, intersection["unknown_dword"])
        for direction in ["west", "north", "east", "south"]:
            var value = intersection["directions"][direction]
            _append_u32(body, value["count"])
            _append_u8(body, 1 if value["value"] else 0)
            for bytes in value["entries"]:
                body.append_array(bytes)

    _append_u32(body, network_map.transit_enabled_tiles.size())
    for tile in network_map.transit_enabled_tiles:
        _append_u16(body, tile["z"])
        _append_u16(body, tile["x"])
        _append_u32(body, tile["value"])
        _append_pointer(body, tile["pointer"])
    for value in network_map.tail_unknown:
        _append_u32(body, value)
    _append_u32(body, network_map.tail_tile_x)
    _append_u32(body, network_map.tail_tile_z)
    body.append_array(network_map.tail_bytes)
    if network_map.major != 3:
        _append_u32(body, network_map.y_intersections.size())
        for intersection in network_map.y_intersections:
            _append_pointer(body, intersection["pointer"])
            for direction in ["west", "north", "east", "south"]:
                var values = intersection["directions"][direction]
                _append_u32(body, values["values"].size())
                for value in values["values"]:
                    _append_u32(body, value)
                _append_u16(body, values["word"])

    var record = PackedByteArray()
    _append_u32(record, body.size() + 8)
    _append_u32(record, _crc32(body, 0))
    record.append_array(body)
    return record

static func _rewrite_dbpf(dbpf : DBPF, replacements : Dictionary, destination : String) -> Dictionary:
    var chunks = []
    var dir_entries = []
    for index in dbpf.indices.values():
        if index.type_id == DBDF_TYPE:
            continue
        var key = SubfileTGI.TGI2str(index.type_id, index.group_id, index.instance_id)
        var bytes : PackedByteArray
        if replacements.has(key):
            bytes = replacements[key]
        else:
            dbpf.file.seek(index.location)
            bytes = dbpf.file.get_buffer(index.size)
            var compressed = dbpf.compressed_files.get(key, null)
            if compressed != null:
                dir_entries.append({"t": index.type_id, "g": index.group_id,
                    "i": index.instance_id, "size": compressed.final_size})
        chunks.append({"t": index.type_id, "g": index.group_id, "i": index.instance_id, "data": bytes})

    var dir = PackedByteArray()
    for entry in dir_entries:
        _append_u32(dir, entry["t"])
        _append_u32(dir, entry["g"])
        _append_u32(dir, entry["i"])
        _append_u32(dir, entry["size"])
    if not dir.is_empty():
        chunks.append({"t": DBDF_TGI[0], "g": DBDF_TGI[1], "i": DBDF_TGI[2], "data": dir})

    var output = PackedByteArray()
    dbpf.file.seek(0)
    var header = dbpf.file.get_buffer(96)
    output.append_array(header)
    var entries = []
    for chunk in chunks:
        var offset = output.size()
        output.append_array(chunk["data"])
        entries.append({"t": chunk["t"], "g": chunk["g"], "i": chunk["i"],
            "offset": offset, "size": chunk["data"].size()})
    var index_offset = output.size()
    for entry in entries:
        _append_u32(output, entry["t"])
        _append_u32(output, entry["g"])
        _append_u32(output, entry["i"])
        _append_u32(output, entry["offset"])
        _append_u32(output, entry["size"])
    var index_size = entries.size() * 20
    output.encode_u32(36, entries.size())
    output.encode_u32(40, index_offset)
    output.encode_u32(44, index_size)

    var file = FileAccess.open(destination, FileAccess.WRITE)
    if file == null:
        return {"error": "Could not open destination (error %d)" % FileAccess.get_open_error()}
    file.store_buffer(output)
    file.close()
    return {"sc4": destination, "bytes": output.size()}

static func _append_pointer(out : PackedByteArray, pointer : Dictionary):
    _append_u32(out, pointer.get("mem", 0))
    if pointer.get("mem", 0) != 0:
        _append_u32(out, pointer.get("type", 0))

static func _append_u8(out : PackedByteArray, value : int):
    out.append(value & 0xff)

static func _append_u16(out : PackedByteArray, value : int):
    var bytes = PackedByteArray()
    bytes.resize(2)
    bytes.encode_u16(0, value)
    out.append_array(bytes)

static func _append_u32(out : PackedByteArray, value : int):
    var bytes = PackedByteArray()
    bytes.resize(4)
    bytes.encode_u32(0, value)
    out.append_array(bytes)

static func _u32(bytes : PackedByteArray, offset : int) -> int:
    return bytes.decode_u32(offset)

static func _crc32(bytes : PackedByteArray, start : int) -> int:
    var crc : int = 0xffffffff
    var end = min(bytes.size(), start + MAX_CRC_BYTES)
    for i in range(start, end):
        var table_index = ((crc >> 24) ^ bytes[i]) & 0xff
        crc = (((crc << 8) & 0xffffffff) ^ _crc_table_value(table_index)) & 0xffffffff
    return crc

static func _crc_table_value(index : int) -> int:
    var value = index << 24
    for _i in range(8):
        if (value & 0x80000000) != 0:
            value = ((value << 1) ^ CRC_POLY) & 0xffffffff
        else:
            value = (value << 1) & 0xffffffff
    return value
