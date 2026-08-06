import logging

import pytest

from services import market_service


@pytest.fixture(autouse=True)
def enable_logging(caplog):
    caplog.set_level(logging.DEBUG)
    yield


def test_no_tick_and_no_info_returns_none(monkeypatch):
    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: None,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: None,
    )

    result = market_service.get_market("EURUSD")

    assert result is None


def test_tick_only(monkeypatch):
    tick = {
        "bid": 1.1000,
        "ask": 1.1002,
        "time": 123456789,
        "volume": 100,
    }

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: tick,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: None,
    )

    result = market_service.get_market("EURUSD")

    assert result["bid"] == 1.1000
    assert result["ask"] == 1.1002
    assert result["spread"] == pytest.approx(0.0002)
    assert result["volume"] == 100
    assert result["digits"] is None
    assert result["point"] is None


def test_info_only(monkeypatch):
    info = {
        "digits": 5,
        "point": 0.00001,
        "high": 1.2000,
        "low": 1.1000,
    }

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: None,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: info,
    )

    result = market_service.get_market("EURUSD")

    assert result["digits"] == 5
    assert result["point"] == 0.00001
    assert result["high"] == 1.2000
    assert result["low"] == 1.1000
    assert result["bid"] is None
    assert result["ask"] is None


def test_complete_market_data(monkeypatch):
    tick = {
        "bid": 1900.10,
        "ask": 1900.30,
        "time": 111,
        "volume": 250,
    }

    info = {
        "digits": 2,
        "point": 0.01,
        "high": 1920.00,
        "low": 1880.00,
    }

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: tick,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: info,
    )

    result = market_service.get_market("XAUUSD")

    assert result["bid"] == 1900.10
    assert result["ask"] == 1900.30
    assert result["spread"] == pytest.approx(0.20)
    assert result["digits"] == 2
    assert result["point"] == 0.01
    assert result["high"] == 1920.00
    assert result["low"] == 1880.00


def test_non_dict_tick_is_handled(monkeypatch):
    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: "bad-data",
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: {},
    )

    result = market_service.get_market("EURUSD")

    assert result["bid"] is None
    assert result["ask"] is None
    assert result["digits"] is None


def test_non_dict_info_is_handled(monkeypatch):
    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: {},
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: "bad-info",
    )

    result = market_service.get_market("EURUSD")

    assert result["digits"] is None
    assert result["point"] is None
    assert result["high"] is None
    assert result["low"] is None


def test_invalid_bid_ask_does_not_crash(monkeypatch):
    tick = {
        "bid": "abc",
        "ask": "xyz",
    }

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: tick,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: {},
    )

    result = market_service.get_market("EURUSD")

    assert result["spread"] is None


def test_connection_manager_exception_returns_none(monkeypatch, caplog):
    def raise_error(symbol):
        raise RuntimeError("Broker unavailable")

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        raise_error,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: {},
    )

    result = market_service.get_market("EURUSD")

    assert result is None
    assert "Failed to fetch market data" in caplog.text


def test_logging_when_data_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: None,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: None,
    )

    market_service.get_market("EURUSD")

    assert "Market data unavailable" in caplog.text


def test_return_schema(monkeypatch):
    tick = {
        "bid": 1,
        "ask": 2,
        "time": 3,
        "volume": 4,
    }

    info = {
        "digits": 5,
        "point": 6,
        "high": 7,
        "low": 8,
    }

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_tick",
        lambda symbol: tick,
    )

    monkeypatch.setattr(
        market_service.connection_manager,
        "fetch_symbol_info",
        lambda symbol: info,
    )

    result = market_service.get_market("EURUSD")

    assert set(result.keys()) == {
        "bid",
        "ask",
        "spread",
        "time",
        "digits",
        "point",
        "volume",
        "high",
        "low",
    }
