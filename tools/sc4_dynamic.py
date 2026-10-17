#!/usr/bin/env python3
"""Dynamic SC4 memory analysis: raw dumps, typed diffs, pokes, and watchpoints.

This is the active counterpart to the read-only observatory. It works on the
user's own live SC4 process and keeps every byte it captures outside Git.

- ``dump``  freezes the process (SIGSTOP), copies writable private memory to a
  raw file with a region index, and resumes it (SIGCONT).
- ``diff``  compares two dumps as typed words, or three dumps as a sensitivity
  test: which words moved differently in step B->C than in step A->B.
- ``poke``  writes one typed value while frozen, reads it back, and journals the
  old bytes so ``--restore`` can undo it.
- ``watch`` attaches GDB with hardware watchpoints and logs every instruction
  that writes (or reads) the watched words, plus stack return-address
  candidates inside the executable. Those addresses are the inputs for a
  focused REA/Ghidra ``function`` query.

Addresses are only valid for the current process. Nothing here is portable
across sessions until a pointer path from a module global is recovered.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import sc4_budget_probe
import sc4_clock_probe
from memory_observatory import ObservatoryError, parse_maps, process_identity, utc_now


DUMP_SCHEMA = "sc4-lab.sc4-dynamic-dump.v1"
DIFF_SCHEMA = "sc4-lab.sc4-dynamic-diff.v1"
WATCH_SCHEMA = "sc4-lab.sc4-dynamic-watch.v1"
POKE_SCHEMA = "sc4-lab.sc4-dynamic-poke.v1"
DEFAULT_ROOT = Path.home() / ".cache" / "opensc4" / "dynamic"
REPO_ROOT = Path(__file__).resolve().parents[1]
TYPES = {"u32": ("<I", 4), "i32": ("<i", 4), "f32": ("<f", 4), "i64": ("<q", 8), "f64": ("<d", 8), "u8": ("<B", 1)}
NUMPY_TYPES = {"u32": "<u4", "i32": "<i4", "f32": "<f4", "i64": "<i8", "f64": "<f8"}


class DynamicError(Exception):
    pass


def outside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise DynamicError(f"refusing to write raw process data inside the repository: {resolved}")
    return resolved


def parse_int(text: str) -> int:
    return int(text, 0)


# --- process control ---------------------------------------------------------

def process_state(pid: int) -> str:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("State:"):
            return line.split()[1]
    return "?"


class Frozen:
    """SIGSTOP the whole process for a consistent view; always SIGCONT after."""

    def __init__(self, pid: int, enabled: bool = True):
        self.pid = pid
        self.enabled = enabled

    def __enter__(self) -> "Frozen":
        if self.enabled:
            os.kill(self.pid, signal.SIGSTOP)
            deadline = time.monotonic() + 5
            while process_state(self.pid) not in {"T", "t"}:
                if time.monotonic() > deadline:
                    os.kill(self.pid, signal.SIGCONT)
                    raise DynamicError("process did not stop within 5 s")
                time.sleep(0.01)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.enabled:
            os.kill(self.pid, signal.SIGCONT)


def exe_regions(pid: int, image_name: str) -> list[dict[str, Any]]:
    return [r for r in parse_maps(pid) if r["name"] == image_name or r["pathname"].endswith(image_name)]


def dump_regions(pid: int, image_name: str, include_files: bool) -> list[dict[str, Any]]:
    chosen = []
    for region in parse_maps(pid):
        perms = region["perms"]
        if not perms.startswith("rw") or "p" not in perms or region["end"] > 0x1_0000_0000:
            continue
        if region["name"] in {"[vvar]", "[vdso]", "[vsyscall]", "[stack]"}:
            continue
        is_exe = region["pathname"].endswith(image_name)
        is_file = region["pathname"].startswith("/") and not is_exe
        if is_file and not include_files:
            continue
        chosen.append({**region, "kind": "exe" if is_exe else ("file" if is_file else "anon")})
    return chosen


def live_metrics(pid: int, image_name: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    try:
        base = sc4_budget_probe.image_base(pid, image_name)
        handle = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
        try:
            metrics.update(sc4_budget_probe.sample(handle, pid, base)["metrics"])
            metrics.update(sc4_clock_probe.sample(handle, pid, base)["metrics"])
        finally:
            os.close(handle)
    except Exception as exc:  # metrics are context; a dump without them is still valid
        metrics["error"] = str(exc)
    return metrics


# --- dump --------------------------------------------------------------------

def dump(args: argparse.Namespace) -> int:
    root = outside_repo(args.root)
    label = args.label or time.strftime("%Y%m%dT%H%M%S")
    out = root / label
    if out.exists():
        raise DynamicError(f"dump already exists: {out}")
    out.mkdir(parents=True)
    identity = process_identity(args.pid)
    started = time.monotonic()
    index = []
    offset = 0
    with Frozen(args.pid, not args.no_freeze):
        metrics = live_metrics(args.pid, args.image_name)
        regions = dump_regions(args.pid, args.image_name, args.include_files)
        handle = os.open(f"/proc/{args.pid}/mem", os.O_RDONLY)
        try:
            with open(out / "memory.bin", "wb") as blob:
                for region in regions:
                    data = bytearray()
                    position = region["start"]
                    while position < region["end"]:
                        length = min(1 << 22, region["end"] - position)
                        try:
                            chunk = os.pread(handle, length, position)
                        except OSError:
                            chunk = b""
                        data += chunk.ljust(length, b"\0")
                        position += length
                    blob.write(data)
                    index.append({
                        "start": region["start"], "end": region["end"], "size": region["size"],
                        "perms": region["perms"], "kind": region["kind"], "name": region["name"],
                        "file_offset": offset,
                    })
                    offset += region["size"]
        finally:
            os.close(handle)
    meta = {
        "schema": DUMP_SCHEMA,
        "captured_utc": utc_now(),
        "label": label,
        "process": identity,
        "frozen": not args.no_freeze,
        "freeze_seconds": round(time.monotonic() - started, 3),
        "bytes": offset,
        "metrics": metrics,
        "note": args.note,
        "regions": index,
    }
    (out / "dump.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"dump": str(out), "regions": len(index), "mib": round(offset / 2**20, 1),
                      "freeze_seconds": meta["freeze_seconds"],
                      "date": {k: metrics.get(k) for k in ("simulation_year", "simulation_month", "simulation_day")},
                      "funds_public": metrics.get("funds_public")}))
    return 0


# --- diff --------------------------------------------------------------------

def load_dump(path: Path) -> tuple[dict[str, Any], Any]:
    import numpy as np

    meta = json.loads((path / "dump.json").read_text())
    if meta.get("schema") != DUMP_SCHEMA:
        raise DynamicError(f"not a dynamic dump: {path}")
    return meta, np.memmap(path / "memory.bin", dtype="u1", mode="r")


def common_regions(metas: list[dict[str, Any]]) -> list[tuple[dict[str, Any], ...]]:
    keyed = [{(r["start"], r["end"]): r for r in meta["regions"]} for meta in metas]
    shared = set(keyed[0]).intersection(*keyed[1:])
    return [tuple(k[key] for k in keyed) for key in sorted(shared)]


def typed_view(blob: Any, region: dict[str, Any], dtype: str) -> Any:
    width = int(dtype[-1])
    raw = blob[region["file_offset"]: region["file_offset"] + region["size"]]
    return raw[: len(raw) - len(raw) % width].view(dtype)


def plausible(values: Any, dtype: str) -> Any:
    import numpy as np

    if dtype.startswith("<f"):
        finite = np.isfinite(values)
        magnitude = np.abs(np.where(finite, values, 0))
        return finite & ((magnitude == 0) | ((magnitude > 1e-6) & (magnitude < 1e9)))
    return np.ones(values.shape, dtype=bool)


def diff(args: argparse.Namespace) -> int:
    import numpy as np

    dumps = [load_dump(path) for path in args.dumps]
    metas = [meta for meta, _ in dumps]
    dtype = NUMPY_TYPES[args.type]
    width = int(dtype[-1])
    rows: list[dict[str, Any]] = []
    region_counts: list[dict[str, Any]] = []
    for regions in common_regions(metas):
        if args.kind and regions[0]["kind"] not in args.kind:
            continue
        views = [typed_view(blob, region, dtype) for (_, blob), region in zip(dumps, regions)]
        length = min(len(view) for view in views)
        views = [view[:length] for view in views]
        if len(views) == 2:
            a, b = views
            mask = a != b
            if args.type.startswith("f"):
                mask &= plausible(a, dtype) & plausible(b, dtype)
            score = None
        else:
            a, b, c = views
            first = b.astype("f8") - a.astype("f8")
            second = c.astype("f8") - b.astype("f8")
            mask = first != second
            if args.type.startswith("f"):
                mask &= plausible(a, dtype) & plausible(b, dtype) & plausible(c, dtype)
            score = np.abs(second - first)
        if args.delta is not None:
            mask &= (views[-1].astype("f8") - views[0].astype("f8")) == args.delta
        if args.range:
            low, high = args.range
            for view in views:
                mask &= (view >= low) & (view <= high)
        if args.min_abs_delta:
            moved = np.abs(views[-1].astype("f8") - views[0].astype("f8"))
            mask &= moved >= args.min_abs_delta
        hits = np.nonzero(mask)[0]
        if not len(hits):
            continue
        region_counts.append({"start": hex(regions[0]["start"]), "kind": regions[0]["kind"],
                              "name": regions[0]["name"], "changed_words": int(len(hits))})
        if score is not None:
            hits = hits[np.argsort(-score[hits], kind="stable")]
        for word in hits[: args.limit]:
            row = {"address": hex(regions[0]["start"] + int(word) * width), "kind": regions[0]["kind"]}
            row["values"] = [view[word].item() for view in views]
            if score is not None:
                row["delta_change"] = float(score[word])
            rows.append(row)
    if len(args.dumps) == 3:
        rows.sort(key=lambda row: -row["delta_change"])
    rows = rows[: args.limit]
    result = {
        "schema": DIFF_SCHEMA,
        "created_utc": utc_now(),
        "mode": "pair" if len(args.dumps) == 2 else "sensitivity",
        "type": args.type,
        "dumps": [{"label": m["label"], "metrics": {k: m["metrics"].get(k) for k in
                   ("simulation_date_serial", "funds_public", "tax_income")}} for m in metas],
        "changed_words_total": sum(r["changed_words"] for r in region_counts),
        "regions": sorted(region_counts, key=lambda r: -r["changed_words"])[:50],
        "words": rows,
    }
    if args.out:
        outside_repo(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"changed_words_total": result["changed_words_total"], "regions_changed": len(region_counts),
                      "top": rows[:10]}, indent=1))
    return 0


# --- poke --------------------------------------------------------------------

def budget_field(pid: int, image_name: str, field: str) -> tuple[int, str]:
    base = sc4_budget_probe.image_base(pid, image_name)
    handle = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    try:
        budget = sc4_budget_probe.read_value(handle, base + sc4_budget_probe.BUDGET_GLOBAL_RVA, "<I")
    finally:
        os.close(handle)
    if budget < 0x10000:
        raise DynamicError(f"budget pointer is invalid: 0x{budget:x}")
    name, _, index = field.partition(":")
    fields = {
        "funds": (sc4_budget_probe.FUNDS_OFFSET, "i64"),
        "funds_working": (sc4_budget_probe.FUNDS_WORKING_OFFSET, "i64"),
        "tax_income": (sc4_budget_probe.TAX_INCOME_OFFSET, "i64"),
        "tax_rate": (sc4_budget_probe.RATE_BASE, "f32"),
        "tax_total": (sc4_budget_probe.TAX_CATEGORY_TOTAL_BASE, "i64"),
    }
    if name not in fields:
        raise DynamicError(f"unknown field {name}; choose from {', '.join(fields)}")
    offset, value_type = fields[name]
    if name in {"tax_rate", "tax_total"}:
        slot = int(index or 0)
        if not 0 <= slot < sc4_budget_probe.RATE_COUNT:
            raise DynamicError("category index must be 0..11")
        offset += slot * sc4_budget_probe.RECORD_STRIDE
    return budget + offset, value_type


def poke(args: argparse.Namespace) -> int:
    journal = outside_repo(args.journal)
    if args.restore:
        entry = json.loads(journal.read_text().splitlines()[-1])
        address, value_type, payload = int(entry["address"], 16), entry["type"], bytes.fromhex(entry["old_hex"])
        label = "restore"
    else:
        if args.field:
            address, value_type = budget_field(args.pid, args.image_name, args.field)
        elif args.address is not None and args.type:
            address, value_type = args.address, args.type
        else:
            raise DynamicError("give --field, or --address with --type")
        fmt, _ = TYPES[value_type]
        number = float(args.value) if value_type.startswith("f") else int(args.value, 0)
        payload = struct.pack(fmt, number)
        label = args.field or "address"
    fmt, size = TYPES[value_type]
    with Frozen(args.pid):
        with open(f"/proc/{args.pid}/mem", "r+b", buffering=0) as mem:
            mem.seek(address)
            old = mem.read(size)
            if not args.dry_run:
                mem.seek(address)
                mem.write(payload)
            mem.seek(address)
            new = mem.read(size)
    entry = {
        "schema": POKE_SCHEMA, "captured_utc": utc_now(), "pid": args.pid, "target": label,
        "address": hex(address), "type": value_type, "dry_run": args.dry_run,
        "old": struct.unpack(fmt, old)[0], "new": struct.unpack(fmt, new)[0],
        "old_hex": old.hex(), "verified": args.dry_run or new == payload,
    }
    if not args.dry_run and not args.restore:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with open(journal, "a") as handle:
            handle.write(json.dumps(entry) + "\n")
    print(json.dumps(entry))
    return 0 if entry["verified"] else 1


# --- watch -------------------------------------------------------------------

GDB_SCRIPT = r'''
import gdb, json, struct, time
CFG = json.load(open(CFG_PATH))
OUT = open(CFG["out"], "a", buffering=1)
TEXT_LO, TEXT_HI = CFG["text_lo"], CFG["text_hi"]
counts = {}
total = [0]

def stack_returns():
    esp = int(gdb.parse_and_eval("$esp")) & 0xffffffff
    try:
        raw = bytes(gdb.selected_inferior().read_memory(esp, 4 * CFG["stack_words"]))
    except gdb.MemoryError:
        return []
    words = struct.unpack("<%dI" % CFG["stack_words"], raw)
    return [hex(w) for w in words if TEXT_LO <= w < TEXT_HI][:CFG["max_returns"]]

class Watch(gdb.Breakpoint):
    def __init__(self, spec):
        cls = {"write": gdb.WP_WRITE, "read": gdb.WP_READ, "access": gdb.WP_ACCESS}[spec["mode"]]
        super().__init__("*(unsigned int *)%s" % spec["address"], gdb.BP_WATCHPOINT, cls, internal=False)
        self.spec = spec
    def stop(self):
        pc = int(gdb.parse_and_eval("$pc")) & 0xffffffff
        key = (self.spec["name"], pc)
        counts[key] = counts.get(key, 0) + 1
        total[0] += 1
        if counts[key] <= CFG["samples_per_pc"]:
            value = struct.unpack("<I", bytes(gdb.selected_inferior().read_memory(int(self.spec["address"], 16), 4)))[0]
            regs = {r: int(gdb.parse_and_eval("$" + r)) & 0xffffffff for r in ("eax", "ecx", "edx", "ebx", "esi", "edi", "ebp", "esp")}
            OUT.write(json.dumps({"t": time.time(), "watch": self.spec["name"], "mode": self.spec["mode"],
                                  "pc_after": hex(pc), "value_u32": value,
                                  "regs": {k: hex(v) for k, v in regs.items()},
                                  "stack_returns": stack_returns()}) + "\n")
        if total[0] >= CFG["max_hits"]:
            for bp in gdb.breakpoints() or ():
                bp.enabled = False
        return False

def summary():
    OUT.write(json.dumps({"summary": [{"watch": k[0], "pc_after": hex(k[1]), "hits": v}
                                      for k, v in sorted(counts.items(), key=lambda kv: -kv[1])],
                          "total_hits": total[0]}) + "\n")
    OUT.flush()

for spec in CFG["watches"]:
    Watch(spec)
'''


def watch(args: argparse.Namespace) -> int:
    out = outside_repo(args.out)
    specs = []
    for item in args.watch:
        target, _, mode = item.partition("@")
        mode = mode or "write"
        if mode not in {"write", "read", "access"}:
            raise DynamicError(f"bad watch mode in {item}")
        if target.startswith("0x"):
            address = int(target, 16)
        else:
            address, _ = budget_field(args.pid, args.image_name, target)
        specs.append({"name": target, "mode": mode, "address": hex(address)})
    if not 1 <= len(specs) <= 4:
        raise DynamicError("x86 has four debug registers: give 1..4 --watch targets")
    text = [r for r in exe_regions(args.pid, args.image_name) if "x" in r["perms"]]
    text_lo = min((r["start"] for r in text), default=0x401000)
    text_hi = max((r["end"] for r in text), default=0xB00000)
    workdir = Path(tempfile.mkdtemp(prefix="sc4-watch-"))
    cfg = workdir / "cfg.json"
    cfg.write_text(json.dumps({"out": str(out), "watches": specs, "text_lo": text_lo, "text_hi": text_hi,
                               "stack_words": args.stack_words, "max_returns": 8,
                               "samples_per_pc": args.samples_per_pc, "max_hits": args.max_hits}))
    script = workdir / "watch.py"
    script.write_text(f"CFG_PATH = {str(cfg)!r}\n" + GDB_SCRIPT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": WATCH_SCHEMA, "started_utc": utc_now(), "pid": args.pid,
                               "watches": specs, "text_range": [hex(text_lo), hex(text_hi)],
                               "duration": args.duration,
                               "metrics_before": live_metrics(args.pid, args.image_name)}) + "\n")
    quiet = "SIGSEGV SIGUSR1 SIGUSR2 SIGILL SIGFPE SIGBUS SIGPIPE SIGALRM SIGIO SIGCHLD SIGWINCH SIGQUIT SIGSYS"
    command = ["gdb", "-q", "-n", "-batch", "-p", str(args.pid),
               "-ex", "set pagination off", "-ex", "set confirm off",
               "-ex", f"handle {quiet} nostop noprint pass", "-ex", "handle SIGINT stop print nopass",
               "-ex", f"source {script}", "-ex", "continue",
               "-ex", "python summary()", "-ex", "delete", "-ex", "detach", "-ex", "quit"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               start_new_session=True)
    try:
        process.wait(timeout=args.duration)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
    log = process.stdout.read() if process.stdout else ""
    (workdir / "gdb.log").write_text(log)
    if process_state(args.pid) in {"T", "t"}:
        os.kill(args.pid, signal.SIGCONT)
    with open(out, "a") as handle:
        handle.write(json.dumps({"metrics_after": live_metrics(args.pid, args.image_name),
                                 "gdb_exit": process.returncode, "gdb_log": str(workdir / "gdb.log")}) + "\n")
    summary = next((json.loads(line) for line in out.read_text().splitlines() if '"summary"' in line), None)
    print(json.dumps({"out": str(out), "gdb_exit": process.returncode,
                      "summary": summary["summary"][:20] if summary else "no summary; see gdb log",
                      "gdb_log": str(workdir / "gdb.log")}, indent=1))
    return 0


# --- cli -----------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root.add_argument("--image-name", default="SimCity 4.exe")
    sub = root.add_subparsers(dest="command", required=True)

    d = sub.add_parser("dump", help="freeze, copy writable memory, resume")
    d.add_argument("--pid", type=int, required=True)
    d.add_argument("--label")
    d.add_argument("--note", default="")
    d.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    d.add_argument("--include-files", action="store_true", help="also dump writable file-backed regions (DLL data)")
    d.add_argument("--no-freeze", action="store_true")

    f = sub.add_parser("diff", help="typed diff of 2 dumps, or sensitivity across 3")
    f.add_argument("dumps", type=Path, nargs="+")
    f.add_argument("--type", choices=sorted(NUMPY_TYPES), default="i32")
    f.add_argument("--kind", action="append", choices=("anon", "exe", "file"))
    f.add_argument("--min-abs-delta", type=float, default=0.0)
    f.add_argument("--delta", type=float, help="keep words whose last-minus-first change equals this")
    f.add_argument("--range", type=float, nargs=2, metavar=("LOW", "HIGH"), help="keep words inside this value range in every dump")
    f.add_argument("--limit", type=int, default=200)
    f.add_argument("--out", type=Path)

    p = sub.add_parser("poke", help="write one value while frozen, journaled")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--field", help="funds | funds_working | tax_income | tax_rate:N | tax_total:N")
    p.add_argument("--address", type=parse_int)
    p.add_argument("--type", choices=sorted(TYPES))
    p.add_argument("--value")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true", help="undo the last journaled poke")
    p.add_argument("--journal", type=Path, default=DEFAULT_ROOT / "pokes.jsonl")

    w = sub.add_parser("watch", help="log instructions that touch watched words (GDB hardware watchpoints)")
    w.add_argument("--pid", type=int, required=True)
    w.add_argument("--watch", action="append", required=True,
                   help="field or 0xADDR, optionally @write|@read|@access (default write)")
    w.add_argument("--duration", type=float, default=60)
    w.add_argument("--max-hits", type=int, default=20000)
    w.add_argument("--samples-per-pc", type=int, default=5)
    w.add_argument("--stack-words", type=int, default=64)
    w.add_argument("--out", type=Path, default=DEFAULT_ROOT / "watch.jsonl")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "dump":
            return dump(args)
        if args.command == "diff":
            if len(args.dumps) not in {2, 3}:
                raise DynamicError("diff takes 2 dumps (pair) or 3 (sensitivity)")
            return diff(args)
        if args.command == "poke":
            if not args.restore and args.value is None and not args.dry_run:
                raise DynamicError("--value is required")
            return poke(args)
        return watch(args)
    except (OSError, ValueError, ObservatoryError, DynamicError) as exc:
        print(f"SC4 DYNAMIC FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
