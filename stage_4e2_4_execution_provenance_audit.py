"""Certify broker execution-price provenance without claiming quote replication."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_REASONS = {"DEAL_REASON_MOBILE", "DEAL_REASON_SL", "DEAL_REASON_SO"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tick-manifest", required=True, type=Path)
    parser.add_argument("--raw-deals", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def flatten(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("raw deal evidence must be an array")
    result: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        records = item.get("Records")
        if isinstance(records, list):
            result.extend(record for record in records if isinstance(record, dict))
        elif "record_id" in item:
            result.append(item)
    return result


def reason_context(reason: str) -> str:
    return {
        "DEAL_REASON_MOBILE": "FOUNDER_INITIATED_MARKET_EXECUTION",
        "DEAL_REASON_SL": "PROTECTIVE_STOP_EXECUTION",
        "DEAL_REASON_SO": "BROKER_STOP_OUT_EXECUTION",
    }[reason]


def reconcile(tick_manifest: dict[str, Any], raw_payload: Any) -> dict[str, Any]:
    events = tick_manifest.get("events")
    if tick_manifest.get("stage") != "4E.2.3" or not isinstance(events, list):
        raise ValueError("tick manifest is not valid Stage 4E.2.3 evidence")
    raw = flatten(raw_payload)
    wanted = {item.get("sourceRecordId") for item in events}
    matches: dict[str, list[dict[str, Any]]] = {record_id: [] for record_id in wanted}
    for item in raw:
        if item.get("record_id") in matches:
            matches[item["record_id"]].append(item)
    bad = {key: len(value) for key, value in matches.items() if len(value) != 1}
    if bad:
        raise ValueError(f"raw deal cardinality failure: {bad}")

    reconciled: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for event in events:
        record_id = event["sourceRecordId"]
        deal = matches[record_id][0]
        reason = deal.get("reason")
        reasons[str(reason)] += 1
        checks = {
            "recordId": deal.get("record_id") == record_id,
            "symbol": deal.get("symbol") == event.get("symbol"),
            "dealType": deal.get("type") == event.get("dealType"),
            "executionPrice": (
                isinstance(deal.get("price"), (int, float))
                and math.isfinite(float(deal["price"]))
                and float(deal["price"]) == float(event.get("executionPrice"))
            ),
            "recognizedExecutionReason": reason in ALLOWED_REASONS,
            "tickEvidenceAvailable": event.get("evidenceAvailable") is True,
            "nearestTickWithinTwoSeconds": (
                event.get("nearestTickDistanceMilliseconds") is not None
                and float(event["nearestTickDistanceMilliseconds"]) <= 2000
            ),
        }
        passed = all(checks.values())
        item = {
            "sourceRecordId": record_id,
            "dealId": str(deal.get("id")),
            "positionId": str(deal.get("positionId")),
            "symbol": deal.get("symbol"),
            "entryType": deal.get("entryType"),
            "dealType": deal.get("type"),
            "executionReason": reason,
            "executionContext": reason_context(reason) if reason in ALLOWED_REASONS else "UNKNOWN",
            "executionPrice": float(deal["price"]) if isinstance(deal.get("price"), (int, float)) else None,
            "eventUTC": event.get("eventUTC"),
            "nearestTickUTC": event.get("nearestTickUTC"),
            "nearestSidePrice": event.get("nearestSidePrice"),
            "nearestTickDistanceMilliseconds": event.get("nearestTickDistanceMilliseconds"),
            "nearestDeviationPoints": event.get("nearestDeviationPoints"),
            "minimumWindowDeviationPoints": event.get("minimumWindowDeviationPoints"),
            "checks": checks,
            "provenanceReconciled": passed,
            "quoteReplicationAsserted": False,
        }
        reconciled.append(item)
        if not passed:
            failures.append({"sourceRecordId": record_id, "failedChecks": [key for key, value in checks.items() if not value]})
    return {
        "events": reconciled,
        "failures": failures,
        "reasonCounts": dict(sorted(reasons.items())),
        "counts": {
            "events": len(events),
            "provenanceReconciled": sum(item["provenanceReconciled"] for item in reconciled),
            "unresolved": len(failures),
        },
    }


def main() -> int:
    args = parse_args()
    tick_manifest = load(args.tick_manifest)
    result = reconcile(tick_manifest, load(args.raw_deals))
    certified = result["counts"]["events"] == 52 and result["counts"]["provenanceReconciled"] == 52
    status = "EXECUTION_PRICE_PROVENANCE_CERTIFIED_QUOTE_REPLICATION_NOT_ASSERTED" if certified else "EXECUTION_PRICE_PROVENANCE_REVIEW_REQUIRED"
    common = {
        "schemaVersion": "1.0.0",
        "stage": "4E.2.4",
        "generatedAtUTC": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": status,
        "certificationScope": "Broker-deal execution-price identity and side-aware market-context provenance",
        "counts": result["counts"],
        "executionReasonCounts": result["reasonCounts"],
        "gates": {
            "brokerDealIdentity": certified,
            "executionPriceProvenance": certified,
            "sideAwareTickContextAvailable": certified,
            "exactHistoricalQuoteReplication": False,
        },
        "authorization": {
            "technicalFeatureCalculation": False,
            "strategyFormulation": False,
            "paperTrading": False,
            "liveTrading": False,
            "orderPlacement": False,
        },
        "provenance": {
            "tickManifestFile": args.tick_manifest.name,
            "tickManifestSha256": sha256(args.tick_manifest),
            "rawDealFile": args.raw_deals.name,
            "rawDealSha256": sha256(args.raw_deals),
        },
        "limitations": [
            "Execution prices are certified as identical to the preserved broker deal records, not as exact reproductions of public historical quote ticks.",
            "Broker fill mechanics, execution latency, slippage, markups, stop-loss gaps, and stop-out calculations are not reconstructed by this stage.",
            "No strategy or trading authorization is created.",
        ],
    }
    report = {**common, "events": result["events"], "failures": result["failures"]}
    certification = {
        **common,
        "certified": certified,
        "executionPriceProvenanceCertified": certified,
        "exactHistoricalQuoteReplicationCertified": False,
        "decision": "Broker execution-price provenance certified; exact quote replication is outside the certified scope." if certified else "Broker execution-price provenance requires review.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "wealthbuilder_execution_provenance_report_4e2_4_v1.json": report,
        "wealthbuilder_execution_provenance_certification_4e2_4_v1.json": certification,
    }
    for name, payload in outputs.items():
        path = args.output_dir / name
        if path.exists():
            raise FileExistsError(f"refusing to overwrite evidence: {path}")
        temporary = path.with_suffix(".json.partial")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    print(json.dumps({"stage": "4E.2.4", "status": status, "certified": certified, "counts": result["counts"], "outputs": sorted(outputs)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
