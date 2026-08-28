from datetime import timezone

import pytest

from wealthbuilder_certification.timestamps import (
    canonicalize_deal_timestamp,
    parse_aware_utc,
    parse_broker_wall,
)


def test_canonicalization_preserves_both_sources_and_uses_per_deal_broker_coordinate():
    evidence = canonicalize_deal_timestamp(
        {"time": "2025-05-28T22:49:49.400Z", "brokerTime": "2025-05-28 23:49:49.400"}
    )
    result = evidence.as_dict()
    assert result["sourceTime"] == "2025-05-28T22:49:49.400Z"
    assert result["brokerTime"] == "2025-05-28 23:49:49.400"
    assert result["canonicalTimeUTC"] == "2025-05-28T23:49:49.400Z"
    assert result["observedBrokerMinusSourceMinutes"] == 60
    assert result["timezoneClaim"] is False


@pytest.mark.parametrize(
    ("source", "broker", "offset"),
    [
        ("2025-07-22T09:00:00Z", "2025-07-22 10:00:00.000", 60),
        ("2026-03-09T09:00:00Z", "2026-03-09 09:00:00.000", 0),
        ("2026-04-01T09:00:00Z", "2026-04-01 10:00:00.000", 60),
    ],
)
def test_offset_is_derived_independently_across_date_boundaries(source, broker, offset):
    evidence = canonicalize_deal_timestamp({"time": source, "brokerTime": broker})
    assert evidence.observed_broker_minus_source_minutes == offset


@pytest.mark.parametrize("value", [None, "", "2025-01-01 00:00:00", "not-a-time"])
def test_source_time_must_be_valid_and_timezone_aware(value):
    with pytest.raises(ValueError):
        parse_aware_utc(value, "time")


@pytest.mark.parametrize("value", ["2025-01-01T00:00:00Z", "2025-01-01 00:00:00+02:00", "bad"])
def test_broker_time_must_be_timezone_naive(value):
    with pytest.raises(ValueError):
        parse_broker_wall(value)


def test_unreviewed_offset_fails_closed():
    with pytest.raises(ValueError, match="unapproved"):
        canonicalize_deal_timestamp(
            {"time": "2025-01-01T00:00:00Z", "brokerTime": "2025-01-01 02:00:00.000"}
        )


def test_aware_timestamp_is_normalized_to_utc():
    parsed = parse_aware_utc("2025-01-01T02:00:00+02:00", "time")
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 0

