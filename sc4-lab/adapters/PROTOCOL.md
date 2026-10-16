# Adapter wire protocol

Adapters may run in-process or as a sidecar. The sidecar form uses one JSON
request per line on stdin and one JSON response per line on stdout. Diagnostics
belong on stderr. This keeps OpenSC4, the SC4 reference runner, and OpenGlassBox
replaceable without sharing pointers or parser objects.

## Envelope

Every request contains:

```json
{
  "protocol": "opensc4.adapter.v1",
  "request_id": 7,
  "operation": "snapshot",
  "payload": {}
}
```

Every response contains the same `request_id`:

```json
{
  "protocol": "opensc4.adapter.v1",
  "request_id": 7,
  "ok": true,
  "result": {}
}
```

Failures are data, not process termination:

```json
{
  "protocol": "opensc4.adapter.v1",
  "request_id": 8,
  "ok": false,
  "error": {"code": "invalid_command", "message": "..."}
}
```

## Operations

| Operation | Payload | Result |
| --- | --- | --- |
| `hello` | `{}` | backend id, contract, capabilities, save schema |
| `reset` | scenario dictionary | initial snapshot and event cursor |
| `validate_command` | command dictionary | acceptance and reason |
| `command` | command dictionary | acceptance, snapshot, new events |
| `advance` | `{seconds}` | snapshot and new events |
| `snapshot` | `{}` | current plain-data snapshot |
| `events` | `{cursor}` | events after the cursor |
| `save` | `{}` | versioned plain-data state |
| `load` | state dictionary | acceptance and snapshot |
| `shutdown` | `{}` | acknowledgement, then clean process exit |

The adapter owns its clock and update order. The caller must not assume that a
SC4 month equals a fixed number of candidate ticks; observations record both
the named sampling event and backend tick/cursor metadata.

## Ownership and safety

- JSON values are copied at the process boundary.
- No Godot `Node`, C++ pointer, SC4 parser object, executable path, asset path,
  or original save content crosses the protocol.
- Unknown operations and malformed payloads return structured errors.
- `request_id` is echoed exactly so asynchronous callers can correlate replies.
- A backend must not rewrite reference observations, scenario files, or
  verifier tolerances.

The protocol is an integration seam, not proof that an adapter matches SC4.

The data-free fixture under `adapters/mock/` is the first executable consumer.
Use it to validate the transport before connecting an OpenGlassBox or local SC4
adapter.
