#!/usr/bin/env python3
"""Read-only dynamic memory observation for a user-owned process.

Defaults are deliberately conservative: inspect readable private mappings,
scan numeric values without persisting raw bytes, and store only hashes in
differential snapshots. This is an observation tool, not a memory patcher or
code injector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SNAPSHOT_SCHEMA = "sc4-lab.memory-snapshot.v1"
TYPE_FORMATS = {
    "u32": ("<I", 4),
    "i32": ("<i", 4),
    "u64": ("<Q", 8),
    "i64": ("<q", 8),
    "f32": ("<f", 4),
    "f64": ("<d", 8),
}


class ObservatoryError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def proc_path(pid: int, name: str) -> Path:
    return Path("/proc") / str(pid) / name


def process_identity(pid: int) -> dict[str, Any]:
    root = Path("/proc") / str(pid)
    try:
        stat = root.stat()
        if stat.st_uid != os.getuid():
            raise ObservatoryError("refusing a process owned by another user")
        cmdline = (root / "cmdline").read_bytes().split(b"\0")[0].decode(errors="replace")
        status = {}
        for line in (root / "status").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(":")
            if key in {"Name", "State", "Uid", "VmRSS", "VmSize", "Threads"}:
                status[key] = value.strip()
    except OSError as exc:
        raise ObservatoryError(f"cannot inspect process {pid}: {exc}") from exc
    return {
        "pid": pid,
        "command_basename": Path(cmdline).name,
        "status": status,
        "current_user_only": True,
    }


def parse_maps(pid: int) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    try:
        lines = proc_path(pid, "maps").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ObservatoryError(f"cannot read maps for {pid}: {exc}") from exc
    for line in lines:
        fields = line.split(maxsplit=5)
        if len(fields) < 5:
            continue
        start_text, end_text = fields[0].split("-", 1)
        pathname = fields[5] if len(fields) == 6 else ""
        regions.append({
            "start": int(start_text, 16),
            "end": int(end_text, 16),
            "size": int(end_text, 16) - int(start_text, 16),
            "perms": fields[1],
            "offset": int(fields[2], 16),
            "pathname": pathname,
            "name": Path(pathname).name if pathname.startswith("/") else pathname,
        })
    return regions


def selected_regions(pid: int, include_executable: bool, max_region_bytes: int) -> list[dict[str, Any]]:
    regions = []
    for region in parse_maps(pid):
        perms = region["perms"]
        if "r" not in perms or region["size"] > max_region_bytes:
            continue
        if "p" not in perms:
            continue
        if not include_executable and "x" in perms:
            continue
        if region["name"] in {"[vvar]", "[vdso]", "[vsyscall]"}:
            continue
        regions.append(region)
    return regions


def open_memory(pid: int) -> int:
    try:
        return os.open(proc_path(pid, "mem"), os.O_RDONLY)
    except OSError as exc:
        raise ObservatoryError(
            f"cannot read /proc/{pid}/mem: {exc}; ptrace permissions may block observation"
        ) from exc


def read_region(handle: int, start: int, size: int, chunk_size: int = 1024 * 1024) -> Iterable[tuple[int, bytes]]:
    offset = 0
    while offset < size:
        length = min(chunk_size, size - offset)
        try:
            data = os.pread(handle, length, start + offset)
        except OSError:
            data = b""
        if data:
            yield offset, data
        offset += length


def parse_value(value: str, value_type: str) -> tuple[Any, bytes]:
    if value_type not in TYPE_FORMATS:
        raise ObservatoryError(f"unsupported numeric type: {value_type}")
    fmt, _ = TYPE_FORMATS[value_type]
    try:
        parsed: Any = float(value) if value_type.startswith("f") else int(value, 0)
        packed = struct.pack(fmt, parsed)
    except (ValueError, struct.error) as exc:
        raise ObservatoryError(f"invalid {value_type} value {value!r}") from exc
    if isinstance(parsed, float) and not math.isfinite(parsed):
        raise ObservatoryError("non-finite float values are not supported")
    return parsed, packed


def scan_value(pid: int, value: str, value_type: str, max_results: int, include_executable: bool, max_region_bytes: int) -> dict[str, Any]:
    parsed, needle = parse_value(value, value_type)
    _, width = TYPE_FORMATS[value_type]
    regions = selected_regions(pid, include_executable, max_region_bytes)
    matches: list[dict[str, Any]] = []
    errors = 0
    handle = open_memory(pid)
    try:
        for region in regions:
            carry = b""
            for offset, data in read_region(handle, region["start"], region["size"]):
                block = carry + data
                base = region["start"] + offset - len(carry)
                position = block.find(needle)
                while position >= 0:
                    address = base + position
                    matches.append({
                        "address": f"0x{address:x}",
                        "address_int": address,
                        "value_type": value_type,
                        "value": parsed,
                        "region_start": f"0x{region['start']:x}",
                        "region_name": region["name"],
                        "region_perms": region["perms"],
                    })
                    if len(matches) >= max_results:
                        return {"schema": "sc4-lab.memory-scan.v1", "pid": pid, "matches": matches, "truncated": True, "regions_considered": len(regions), "read_errors": errors}
                    position = block.find(needle, position + 1)
                carry = block[-(width - 1):] if width > 1 else b""
    finally:
        os.close(handle)
    return {"schema": "sc4-lab.memory-scan.v1", "pid": pid, "matches": matches, "truncated": False, "regions_considered": len(regions), "read_errors": errors}


def snapshot(pid: int, include_executable: bool, max_region_bytes: int, chunk_size: int) -> dict[str, Any]:
    regions = selected_regions(pid, include_executable, max_region_bytes)
    handle = open_memory(pid)
    hashed_regions: list[dict[str, Any]] = []
    try:
        for region in regions:
            chunks: list[dict[str, Any]] = []
            for offset, data in read_region(handle, region["start"], region["size"], chunk_size):
                chunks.append({"offset": offset, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            hashed_regions.append({
                "start": region["start"],
                "end": region["end"],
                "size": region["size"],
                "perms": region["perms"],
                "name": region["name"],
                "chunks": chunks,
            })
    finally:
        os.close(handle)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "captured_utc": utc_now(),
        "process": process_identity(pid),
        "raw_bytes_recorded": False,
        "regions": hashed_regions,
    }


def snapshot_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_regions = {(r["start"], r["end"]): r for r in before.get("regions", [])}
    changed: list[dict[str, Any]] = []
    for region in after.get("regions", []):
        key = (region["start"], region["end"])
        previous = before_regions.get(key, {})
        old = {(c["offset"], c["size"]): c["sha256"] for c in previous.get("chunks", [])}
        new = {(c["offset"], c["size"]): c["sha256"] for c in region.get("chunks", [])}
        changed_chunks = [offset for (offset, _), digest in new.items() if old.get((offset, _)) != digest]
        if changed_chunks:
            changed.append({
                "start": f"0x{region['start']:x}",
                "end": f"0x{region['end']:x}",
                "name": region["name"],
                "changed_chunks": len(changed_chunks),
                "first_changed_offset": min(changed_chunks),
            })
    return {
        "schema": "sc4-lab.memory-diff.v1",
        "created_utc": utc_now(),
        "raw_bytes_recorded": False,
        "changed_regions": changed,
        "changed_region_count": len(changed),
    }


def read_address(pid: int, address: int, value_type: str) -> Any:
    fmt, width = TYPE_FORMATS[value_type]
    handle = open_memory(pid)
    try:
        data = os.pread(handle, width, address)
    finally:
        os.close(handle)
    if len(data) != width:
        raise ObservatoryError(f"could not read {width} bytes at 0x{address:x}")
    return struct.unpack(fmt, data)[0]


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservatoryError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ObservatoryError(f"JSON object expected: {path}")
    return value


def self_test() -> int:
    helper = (
        "import ctypes,mmap,struct,sys,time; "
        "b=mmap.mmap(-1,4096,flags=mmap.MAP_PRIVATE|mmap.MAP_ANONYMOUS,prot=mmap.PROT_READ|mmap.PROT_WRITE); "
        "struct.pack_into('<I',b,0,305419896); "
        "print(ctypes.addressof(ctypes.c_char.from_buffer(b)),flush=True); "
        "line=sys.stdin.readline(); "
        "struct.pack_into('<I',b,0,305419897); "
        "print('changed',flush=True); time.sleep(0.2)"
    )
    child = subprocess.Popen([sys.executable, "-c", helper], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None
        address = int(child.stdout.readline().strip())
        first = scan_value(child.pid, "0x12345678", "u32", 32, False, 64 * 1024 * 1024)
        if not any(item["address_int"] == address for item in first["matches"]):
            raise ObservatoryError("self-test did not find the known value")
        before = snapshot(child.pid, False, 64 * 1024 * 1024, 4096)
        assert child.stdin is not None
        child.stdin.write("change\n")
        child.stdin.flush()
        if child.stdout.readline().strip() != "changed":
            raise ObservatoryError("self-test helper did not change its value")
        observed = read_address(child.pid, address, "u32")
        if observed != 0x12345679:
            raise ObservatoryError(f"self-test observed {observed!r}")
        after = snapshot(child.pid, False, 64 * 1024 * 1024, 4096)
        if snapshot_diff(before, after)["changed_region_count"] == 0:
            raise ObservatoryError("self-test did not find a changed memory region")
    finally:
        if child.stdin is not None:
            child.stdin.close()
        child.wait(timeout=2)
    print("MEMORY OBSERVATORY SELF-TEST PASS")
    return 0


def argument_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--pid", type=int)
    root.add_argument("--include-executable", action="store_true")
    root.add_argument("--max-region-mb", type=int, default=64)
    sub = root.add_subparsers(dest="command", required=True)
    maps = sub.add_parser("maps")
    maps.add_argument("--out", type=Path)
    scan = sub.add_parser("scan")
    scan.add_argument("--value", required=True)
    scan.add_argument("--type", choices=sorted(TYPE_FORMATS), default="u32")
    scan.add_argument("--max-results", type=int, default=1000)
    scan.add_argument("--out", type=Path)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--chunk-size", type=int, default=1024 * 1024)
    snap.add_argument("--out", type=Path, required=True)
    diff = sub.add_parser("diff")
    diff.add_argument("--before", type=Path, required=True)
    diff.add_argument("--after", type=Path, required=True)
    diff.add_argument("--out", type=Path, required=True)
    watch = sub.add_parser("watch")
    watch.add_argument("--address", type=lambda value: int(value, 0), action="append", required=True)
    watch.add_argument("--type", choices=sorted(TYPE_FORMATS), default="u32")
    watch.add_argument("--interval", type=float, default=1.0)
    watch.add_argument("--duration", type=float, required=True)
    watch.add_argument("--out", type=Path, required=True)
    sub.add_parser("self-test")
    return root


def main() -> int:
    args = argument_parser().parse_args()
    if args.command == "self-test":
        return self_test()
    if args.pid is None:
        print("--pid is required for this command", file=sys.stderr)
        return 2
    try:
        max_region_bytes = args.max_region_mb * 1024 * 1024
        if args.command == "maps":
            result = {"schema": "sc4-lab.memory-maps.v1", "process": process_identity(args.pid), "regions": selected_regions(args.pid, args.include_executable, max_region_bytes)}
            if args.out:
                write_json(args.out, result)
            else:
                print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "scan":
            result = scan_value(args.pid, args.value, args.type, args.max_results, args.include_executable, max_region_bytes)
            if args.out:
                write_json(args.out, result)
            else:
                print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "snapshot":
            write_json(args.out, snapshot(args.pid, args.include_executable, max_region_bytes, args.chunk_size))
        elif args.command == "diff":
            write_json(args.out, snapshot_diff(load_json(args.before), load_json(args.after)))
        elif args.command == "watch":
            deadline = time.monotonic() + args.duration
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("w", encoding="utf-8") as output:
                while True:
                    row = {"captured_utc": utc_now(), "pid": args.pid, "values": {f"0x{address:x}": read_address(args.pid, address, args.type) for address in args.address}}
                    output.write(json.dumps(row, sort_keys=True) + "\n")
                    output.flush()
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(max(0.01, args.interval))
        print(f"MEMORY OBSERVATORY PASS: {args.command}")
        return 0
    except (ObservatoryError, OSError, ValueError) as exc:
        print(f"memory observatory failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
