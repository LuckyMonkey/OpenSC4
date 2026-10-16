extends Control

"""
Once everything is loaded the it changes to Region scene or the DAT explorer
"""

var label_node
var load_progress_node
var next_scene_node
var config

var loading_thread : Thread
var dat_files : Array = [
                         "Apps/SimCity 4.ini",
                         "Sound.dat",
                         "Intro.dat",
                         "SimCity_1.dat",
                         "SimCity_2.dat",
                         "SimCity_3.dat",
                         "SimCity_4.dat",
                         "SimCity_5.dat",
                         "EP1.dat",]
                        
func _ready():
    #_generate_types_dict_from_XML()
    config = INI.new("user://config.ini")
    Core.game_dir = ""
    if config.sections.has("paths"):
        Core.game_dir = str(config.sections["paths"].get("sc4_files", ""))

    while not _game_dir_is_complete(Core.game_dir):
        $dialog.title = "Select the SimCity 4 installation folder"
        $dialog.popup_centered(get_viewport_rect().size / 2)
        # FileDialog hides itself through the handlers below after either a
        # selection or cancellation. This keeps the boot path asynchronous
        # without depending on the inherited `confirmed` signal.
        while $dialog.visible:
            await get_tree().process_frame
        if Core.game_dir.is_empty():
            Log.error("No valid SimCity 4 installation folder was selected")
            get_tree().quit(1)
            return

    config.sections["paths"] = {"sc4_files": Core.game_dir}
    config.save_file()
    $dialog.deselect_all()
    $LoadProgress.value = 0
    loading_thread = Thread.new()
    Log.info("Loading OpenSC4...")
    Log.info("Using %s as game data folder" % Core.game_dir)
    # Would be nice to start multiple threads here not only one
    label_node = $CurrentFileLabel
    load_progress_node = $LoadProgress
    next_scene_node = $NextScene
    var err = loading_thread.start(Callable(self,'load_DATs'))
    if err != OK:
        Log.error("Error starting thread: " % err)
        return

func _game_dir_is_complete(path: String) -> bool:
    if path.is_empty() or not DirAccess.dir_exists_absolute(path):
        return false
    for dat_file in dat_files:
        if not FileAccess.file_exists(path.path_join(dat_file)):
            return false
    return true

func _exit_tree():
    if loading_thread != null:
        loading_thread.wait_to_finish()

func load_DATs():
    for dat_file in dat_files :
        load_single_DAT(dat_file)
    finish_loading()

func finish_loading():
    Log.info("DBPF files loaded")
    next_scene_node.call_deferred("set_visible", true)

func load_single_DAT(dat_file : String):
    var src = Core.game_dir + "/" + dat_file
    label_node.call_deferred("set_text",("Loading: %s" % src ))
    var dbpf = DBPF.new(src)
    #dbpf.DEBUG_show_all_subfiles_to_file(dat_file)
    Core.add_dbpf(dbpf)
    Boot.load_progress_val += 100.0 / len(dat_files)
    #this doesn't seem to actually occur
    load_progress_node.call_deferred("set_value", Boot.load_progress_val)


func _on_dialog_confirmed():
    Core.game_dir = $dialog.current_dir

func _on_dialog_dir_selected(path: String):
    Core.game_dir = path
    $dialog.hide()

func _on_dialog_canceled():
    Core.game_dir = ""
    $dialog.hide()

func _on_DATExplorerButton_pressed():
    print("here")
    var err = get_tree().change_scene_to_file("res://DATExplorer/DATExplorer.tscn")
    if err != OK:
        Log.error("Error: %s" % err)

func _on_GameButton_pressed():
    var err = get_tree().change_scene_to_file("res://Region.tscn")
    if err != OK:
        Log.error("Error: %s" % err)
    
