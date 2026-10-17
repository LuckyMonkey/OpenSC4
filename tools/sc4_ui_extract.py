#!/usr/bin/env python3
"""Recover SC4's live UI window tree from process memory (read-only).

SC4's .UI files only hold the 800x600 design layout; the game's code places
and sizes panels for the real screen at runtime. This tool reads the live
window objects instead.

    catalog   parse every .UI file in the DATs: window id, class, design area
    discover  freeze SC4, find catalog window ids in memory, and infer the
              window object layout (where the area rect and links live) from
              agreement across many windows
    dump      walk the live window tree with that layout and write JSON
              (id, class, vtable, runtime rect, visibility, children)

Memory is only read (SIGSTOP/SIGCONT around a snapshot). Output stays local.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dat_dump  # noqa: E402
import sc4_dynamic  # noqa: E402

DATS = ["SimCity_1.dat", "SimCity_2.dat", "SimCity_3.dat", "SimCity_4.dat", "SimCity_5.dat", "EP1.dat"]
UI_TYPE, UI_GROUP = 0x00000000, 0x96A006B0
AREA = re.compile(r"area=\((-?\d+),(-?\d+),(-?\d+),(-?\d+)\)")


def catalog(game_dir: Path) -> list[dict[str, Any]]:
    windows = []
    for name in DATS:
        db = dat_dump.DBPF(str(game_dir / name))
        for sf in db.find(UI_TYPE, UI_GROUP):
            text = db.raw_bytes(sf).decode("latin-1", "replace")
            if "<LEGACY" not in text:
                continue
            depth = 0
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("<CHILDREN"):
                    depth += 1
                elif s.startswith("</CHILDREN"):
                    depth -= 1
                elif s.startswith("<LEGACY"):
                    m = AREA.search(s)
                    wid = re.search(r" id=0x([0-9a-fA-F]+)", s)
                    cls = re.search(r"clsid=(\S+)", s)
                    windows.append({"ui_file": f"{sf.instance_id:08x}", "depth": depth,
                                    "id": int(wid.group(1), 16) if wid else None,
                                    "clsid": cls.group(1) if cls else None,
                                    "area": [int(v) for v in m.groups()] if m else None})
    return windows


def snapshot(pid: int, image_name: str) -> tuple[list[tuple[int, int]], bytes]:
    """Frozen copy of writable private memory below 4 GiB: (regions, blob)."""
    regions, chunks = [], []
    with sc4_dynamic.Frozen(pid):
        handle = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
        try:
            for region in sc4_dynamic.dump_regions(pid, image_name, include_files=False):
                data = bytearray()
                pos = region["start"]
                while pos < region["end"]:
                    length = min(1 << 22, region["end"] - pos)
                    try:
                        piece = os.pread(handle, length, pos)
                    except OSError:
                        piece = b""
                    data += piece.ljust(length, b"\0")
                    pos += length
                regions.append((region["start"], len(data)))
                chunks.append(bytes(data))
        finally:
            os.close(handle)
    return regions, b"".join(chunks)


class Memory:
    def __init__(self, regions: list[tuple[int, int]], blob: bytes):
        self.regions = regions
        self.blob = blob
        self.offsets = []
        off = 0
        for start, size in regions:
            self.offsets.append(off)
            off += size
        self.words = np.frombuffer(blob[: len(blob) // 4 * 4], dtype="<u4")

    def addr_of(self, file_offset: int) -> int:
        for (start, size), base in zip(self.regions, self.offsets):
            if base <= file_offset < base + size:
                return start + file_offset - base
        raise ValueError(file_offset)

    def off_of(self, addr: int) -> int | None:
        for (start, size), base in zip(self.regions, self.offsets):
            if start <= addr < start + size:
                return base + addr - start
        return None

    def u32(self, addr: int) -> int | None:
        off = self.off_of(addr)
        if off is None or off + 4 > len(self.blob):
            return None
        return struct.unpack_from("<I", self.blob, off)[0]

    def i32s(self, addr: int, n: int) -> tuple | None:
        off = self.off_of(addr)
        if off is None or off + 4 * n > len(self.blob):
            return None
        return struct.unpack_from(f"<{n}i", self.blob, off)


def discover(args: argparse.Namespace) -> int:
    windows = json.loads(Path(args.catalog).read_text())
    # Ids that are unique in the catalog and have a non-degenerate area.
    counts = collections.Counter(w["id"] for w in windows if w["id"])
    probes = {w["id"]: w for w in windows if w["id"] and counts[w["id"]] == 1 and w["area"]
              and w["area"][2] > w["area"][0] and w["area"][3] > w["area"][1]}
    regions, blob = snapshot(args.pid, args.image_name)
    mem = Memory(regions, blob)
    ids = np.array(sorted(probes), dtype="<u4")
    hit_words = np.nonzero(np.isin(mem.words, ids))[0]
    print(f"snapshot {len(blob) >> 20} MiB, {len(probes)} probe ids, {len(hit_words)} aligned id hits")

    # For every hit, look for the window's design size nearby, as
    # (left, top, right, bottom) int32 or as width/height.
    rect_offsets = collections.Counter()
    found_ids = set()
    for w in hit_words:
        wid = int(mem.words[w])
        x1, y1, x2, y2 = probes[wid]["area"]
        width, height = x2 - x1, y2 - y1
        lo, hi = max(0, w - 64), min(len(mem.words) - 4, w + 64)
        near = mem.words[lo:hi + 4].view("<i4")
        for k in range(hi - lo):
            a, b, c, d = (int(v) for v in near[k:k + 4])
            if c - a == width and d - b == height and width > 0:
                rect_offsets[("ltrb", (lo + k - w) * 4)] += 1
                found_ids.add(wid)
            if c == width and d == height and width > 0:
                rect_offsets[("xywh", (lo + k - w) * 4)] += 1
                found_ids.add(wid)
    print(f"ids with a matching rect nearby: {len(found_ids)}")
    for (kind, offset), count in rect_offsets.most_common(10):
        print(f"  rect {kind} at id{offset:+#x}: {count}")
    report = {"probe_ids": len(probes), "id_hits": int(len(hit_words)), "ids_with_rect": len(found_ids),
              "rect_offsets": [[k, int(o), int(c)] for (k, o), c in rect_offsets.most_common(20)]}
    out = sc4_dynamic.outside_repo(Path(args.out))
    out.write_text(json.dumps(report, indent=2))
    print(f"report: {out}")
    return 0


# Window object layout, discovered on the Steam executable (see docs):
#   +0x00 vtable  +0x10 id  +0x14 runtime rect (l,t,r,b; parent-relative)
#   +0x24 client rect (0,0,w,h)  +0x4C parent window  +0xB8 design rect (.UI)
#   +0xC8 window flags
OFF_ID, OFF_RECT, OFF_CLIENT, OFF_PARENT, OFF_DESIGN, OFF_FLAGS = 0x10, 0x14, 0x24, 0x4C, 0xB8, 0xC8


def find_windows(mem: Memory, by_id: dict[int, dict[str, Any]]) -> list[int]:
    """Window objects: rect + matching (0,0,w,h) client rect + the framework
    pointer pair at +0x04/+0x08. The pair is learned from objects whose id
    and size both match the .UI catalog, so data tables cannot impersonate it."""
    w = mem.words.view("<i4")
    u = mem.words
    b = np.arange(0, len(w) - 60)
    L, T, R, B = w[b + 5], w[b + 6], w[b + 7], w[b + 8]
    ok = (R >= L) & (B >= T) & (w[b + 9] == 0) & (w[b + 10] == 0) & (w[b + 11] == R - L) & (w[b + 12] == B - T)
    ok &= (u[b + 3] < 64) & (u[b] >= 0x400000) & (u[b] < 0x1000000)
    idx = np.nonzero(ok)[0]
    pairs = collections.Counter()
    for i in idx:
        entry = by_id.get(int(u[i + 4]))
        if entry and entry["area"]:
            x1, y1, x2, y2 = entry["area"]
            if int(w[i + 11]) == x2 - x1 and int(w[i + 12]) == y2 - y1:
                pairs[(int(u[i + 1]), int(u[i + 2]))] += 1
    if not pairs:
        return []
    pair = pairs.most_common(1)[0][0]
    keep = idx[(u[idx + 1] == pair[0]) & (u[idx + 2] == pair[1])]
    return [mem.addr_of(int(i) * 4) for i in keep]


def dump(args: argparse.Namespace) -> int:
    windows = json.loads(Path(args.catalog).read_text())
    by_id = {}
    for entry in windows:
        if entry["id"]:
            by_id.setdefault(entry["id"], entry)
    regions, blob = snapshot(args.pid, args.image_name)
    mem = Memory(regions, blob)
    bases = find_windows(mem, by_id)
    baseset = set(bases)
    nodes = {}
    for a in bases:
        wid = mem.u32(a + OFF_ID)
        if wid is None or mem.i32s(a + OFF_DESIGN, 4) is None or mem.u32(a + OFF_FLAGS) is None:
            continue
        node = {
            "addr": f"{a:#x}", "vtable": f"{mem.u32(a):#x}", "id": f"{wid:#010x}",
            "rect": list(mem.i32s(a + OFF_RECT, 4)), "design": list(mem.i32s(a + OFF_DESIGN, 4)),
            "flags": f"{mem.u32(a + OFF_FLAGS):#010x}", "children": [],
        }
        parent = mem.u32(a + OFF_PARENT)
        node["parent"] = parent if parent in baseset else None
        if wid in by_id:
            node["catalog"] = {k: by_id[wid][k] for k in ("ui_file", "clsid", "area")}
        nodes[a] = node
    roots = []
    for a, node in nodes.items():
        if node["parent"] in nodes:
            nodes[node["parent"]]["children"].append(node)
        else:
            roots.append(node)
    for node in nodes.values():
        node["children"].sort(key=lambda n: int(n["addr"], 16))
        node["parent"] = f"{node['parent']:#x}" if node["parent"] in nodes else None
    screen = max(((n["rect"][2], n["rect"][3]) for n in roots), default=(0, 0))
    result = {"schema": "opensc4.sc4-live-ui.v1", "window_count": len(nodes), "screen": screen, "roots": roots}
    out = sc4_dynamic.outside_repo(Path(args.out))
    out.write_text(json.dumps(result, indent=1))
    vt = collections.Counter(n["vtable"] for n in nodes.values())
    print(f"{len(nodes)} windows, {len(roots)} root(s), screen {screen}, vtables {dict(vt.most_common(6))}")
    print(f"tree -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image-name", default="SimCity 4.exe")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("catalog")
    c.add_argument("--game-dir", type=Path, required=True)
    c.add_argument("--out", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--pid", type=int, required=True)
    d.add_argument("--catalog", required=True)
    d.add_argument("--out", required=True)
    u = sub.add_parser("dump")
    u.add_argument("--pid", type=int, required=True)
    u.add_argument("--catalog", required=True)
    u.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.command == "dump":
        return dump(args)
    if args.command == "catalog":
        windows = catalog(args.game_dir)
        out = sc4_dynamic.outside_repo(Path(args.out))
        out.write_text(json.dumps(windows))
        print(f"{len(windows)} windows -> {out}")
        return 0
    return discover(args)


if __name__ == "__main__":
    raise SystemExit(main())
