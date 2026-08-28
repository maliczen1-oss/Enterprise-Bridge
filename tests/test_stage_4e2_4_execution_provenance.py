import pytest

from stage_4e2_4_execution_provenance_audit import reconcile


def _evidence():
    event = {
        "sourceRecordId": "deal-a", "symbol": "XAUUSD.mic", "dealType": "DEAL_TYPE_BUY",
        "executionPrice": 100.5, "eventUTC": "2025-01-01T00:00:00Z",
        "nearestTickUTC": "2025-01-01T00:00:00Z", "nearestSidePrice": 100.4,
        "nearestTickDistanceMilliseconds": 100, "nearestDeviationPoints": 10,
        "minimumWindowDeviationPoints": 0, "evidenceAvailable": True,
    }
    deal = {
        "record_id": "deal-a", "id": "1", "positionId": "2", "symbol": "XAUUSD.mic",
        "entryType": "DEAL_ENTRY_IN", "type": "DEAL_TYPE_BUY", "price": 100.5,
        "reason": "DEAL_REASON_MOBILE",
    }
    return {"stage": "4E.2.3", "events": [event]}, [{"Records": [deal]}]


def test_certifies_broker_price_identity_without_claiming_quote_replication():
    manifest, raw = _evidence()
    result = reconcile(manifest, raw)
    assert result["counts"] == {"events": 1, "provenanceReconciled": 1, "unresolved": 0}
    assert result["events"][0]["quoteReplicationAsserted"] is False


def test_price_disagreement_is_reported_not_tolerated():
    manifest, raw = _evidence()
    raw[0]["Records"][0]["price"] = 100.6
    result = reconcile(manifest, raw)
    assert result["counts"]["unresolved"] == 1
    assert result["failures"][0]["failedChecks"] == ["executionPrice"]


def test_missing_or_duplicate_raw_deal_fails_closed():
    manifest, raw = _evidence()
    with pytest.raises(ValueError, match="cardinality"):
        reconcile(manifest, [])
    raw[0]["Records"].append(dict(raw[0]["Records"][0]))
    with pytest.raises(ValueError, match="cardinality"):
        reconcile(manifest, raw)
