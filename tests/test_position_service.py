import logging

import pytest

from services import position_service


@pytest.fixture(autouse=True)
def enable_logging(caplog):
    caplog.set_level(logging.DEBUG)
    yield


def test_empty_response_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: None,
    )

    result = position_service.get_positions()

    assert result == []


def test_empty_list_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: [],
    )

    result = position_service.get_positions()

    assert result == []


def test_non_dict_entries_are_skipped(monkeypatch):
    raw = [
        "bad-entry",
        123,
        None,
        {
            "ticket": 1,
            "symbol": "EURUSD",
            "volume": 0.10,
        },
    ]

    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: raw,
    )

    result = position_service.get_positions()

    assert len(result) == 1
    assert result[0]["ticket"] == 1
    assert result[0]["symbol"] == "EURUSD"


def test_alias_normalization(monkeypatch):
    raw = [
        {
            "position": 12345,
            "name": "GBPUSD",
            "lots": 0.25,
            "open_price": 1.2500,
            "current_price": 1.2550,
            "position_type": "BUY",
            "time_setup": 1234567890,
        }
    ]

    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: raw,
    )

    result = position_service.get_positions()

    assert len(result) == 1

    pos = result[0]

    assert pos["ticket"] == 12345
    assert pos["symbol"] == "GBPUSD"
    assert pos["volume"] == 0.25
    assert pos["price_open"] == 1.2500
    assert pos["price_current"] == 1.2550
    assert pos["type"] == "BUY"
    assert pos["time"] == 1234567890


def test_primary_fields_take_precedence(monkeypatch):
    raw = [
        {
            "ticket": 555,
            "position": 999,
            "symbol": "XAUUSD",
            "name": "SHOULD_NOT_USE",
            "volume": 1.0,
            "lots": 5.0,
            "price_open": 2400.0,
            "open_price": 1.0,
            "price": 2410.0,
            "current_price": 1.0,
            "type": "SELL",
            "position_type": "BUY",
            "time": 111,
            "time_setup": 222,
        }
    ]

    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: raw,
    )

    result = position_service.get_positions()

    pos = result[0]

    assert pos["ticket"] == 555
    assert pos["symbol"] == "XAUUSD"
    assert pos["volume"] == 1.0
    assert pos["price_open"] == 2400.0
    assert pos["price_current"] == 2410.0
    assert pos["type"] == "SELL"
    assert pos["time"] == 111


def test_missing_fields_are_handled(monkeypatch):
    raw = [
        {}
    ]

    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: raw,
    )

    result = position_service.get_positions()

    assert len(result) == 1

    pos = result[0]

    expected_keys = {
        "ticket",
        "symbol",
        "volume",
        "price_open",
        "price_current",
        "swap",
        "profit",
        "comment",
        "time",
        "type",
    }

    assert set(pos.keys()) == expected_keys

    assert pos["ticket"] is None
    assert pos["symbol"] is None


def test_connection_manager_exception_returns_empty_list(monkeypatch, caplog):
    def raise_error():
        raise RuntimeError("MT5 unavailable")

    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        raise_error,
    )

    result = position_service.get_positions()

    assert result == []

    assert "Failed to fetch positions" in caplog.text


def test_logging_when_skipping_bad_entries(monkeypatch, caplog):
    raw = [
        "invalid",
        {
            "ticket": 1,
            "symbol": "EURUSD",
        },
    ]

    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: raw,
    )

    result = position_service.get_positions()

    assert len(result) == 1

    assert "Skipping non-dict position entry" in caplog.text


def test_returned_schema(monkeypatch):
    raw = [
        {
            "ticket": 777,
            "symbol": "NAS100",
            "volume": 0.50,
            "price_open": 20000,
            "price": 20100,
            "swap": 0,
            "profit": 150,
            "comment": "test",
            "time": 999,
            "type": "BUY",
        }
    ]

    monkeypatch.setattr(
        position_service.connection_manager,
        "fetch_positions",
        lambda: raw,
    )

    result = position_service.get_positions()

    pos = result[0]

    assert set(pos.keys()) == {
        "ticket",
        "symbol",
        "volume",
        "price_open",
        "price_current",
        "swap",
        "profit",
        "comment",
        "time",
        "type",
    }
