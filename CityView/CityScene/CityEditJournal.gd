extends RefCounted

class_name CityEditJournal

const SCHEMA : String = "opensc4.city-edit.v1"

static func document(source_path : String, city_name : String, region_name : String,
        road_edits : Array) -> Dictionary:
    return {
        "schema": SCHEMA,
        "created_utc": Time.get_datetime_string_from_system(true),
        "source_city": source_path,
        "city_name": city_name,
        "region_name": region_name,
        "edits": {
            "roads": road_edits.duplicate(true),
        },
        "replay_status": "journal_only",
        "replay_note": "This journal is not yet a valid SC4 DBPF patch. The paired .sc4 is an untouched baseline copy.",
    }

static func write(path : String, payload : Dictionary) -> int:
    var file = FileAccess.open(path, FileAccess.WRITE)
    if file == null:
        return FileAccess.get_open_error()
    file.store_string(JSON.stringify(payload, "\t"))
    file.store_string("\n")
    file.close()
    return OK

static func safe_copy_with_journal(source_path : String, destination_path : String,
        payload : Dictionary) -> Dictionary:
    var source = source_path.simplify_path()
    var destination = destination_path.simplify_path()
    if source.is_empty() or destination.is_empty():
        return {"error": "Source or destination path is empty"}
    if source == destination:
        return {"error": "Refusing to overwrite the source city"}
    if not FileAccess.file_exists(source):
        return {"error": "Source city does not exist: %s" % source}
    if not destination.to_lower().ends_with(".sc4"):
        destination += ".sc4"
    if FileAccess.file_exists(destination):
        return {"error": "Destination already exists; choose a new SC4 filename"}

    var copy_error = DirAccess.copy_absolute(source, destination)
    if copy_error != OK:
        return {"error": "Could not copy SC4 baseline (error %d)" % copy_error}
    var journal_path = destination + ".opensc4.json"
    var journal_error = write(journal_path, payload)
    if journal_error != OK:
        # The baseline copy is still recoverable and useful, so report both
        # paths rather than deleting it or touching the source.
        return {
            "error": "SC4 baseline copied, but journal write failed (error %d)" % journal_error,
            "sc4": destination,
        }
    return {"sc4": destination, "journal": journal_path}
