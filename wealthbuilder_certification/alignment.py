"""Canonical timestamp-to-candle alignment for Stage 4E.2.2."""

from __future__ import annotations

import bisect
import math
from collections import Counter
from datetime import datetime
from typing import Any

from .ohlc import Bar, BarSeries, REQUIRED_TIMEFRAMES, TIMEFRAME_SECONDS
from .timestamps import canonicalize_deal_timestamp, iso_utc, parse_aware_utc


EXPECTED_TRADES = 85
EXPECTED_LINKED_DEALS = 170
EXPECTED_CHECKS = 680


def ledger_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = next((payload.get(key) for key in ("trades", "records", "data") if isinstance(payload.get(key), list)), None)
    else:
        records = None
    if not isinstance(records, list) or not records or not all(isinstance(item, dict) for item in records):
        raise ValueError("ledger must be a non-empty JSON record array")
    return records


def flatten_raw_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("raw deal evidence must be a JSON array")
    flattened: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        nested = item.get("Records")
        if isinstance(nested, list):
            flattened.extend(record for record in nested if isinstance(record, dict))
        elif "record_id" in item:
            flattened.append(item)
    return flattened


def linked_deal_map(records: list[dict[str, Any]], ledger: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    linked_ids = [record.get(field) for record in ledger for field in ("EntryRecordId", "ExitRecordId")]
    if any(not isinstance(item, str) or not item for item in linked_ids):
        raise ValueError("every ledger endpoint must have a non-empty source record ID")
    if len(linked_ids) != len(set(linked_ids)):
        raise ValueError("ledger source record IDs are not unique")
    wanted = set(linked_ids)
    matches: dict[str, list[dict[str, Any]]] = {item: [] for item in wanted}
    for record in records:
        record_id = record.get("record_id")
        if record_id in matches:
            matches[record_id].append(record)
    bad = {key: len(value) for key, value in matches.items() if len(value) != 1}
    if bad:
        raise ValueError(f"linked source deal cardinality failure: {bad}")
    return {key: value[0] for key, value in matches.items()}


def _containing_bar(series: BarSeries, event: datetime) -> Bar | None:
    event_epoch = event.timestamp()
    index = bisect.bisect_right(series.epochs, event_epoch) - 1
    if index < 0:
        return None
    bar = series.bars[index]
    return bar if bar.epoch <= event_epoch < bar.epoch + TIMEFRAME_SECONDS[series.timeframe] else None


def _validate_link(ledger: dict[str, Any], deal: dict[str, Any], endpoint: str) -> None:
    expected_entry_type = "DEAL_ENTRY_IN" if endpoint == "entry" else "DEAL_ENTRY_OUT"
    deal_id_field = "EntryDealId" if endpoint == "entry" else "ExitDealId"
    ledger_time_field = "EntryTime" if endpoint == "entry" else "ExitTime"
    ledger_price_field = "EntryPrice" if endpoint == "entry" else "ExitPrice"
    comparisons = {
        "DealId": (str(ledger.get(deal_id_field)), str(deal.get("id"))),
        "PositionId": (str(ledger.get("PositionId")), str(deal.get("positionId"))),
        "Symbol": (ledger.get("Symbol"), deal.get("symbol")),
        "EntryType": (expected_entry_type, deal.get("entryType")),
    }
    mismatches = [name for name, pair in comparisons.items() if pair[0] != pair[1]]
    if mismatches:
        raise ValueError(f"{endpoint} source deal disagrees with ledger fields: {mismatches}")
    ledger_time = parse_aware_utc(ledger.get(ledger_time_field), ledger_time_field)
    source_time = parse_aware_utc(deal.get("time"), "time")
    if ledger_time != source_time:
        raise ValueError(f"{endpoint} source time disagrees with ledger time")
    try:
        ledger_price = float(ledger.get(ledger_price_field))
        source_price = float(deal.get("price"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{endpoint} price is not numeric") from exc
    if not math.isfinite(ledger_price) or not math.isfinite(source_price) or ledger_price != source_price:
        raise ValueError(f"{endpoint} source price disagrees with ledger price")


def align(
    ledger: list[dict[str, Any]],
    raw_records: list[dict[str, Any]],
    sources: dict[tuple[str, str], BarSeries],
) -> dict[str, Any]:
    deals = linked_deal_map(raw_records, ledger)
    checks: list[dict[str, Any]] = []
    aligned_records: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    offsets: Counter[int] = Counter()

    for record_index, trade in enumerate(ledger):
        endpoint_evidence: dict[str, Any] = {}
        record_checks: list[dict[str, Any]] = []
        record_failures: list[str] = []
        for endpoint, record_field, time_field, price_field in (
            ("entry", "EntryRecordId", "EntryTime", "EntryPrice"),
            ("exit", "ExitRecordId", "ExitTime", "ExitPrice"),
        ):
            deal = deals[trade[record_field]]
            _validate_link(trade, deal, endpoint)
            timestamp = canonicalize_deal_timestamp(deal)
            offsets[timestamp.observed_broker_minus_source_minutes] += 1
            endpoint_evidence[endpoint] = {
                "sourceRecordId": trade[record_field],
                "sourceDealId": str(deal.get("id")),
                "sourceDealType": deal.get("type"),
                "price": float(trade[price_field]),
                "timestampEvidence": timestamp.as_dict(),
            }
            for timeframe in REQUIRED_TIMEFRAMES:
                series = sources[(trade["Symbol"], timeframe)]
                bar = _containing_bar(series, timestamp.canonical_utc)
                timestamp_aligned = bar is not None
                strict_price_contained = bool(
                    bar is not None and bar.low <= float(trade[price_field]) <= bar.high
                )
                reason = "ALIGNED"
                if bar is None:
                    reason = "NO_CONTAINING_CANDLE"
                    record_failures.append(f"{endpoint}:{timeframe}:NO_CONTAINING_CANDLE")
                elif not strict_price_contained:
                    reason = "PRICE_OUTSIDE_BID_OHLC_DIAGNOSTIC"
                check = {
                    "recordIndex": record_index,
                    "positionId": str(trade.get("PositionId")),
                    "endpoint": endpoint,
                    "timeframe": timeframe,
                    "symbol": trade["Symbol"],
                    "sourceRecordId": trade[record_field],
                    "canonicalEventUTC": iso_utc(timestamp.canonical_utc),
                    "canonicalEventEpoch": timestamp.canonical_utc.timestamp(),
                    "sourceFile": series.source_file,
                    "sourceSha256": series.source_hash,
                    "timestampAligned": timestamp_aligned,
                    "executionPrice": float(trade[price_field]),
                    "strictBidOhlcPriceContained": strict_price_contained,
                    "priceEvidenceStatus": "DIAGNOSTIC_ONLY_REQUIRES_BID_ASK_OR_TICK_EVIDENCE",
                    "reason": reason,
                    "candle": bar.compact() if bar else None,
                }
                checks.append(check)
                record_checks.append(check)
        entry_time = endpoint_evidence["entry"]["timestampEvidence"]["canonicalTimeUTC"]
        exit_time = endpoint_evidence["exit"]["timestampEvidence"]["canonicalTimeUTC"]
        if parse_aware_utc(exit_time, "canonical exit") < parse_aware_utc(entry_time, "canonical entry"):
            record_failures.append("CANONICAL_EXIT_BEFORE_ENTRY")
        aligned_record = {
            "recordIndex": record_index,
            "positionId": str(trade.get("PositionId")),
            "symbol": trade.get("Symbol"),
            "aligned": not record_failures,
            "endpoints": endpoint_evidence,
            "checkCount": len(record_checks),
            "timestampAlignedCheckCount": sum(item["timestampAligned"] for item in record_checks),
            "strictBidOhlcPriceContainedCount": sum(item["strictBidOhlcPriceContained"] for item in record_checks),
            "failures": record_failures,
        }
        aligned_records.append(aligned_record)
        if record_failures:
            unresolved.append({
                "recordIndex": record_index,
                "positionId": str(trade.get("PositionId")),
                "symbol": trade.get("Symbol"),
                "reasons": record_failures,
            })

    temporal_passed = sum(item["timestampAligned"] for item in checks)
    price_contained = sum(item["strictBidOhlcPriceContained"] for item in checks)
    return {
        "records": aligned_records,
        "checks": checks,
        "unresolvedRecords": unresolved,
        "counts": {
            "tradeRecords": len(ledger),
            "linkedDeals": len(deals),
            "checks": len(checks),
            "timestampAlignedChecks": temporal_passed,
            "timestampUnalignedChecks": len(checks) - temporal_passed,
            "strictBidOhlcPriceContainedChecks": price_contained,
            "strictBidOhlcPriceExceptionChecks": len(checks) - price_contained,
            "unresolvedRecords": len(unresolved),
        },
        "observedOffsetMinutes": {str(key): value for key, value in sorted(offsets.items())},
        "expectedCounts": {
            "tradeRecords": EXPECTED_TRADES,
            "linkedDeals": EXPECTED_LINKED_DEALS,
            "checks": EXPECTED_CHECKS,
        },
    }
