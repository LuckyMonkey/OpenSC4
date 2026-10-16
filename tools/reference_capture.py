#!/usr/bin/env python3
"""Capture local-only SC4 save/process metadata without copying game bytes.

This tool is for black-box observation. It stores hashes and fixed-size chunk
hashes, not save contents. Process capture is limited to metadata and optional
/proc/<pid>/maps ranges for the current user; it does not read raw memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "sc4-lab.local-reference-capture.v1"
DEFAULT_CHUNK_SIZE = 4096


class CaptureError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_manifest(path: Path, chunk_size: int) -> dict[str, Any]:
    if not path.is_file():
        raise CaptureError(f"save file does not exist: {path}")
    if chunk_size <= 0:
        raise CaptureError("chunk size must be positive")
    whole = hashlib.sha256()
    chunks: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        index = 0
        while data := handle.read(chunk_size):
            digest = hashlib.sha256(data).hexdigest()
            whole.update(data)
            chunks.append({"index": index, "sha256": digest, "size": len(data)})
            index += 1
    stat = path.stat()
    return {
        "basename": path.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": whole.hexdigest(),
        "chunk_size": chunk_size,
        "chunks": chunks,
        "source_path_recorded": False,
    }


def status_values(pid: int) -> dict[str, str]:
    status_path = Path("/proc") / str(pid) / "status"
    wanted = {"Name", "State", "VmRSS", "VmSize", "Threads", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches"}
    result: dict[str, str] = {}
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(":")
            if key in wanted:
                result[key] = value.strip()
    except OSError as exc:
        raise CaptureError(f"cannot read process status for {pid}: {exc}") from exc
    return result


def maps_summary(pid: int) -> dict[str, Any]:
    maps_path = Path("/proc") / str(pid) / "maps"
    regions = 0
    bytes_total = 0
    permissions: dict[str, int] = {}
    files: set[str] = set()
    try:
        lines = maps_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CaptureError(f"cannot read process maps for {pid}: {exc}") from exc
    for line in lines:
        fields = line.split(maxsplit=5)
        if len(fields) < 2:
            continue
        start_text, end_text = fields[0].split("-", 1)
        bytes_total += int(end_text, 16) - int(start_text, 16)
        perms = fields[1]
        permissions[perms] = permissions.get(perms, 0) + 1
        regions += 1
        if len(fields) == 6 and fields[5].startswith("/"):
            files.add(Path(fields[5]).name)
    return {
        "regions": regions,
        "virtual_bytes": bytes_total,
        "permissions": permissions,
        "mapped_file_basenames": sorted(files),
    }


def process_manifest(pid: int, include_maps: bool) -> dict[str, Any]:
    proc_path = Path("/proc") / str(pid)
    try:
        stat = proc_path.stat()
    except OSError as exc:
        raise CaptureError(f"cannot inspect process {pid}: {exc}") from exc
    if stat.st_uid != os.getuid():
        raise CaptureError("refusing process metadata for another user")
    try:
        command = (proc_path / "cmdline").read_bytes().split(b"\0")[0].decode(errors="replace")
    except OSError as exc:
        raise CaptureError(f"cannot read process command for {pid}: {exc}") from exc
    result: dict[str, Any] = {
        "pid": pid,
        "command_basename": Path(command).name,
        "status": status_values(pid),
        "raw_memory_read": False,
    }
    if include_maps:
        result["maps"] = maps_summary(pid)
    return result


def capture(save: Path | None, pid: int | None, chunk_size: int, include_maps: bool, phase: str) -> dict[str, Any]:
    if save is None and pid is None:
        raise CaptureError("provide --save and/or --pid")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "captured_utc": utc_now(),
        "phase": phase,
        "reference_claim": False,
        "provenance": {
            "kind": "local-observation-metadata",
            "raw_game_bytes_recorded": False,
            "raw_memory_recorded": False,
        },
    }
    if save is not None:
        result["save"] = file_manifest(save, chunk_size)
    if pid is not None:
        result["process"] = process_manifest(pid, include_maps)
    return result


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read capture {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise CaptureError(f"invalid capture schema: {path}")
    return value


def changed_ranges(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, int]]:
    before_save = before.get("save", {})
    after_save = after.get("save", {})
    chunk_size = int(after_save.get("chunk_size", DEFAULT_CHUNK_SIZE))
    before_chunks = {int(chunk["index"]): chunk["sha256"] for chunk in before_save.get("chunks", [])}
    after_chunks = {int(chunk["index"]): chunk["sha256"] for chunk in after_save.get("chunks", [])}
    changed = sorted(index for index in set(before_chunks) | set(after_chunks) if before_chunks.get(index) != after_chunks.get(index))
    ranges: list[dict[str, int]] = []
    for index in changed:
        start = index * chunk_size
        end = start + chunk_size
        if ranges and ranges[-1]["end"] == start:
            ranges[-1]["end"] = end
        else:
            ranges.append({"start": start, "end": end})
    return ranges


def diff_captures(before_path: Path, after_path: Path) -> dict[str, Any]:
    before = load_json(before_path)
    after = load_json(after_path)
    ranges = changed_ranges(before, after)
    before_save = before.get("save", {})
    after_save = after.get("save", {})
    return {
        "schema": "sc4-lab.local-reference-diff.v1",
        "created_utc": utc_now(),
        "reference_claim": False,
        "before_basename": before_save.get("basename"),
        "after_basename": after_save.get("basename"),
        "before_sha256": before_save.get("sha256"),
        "after_sha256": after_save.get("sha256"),
        "size_delta": int(after_save.get("size", 0)) - int(before_save.get("size", 0)),
        "changed_chunk_ranges": ranges,
        "changed_chunks": sum((item["end"] - item["start"]) // int(after_save.get("chunk_size", DEFAULT_CHUNK_SIZE)) for item in ranges),
        "raw_bytes_recorded": False,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--save", type=Path)
    snapshot.add_argument("--pid", type=int)
    snapshot.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    snapshot.add_argument("--include-maps", action="store_true")
    snapshot.add_argument("--phase", default="manual")
    snapshot.add_argument("--out", type=Path, required=True)
    diff = sub.add_parser("diff")
    diff.add_argument("--before", type=Path, required=True)
    diff.add_argument("--after", type=Path, required=True)
    diff.add_argument("--out", type=Path, required=True)
    watch = sub.add_parser("watch")
    watch.add_argument("--save", type=Path, required=True)
    watch.add_argument("--pid", type=int)
    watch.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    watch.add_argument("--include-maps", action="store_true")
    watch.add_argument("--interval", type=float, default=1.0)
    watch.add_argument("--duration", type=float, required=True)
    watch.add_argument("--out", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "snapshot":
            write_json(args.out, capture(args.save, args.pid, args.chunk_size, args.include_maps, args.phase))
        elif args.command == "diff":
            write_json(args.out, diff_captures(args.before, args.after))
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + args.duration
            previous_hash: str | None = None
            with args.out.open("w", encoding="utf-8") as output:
                while True:
                    current = capture(args.save, args.pid, args.chunk_size, args.include_maps, "watch")
                    current_hash = current["save"]["sha256"]
                    if current_hash != previous_hash:
                        output.write(json.dumps(current, sort_keys=True) + "\n")
                        output.flush()
                        previous_hash = current_hash
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(max(0.01, args.interval))
    except CaptureError as exc:
        print(f"reference capture failed: {exc}", file=sys.stderr)
        return 2
    print(f"REFERENCE CAPTURE PASS: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
