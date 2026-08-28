from datetime import datetime, timezone

import pytest

from wealthbuilder_certification.alignment import align, flatten_raw_records, linked_deal_map
from wealthbuilder_certification.ohlc import Bar, BarSeries, REQUIRED_TIMEFRAMES


def _corpus():
    ledger = []
    deals = []
    for index in range(85):
        entry_id = f"entry-{index}"
        exit_id = f"exit-{index}"
        position = str(1000 + index)
        hour = 10 if index % 2 else 9
        source_hour = hour - (index % 2)
        ledger.append(
            {
                "PositionId": position,
                "Symbol": "TEST.mic",
                "EntryDealId": str(2000 + index * 2),
                "ExitDealId": str(2001 + index * 2),
                "EntryRecordId": entry_id,
                "ExitRecordId": exit_id,
                "EntryTime": f"2025-01-01T{source_hour:02d}:01:00.000Z",
                "ExitTime": f"2025-01-01T{source_hour:02d}:02:00.000Z",
                "EntryPrice": 100.0,
                "ExitPrice": 100.0,
            }
        )
        for endpoint, record_id, deal_id, minute, entry_type in (
            ("entry", entry_id, 2000 + index * 2, 1, "DEAL_ENTRY_IN"),
            ("exit", exit_id, 2001 + index * 2, 2, "DEAL_ENTRY_OUT"),
        ):
            deals.append(
                {
                    "record_id": record_id,
                    "id": str(deal_id),
                    "positionId": position,
                    "symbol": "TEST.mic",
                    "entryType": entry_type,
                    "type": "DEAL_TYPE_BUY",
                    "time": f"2025-01-01T{source_hour:02d}:{minute:02d}:00.000Z",
                    "brokerTime": f"2025-01-01 {hour:02d}:{minute:02d}:00.000",
                    "price": 100.0,
                }
            )
    bars = (
        Bar(1735722000, "2025-01-01T09:00:00Z", 100, 101, 99, 100, 1, 1, 0),
        Bar(1735725600, "2025-01-01T10:00:00Z", 100, 101, 99, 100, 1, 1, 0),
    )
    sources = {
        ("TEST.mic", timeframe): BarSeries("TEST.mic", timeframe, f"test_{timeframe}.csv", timeframe, bars)
        for timeframe in REQUIRED_TIMEFRAMES
    }
    return ledger, deals, sources


def test_full_corpus_produces_exactly_680_independent_checks():
    ledger, deals, sources = _corpus()
    result = align(ledger, deals, sources)
    assert result["counts"] == {
        "tradeRecords": 85,
        "linkedDeals": 170,
        "checks": 680,
        "timestampAlignedChecks": 680,
        "timestampUnalignedChecks": 0,
        "strictBidOhlcPriceContainedChecks": 680,
        "strictBidOhlcPriceExceptionChecks": 0,
        "unresolvedRecords": 0,
    }
    assert result["observedOffsetMinutes"] == {"0": 86, "60": 84}
    assert all(record["checkCount"] == 8 for record in result["records"])


def test_candle_close_boundary_does_not_belong_to_previous_bar():
    ledger, deals, sources = _corpus()
    sources[("TEST.mic", "M5")] = BarSeries(
        "TEST.mic", "M5", "m5.csv", "hash",
        (Bar(1735722000, "2025-01-01T09:00:00Z", 100, 101, 99, 100, 1, 1, 0),),
    )
    result = align(ledger, deals, sources)
    assert result["counts"]["timestampUnalignedChecks"] > 0


def test_duplicate_or_missing_link_fails_closed():
    ledger, deals, _ = _corpus()
    with pytest.raises(ValueError, match="cardinality"):
        linked_deal_map(deals[:-1], ledger)
    with pytest.raises(ValueError, match="cardinality"):
        linked_deal_map(deals + [dict(deals[0])], ledger)


def test_source_deal_identity_mismatch_fails_closed():
    ledger, deals, sources = _corpus()
    deals[0]["symbol"] = "WRONG.mic"
    with pytest.raises(ValueError, match="disagrees"):
        align(ledger, deals, sources)


def test_flatten_raw_reconciliation_groups():
    assert flatten_raw_records([{"Records": [{"record_id": "a"}]}, {"record_id": "b"}]) == [
        {"record_id": "a"}, {"record_id": "b"}
    ]

