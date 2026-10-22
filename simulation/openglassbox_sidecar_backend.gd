class_name OpenGlassBoxSidecarBackend
extends SimulationBackend

## JSON-line client for the real external OpenGlassBox sidecar.
##
## This keeps the Godot boundary plain-data only. The sidecar owns all native
## OpenGlassBox objects; this class owns the pipe and translates responses to
## the SimulationBackend contract.

var _stdio : FileAccess
# Kept open for the process lifetime: a freed stderr pipe would close its read
# end and SIGPIPE the sidecar on its first diagnostic line.
var _stderr : FileAccess
var _pid := -1
var _request_id := 0
var _hello : Dictionary = {}
var last_error : Dictionary = {}
var request_timeout_ms := 120000
const MAX_REPLY_BYTES := 33554432

func backend_id() -> String:
    return str(_hello.get("backend_id", "openglassbox-sidecar-v1"))

func contract_id() -> String:
    return CONTRACT_ID

func backend_fingerprint() -> String:
    return str(_hello.get("backend_fingerprint", backend_id()))

func save_schema() -> String:
    return str(_hello.get("save_schema", "opensc4.openglassbox-sidecar.v1"))

func capabilities() -> Dictionary:
    return _hello.get("capabilities", {"api_version": API_VERSION, "contract": CONTRACT_ID})

func start(sidecar_path : String, helper_path : String = "") -> bool:
    stop()
    var global_sidecar := ProjectSettings.globalize_path(sidecar_path) if sidecar_path.begins_with("res://") else sidecar_path
    var arguments := PackedStringArray([global_sidecar])
    var env_helper := helper_path
    if env_helper.begins_with("res://"):
        env_helper = ProjectSettings.globalize_path(env_helper)
    if not env_helper.is_empty():
        OS.set_environment("OPENSC4_OPENGLASSBOX_HELPER", env_helper)
    # Nonblocking reads let every request enforce a deadline, including restore.
    var process := OS.execute_with_pipe("/usr/bin/python3", arguments, false)
    if not process.has("stdio"):
        push_error("Could not start OpenGlassBox sidecar: %s" % process)
        return false
    _stdio = process["stdio"]
    _stderr = process.get("stderr", null)
    _pid = int(process.get("pid", -1))
    var result := _request("hello", {})
    if not bool(result.get("ok", false)):
        stop()
        return false
    _hello = result.get("result", {})
    return true

func stop() -> void:
    if _pid >= 0 and OS.is_process_running(_pid):
        OS.kill(_pid)
    if is_instance_valid(_stdio):
        _stdio.close()
    _stdio = null
    if is_instance_valid(_stderr):
        _stderr.close()
    _stderr = null
    _pid = -1
    _hello = {}

func is_running() -> bool:
    return is_instance_valid(_stdio) and _pid >= 0 and OS.is_process_running(_pid)

func reset(scenario : Dictionary) -> void:
    _require_running()
    _request_ok("reset", scenario)

func advance_seconds(seconds : float) -> Dictionary:
    _require_running()
    return _request_ok("advance", {"seconds": seconds}).get("result", {}).get("snapshot", {})

func apply_command(command : Dictionary) -> Dictionary:
    _require_running()
    return _request_ok("command", command).get("result", {})

func validate_command(command : Dictionary) -> Dictionary:
    _require_running()
    return _request_ok("validate_command", command).get("result", {})

func snapshot() -> Dictionary:
    _require_running()
    return _request_ok("snapshot", {}).get("result", {})

func save_state() -> Dictionary:
    _require_running()
    return _request_ok("save", {}).get("result", {})

func load_state(state : Dictionary) -> bool:
    _require_running()
    return bool(_request_ok("load", state).get("result", {}).get("accepted", false))

func event_cursor() -> int:
    return int(snapshot().get("event_cursor", 0))

func events_since(cursor : int) -> Array:
    _require_running()
    return _request_ok("events", {"cursor": cursor}).get("result", {}).get("events", [])

func _request_ok(operation : String, payload : Variant) -> Dictionary:
    var result := _request(operation, payload)
    if not bool(result.get("ok", false)):
        push_error("OpenGlassBox sidecar rejected %s: %s" % [operation, result.get("error", {})])
    return result

func _request(operation : String, payload : Variant) -> Dictionary:
    if not is_running():
        return _failure("sidecar_unavailable", "sidecar is not running")
    last_error = {}
    _request_id += 1
    var envelope := {
        "protocol": "opensc4.adapter.v1",
        "request_id": _request_id,
        "operation": operation,
        "payload": payload,
    }
    var deadline := Time.get_ticks_msec() + request_timeout_ms
    var outgoing := (JSON.stringify(envelope, "", true, true) + "\n").to_utf8_buffer()
    if outgoing.size() > MAX_REPLY_BYTES:
        return _failure("sidecar_limit", "request exceeds limit")
    var offset := 0
    # Linux PIPE_BUF is 4096: these writes either fit completely or return
    # EAGAIN. A single nonblocking store_line can silently write only a prefix.
    while offset < outgoing.size():
        var end := mini(offset + 4096, outgoing.size())
        if _stdio.store_buffer(outgoing.slice(offset, end)):
            offset = end
        else:
            if not OS.is_process_running(_pid):
                return _failure("sidecar_eof", "sidecar exited while writing", true)
            if Time.get_ticks_msec() >= deadline:
                return _failure("sidecar_timeout", "sidecar write deadline exceeded", true)
            OS.delay_msec(2)
    var bytes := PackedByteArray()
    while true:
        var chunk := _stdio.get_buffer(65536)
        if not chunk.is_empty():
            bytes.append_array(chunk)
            if bytes.size() > MAX_REPLY_BYTES:
                return _failure("sidecar_limit", "response exceeds limit", true)
            if bytes.find(10) >= 0:
                break
        if not OS.is_process_running(_pid):
            return _failure("sidecar_eof", "sidecar exited", true)
        if Time.get_ticks_msec() >= deadline:
            return _failure("sidecar_timeout", "sidecar request deadline exceeded", true)
        OS.delay_msec(2)
    var line := bytes.get_string_from_utf8()

    var parsed = JSON.parse_string(line)
    if not parsed is Dictionary:
        return _failure("sidecar_json", "invalid sidecar response", true)
    if int(parsed.get("request_id", -1)) != _request_id:
        return _failure("sidecar_request_id", "response id mismatch", true)
    if parsed.get("protocol", "") != "opensc4.adapter.v1":
        return _failure("sidecar_protocol", "response protocol mismatch", true)
    if not bool(parsed.get("ok", false)):
        last_error = parsed.get("error", {})
    return parsed

func _failure(code : String, message : String, terminate : bool = false) -> Dictionary:
    last_error = {"code": code, "message": message}
    if terminate:
        stop()
    return {"ok": false, "error": last_error}

func _require_running() -> void:
    if not is_running():
        push_error("OpenGlassBox sidecar is not running")
