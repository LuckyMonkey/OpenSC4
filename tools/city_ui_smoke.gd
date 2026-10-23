extends "res://tools/play_city.gd"

func _ready():
    super._ready()
    var city = get_child(0)
    var controls : Sc4CityControls
    for child in city.get_node("UICanvas").get_children():
        if child is Sc4CityControls:
            controls = child
    if controls == null or controls._textures.size() < 12 or controls._buttons.size() != 9:
        _fail("original asset resolution")
        return
    for button in controls._buttons.values():
        if not button is TextureButton:
            _fail("unexpected fallback control")
            return
    var art : Image = controls._textures[0x13d14ca0].get_image()
    if art.get_pixel(0, 0).a != 0.0:
        _fail("magenta color-key transparency")
        return
    var minimap := controls._puck.get_child(1) as TextureRect
    if minimap.size != Vector2(62, 62):
        _fail("minimap fits original artwork")
        return
    if city.editor_panel.visible:
        _fail("export panel starts collapsed")
        return
    controls._buttons.tools.pressed.emit()
    if not city.editor_panel.visible:
        _fail("tools button")
        return
    controls._buttons.tools.pressed.emit()
    controls._road.button_pressed = true
    if not city.transit_editor.build_tool_enabled:
        _fail("original transportation button enables road tool")
        return
    controls._road.button_pressed = false
    if city.transit_editor.build_tool_enabled:
        _fail("road tool disable")
        return
    var sim : CitySim = city.city_sim
    if sim == null or sim.backend == null:
        _fail("live simulation")
        return
    controls._buttons.pause.pressed.emit()
    if sim.running:
        _fail("pause control")
        return
    controls._buttons.slow.pressed.emit()
    if not sim.running or sim.seconds_per_day != 1.0:
        _fail("simulation speed control")
        return
    sim.set_paused(true)
    var camera = city.get_node("CameraHandler")
    var before = camera.zoom
    controls._buttons.zoom_in.pressed.emit()
    if camera.zoom != before + 1:
        _fail("zoom button")
        return
    controls._buttons.zoom_out.pressed.emit()
    var rotation = camera.rotated
    controls._buttons.clockwise.pressed.emit()
    if camera.rotated != posmod(rotation + 1, 4):
        _fail("rotation button")
        return
    controls._buttons.counterclockwise.pressed.emit()
    for resolution in [Vector2i(1280, 720), Vector2i(1600, 900), Vector2i(3440, 1440)]:
        get_window().size = resolution
        controls._layout()
        var bounds := Rect2(controls._puck.position, controls._puck.size)
        if not Rect2(Vector2.ZERO, Vector2(resolution)).encloses(bounds):
            _fail("viewport anchoring")
            return
    sim.stop()
    print("CITY UI PASS: 12 original textures, transparency, controls, road tool, simulation, camera, anchoring")
    get_tree().quit(0)

func _fail(message : String) -> void:
    push_error("CITY UI FAIL: " + message)
    get_tree().quit(1)
