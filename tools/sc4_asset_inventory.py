#!/usr/bin/env python3
"""Inventory user-owned SC4 assets; optionally export original UI PNGs locally.

No game resources belong in the repository. Later archives override earlier TGIs,
matching Core.add_dbpf. The manifest records identifiers, dimensions and source
archives; layouts are parsed to associate button IDs with their original images.
"""
import argparse
import collections
import json
import re
import struct
from pathlib import Path
from dat_dump import DBPF

ARCHIVES = [f"SimCity_{n}.dat" for n in range(1, 6)] + ["EP1.dat"]
ATTR = re.compile(r'(\w+)=("[^"]*"|\([^)]*\)|\{[^}]*\}|[^\s>]+)')
GROUPS = {0x46A006B0: "ui", 0x22DEC92D: "tool_icons", 0x891B0E1A: "terrain", 0x1ABE787D: "network_and_model_textures", 0x0986135E: "lot_ground"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--export-ui", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if output == repo or repo in output.parents:
        parser.error("Choose a local output folder outside the source repository")
    output.mkdir(parents=True, exist_ok=True)
    resources, layouts = {}, {}
    for name in ARCHIVES:
        archive = DBPF(args.game_dir / name)
        for entry in archive.subfiles:
            category = GROUPS.get(entry.group_id)
            if category and entry.type_id in (0x856DDBAC, 0x7AB50E44):
                key = '-'.join(f'{n:08x}' for n in entry.tgi)
                item = dict(tgi=key, category=category, archive=name, bytes=entry.size)
                if entry.type_id == 0x856DDBAC:
                    raw = archive.raw_bytes(entry)
                    if raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) >= 24:
                        item['width'], item['height'] = struct.unpack_from('>II', raw, 16)
                        if args.export_ui and category in ('ui', 'tool_icons'):
                            (output / (key + '.png')).write_bytes(raw)
                resources[key] = item
            if entry.type_id == 0 and entry.group_id in (0x96A006B0, 0x08000600):
                key = '-'.join(f'{n:08x}' for n in entry.tgi)
                text = archive.raw_bytes(entry).decode('utf-8', errors='replace')
                buttons = []
                for tag in re.findall(r'<LEGACY\s.*?>', text, re.S):
                    attrs = {k: v.strip('"') for k, v in ATTR.findall(tag)}
                    if attrs.get('iid') == 'IGZWinBtn':
                        buttons.append({k: attrs[k] for k in ('id', 'area', 'image', 'style', 'tiptext') if k in attrs})
                layouts[key] = dict(archive=name, buttons=buttons)
    counts = dict(collections.Counter(item['category'] for item in resources.values()))
    manifest = dict(schema='opensc4.asset-inventory.v1', counts=counts,
                    resources=sorted(resources.values(), key=lambda r: r['tgi']), layouts=layouts)
    (output / 'inventory.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(counts=counts, layouts=len(layouts), manifest=str(output/'inventory.json'))))

if __name__ == '__main__':
    main()
