extends DBPFSubfile

# Parses SC4's network index subfile (type 0x6A0F82B2, cSC4TrafficNetworkMap)
# from a city save: the game's own index from city tiles to the network
# occupants sitting on them, spanning every network subfile at once (ground
# networks, pipes, power lines, bridges).
#
# HONEST LIMITS. The serialized object is still only semantically understood in
# part, but its byte layout is now decoded structurally from an open-source SC4
# savegame implementation. Unknown blocks are retained as raw bytes so the
# writer can preserve them without pretending to know their simulation meaning.
# What this parser exposes:
#
#   * the header: record size, CRC, memory address, version, city tile count
#     (128x128 = 16384) and network tile count;
#   * the structured tile/intersection/transit arrays and their opaque fields;
#   * the compatibility reference scan: one {tile_number, mem, subfile_type}
#     triple per network tile, where `mem` matches the memory address in that
#     occupant's own record and `subfile_type` says which subfile to find it in.
#
# The semantic meaning of the block tables, intersections, and opaque reps is
# still open. Do not treat structural reserialization as proof of simulation
# equivalence.
#
# What `tile_number` means is still open. It is NOT a plain row-major tile index
# -- tested against the actual tile coordinates of the ground-network records,
# both (n-1)%128/(n-1)/128 and its transpose match only about half the entries.
# It is exposed raw; do not read a coordinate out of it without checking first.
class_name NetworkIndexSubfile

# Subfile type ids a reference may point at. Used to recognise the start of a
# reference triple during resynchronisation.
const NETWORK_SUBFILE_TYPES : Array = [
    0xc9c05c6e,   # ground networks
    0x49c05b9f,   # pipes
    0xc9c05c5d,   # power lines
    0xca16374f,   # bridges / elevated
    0x8a4bd52b,   # tunnels
    0x49c1a034,   # prebuilt networks
]

# How far past a reference we are willing to scan before giving up. The largest
# gap observed in the shipped saves is a few hundred bytes.
const RESYNC_WINDOW : int = 8192

class TileReference:
    var tile_number : int         # the game's own tile key; meaning undecoded
    var mem : int                 # memory address of the occupant record
    var subfile_type : int        # which network subfile holds that record

var major : int = 0
var city_tile_count : int = 0     # 16384 on a 2x2 km map
var network_tile_count : int = 0  # first array count in the serialized index
var tile_refs : Array = []
var tiles : Array = []
var intersections : Array = []
var transit_enabled_tiles : Array = []
var y_intersections : Array = []
var structured_decode_ok : bool = false
var tail_unknown : Array = []
var tail_tile_x : int = 0
var tail_tile_z : int = 0
var tail_bytes : PackedByteArray = PackedByteArray()

func _init(index):
    super._init(index)

func load(file, dbdf=null):
    super.load(file, dbdf)
    var n = raw_data.size()
    if n < 22:
        Log.warn("NetworkIndexSubfile: record is only %d bytes" % n)
        return OK
    var buf = StreamPeerBuffer.new()
    buf.data_array = raw_data

    var size = buf.get_u32()
    buf.get_u32()                 # crc
    buf.get_u32()                 # mem
    major = buf.get_u16()
    city_tile_count = buf.get_u32()
    network_tile_count = buf.get_u32()
    if size != n:
        Log.warn("NetworkIndexSubfile: declared size %d but subfile is %d bytes" % [size, n])

    var cursor = buf.get_position()
    while tile_refs.size() < network_tile_count:
        var at = _find_reference(cursor, n)
        if at < 0:
            break
        buf.seek(at)
        var ref = TileReference.new()
        ref.tile_number = buf.get_u32()
        ref.mem = buf.get_u32()
        ref.subfile_type = buf.get_u32()
        tile_refs.append(ref)
        cursor = buf.get_position()

    if tile_refs.size() != network_tile_count:
        Log.warn("NetworkIndexSubfile: recovered %d of %d declared tile references"
            % [tile_refs.size(), network_tile_count])
    _decode_structured_index()
    return OK

# Decode the full array layout used by the open-source SC4 savegame
# implementation. The older resynchronising reference scan above remains as a
# defensive fallback and as a useful cross-check; this richer representation is
# what a future writer will need. Values are dictionaries so they remain plain
# data and do not become a second simulation model.
# Bounds checks also latch failure: reaching EOF after a truncated read must
# never make the experimental writer consider an incomplete decode successful.
class CheckedReader:
    var data : PackedByteArray
    var position := 0
    var valid := true

    func _init(bytes : PackedByteArray):
        data = bytes

    func take(count : int) -> PackedByteArray:
        if not valid or count < 0 or count > data.size() - position:
            valid = false
            return PackedByteArray()
        var result := data.slice(position, position + count)
        position += count
        return result

    func get_u8() -> int:
        var bytes := take(1)
        return bytes[0] if valid else 0

    func get_u16() -> int:
        var bytes := take(2)
        return bytes.decode_u16(0) if valid else 0

    func get_u32() -> int:
        var bytes := take(4)
        return bytes.decode_u32(0) if valid else 0

    func get_count(minimum_size : int) -> int:
        var count := get_u32()
        if not valid or count > (data.size() - position) / minimum_size:
            valid = false
            return 0
        return count

    func get_position() -> int:
        return position

func _decode_structured_index():
    structured_decode_ok = false
    tiles.clear()
    intersections.clear()
    transit_enabled_tiles.clear()
    y_intersections.clear()
    tail_unknown.clear()
    tail_bytes = PackedByteArray()
    tail_tile_x = 0
    tail_tile_z = 0
    if raw_data.size() >= 22 and city_tile_count > 0:
        _decode_structured_body()
    if not structured_decode_ok:
        # Keep independently scanned tile_refs, never publish partial writer data.
        tiles.clear()
        intersections.clear()
        transit_enabled_tiles.clear()
        y_intersections.clear()
        tail_unknown.clear()
        tail_bytes = PackedByteArray()
        tail_tile_x = 0
        tail_tile_z = 0
        Log.warn("NetworkIndexSubfile: unsupported or truncated structured layout; using reference scan only")

func _decode_structured_body():
    var buf = CheckedReader.new(raw_data)
    buf.take(18) # size, crc, mem, major, city tile count
    if buf.get_position() + 4 > raw_data.size():
        return
    var tile_count = buf.get_count(83)
    tiles.clear()
    for _i in range(tile_count):
        var number = buf.get_u32()
        var pointer = _read_pointer(buf)
        var blocks = []
        var block_count = buf.get_count(8)
        for _block_i in range(block_count):
            var block_number = buf.get_u32()
            var bytes = []
            var byte_count = buf.get_count(8)
            for _byte_i in range(byte_count):
                bytes.append(_read_bytes(buf, 8))
            blocks.append({"number": block_number, "bytes": bytes})
        var automata = []
        var automata_count = buf.get_count(4)
        for _automata_i in range(automata_count):
            automata.append(_read_pointer(buf))
        var tile_unknown = {
            "byte": buf.get_u8(),
            "dwords": [buf.get_u32(), buf.get_u32(), buf.get_u32()],
        }
        var reps = []
        for _rep_i in range(4):
            reps.append(_read_bytes(buf, 12))
        var reps_unknown = buf.get_u16()
        var reps2 = []
        var reps2_count = buf.get_count(10)
        for _rep2_i in range(reps2_count):
            reps2.append({"number": buf.get_u32(), "bytes": _read_bytes(buf, 6)})
        tiles.append({
            "number": number,
            "x": number % int(sqrt(float(city_tile_count))),
            "z": number / int(sqrt(float(city_tile_count))),
            "pointer": pointer,
            "blocks": blocks,
            "automata": automata,
            "unknown": tile_unknown,
            "reps": reps,
            "reps_unknown": reps_unknown,
            "reps2": reps2,
        })

    intersections.clear()
    var intersection_count = buf.get_count(77)
    for _intersection_i in range(intersection_count):
        var intersection = {
            "pointer": _read_pointer(buf),
            "unknown_byte": buf.get_u8(),
            "unknown_dword": buf.get_u32(),
            "directions": {},
        }
        for direction in ["west", "north", "east", "south"]:
            var meaningful_count = buf.get_u32()
            var bool_value = buf.get_u8() != 0
            var entries = []
            for _entry_i in range(3):
                entries.append(_read_bytes(buf, 4))
            intersection["directions"][direction] = {
                "count": meaningful_count,
                "value": bool_value,
                "entries": entries,
            }
        intersections.append(intersection)

    transit_enabled_tiles.clear()
    var transit_count = buf.get_count(12)
    for _transit_i in range(transit_count):
        transit_enabled_tiles.append({
            "z": buf.get_u16(),
            "x": buf.get_u16(),
            "value": buf.get_u32(),
            "pointer": _read_pointer(buf),
        })

    tail_unknown = [buf.get_u32(), buf.get_u32()]
    tail_tile_x = buf.get_u32()
    tail_tile_z = buf.get_u32()
    tail_bytes = _read_bytes(buf, 10)
    y_intersections.clear()
    if major != 3:
        var y_count = buf.get_count(28)
        for _y_i in range(y_count):
            var y = {"pointer": _read_pointer(buf), "directions": {}}
            for direction in ["west", "north", "east", "south"]:
                var values = []
                var value_count = buf.get_count(4)
                for _value_i in range(value_count):
                    values.append(buf.get_u32())
                y["directions"][direction] = {"values": values, "word": buf.get_u16()}
            y_intersections.append(y)

    structured_decode_ok = buf.valid and buf.get_position() == raw_data.size()
    if not structured_decode_ok:
        Log.warn("NetworkIndexSubfile: structured decode left %d bytes" %
            (raw_data.size() - buf.get_position()))

func _read_pointer(buf : CheckedReader) -> Dictionary:
    var mem = buf.get_u32()
    if mem == 0:
        return {"mem": 0, "type": 0}
    return {"mem": mem, "type": buf.get_u32()}

func _read_bytes(buf : CheckedReader, count : int) -> PackedByteArray:
    return buf.take(count)

# Scans forward from `from` for the next reference triple, recognising it by a
# known network subfile type id in the third dword and a plausible tile number.
# Returns the offset, or -1 if none turns up inside the resync window.
func _find_reference(from : int, to : int) -> int:
    var limit = min(to - 12, from + RESYNC_WINDOW)
    var o = from
    while o <= limit:
        if NETWORK_SUBFILE_TYPES.has(_u32(o + 8)) and _u32(o) < city_tile_count:
            return o
        o += 1
    return -1

# {subfile type id: reference count}, for logging and harness assertions.
func type_histogram() -> Dictionary:
    var hist = {}
    for ref in tile_refs:
        var key = "0x%08x" % ref.subfile_type
        hist[key] = hist.get(key, 0) + 1
    return hist
