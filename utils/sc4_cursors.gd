class_name Sc4Cursors
extends RefCounted

## SC4's own mouse cursors (type 0xAA5C3144), read from the user's DATs.
##
## Each cursor instance ships in four colour-depth variants (group 0x32 full
## colour, then 0x08, 0x04, 0x01); full colour is used when present. Instance
## ids were identified from a rendered contact sheet of all 111 cursors.

const CUR_TYPE := 0xAA5C3144
const GROUPS := [0x32, 0x08, 0x04, 0x01]

const IDS := {
    "default": 0xC16C4E1B,      # white circle: the city view pointer
    "arrow": 0x00000001,        # region view / UI pointer
    "hand": 0x00000011,         # pointing hand over buttons
    "grab": 0x00000012,         # drag/pan
    "wait": 0x0000000F,         # hourglass
    "query": 0x816D7F74,
    "bulldoze": 0x8BD4B428,
    "zone_residential": 0x02E43524,
    "zone_commercial": 0xC2E43505,
    "zone_industrial": 0x22E43512,
    "street": 0x6B730B83,
    "road": 0x2A920BF9,
    "avenue": 0x6BE091B4,
    "highway": 0x8BF30A8B,
    "rail": 0xEBE091B6,
}

static var _cache : Dictionary = {}

static func load_cursor(name : String) -> Dictionary:
    if _cache.has(name):
        return _cache[name]
    var result := {}
    var iid : int = IDS.get(name, 0)
    for group in GROUPS:
        if Core.subfile_indices.has(SubfileTGI.TGI2str(CUR_TYPE, group, iid)):
            var cur = Core.subfile(CUR_TYPE, group, iid, CURSubfile)
            if cur != null and not cur.entries.is_empty():
                result = {"texture": cur.get_as_texture(), "hotspot": cur.entries[0].vec_hotspot}
                break
    _cache[name] = result
    return result

## Make `name` the arrow cursor; returns false (and leaves the cursor) if the
## DATs do not have it.
static func apply(name : String) -> bool:
    var cursor := load_cursor(name)
    if cursor.is_empty():
        return false
    Input.set_custom_mouse_cursor(cursor["texture"], Input.CURSOR_ARROW, cursor["hotspot"])
    return true
