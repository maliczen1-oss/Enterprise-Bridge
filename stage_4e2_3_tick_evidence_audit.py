"""Validate and summarize Stage 4E.2.3 MT5 tick evidence offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def count_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"source_record_id", "time_msc", "bid", "ask", "point"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("tick CSV does not contain the required evidence columns")
        count = 0
        for row_number, row in enumerate(reader, 2):
            for field in ("bid", "ask", "point"):
                value = float(row[field])
                if not math.isfinite(value) or (field == "point" and value <= 0):
                    raise ValueError(f"tick CSV row {row_number} has invalid {field}")
            int(row["time_msc"])
            count += 1
    return count


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    if manifest.get("stage") != "4E.2.3" or manifest.get("mode") != "READ_ONLY":
        raise ValueError("manifest is not read-only Stage 4E.2.3 evidence")
    if manifest.get("tradingOperationsPerformed") is not False:
        raise ValueError("manifest does not affirm zero trading operations")
    tick_meta = manifest.get("tickFile", {})
    tick_path = args.manifest.parent / tick_meta.get("file", "")
    if not tick_path.is_file():
        raise ValueError("tick evidence CSV is missing")
    if sha256(tick_path) != tick_meta.get("sha256") or tick_path.stat().st_size != tick_meta.get("byteSize"):
        raise ValueError("tick evidence provenance check failed")
    row_count = count_rows(tick_path)
    if row_count != manifest.get("tickRowCount"):
        raise ValueError("tick evidence row count disagrees with manifest")
    events = manifest.get("events")
    if not isinstance(events, list) or len(events) != manifest.get("eventCount"):
        raise ValueError("event evidence count disagrees with manifest")
    if len({item.get("sourceRecordId") for item in events}) != len(events):
        raise ValueError("event evidence IDs are not unique")
    with_ticks = [item for item in events if item.get("evidenceAvailable")]
    without_ticks = [item for item in events if not item.get("evidenceAvailable")]
    within_two_seconds = [
        item for item in with_ticks
        if float(item.get("nearestTickDistanceMilliseconds")) <= 2000
    ]
    minimum_within_one_point = [
        item for item in with_ticks
        if float(item.get("minimumWindowDeviationPoints")) <= 1
    ]
    nearest_within_one_point = [
        item for item in with_ticks
        if float(item.get("nearestDeviationPoints")) <= 1
    ]
    unresolved = [
        {
            "sourceRecordId": item.get("sourceRecordId"),
            "symbol": item.get("symbol"),
            "eventUTC": item.get("eventUTC"),
            "nearestTickDistanceMilliseconds": item.get("nearestTickDistanceMilliseconds"),
            "nearestDeviationPoints": item.get("nearestDeviationPoints"),
            "minimumWindowDeviationPoints": item.get("minimumWindowDeviationPoints"),
            "reason": "NO_ONE_POINT_SIDE_PRICE_MATCH_AT_NEAREST_TICK",
        }
        for item in with_ticks
        if float(item.get("nearestDeviationPoints")) > 1
    ] + [
        {
            "sourceRecordId": item.get("sourceRecordId"),
            "symbol": item.get("symbol"),
            "eventUTC": item.get("eventUTC"),
            "reason": "NO_TICK_EVIDENCE_RETURNED",
        }
        for item in without_ticks
    ]
    exact_execution_certified = len(nearest_within_one_point) == len(events)
    status = "EXECUTION_PRICE_TICK_CERTIFIED" if exact_execution_certified else "TICK_EVIDENCE_ACQUIRED_EXECUTION_PRICE_REVIEW_REQUIRED"
    common: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "stage": "4E.2.3",
        "generatedAtUTC": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": status,
        "certificationScope": "Side-aware historical tick evidence for 52 unique Stage 4E.2.2 execution-price exceptions",
        "counts": {
            "events": len(events),
            "eventsWithTicks": len(with_ticks),
            "eventsWithoutTicks": len(without_ticks),
            "tickRows": row_count,
            "nearestTicksWithinTwoSeconds": len(within_two_seconds),
            "eventsWithOnePointMatchAnywhereInWindow": len(minimum_within_one_point),
            "eventsWithOnePointMatchAtNearestTick": len(nearest_within_one_point),
            "unresolvedEvents": len(unresolved),
        },
        "gates": {
            "tickFileIntegrity": True,
            "allEventsHaveTickEvidence": not without_ticks,
            "allNearestTicksWithinTwoSeconds": len(within_two_seconds) == len(events),
            "executionPriceTickMatch": exact_execution_certified,
        },
        "authorization": {
            "technicalFeatureCalculation": False,
            "strategyFormulation": False,
            "paperTrading": False,
            "liveTrading": False,
            "orderPlacement": False,
        },
        "limitations": [
            "Historical quote ticks prove market context but do not independently prove broker fill mechanics, slippage, latency, markups, or stop-out pricing.",
            "A quote elsewhere in the 60-second window is not treated as proof of the execution price at the event timestamp.",
            "No inferred tolerance is used to force certification.",
        ],
        "provenance": {
            "manifestFile": args.manifest.name,
            "manifestSha256": sha256(args.manifest),
            "tickFile": tick_path.name,
            "tickFileSha256": sha256(tick_path),
        },
    }
    report = {**common, "events": events, "unresolvedEvents": unresolved}
    certification = {
        **common,
        "certified": exact_execution_certified,
        "tickEvidenceAcquired": len(with_ticks) == len(events),
        "executionPriceTickCertified": exact_execution_certified,
        "decision": "Tick evidence acquired for all events; exact execution-price certification remains locked." if not exact_execution_certified else "Execution prices certified against side-aware historical ticks.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "wealthbuilder_tick_evidence_report_4e2_3_v1.json": report,
        "wealthbuilder_tick_evidence_certification_4e2_3_v1.json": certification,
    }
    for name, payload in outputs.items():
        path = args.output_dir / name
        if path.exists():
            raise FileExistsError(f"refusing to overwrite evidence: {path}")
        temporary = path.with_suffix(".json.partial")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    print(json.dumps({"stage": "4E.2.3", "status": status, "counts": common["counts"], "outputs": sorted(outputs)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
