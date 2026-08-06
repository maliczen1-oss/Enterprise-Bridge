import logging

import pytest

from services import symbol_service


@pytest.fixture(autouse=True)
def enable_logging(caplog):
    caplog.set_level(logging.DEBUG)
    yield


def test_none_response_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: None,
    )

    result = symbol_service.get_symbols()

    assert result == []


def test_empty_list_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: [],
    )

    result = symbol_service.get_symbols()

    assert result == []


def test_non_dict_entries_are_skipped(monkeypatch):
    raw = [
        "bad-entry",
        123,
        None,
        {
            "name": "EURUSD",
            "digits": 5,
        },
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    assert len(result) == 1
    assert result[0]["name"] == "EURUSD"


def test_alias_normalization(monkeypatch):
    raw = [
        {
            "symbol": "NAS100",
            "trade": "FULL",
            "lot_size": 1,
            "currency_base": "USD",
            "digits": 2,
            "point": 0.01,
            "spread": 15,
        }
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    assert len(result) == 1

    sym = result[0]

    assert sym["name"] == "NAS100"
    assert sym["trade_mode"] == "FULL"
    assert sym["contract_size"] == 1
    assert sym["currency"] == "USD"
    assert sym["digits"] == 2
    assert sym["point"] == 0.01
    assert sym["spread"] == 15


def test_primary_fields_take_precedence(monkeypatch):
    raw = [
        {
            "name": "XAUUSD",
            "symbol": "SHOULD_NOT_USE",
            "trade_mode": "MARKET",
            "trade": "LIMITED",
            "contract_size": 100,
            "lot_size": 1,
            "currency": "USD",
            "currency_base": "EUR",
            "digits": 2,
            "point": 0.01,
            "spread": 20,
            "visible": False,
        }
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    sym = result[0]

    assert sym["name"] == "XAUUSD"
    assert sym["trade_mode"] == "MARKET"
    assert sym["contract_size"] == 100
    assert sym["currency"] == "USD"
    assert sym["visible"] is False


def test_visible_defaults_true(monkeypatch):
    raw = [
        {
            "name": "EURUSD",
        }
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    assert result[0]["visible"] is True


def test_missing_fields_are_handled(monkeypatch):
    raw = [
        {}
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    sym = result[0]

    expected = {
        "name",
        "visible",
        "trade_mode",
        "digits",
        "point",
        "spread",
        "contract_size",
        "currency",
    }

    assert set(sym.keys()) == expected

    assert sym["name"] is None
    assert sym["trade_mode"] is None
    assert sym["currency"] is None


def test_connection_manager_exception_returns_empty_list(monkeypatch, caplog):
    def raise_error():
        raise RuntimeError("Broker unavailable")

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        raise_error,
    )

    result = symbol_service.get_symbols()

    assert result == []

    assert "Failed to fetch symbols" in caplog.text


def test_logging_when_skipping_bad_entries(monkeypatch, caplog):
    raw = [
        "bad-entry",
        {
            "name": "EURUSD",
        },
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    assert len(result) == 1

    assert "Skipping non-dict symbol entry" in caplog.text


def test_return_schema(monkeypatch):
    raw = [
        {
            "name": "GBPUSD",
            "visible": True,
            "trade_mode": "FULL",
            "digits": 5,
            "point": 0.00001,
            "spread": 12,
            "contract_size": 100000,
            "currency": "GBP",
        }
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    sym = result[0]

    assert set(sym.keys()) == {
        "name",
        "visible",
        "trade_mode",
        "digits",
        "point",
        "spread",
        "contract_size",
        "currency",
    }


def test_multiple_symbols(monkeypatch):
    raw = [
        {"name": "EURUSD"},
        {"name": "GBPUSD"},
        {"name": "USDJPY"},
    ]

    monkeypatch.setattr(
        symbol_service.connection_manager,
        "fetch_symbols",
        lambda: raw,
    )

    result = symbol_service.get_symbols()

    assert len(result) == 3
    assert result[0]["name"] == "EURUSD"
    assert result[1]["name"] == "GBPUSD"
    assert result[2]["name"] == "USDJPY"
