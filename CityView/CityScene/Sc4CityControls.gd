class_name Sc4CityControls
extends Control

## Original SC4 artwork, resolved from the user's DATs at runtime. Only controls
## with implemented behavior are exposed. No extracted images ship with OpenSC4.
const PNG := 0x856ddbac
const GROUP := 0x46a006b0
const CAMERA_LAYOUT := 0xc973b411
var city : Node
var _puck : Control
var _date : Label
var _buttons : Dictionary = {}
var _textures : Dictionary = {}
var _camera_attributes : Dictionary = {}
var _road : BaseButton
var _tools : Button

func _ready() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    _camera_attributes = _read_buttons(CAMERA_LAYOUT)
    var background := _texture(0x13d14ca0)
    if background == null:
        Log.warn("Original city controls unavailable; keeping editor panel")
        return
    _puck = Control.new()
    _puck.size = Vector2(235, 222)
    _puck.mouse_filter = Control.MOUSE_FILTER_STOP
    add_child(_puck)
    var art := TextureRect.new()
    art.texture = background
    art.mouse_filter = Control.MOUSE_FILTER_IGNORE
    _puck.add_child(art)
    # The stock panel contains a sample map baked into its art. Cover that with
    # a map generated from this save's heights and network tiles.
    var map := TextureRect.new()
    map.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
    map.texture = _minimap()
    map.position = Vector2(23, 72)
    map.size = Vector2(62, 62)
    map.mouse_filter = Control.MOUSE_FILTER_IGNORE
    map.tooltip_text = "Loaded city terrain and transport networks"
    _puck.add_child(map)
    _camera_button("zoom_out", "0xe9920494", "Zoom out", func(): _camera_action("_zoom_step", -1))
    _camera_button("zoom_in", "0x4992046a", "Zoom in", func(): _camera_action("_zoom_step", 1))
    _camera_button("clockwise", "0x2a4fbb08", "Rotate clockwise", func(): _camera_action("_rotate_step", 1))
    _camera_button("counterclockwise", "0x8a4fbaea", "Rotate counterclockwise", func(): _camera_action("_rotate_step", -1))
    _camera_button("pause", "0xc998bb81", "Pause simulation (F6)", func(): _pause())
    _camera_button("slow", "0x6a4fbb31", "Run slowly", func(): _speed(1.0))
    _camera_button("medium", "0x4a4fbb60", "Run at medium speed", func(): _speed(0.5))
    _camera_button("fast", "0x8998bbdf", "Run as fast as the simulation allows", func(): _speed(0.1))
    _camera_button("tools", "0x00000044", "Show tools and export options", func(): _toggle_tools())
    var name_label := _label(city.city_name, Vector2(49, 183), Vector2(143, 21), 13)
    name_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    _date = _label("", Vector2(98, 140), Vector2(84, 16), 11)
    var tool_row := HBoxContainer.new()
    tool_row.position = Vector2(18, 16)
    tool_row.add_theme_constant_override("separation", 8)
    add_child(tool_row)
    _road = _atlas_button(0x14215e23, Vector2i(64, 50), "Build road — staged locally")
    _road.toggle_mode = true
    _road.toggled.connect(func(on):
        city.editor_panel.road_button.set_pressed_no_signal(on)
        city.editor_panel._on_road_toggled(on))
    tool_row.add_child(_road)
    city.editor_panel.road_button.toggled.connect(func(on): _road.set_pressed_no_signal(on))
    _tools = Button.new()
    _tools.text = "Tools & export"
    _tools.pressed.connect(_toggle_tools)
    tool_row.add_child(_tools)
    var back := _atlas_button(0x13e14f91, Vector2i(40, 36), "Return to region")
    back.pressed.connect(city._on_return_requested)
    tool_row.add_child(back)
    city.editor_panel.position = Vector2(18, 78)
    city.editor_panel.hide()
    get_viewport().size_changed.connect(_layout)
    _layout()
    Log.info("Original city controls: %d PNG resources loaded from DATs" % _textures.size())

func _layout() -> void:
    var viewport := get_viewport_rect().size
    # Preserve original pixels; larger viewports gain map space, not stretched UI.
    _puck.position = Vector2(12, maxf(78, viewport.y - 234))

func _read_buttons(instance : int) -> Dictionary:
    var key := SubfileTGI.TGI2str(0, 0x96a006b0, instance)
    if not Core.subfile_indices.has(key):
        return {}
    var resource = Core.subfile(0, 0x96a006b0, instance, DBPFSubfile)
    var tag := RegEx.new()
    tag.compile("(?s)<LEGACY\\s.*?>")
    var attr := RegEx.new()
    attr.compile('(\\w+)=("[^"]*"|\\([^)]*\\)|\\{[^}]*\\}|[^\\s>]+)')
    var result := {}
    for match_tag in tag.search_all(resource.raw_data.get_string_from_utf8()):
        var attributes := {}
        for match_attr in attr.search_all(match_tag.get_string()):
            attributes[match_attr.get_string(1)] = match_attr.get_string(2).trim_prefix('"').trim_suffix('"')
        if attributes.get("iid") == "IGZWinBtn" and attributes.has("id"):
            result[attributes.id] = attributes
    return result

func _camera_button(action : String, id : String, tip : String, callback : Callable) -> void:
    var attrs : Dictionary = _camera_attributes.get(id, {})
    if not attrs.has("area") or not attrs.has("image"):
        return
    var coords : PackedStringArray = str(attrs.area).trim_prefix("(").trim_suffix(")").split(",")
    var image_ids : PackedStringArray = str(attrs.image).trim_prefix("{").trim_suffix("}").split(",")
    if coords.size() != 4 or image_ids.size() != 2:
        return
    # SC4 area values are left, top, right, bottom (not width/height).
    var bounds := Rect2(int(coords[0]), int(coords[1]), int(coords[2]) - int(coords[0]), int(coords[3]) - int(coords[1]))
    var button := _atlas_button(("0x" + image_ids[1]).hex_to_int(), Vector2i(bounds.size), tip)
    button.position = bounds.position
    button.pressed.connect(callback)
    _puck.add_child(button)
    _buttons[action] = button

func _atlas_button(instance : int, frame : Vector2i, tip : String) -> BaseButton:
    var texture := _texture(instance)
    if texture == null or texture.get_width() != frame.x * 4 or texture.get_height() < frame.y:
        var fallback := Button.new()
        fallback.text = tip.get_slice("|", 0)
        fallback.tooltip_text = tip
        return fallback
    var button := TextureButton.new()
    var states : Array[AtlasTexture] = []
    for i in 4:
        var atlas := AtlasTexture.new()
        atlas.atlas = texture
        atlas.region = Rect2(i * frame.x, 0, frame.x, frame.y)
        states.append(atlas)
    button.texture_disabled = states[0]
    button.texture_normal = states[1]
    button.texture_pressed = states[2]
    button.texture_hover = states[3]
    button.tooltip_text = tip
    button.focus_mode = Control.FOCUS_NONE
    return button

func _texture(instance : int) -> Texture2D:
    if _textures.has(instance):
        return _textures[instance]
    if not Core.subfile_indices.has(SubfileTGI.TGI2str(PNG, GROUP, instance)):
        return null
    var resource = Core.subfile(PNG, GROUP, instance, ImageSubfile)
    if resource == null or resource.img == null:
        return null
    var image : Image = resource.img.duplicate()
    image.convert(Image.FORMAT_RGBA8)
    # SC4's legacy UI uses magenta as a color key even in RGBA PNGs.
    for y in image.get_height():
        for x in image.get_width():
            var pixel := image.get_pixel(x, y)
            if pixel.r > 0.99 and pixel.g < 0.01 and pixel.b > 0.99:
                image.set_pixel(x, y, Color.TRANSPARENT)
    var texture := ImageTexture.create_from_image(image)
    _textures[instance] = texture
    return texture

func _minimap() -> Texture2D:
    var heights : Array = city.height_map
    var image := Image.create(city.width - 1, city.height - 1, false, Image.FORMAT_RGB8)
    for z in image.get_height():
        for x in image.get_width():
            var altitude := float(heights[z][x])
            image.set_pixel(x, z, Color(0.17, 0.36, 0.55) if altitude < 250.0 else Color(0.36, 0.48, 0.23))
    for tile in city.network_tiles:
        var x : int = tile.tile_x()
        var z : int = tile.tile_z()
        if x >= 0 and z >= 0 and x < image.get_width() and z < image.get_height():
            image.set_pixel(x, z, Color(0.78, 0.76, 0.63))
    return ImageTexture.create_from_image(image)

func _label(text : String, pos : Vector2, dimensions : Vector2, font_size : int) -> Label:
    var label := Label.new()
    label.text = text
    label.position = pos
    label.size = dimensions
    label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    label.add_theme_color_override("font_color", Color(0.2, 0.27, 0.4))
    label.add_theme_font_size_override("font_size", font_size)
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    _puck.add_child(label)
    return label

func _toggle_tools() -> void:
    city.editor_panel.visible = not city.editor_panel.visible

func _camera_action(method : String, direction : int) -> void:
    var camera = city.get_node("CameraHandler")
    if camera.free_mode:
        camera._toggle_free()
    camera.call(method, direction)

func _pause() -> void:
    if city.city_sim != null:
        city.city_sim.set_paused(city.city_sim.running)

func _speed(seconds : float) -> void:
    if city.city_sim != null:
        city.city_sim.seconds_per_day = seconds
        city.city_sim.set_paused(false)

func _process(_delta : float) -> void:
    if _puck == null:
        return
    var sim : CitySim = city.city_sim
    _date.text = sim.simulation_date if sim != null else "No simulation"
    for action in ["pause", "slow", "medium", "fast"]:
        if not _buttons.has(action):
            continue
        var button : BaseButton = _buttons[action]
        button.disabled = sim == null or not sim.failure.is_empty() or not sim._checkpoint_operation.is_empty()
        button.toggle_mode = true
        var selected := false
        if sim != null:
            selected = not sim.running if action == "pause" else sim.running and is_equal_approx(sim.seconds_per_day, {"slow": 1.0, "medium": 0.5, "fast": 0.1}.get(action, -1.0))
        button.set_pressed_no_signal(selected)
