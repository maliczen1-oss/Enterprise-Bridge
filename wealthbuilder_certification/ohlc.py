"""Strict loading and validation of Stage 4E.2 MT5 OHLC exports."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14_400}
REQUIRED_TIMEFRAMES = tuple(TIMEFRAME_SECONDS)
EXPECTED_COLUMNS = {
    "symbol", "time_utc", "time_epoch_utc", "open", "high", "low",
    "close", "tick_volume", "spread", "real_volume",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


@dataclass(frozen=True)
class Bar:
    epoch: int
    time_utc: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int

    def compact(self) -> dict[str, Any]:
        return {
            "timeUTC": self.time_utc,
            "timeEpochUTC": self.epoch,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tickVolume": self.tick_volume,
            "spread": self.spread,
            "realVolume": self.real_volume,
        }


@dataclass(frozen=True)
class BarSeries:
    symbol: str
    timeframe: str
    source_file: str
    source_hash: str
    bars: tuple[Bar, ...]

    @property
    def epochs(self) -> tuple[int, ...]:
        return tuple(item.epoch for item in self.bars)


def _finite_float(raw: str, path: Path, row: int, field: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path.name} row {row} has invalid {field}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{path.name} row {row} has non-finite {field}")
    return value


def read_bars(path: Path, expected_symbol: str) -> tuple[tuple[Bar, ...], dict[str, Any]]:
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or set(reader.fieldnames) != EXPECTED_COLUMNS:
            raise ValueError(f"{path.name} does not have the exact broker OHLC schema")
        for row_number, row in enumerate(reader, 2):
            if row["symbol"] != expected_symbol:
                raise ValueError(f"{path.name} row {row_number} has unexpected symbol {row['symbol']!r}")
            try:
                epoch = int(row["time_epoch_utc"])
                tick_volume = int(row["tick_volume"])
                spread = int(row["spread"])
                real_volume = int(row["real_volume"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path.name} row {row_number} has invalid integer data") from exc
            expected_time = datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            if row["time_utc"] != expected_time:
                raise ValueError(f"{path.name} row {row_number} timestamp disagrees with its UTC epoch")
            bar = Bar(
                epoch=epoch,
                time_utc=row["time_utc"],
                open=_finite_float(row["open"], path, row_number, "open"),
                high=_finite_float(row["high"], path, row_number, "high"),
                low=_finite_float(row["low"], path, row_number, "low"),
                close=_finite_float(row["close"], path, row_number, "close"),
                tick_volume=tick_volume,
                spread=spread,
                real_volume=real_volume,
            )
            if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.high < bar.low:
                raise ValueError(f"{path.name} row {row_number} violates OHLC invariants")
            if min(tick_volume, spread, real_volume) < 0:
                raise ValueError(f"{path.name} row {row_number} has negative volume or spread")
            bars.append(bar)
    if not bars:
        raise ValueError(f"{path.name} contains no bars")
    epochs = [bar.epoch for bar in bars]
    duplicates = sum(count - 1 for count in Counter(epochs).values() if count > 1)
    if duplicates:
        raise ValueError(f"{path.name} contains {duplicates} duplicate epochs")
    if any(right <= left for left, right in zip(epochs, epochs[1:])):
        raise ValueError(f"{path.name} epochs are not strictly ascending")
    return tuple(bars), {
        "sourceFile": path.name,
        "sha256": sha256(path),
        "byteSize": path.stat().st_size,
        "barCount": len(bars),
        "firstBarUTC": bars[0].time_utc,
        "lastBarUTC": bars[-1].time_utc,
        "strictlyAscending": True,
        "duplicateTimestampCount": 0,
        "ohlcViolationCount": 0,
    }


def load_sources(ohlc_dir: Path, ledger_symbols: set[str]) -> tuple[dict[tuple[str, str], BarSeries], dict[str, Any], dict[str, Any]]:
    manifest_path = ohlc_dir / "mt5_ohlc_export_manifest_4e2_v1.json"
    manifest = load_json(manifest_path)
    exports = manifest.get("exports") if isinstance(manifest, dict) else None
    if not isinstance(exports, list):
        raise ValueError("source manifest has no exports array")
    expected = {(symbol, timeframe) for symbol in ledger_symbols for timeframe in REQUIRED_TIMEFRAMES}
    actual: set[tuple[str, str]] = set()
    series: dict[tuple[str, str], BarSeries] = {}
    validation: dict[str, Any] = {}
    for item in exports:
        if not isinstance(item, dict):
            raise ValueError("source manifest contains a non-object export")
        key = (item.get("symbol"), item.get("timeframe"))
        file_name = item.get("file")
        if key in actual:
            raise ValueError(f"duplicate source metadata for {key}")
        if key not in expected or not isinstance(file_name, str):
            raise ValueError(f"unexpected or incomplete source metadata: {key}")
        actual.add(key)
        path = ohlc_dir / file_name
        bars, facts = read_bars(path, key[0])
        facts["sha256MatchesManifest"] = facts["sha256"] == item.get("sha256")
        facts["barCountMatchesManifest"] = facts["barCount"] == item.get("barCount")
        if not facts["sha256MatchesManifest"] or not facts["barCountMatchesManifest"]:
            raise ValueError(f"manifest provenance mismatch for {file_name}")
        series[key] = BarSeries(key[0], key[1], file_name, facts["sha256"], bars)
        validation[f"{key[0]}|{key[1]}"] = facts
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"OHLC source set mismatch; missing={missing}, extra={extra}")
    provenance = {
        "sourceManifest": manifest_path.name,
        "sourceManifestSha256": sha256(manifest_path),
        "sourceManifestByteSize": manifest_path.stat().st_size,
        "sourceServer": manifest.get("source", {}).get("server"),
        "sourceTimestampBasis": manifest.get("source", {}).get("timestampBasis"),
    }
    return series, validation, provenance
