#!/usr/bin/env python3
"""Create a metadata-only manifest for a local native analysis target.

The manifest contains provenance and PE header metadata, never a copy of the
target or its extracted strings/code.  Keep generated manifests outside the
repository (normally under /tmp or a private lab directory).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any


SCHEMA = "opensc4.rea.target.v1"
MACHINES = {
    0x014C: "x86",
    0x8664: "x86_64",
    0xAA64: "arm64",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pe_metadata(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError("target is not an MZ/PE executable")
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        stream.seek(pe_offset)
        header = stream.read(24)
        if len(header) != 24 or header[:4] != b"PE\0\0":
            raise ValueError("target has no valid PE signature")
        machine, sections, timestamp, _, _, optional_size, characteristics = struct.unpack(
            "<HHIIIHH", header[4:24]
        )
        optional = stream.read(optional_size)
        magic = struct.unpack_from("<H", optional, 0)[0] if len(optional) >= 2 else None
        return {
            "machine": f"0x{machine:04x}",
            "architecture": MACHINES.get(machine, "unknown"),
            "section_count": sections,
            "pe_timestamp": timestamp,
            "optional_header_magic": f"0x{magic:04x}" if magic is not None else None,
            "characteristics": f"0x{characteristics:04x}",
        }


def build_manifest(path: Path, provider: str) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    stat = path.stat()
    return {
        "schema": SCHEMA,
        "target": {
            "kind": "native_pe",
            "basename": path.name,
            "absolute_path": str(path),
            "size_bytes": stat.st_size,
            "sha256": sha256_file(path),
            "modified_ns": stat.st_mtime_ns,
            "pe": pe_metadata(path),
        },
        "analysis": {
            "provider": provider,
            "read_policy": "metadata_only_manifest; analysis_output_stays_local",
            "planned_queries": [
                "list functions and strings",
                "identify save/load and simulation update call paths",
                "trace one utility or city-statistic calculation",
            ],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path, help="local PE executable or DLL")
    parser.add_argument("--provider", default="not_configured", help="REA provider name")
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    parser.add_argument("--self-test", action="store_true", help="run a parser/hash self-test")
    return parser.parse_args()


def self_test() -> None:
    import tempfile

    dos = bytearray(64)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)
    pe = b"PE\0\0" + struct.pack("<HHIIIHH", 0x014C, 1, 0, 0, 0, 2, 0x0102)
    with tempfile.TemporaryDirectory(prefix="opensc4-rea-") as directory:
        path = Path(directory) / "synthetic.exe"
        path.write_bytes(bytes(dos) + pe + struct.pack("<H", 0x010B))
        manifest = build_manifest(path, "self-test")
        assert manifest["schema"] == SCHEMA
        assert manifest["target"]["pe"]["architecture"] == "x86"
        assert len(manifest["target"]["sha256"]) == 64
    print("REA TARGET MANIFEST SELF-TEST PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.target is None:
        print("target is required unless --self-test is used", file=sys.stderr)
        return 2
    try:
        manifest = build_manifest(args.target, args.provider)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().resolve().write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
