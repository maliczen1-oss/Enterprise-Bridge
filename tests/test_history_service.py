import datetime
import logging

import pytest

from services import history_service


@pytest.fixture(autouse=True)
def enable_logging(caplog):
    caplog.set_level(logging.DEBUG)
    yield


def now():
    return datetime.datetime.utcnow()


def test_empty_history(monkeypatch):
    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: [],
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: [],
    )

    result = history_service.get_history(now(), now())

    assert result == {
        "deals": [],
        "orders": [],
    }


def test_none_history(monkeypatch):
    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: None,
    )

    result = history_service.get_history(now(), now())

    assert result["deals"] == []
    assert result["orders"] == []


def test_deal_normalization(monkeypatch):
    deals = [
        {
            "ticket": 100,
            "symbol": "EURUSD",
            "profit": 50,
            "commission": -2,
            "swap": 1,
            "comment": "deal",
            "time_done": 12345,
        }
    ]

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: deals,
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: [],
    )

    result = history_service.get_history(now(), now())

    deal = result["deals"][0]

    assert deal["ticket"] == 100
    assert deal["symbol"] == "EURUSD"
    assert deal["profit"] == 50
    assert deal["commission"] == -2
    assert deal["swap"] == 1
    assert deal["comment"] == "deal"
    assert deal["close_time"] == 12345


def test_order_normalization(monkeypatch):
    orders = [
        {
            "ticket": 200,
            "symbol": "GBPUSD",
            "profit": 25,
            "commission": -1,
            "swap": 0,
            "comment": "order",
            "time": 98765,
        }
    ]

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: [],
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: orders,
    )

    result = history_service.get_history(now(), now())

    order = result["orders"][0]

    assert order["ticket"] == 200
    assert order["symbol"] == "GBPUSD"
    assert order["profit"] == 25
    assert order["commission"] == -1
    assert order["swap"] == 0
    assert order["comment"] == "order"
    assert order["close_time"] == 98765


def test_limit_is_applied(monkeypatch):
    deals = [
        {"ticket": 1},
        {"ticket": 2},
        {"ticket": 3},
    ]

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: deals,
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: [],
    )

    result = history_service.get_history(
        now(),
        now(),
        limit=2,
    )

    assert len(result["deals"]) == 2


def test_non_dict_entries(monkeypatch):
    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: [
            "bad",
            123,
            {"ticket": 1},
        ],
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: [],
    )

    result = history_service.get_history(now(), now())

    assert result["deals"][0] == {}
    assert result["deals"][1] == {}
    assert result["deals"][2]["ticket"] == 1


def test_missing_fields(monkeypatch):
    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: [
            {}
        ],
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: [],
    )

    result = history_service.get_history(now(), now())

    deal = result["deals"][0]

    expected = {
        "ticket",
        "symbol",
        "profit",
        "commission",
        "swap",
        "comment",
        "close_time",
    }

    assert set(deal.keys()) == expected


def test_deals_exception(monkeypatch, caplog):
    def raise_error(*args, **kwargs):
        raise RuntimeError("Boom")

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        raise_error,
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: [],
    )

    result = history_service.get_history(now(), now())

    assert result["deals"] == []
    assert "Failed to fetch history deals" in caplog.text


def test_orders_exception(monkeypatch, caplog):
    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: [],
    )

    def raise_error(*args, **kwargs):
        raise RuntimeError("Boom")

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        raise_error,
    )

    result = history_service.get_history(now(), now())

    assert result["orders"] == []
    assert "Failed to fetch history orders" in caplog.text


def test_return_schema(monkeypatch):
    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_deals",
        lambda *args, **kwargs: [],
    )

    monkeypatch.setattr(
        history_service.connection_manager,
        "fetch_history_orders",
        lambda *args, **kwargs: [],
    )

    result = history_service.get_history(now(), now())

    assert set(result.keys()) == {
        "deals",
        "orders",
    }
