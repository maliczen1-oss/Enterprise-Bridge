"""
tests/test_account_service.py

Phase 3.3 Certification Test Suite

These tests exercise the REAL implementation in
services/account_service.py.

Only connection_manager.fetch_account() is mocked.
The production normalization logic is always executed.
"""

import logging

import pytest

from services import account_service


@pytest.fixture(autouse=True)
def enable_logging(caplog):
    caplog.set_level(logging.INFO)
    yield


def test_get_account_success(monkeypatch):
    """Normal MT5 payload is correctly normalized."""

    raw = {
        "login": 123456,
        "server": "Demo-Server",
        "company": "Vault Markets",
        "balance": 1000.50,
        "equity": 1015.25,
        "margin": 100.00,
        "margin_free": 915.25,
        "margin_level": 1015.0,
        "currency": "USD",
        "leverage": 500,
        "name": "John Smith",
    }

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: raw,
    )

    result = account_service.get_account()

    assert isinstance(result, dict)

    assert result["account"] == 123456
    assert result["server"] == "Demo-Server"
    assert result["broker"] == "Vault Markets"
    assert result["balance"] == 1000.50
    assert result["equity"] == 1015.25
    assert result["margin"] == 100.00
    assert result["free_margin"] == 915.25
    assert result["margin_level"] == 1015.0
    assert result["currency"] == "USD"
    assert result["leverage"] == 500
    assert result["account_name"] == "John Smith"


def test_login_id_alias(monkeypatch):
    """login_id should be accepted when login is absent."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: {
            "login_id": 987654,
        },
    )

    result = account_service.get_account()

    assert result["account"] == 987654


def test_margin_free_alias(monkeypatch):
    """margin_free alias should populate free_margin."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: {
            "login": 1,
            "margin_free": 250.75,
        },
    )

    result = account_service.get_account()

    assert result["free_margin"] == 250.75


def test_free_margin_direct(monkeypatch):
    """free_margin should also work directly."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: {
            "login": 1,
            "free_margin": 300,
        },
    )

    result = account_service.get_account()

    assert result["free_margin"] == 300


def test_name_alias(monkeypatch):
    """name should become account_name."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: {
            "login": 5,
            "name": "Trader",
        },
    )

    result = account_service.get_account()

    assert result["account_name"] == "Trader"


def test_login_name_alias(monkeypatch):
    """login_name alias should also populate account_name."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: {
            "login": 5,
            "login_name": "Trader Alias",
        },
    )

    result = account_service.get_account()

    assert result["account_name"] == "Trader Alias"


def test_none_response(monkeypatch, caplog):
    """None should return None and log."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: None,
    )

    result = account_service.get_account()

    assert result is None

    assert "Account data unavailable or malformed" in caplog.text


def test_non_dict_response(monkeypatch, caplog):
    """Non-dict responses should be rejected."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: ["bad", "payload"],
    )

    result = account_service.get_account()

    assert result is None

    assert "Account data unavailable or malformed" in caplog.text


def test_empty_dict(monkeypatch):
    """Empty dict is considered malformed."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: {},
    )

    result = account_service.get_account()

    assert result is None


def test_missing_optional_fields(monkeypatch):
    """Missing optional fields should not crash."""

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        lambda: {
            "login": 777,
        },
    )

    result = account_service.get_account()

    assert result["account"] == 777

    assert "balance" in result
    assert "currency" in result
    assert "broker" in result


def test_connection_manager_exception(monkeypatch):
    """
    Current implementation does not swallow exceptions.

    If this behaviour changes later,
    this test should be updated accordingly.
    """

    def explode():
        raise RuntimeError("boom")

    monkeypatch.setattr(
        account_service.connection_manager,
        "fetch_account",
        explode,
    )

    with pytest.raises(RuntimeError):
        account_service.get_account()
