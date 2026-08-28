"""Read-only MT5 tick acquisition for Stage 4E.2.3 price evidence.

The input is the Stage 4E.2.2 gap document. Only unique execution events whose
prices fell outside bid-only OHLC are queried. No order or trading API is used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import MetaTrader5 as mt5


WINDOW_SECONDS = 60
CSV_FIELDS = (
    "source_record_id", "symbol", "event_utc", "execution_price",
    "deal_type", "point", "time_msc", "tick_utc", "bid", "ask", "last",
    "volume", "flags", "volume_real",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gap", required=True, type=Path)
    parser.add_argument("--alignment", required=True, type=Path)
    parser.add_argument("--terminal-path", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--window-seconds", type=int, default=WINDOW_SECONDS)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timezone-naive event timestamp: {value!r}")
    return parsed.astimezone(timezone.utc)


def unique_events(gap: dict[str, Any], alignment: dict[str, Any]) -> list[dict[str, Any]]:
    exception_ids = {
        item.get("sourceRecordId")
        for item in gap.get("strictBidOhlcPriceDiagnosticExceptions", [])
        if isinstance(item, dict)
    }
    evidence: dict[str, dict[str, Any]] = {}
    for record in alignment.get("records", []):
        for endpoint in ("entry", "exit"):
            item = record.get("endpoints", {}).get(endpoint, {})
            record_id = item.get("sourceRecordId")
            if record_id not in exception_ids:
                continue
            timestamp = item.get("timestampEvidence", {}).get("canonicalTimeUTC")
            if not isinstance(timestamp, str):
                raise ValueError(f"missing canonical timestamp for {record_id}")
            event = {
                "sourceRecordId": record_id,
                "symbol": record.get("symbol"),
                "eventUTC": timestamp,
                "executionPrice": float(item.get("price")),
                "dealType": item.get("sourceDealType"),
            }
            if record_id in evidence and evidence[record_id] != event:
                raise ValueError(f"conflicting event evidence for {record_id}")
            evidence[record_id] = event
    missing = exception_ids - set(evidence)
    if missing:
        raise ValueError(f"alignment evidence is missing exception events: {sorted(missing)}")
    return sorted(evidence.values(), key=lambda item: (item["eventUTC"], item["sourceRecordId"]))


def tick_value(tick: Any, field: str) -> Any:
    value = tick[field]
    return value.item() if hasattr(value, "item") else value


def iso_from_msc(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    if args.window_seconds <= 0 or args.window_seconds > 300:
        raise ValueError("--window-seconds must be between 1 and 300")
    gap = load(args.gap)
    alignment = load(args.alignment)
    if gap.get("stage") != "4E.2.2" or alignment.get("stage") != "4E.2.2":
        raise ValueError("inputs must be Stage 4E.2.2 evidence")
    events = unique_events(gap, alignment)
    if not events:
        raise ValueError("there are no price-exception events to query")

    if not mt5.initialize(path=str(args.terminal_path), timeout=60_000):
        raise RuntimeError(f"unable to initialize MT5: {mt5.last_error()}")
    try:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is None or not terminal.connected or account is None:
            raise RuntimeError(f"MT5 is not connected: {mt5.last_error()}")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = args.output_dir / "wealthbuilder_tick_evidence_4e2_3_v1.csv"
        manifest_path = args.output_dir / "wealthbuilder_tick_evidence_manifest_4e2_3_v1.json"
        if csv_path.exists() or manifest_path.exists():
            raise FileExistsError("refusing to overwrite existing Stage 4E.2.3 evidence")
        partial = csv_path.with_suffix(".csv.partial")
        summaries: list[dict[str, Any]] = []
        with partial.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for event_index, event in enumerate(events, 1):
                print(
                    f"QUERY {event_index}/{len(events)} {event['symbol']} {event['eventUTC']}",
                    file=sys.stderr,
                    flush=True,
                )
                info = mt5.symbol_info(event["symbol"])
                if info is None:
                    raise RuntimeError(f"symbol unavailable: {event['symbol']}")
                event_time = parse_utc(event["eventUTC"])
                ticks = mt5.copy_ticks_range(
                    event["symbol"],
                    event_time - timedelta(seconds=args.window_seconds),
                    event_time + timedelta(seconds=args.window_seconds),
                    mt5.COPY_TICKS_ALL,
                )
                if ticks is None:
                    raise RuntimeError(f"tick query failed for {event['sourceRecordId']}: {mt5.last_error()}")
                event_msc = int(event_time.timestamp() * 1000)
                side = "ask" if event["dealType"] == "DEAL_TYPE_BUY" else "bid"
                nearest = None
                min_deviation_points = None
                for tick in ticks:
                    time_msc = int(tick_value(tick, "time_msc"))
                    side_price = float(tick_value(tick, side))
                    deviation = abs(side_price - event["executionPrice"]) / float(info.point)
                    if min_deviation_points is None or deviation < min_deviation_points:
                        min_deviation_points = deviation
                    distance = abs(time_msc - event_msc)
                    if nearest is None or distance < nearest[0]:
                        nearest = (distance, time_msc, side_price, deviation)
                    writer.writerow({
                        "source_record_id": event["sourceRecordId"],
                        "symbol": event["symbol"],
                        "event_utc": event["eventUTC"],
                        "execution_price": format(event["executionPrice"], ".12g"),
                        "deal_type": event["dealType"],
                        "point": format(float(info.point), ".12g"),
                        "time_msc": time_msc,
                        "tick_utc": iso_from_msc(time_msc),
                        "bid": format(float(tick_value(tick, "bid")), ".12g"),
                        "ask": format(float(tick_value(tick, "ask")), ".12g"),
                        "last": format(float(tick_value(tick, "last")), ".12g"),
                        "volume": int(tick_value(tick, "volume")),
                        "flags": int(tick_value(tick, "flags")),
                        "volume_real": format(float(tick_value(tick, "volume_real")), ".12g"),
                    })
                summaries.append({
                    **event,
                    "sideCompared": side,
                    "point": float(info.point),
                    "digits": int(info.digits),
                    "tickCount": len(ticks),
                    "nearestTickDistanceMilliseconds": nearest[0] if nearest else None,
                    "nearestTickUTC": iso_from_msc(nearest[1]) if nearest else None,
                    "nearestSidePrice": nearest[2] if nearest else None,
                    "nearestDeviationPoints": nearest[3] if nearest else None,
                    "minimumWindowDeviationPoints": min_deviation_points,
                    "evidenceAvailable": bool(len(ticks)),
                })
        partial.replace(csv_path)
        manifest = {
            "schemaVersion": "1.0.0",
            "stage": "4E.2.3",
            "mode": "READ_ONLY",
            "purpose": "Side-aware historical tick evidence for Stage 4E.2.2 bid-OHLC price exceptions",
            "brokerServer": account.server,
            "windowSecondsEachSide": args.window_seconds,
            "eventCount": len(events),
            "eventsWithTickEvidence": sum(item["evidenceAvailable"] for item in summaries),
            "eventsWithoutTickEvidence": sum(not item["evidenceAvailable"] for item in summaries),
            "tickRowCount": sum(item["tickCount"] for item in summaries),
            "source": {
                "gapFile": args.gap.name, "gapSha256": sha256(args.gap),
                "alignmentFile": args.alignment.name, "alignmentSha256": sha256(args.alignment),
            },
            "tickFile": {"file": csv_path.name, "sha256": sha256(csv_path), "byteSize": csv_path.stat().st_size},
            "events": summaries,
            "authorization": {
                "strategyFormulation": False, "paperTrading": False,
                "liveTrading": False, "orderPlacement": False,
            },
            "tradingOperationsPerformed": False,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "stage": "4E.2.3", "events": len(events),
            "withTicks": manifest["eventsWithTickEvidence"],
            "withoutTicks": manifest["eventsWithoutTickEvidence"],
            "tickRows": manifest["tickRowCount"],
            "outputs": [str(csv_path), str(manifest_path)],
        }))
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
