from __future__ import annotations

import datetime as dt

import pytest

from services import history_service


@pytest.fixture(autouse=True)
def connected_manager(monkeypatch):
    monkeypatch.setattr(history_service.connection_manager, "get_state", lambda: "CONNECTED")
    monkeypatch.setattr(history_service.connection_manager, "get_last_error", lambda: None)


def window():
    end = dt.datetime.now(dt.timezone.utc)
    return end - dt.timedelta(days=1), end


def set_history(monkeypatch, deals=None, orders=None):
    monkeypatch.setattr(history_service.connection_manager, "fetch_history_deals", lambda *args, **kwargs: deals)
    monkeypatch.setattr(history_service.connection_manager, "fetch_history_orders", lambda *args, **kwargs: orders)


@pytest.mark.parametrize("deals,orders", [([], []), (None, None)])
def test_empty_upstream_history_is_valid(monkeypatch, deals, orders):
    set_history(monkeypatch, deals, orders)
    assert history_service.get_history(*window()) == {"deals": [], "orders": []}


def test_records_are_normalized_without_losing_broker_fields(monkeypatch):
    set_history(
        monkeypatch,
        deals=[{"ticket": 100, "symbol": "EURUSD.a", "profit": 50, "time": 1_700_000_000, "broker_fact": "kept"}],
        orders=[{"ticket": 200, "symbol": "GBPUSD", "volume": 0.1, "time_setup": 1_700_000_100}],
    )
    result = history_service.get_history(*window())
    assert result["deals"][0]["ticket"] == 100
    assert result["deals"][0]["symbol"] == "EURUSD.a"
    assert result["deals"][0]["broker_fact"] == "kept"
    assert result["deals"][0]["record_id"]
    assert result["orders"][0]["ticket"] == 200
    assert result["orders"][0]["record_id"]


def test_invalid_entries_are_ignored_and_duplicates_removed(monkeypatch):
    deal = {"ticket": 1, "symbol": "EURUSD", "time": 1_700_000_000}
    set_history(monkeypatch, deals=["bad", 123, deal, dict(deal)], orders=[])
    result = history_service.get_history(*window())
    assert len(result["deals"]) == 1
    assert result["deals"][0]["ticket"] == 1


def test_limit_applies_across_both_collections(monkeypatch):
    set_history(
        monkeypatch,
        deals=[{"ticket": 1, "time": 100}, {"ticket": 2, "time": 300}],
        orders=[{"ticket": 3, "time_setup": 200}],
    )
    result = history_service.get_history(*window(), limit=2)
    assert len(result["deals"]) + len(result["orders"]) == 2


def test_disconnected_manager_is_rejected(monkeypatch):
    monkeypatch.setattr(history_service.connection_manager, "get_state", lambda: "FAILED")
    set_history(monkeypatch, [], [])
    with pytest.raises(RuntimeError, match="not connected"):
        history_service.get_history(*window())


@pytest.mark.parametrize("collection", ["deals", "orders"])
def test_upstream_failure_is_not_misreported_as_empty_history(monkeypatch, collection):
    def fail(*args, **kwargs):
        raise OSError("broker unavailable")

    set_history(monkeypatch, [], [])
    monkeypatch.setattr(history_service.connection_manager, f"fetch_history_{collection}", fail)
    with pytest.raises(RuntimeError, match=f"historical {collection}"):
        history_service.get_history(*window())


@pytest.mark.parametrize(
    "start,end,kwargs",
    [
        ("bad", dt.datetime.now(dt.timezone.utc), {}),
        (dt.datetime.now(dt.timezone.utc), "bad", {}),
        (dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc), {"ticket": 0}),
        (dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc), {"symbol": " "}),
    ],
)
def test_invalid_inputs_are_rejected(start, end, kwargs):
    with pytest.raises(ValueError):
        history_service.get_history(start, end, **kwargs)
