import csv

import pytest

from stage_4e2_3_mt5_tick_export import CSV_FIELDS, unique_events
from stage_4e2_3_tick_evidence_audit import count_rows


def test_unique_events_collapses_timeframe_duplicates():
    exception = {
        "sourceRecordId": "deal-a", "symbol": "XAUUSD.mic",
        "canonicalEventUTC": "2025-05-28T23:49:49.400Z",
    }
    gap = {"strictBidOhlcPriceDiagnosticExceptions": [exception, dict(exception)]}
    alignment = {
        "records": [{
            "symbol": "XAUUSD.mic",
            "endpoints": {
                "entry": {
                    "sourceRecordId": "deal-a", "sourceDealType": "DEAL_TYPE_BUY",
                    "price": 3286.15,
                    "timestampEvidence": {"canonicalTimeUTC": "2025-05-28T23:49:49.400Z"},
                }
            },
        }]
    }
    events = unique_events(gap, alignment)
    assert len(events) == 1
    assert events[0]["dealType"] == "DEAL_TYPE_BUY"


def test_missing_alignment_evidence_fails_closed():
    gap = {"strictBidOhlcPriceDiagnosticExceptions": [{"sourceRecordId": "missing"}]}
    with pytest.raises(ValueError, match="missing exception events"):
        unique_events(gap, {"records": []})


def test_tick_csv_validation_rejects_non_finite_quote(tmp_path):
    path = tmp_path / "ticks.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow({
            "source_record_id": "a", "symbol": "X", "event_utc": "2025-01-01T00:00:00Z",
            "execution_price": "1", "deal_type": "DEAL_TYPE_BUY", "point": "0.01",
            "time_msc": "1735689600000", "tick_utc": "2025-01-01T00:00:00Z",
            "bid": "nan", "ask": "1", "last": "0", "volume": "1", "flags": "1", "volume_real": "1",
        })
    with pytest.raises(ValueError, match="invalid bid"):
        count_rows(path)
