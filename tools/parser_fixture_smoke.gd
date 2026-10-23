extends Node

const ATCSubfileScript = preload("res://addons/dbpf/ATCSubfile.gd")
const AVPSubfileScript = preload("res://addons/dbpf/AVPSubfile.gd")
const DBPFSubfileScript = preload("res://addons/dbpf/DBPFSubfile.gd")
const SC4UISubfileScript = preload("res://SC4UISubfile.gd")

var fixture_id := 0

func _fail(message : String) -> void:
    push_error("PARSER FIXTURE FAIL: %s" % message)
    get_tree().quit(1)

func _expect(condition : bool, message : String) -> bool:
    if not condition:
        _fail(message)
        return false
    return true

func _index(size : int) -> SubfileIndex:
    var bytes = PackedByteArray()
    bytes.resize(20)
    var stream = StreamPeerBuffer.new()
    stream.data_array = bytes
    var result = SubfileIndex.new(null, stream)
    result.location = 0
    result.size = size
    return result

func _fixture_file(bytes : PackedByteArray) -> String:
    fixture_id += 1
    var path = "user://opensc4-parser-fixture-%d.bin" % fixture_id
    var file = FileAccess.open(path, FileAccess.WRITE)
    file.store_buffer(bytes)
    file.close()
    return path

func _ready() -> void:
    # The marker scan must be bounded and little-endian.
    var base = DBPFSubfileScript.new(null)
    base.raw_data = PackedByteArray([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
    if not _expect(base._u32(1) == 0x44332211, "little-endian helper"):
        return
    if not _expect(base._find_marker(0, 6, 0x44332211) == 1, "bounded marker scan"):
        return
    if not _expect(base._find_marker(0, 4, 0x44332211) == -1, "short scan bound"):
        return

    # Version 6 empty network index: every truncated prefix and oversized
    # count must stay fail-closed, including reads which land exactly at EOF.
    var network_bytes := PackedByteArray()
    network_bytes.resize(60)
    network_bytes.encode_u32(0, 60)
    network_bytes.encode_u16(12, 6)
    network_bytes.encode_u32(14, 16384)
    var network := NetworkIndexSubfile.new(null)
    network.major = 6
    network.city_tile_count = 16384
    network.raw_data = network_bytes
    network._decode_structured_index()
    if not _expect(network.structured_decode_ok, "complete empty network index"):
        return
    for length in range(network_bytes.size()):
        network.raw_data = network_bytes.slice(0, length)
        network._decode_structured_index()
        if not _expect(not network.structured_decode_ok and network.tiles.is_empty(), "truncated network index %d" % length):
            return
    for count_offset in [18, 22, 26, 56]:
        network.raw_data = network_bytes.duplicate()
        network.raw_data.encode_u32(count_offset, 0xffffffff)
        network._decode_structured_index()
        if not _expect(not network.structured_decode_ok, "oversized network count"):
            return
    network.raw_data = network_bytes.duplicate()
    network.raw_data.append(0)
    network._decode_structured_index()
    if not _expect(not network.structured_decode_ok, "network trailing data rejected"):
        return

    # Layout bounds must ignore unrelated parenthesized values and retain the
    # historical 800x600 minimum.
    var ui = SC4UISubfileScript.new(null)
    ui.lines = [
        "<LEGACY type=IGZWinGen area=(0,0,1154,51) color=(1,2,3)>",
        "<LEGACY type=IGZWinGen value=(900,900) area=(10,493,200,107)>",
    ]
    var layout = ui._layout_size()
    if not _expect(layout == Vector2(1154.0, 600.0), "layout bounds"):
        return
    if not _expect(ui.string2rect("(-4,5,6,7)") == Rect2(-4, 5, 6, 7), "negative rectangle"):
        return

    # Truncated ATC must be rejected without crashing.
    var short_atc = PackedByteArray()
    short_atc.resize(8)
    var atc_short_path = _fixture_file(short_atc)
    var atc_short_file = FileAccess.open(atc_short_path, FileAccess.READ)
    var atc_short = ATCSubfileScript.new(_index(short_atc.size()))
    atc_short.load(atc_short_file)
    atc_short_file.close()
    if not _expect(not atc_short.is_valid(), "truncated ATC rejection"):
        return

    # A valid ATC header with one zoom reference should remain readable.
    var atc_bytes = PackedByteArray()
    atc_bytes.resize(48)
    atc_bytes.encode_u32(4, 0x7ab50e44)
    atc_bytes.encode_u32(8, 0x12345678)
    atc_bytes.encode_u32(12, 0x9abcdef0)
    atc_bytes.encode_u32(20, 0x11111111)
    atc_bytes.encode_u32(24, 0x22222222)
    atc_bytes.encode_u32(44, 31)
    var atc_path = _fixture_file(atc_bytes)
    var atc_file = FileAccess.open(atc_path, FileAccess.READ)
    var atc = ATCSubfileScript.new(_index(atc_bytes.size()))
    atc.load(atc_file)
    atc_file.close()
    if not _expect(atc.is_valid() and atc.avp_by_zoom[0] == 0x22222222, "ATC header"):
        return

    # An AVP count larger than the available payload is clipped and reported,
    # rather than reading beyond the fixture.
    var avp_bytes = PackedByteArray()
    avp_bytes.resize(0x24 + 8)
    avp_bytes.encode_u32(4, 2)
    avp_bytes.encode_u32(0x24, 3)
    avp_bytes[0x24 + 4] = 16
    avp_bytes[0x24 + 5] = 8
    var avp_path = _fixture_file(avp_bytes)
    var avp_file = FileAccess.open(avp_path, FileAccess.READ)
    var avp = AVPSubfileScript.new(_index(avp_bytes.size()))
    avp.load(avp_file)
    avp_file.close()
    if not _expect(avp.frames.size() == 1, "AVP truncation clipping"):
        return

    print("PARSER FIXTURE PASS")
    get_tree().quit()
