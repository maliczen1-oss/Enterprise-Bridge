"""Evidence-backed timestamp normalization for Stage 4E.2.2.

MetaApi history records contain two different facts: ``time`` is an aware UTC
instant and ``brokerTime`` is a timezone-naive broker clock reading.  The MT5
OHLC exports used by this certification are keyed by raw MT5 epoch.  The
canonical event timestamp is therefore the broker clock's displayed wall time
projected onto the MT5 UTC-epoch axis.  This is a relabelling for comparison,
not an assertion that the broker clock itself is UTC.

Both source values and their observed relationship are retained in evidence.
No global offset is inferred or applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


BROKER_WALL_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_aware_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def parse_broker_wall(value: Any, field: str = "brokerTime") -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty broker wall-clock string")
    candidate = value.strip()
    if candidate.endswith("Z") or "+" in candidate[10:] or candidate.count("-") > 2:
        raise ValueError(f"{field} must be timezone-naive: {value!r}")
    for format_string in BROKER_WALL_FORMATS:
        try:
            return datetime.strptime(candidate, format_string)
        except ValueError:
            pass
    raise ValueError(f"{field} has an unsupported broker wall-clock format: {value!r}")


@dataclass(frozen=True)
class TimestampEvidence:
    source_time: str
    broker_time: str
    source_time_utc: datetime
    broker_wall: datetime
    canonical_utc: datetime
    observed_broker_minus_source_minutes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "sourceTime": self.source_time,
            "sourceTimeUTC": iso_utc(self.source_time_utc),
            "brokerTime": self.broker_time,
            "brokerTimeKind": "timezone-naive broker wall clock",
            "observedBrokerMinusSourceMinutes": self.observed_broker_minus_source_minutes,
            "canonicalTimeUTC": iso_utc(self.canonical_utc),
            "canonicalizationRule": "broker wall-clock components projected onto MT5 UTC-epoch axis",
            "timezoneClaim": False,
        }


def canonicalize_deal_timestamp(record: dict[str, Any]) -> TimestampEvidence:
    source_raw = record.get("time")
    broker_raw = record.get("brokerTime")
    source = parse_aware_utc(source_raw, "time")
    broker_wall = parse_broker_wall(broker_raw)
    canonical = broker_wall.replace(tzinfo=timezone.utc)
    delta_seconds = (canonical - source).total_seconds()
    if delta_seconds % 60:
        raise ValueError("brokerTime and time differ by a non-whole-minute offset")
    offset_minutes = int(delta_seconds // 60)
    # These are the only two relationships present in the linked 4E.2 source
    # corpus. Fail closed if a future input introduces an unreviewed basis.
    if offset_minutes not in (0, 60):
        raise ValueError(f"unapproved broker/source offset: {offset_minutes} minutes")
    return TimestampEvidence(
        source_time=str(source_raw),
        broker_time=str(broker_raw),
        source_time_utc=source,
        broker_wall=broker_wall,
        canonical_utc=canonical,
        observed_broker_minus_source_minutes=offset_minutes,
    )
