#!/usr/bin/env python3
"""Build a private, metadata-only SC4 distillation evidence pack.

This combines the exact target manifest with the bounded static candidate
ledger. It is deliberately an evidence organizer, not an extractor of raw
executable bytes, save files, memory, or proprietary assets. Generated packs
must remain outside the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import rea_target_manifest
import sc4_static_candidates


SCHEMA = "opensc4.sc4.evidence-pack.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


def classify(value: str) -> tuple[str, str, list[str]]:
    lower = value.lower()
    if value in {"g_funds", "g_population", "g_date"}:
        kind = {"g_funds": "treasury", "g_population": "population", "g_date": "simulation_date"}[value]
        return kind, "visible city aggregate candidate", ["controlled visible-value change", "save/reload", "second session"]
    if lower.startswith("g_power_"):
        return "power", "power statistics or simulator output candidate", ["one-plant city", "funding change", "second session"]
    if lower.startswith("g_water_"):
        return "water", "water statistics or simulator output candidate", ["one-source city", "funding change", "second session"]
    if lower.startswith("g_city_"):
        return "city_statistics", "city statistic or UI publication candidate", ["controlled population change", "save/reload", "second session"]
    if value in {"SimulationClock", "GetSimulationDate", "EnableSimulation"}:
        return "simulation_clock", "simulation control or date-path candidate", ["pause/run", "fixed-duration replay", "second session"]
    if value in {"LoadCity", "SaveCity", "SaveCityQuick"} or value.startswith("kCommandID_"):
        return "persistence", "save/load or command-path candidate", ["save before/after", "reload", "second session"]
    if value.startswith("cSC4"):
        return "manager_type", "named simulator/manager type candidate", ["static caller dossier", "runtime correlation"]
    if value.startswith("kMessage"):
        return "message_type", "simulation message candidate", ["controlled event", "runtime trace"]
    return "other", "named static candidate", ["static review", "runtime correlation"]


def lead_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    for candidate in candidates:
        kind, interpretation, checks = classify(candidate["value"])
        references = candidate.get("code_references", [])
        if candidate["value"] not in {"g_funds", "g_population", "g_date"} and not references:
            continue
        leads.append(
            {
                "value": candidate["value"],
                "virtual_address": candidate.get("virtual_address"),
                "file_offset": candidate.get("file_offset"),
                "section": candidate.get("section"),
                "static_reference_count": len(references),
                "static_references": references,
                "category": kind,
                "interpretation": interpretation,
                "status": "candidate_unverified",
                "verification_sequence": checks,
            }
        )
    return leads


def runtime_summary(snapshot: dict[str, Any], source: Path) -> dict[str, Any]:
    if snapshot.get("schema") != "sc4-lab.memory-snapshot.v1":
        raise ValueError("runtime snapshot has an unexpected schema")
    if snapshot.get("raw_bytes_recorded") is not False:
        raise ValueError("runtime snapshot is not metadata-only")
    process = snapshot.get("process")
    if not isinstance(process, dict) or "pid" not in process:
        raise ValueError("runtime snapshot has no process identity")
    return {
        "status": "captured_metadata_only",
        "snapshot_schema": snapshot["schema"],
        "source_artifact": source.name,
        "captured_utc": snapshot.get("captured_utc"),
        "pid": process["pid"],
        "command_basename": process.get("command_basename"),
        "region_count": len(snapshot.get("regions", [])),
        "raw_bytes_recorded": False,
        "verification_state": "process_identity_and_hashed_regions_captured; no city value verified",
    }


def build_pack(
    target: Path,
    provider: str,
    rea_evidence_ids: list[str],
    runtime_snapshot: tuple[Path, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target = target.expanduser().resolve()
    manifest = rea_target_manifest.build_manifest(target, provider)
    ledger = sc4_static_candidates.build(target, list(sc4_static_candidates.DEFAULT_PATTERNS))
    leads = lead_candidates(ledger["candidates"])
    runtime = {
        "status": "not_collected",
        "required_inputs": [
            "user-owned SC4 process under Wine",
            "small synthetic city with visible date and treasury",
            "before/after save metadata from tools/reference_capture.py",
            "read-only candidate scan from tools/memory_observatory.py",
        ],
        "verification_rule": "No candidate becomes verified from one correlation; repeat after reload and restart.",
    }
    if runtime_snapshot is not None:
        runtime = {
            **runtime,
            "status": "metadata_captured",
            "observation": runtime_summary(runtime_snapshot[1], runtime_snapshot[0]),
        }
    return {
        "schema": SCHEMA,
        "pack_kind": "local_sc4_distillation_evidence",
        "target_manifest": manifest,
        "static_ledger": {
            "schema": ledger["schema"],
            "candidate_count": len(ledger["candidates"]),
            "lead_count": len(leads),
            "method": ledger["method"],
            "leads": leads,
        },
        "rea": {
            "provider": provider,
            "evidence_ids": rea_evidence_ids,
            "native_status": "bounded_static_fallback",
            "limitations": [
                "REA/Ghidra native operations timed out on this legacy PE during the recorded run.",
                "Static strings and address references do not prove runtime execution or write authority.",
                "This pack contains no raw executable bytes, extracted resources, save files, or memory dumps.",
            ],
        },
        "runtime": runtime,
        "next_actions": [
            "Start SC4 with the exact target hash in target_manifest.",
            "Create a tiny city and record visible date and treasury.",
            "Scan one visible value at a time and preserve only candidate addresses and hashes.",
            "Save, change exactly one input, save again, and compare metadata.",
            "Promote a candidate only after reload and second-session confirmation.",
            "Use the verified observation to define an independently written OpenGlassBox rule.",
        ],
        "data_boundary": {
            "raw_bytes_written": False,
            "raw_memory_written": False,
            "save_files_written": False,
            "external_upload": False,
            "recommended_storage": "private local lab directory outside the Git repository",
        },
    }


def markdown(pack: dict[str, Any]) -> str:
    target = pack["target_manifest"]["target"]
    static = pack["static_ledger"]
    runtime = pack["runtime"]
    lines = [
        "# SC4 local evidence pack",
        "",
        "This report is a private local artifact. It records metadata, static",
        "candidate leads, and optional hashed runtime metadata; it is not a copy",
        "of SC4 data or proof of simulation equivalence.",
        "",
        f"- Target: `{target['basename']}`",
        f"- SHA-256: `{target['sha256']}`",
        f"- Architecture: `{target['pe']['architecture']}`",
        f"- Static candidates: `{static['candidate_count']}`",
        f"- Leads retained: `{static['lead_count']}`",
        f"- Runtime status: `{runtime['status']}`",
        "",
        "## Highest-value leads",
        "",
        "| Category | Name | VA | Static refs | Status |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for lead in static["leads"]:
        lines.append(
            f"| {lead['category']} | `{lead['value']}` | `{lead.get('virtual_address') or 'n/a'}` | "
            f"{lead['static_reference_count']} | {lead['status']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "A named string plus a static reference is a lead for controlled",
            "runtime observation. It does not identify a writable field, an",
            "authoritative aggregate, a function boundary, or an algorithm.",
            "",
            "## Next runtime gate",
            "",
            "Run the treasury/date/power sequence in `docs/runbooks/rea-sc4.md`,",
            "then attach only summarized observations and candidate addresses to",
            "the lab. Keep executable bytes, saves, raw memory, and extracted",
            "resources private and outside Git.",
            "",
        ]
    )
    return "\n".join(lines)


def safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return resolved
    raise ValueError("evidence packs must be written outside the Git repository")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--provider", default="ghidra")
    parser.add_argument("--rea-evidence-id", action="append", default=[])
    parser.add_argument("--runtime-snapshot", type=Path, help="optional metadata-only snapshot from memory_observatory.py")
    parser.add_argument("--out", required=True, type=Path, help="private JSON output outside the repository")
    parser.add_argument("--markdown-out", type=Path, help="optional private Markdown report outside the repository")
    args = parser.parse_args()
    try:
        output = safe_output(args.out)
        runtime_snapshot = None
        if args.runtime_snapshot:
            snapshot_path = args.runtime_snapshot.expanduser().resolve()
            runtime_snapshot = (snapshot_path, json.loads(snapshot_path.read_text(encoding="utf-8")))
        pack = build_pack(args.target, args.provider, args.rea_evidence_id, runtime_snapshot)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.markdown_out:
            report = safe_output(args.markdown_out)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(markdown(pack), encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"SC4 EVIDENCE PACK PASS: {output}")
    print(f"target_sha256={pack['target_manifest']['target']['sha256']}")
    print(f"static_candidates={pack['static_ledger']['candidate_count']}")
    print(f"leads={pack['static_ledger']['lead_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
