import csv
import json

import pytest

from wealthbuilder_certification.ohlc import EXPECTED_COLUMNS, load_sources, read_bars, sha256


def _write_csv(path, symbol="TEST.mic", rows=None):
    rows = rows or [
        {
            "symbol": symbol, "time_utc": "2025-01-01T00:00:00Z", "time_epoch_utc": "1735689600",
            "open": "100", "high": "101", "low": "99", "close": "100.5",
            "tick_volume": "10", "spread": "2", "real_volume": "0",
        }
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(EXPECTED_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def test_read_bars_recomputes_integrity_facts(tmp_path):
    path = tmp_path / "bars.csv"
    _write_csv(path)
    bars, facts = read_bars(path, "TEST.mic")
    assert len(bars) == 1
    assert facts["sha256"] == sha256(path)
    assert facts["strictlyAscending"] is True
    assert facts["ohlcViolationCount"] == 0


@pytest.mark.parametrize(
    "change,match",
    [
        ({"time_utc": "2025-01-01T00:01:00Z"}, "timestamp disagrees"),
        ({"high": "98"}, "OHLC invariants"),
        ({"open": "nan"}, "non-finite"),
        ({"spread": "-1"}, "negative"),
    ],
)
def test_invalid_bar_data_fails_closed(tmp_path, change, match):
    row = {
        "symbol": "TEST.mic", "time_utc": "2025-01-01T00:00:00Z", "time_epoch_utc": "1735689600",
        "open": "100", "high": "101", "low": "99", "close": "100.5",
        "tick_volume": "10", "spread": "2", "real_volume": "0",
    }
    row.update(change)
    path = tmp_path / "bad.csv"
    _write_csv(path, rows=[row])
    with pytest.raises(ValueError, match=match):
        read_bars(path, "TEST.mic")


def test_duplicate_or_unsorted_epochs_fail_closed(tmp_path):
    base = {
        "symbol": "TEST.mic", "open": "100", "high": "101", "low": "99", "close": "100",
        "tick_volume": "1", "spread": "1", "real_volume": "0",
    }
    duplicate = [
        {**base, "time_utc": "2025-01-01T00:00:00Z", "time_epoch_utc": "1735689600"},
        {**base, "time_utc": "2025-01-01T00:00:00Z", "time_epoch_utc": "1735689600"},
    ]
    path = tmp_path / "duplicate.csv"
    _write_csv(path, rows=duplicate)
    with pytest.raises(ValueError, match="duplicate"):
        read_bars(path, "TEST.mic")


def test_manifest_hash_or_count_mismatch_fails_closed(tmp_path):
    exports = []
    for timeframe in ("M5", "M15", "H1", "H4"):
        path = tmp_path / f"TEST_{timeframe}.csv"
        _write_csv(path)
        exports.append({"symbol": "TEST.mic", "timeframe": timeframe, "file": path.name, "sha256": sha256(path), "barCount": 1})
    exports[0]["sha256"] = "tampered"
    (tmp_path / "mt5_ohlc_export_manifest_4e2_v1.json").write_text(
        json.dumps({"exports": exports, "source": {"server": "test"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="provenance mismatch"):
        load_sources(tmp_path, {"TEST.mic"})
