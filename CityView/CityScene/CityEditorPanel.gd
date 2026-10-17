extends PanelContainer

class_name CityEditorPanel

signal road_tool_changed(enabled : bool)
signal save_copy_requested
signal journal_requested
signal road_save_requested
signal save_copy_selected(path : String)
signal journal_selected(path : String)
signal road_save_selected(path : String)
signal return_requested

var road_button : Button
var save_button : Button
var journal_button : Button
var status_label : Label
var edit_count_label : Label
var file_dialog : FileDialog
var dialog_purpose : String = ""

func _ready():
    custom_minimum_size = Vector2(350, 0)
    position = Vector2(18, 18)
    mouse_filter = Control.MOUSE_FILTER_STOP

    var margin = MarginContainer.new()
    margin.add_theme_constant_override("margin_left", 12)
    margin.add_theme_constant_override("margin_top", 10)
    margin.add_theme_constant_override("margin_right", 12)
    margin.add_theme_constant_override("margin_bottom", 10)
    add_child(margin)

    var box = VBoxContainer.new()
    box.add_theme_constant_override("separation", 6)
    margin.add_child(box)

    var title = Label.new()
    title.text = "OpenSC4 City Editor"
    title.add_theme_font_size_override("font_size", 18)
    box.add_child(title)

    var subtitle = Label.new()
    subtitle.text = "Road edits are staged locally until the SC4 writer is ready."
    subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    subtitle.modulate = Color(0.78, 0.82, 0.88)
    box.add_child(subtitle)

    road_button = Button.new()
    road_button.text = "Build road"
    road_button.toggle_mode = true
    road_button.tooltip_text = "Drag on the city to preview and commit a road"
    road_button.toggled.connect(_on_road_toggled)
    box.add_child(road_button)

    edit_count_label = Label.new()
    edit_count_label.text = "Staged road tiles: 0"
    box.add_child(edit_count_label)

    save_button = Button.new()
    save_button.text = "Export SC4 baseline + journal"
    save_button.tooltip_text = "Create a new untouched .sc4 copy and a sidecar road journal"
    save_button.pressed.connect(func(): save_copy_requested.emit())
    box.add_child(save_button)

    journal_button = Button.new()
    journal_button.text = "Export road journal"
    journal_button.pressed.connect(func(): journal_requested.emit())
    box.add_child(journal_button)

    var road_save_button = Button.new()
    road_save_button.text = "Experimental save road changes to SC4"
    road_save_button.tooltip_text = "Write a narrow, fail-closed SC4 road patch to a new file"
    road_save_button.pressed.connect(func(): road_save_requested.emit())
    box.add_child(road_save_button)

    var separator = HSeparator.new()
    box.add_child(separator)

    var note = Label.new()
    note.text = "Baseline export is an untouched SC4 copy. Experimental save attempts a narrow road DBPF patch and refuses unsupported layouts; verify its output in SC4 before trusting it."
    note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    note.modulate = Color(1.0, 0.78, 0.48)
    box.add_child(note)

    status_label = Label.new()
    status_label.text = "Ready"
    status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    box.add_child(status_label)

    file_dialog = FileDialog.new()
    file_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
    file_dialog.access = FileDialog.ACCESS_FILESYSTEM
    file_dialog.file_selected.connect(_on_file_selected)
    add_child(file_dialog)

    var back_button = Button.new()
    back_button.text = "Return to region"
    back_button.pressed.connect(func(): return_requested.emit())
    box.add_child(back_button)

func _on_road_toggled(enabled : bool):
    road_button.text = "Stop road tool" if enabled else "Build road"
    road_tool_changed.emit(enabled)

func set_road_tile_count(count : int):
    edit_count_label.text = "Staged road tiles: %d" % count

func set_status(message : String, warning : bool = false):
    status_label.text = message
    status_label.modulate = Color(1.0, 0.78, 0.48) if warning else Color.WHITE

func open_save_copy_dialog(source_path : String):
    dialog_purpose = "sc4"
    file_dialog.filters = PackedStringArray(["*.sc4 ; SimCity 4 city save"])
    file_dialog.current_path = source_path.get_base_dir().path_join(
        "%s - OpenSC4 Road Test.sc4" % source_path.get_file().get_basename())
    file_dialog.popup_centered_ratio(0.72)

func open_journal_dialog(source_path : String):
    dialog_purpose = "journal"
    file_dialog.filters = PackedStringArray(["*.json ; OpenSC4 edit journal"])
    file_dialog.current_path = source_path.get_base_dir().path_join(
        "%s - OpenSC4 Roads.opensc4.json" % source_path.get_file().get_basename())
    file_dialog.popup_centered_ratio(0.72)

func open_road_save_dialog(source_path : String):
    dialog_purpose = "road_save"
    file_dialog.filters = PackedStringArray(["*.sc4 ; SimCity 4 city save"])
    file_dialog.current_path = source_path.get_base_dir().path_join(
        "%s - OpenSC4 Road Save.sc4" % source_path.get_file().get_basename())
    file_dialog.popup_centered_ratio(0.72)

func _on_file_selected(path : String):
    file_dialog.hide()
    if dialog_purpose == "sc4":
        save_copy_selected.emit(path)
    elif dialog_purpose == "journal":
        journal_selected.emit(path)
    elif dialog_purpose == "road_save":
        road_save_selected.emit(path)
