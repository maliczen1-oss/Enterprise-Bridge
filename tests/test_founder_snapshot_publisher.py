from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "Publish-FounderSnapshot.ps1"
).read_text(encoding="utf-8")


def test_publisher_is_outbound_only_and_requires_https():
    assert "^https://" in SCRIPT
    assert "127\\.0\\.0\\.1|localhost" in SCRIPT
    assert 'Method Post' in SCRIPT
    assert "/api/worker/snapshot" in SCRIPT


def test_publisher_reads_only_account_positions_and_public_health():
    assert '"$BridgeUrl/health"' in SCRIPT
    assert '"$BridgeUrl/api/account"' in SCRIPT
    assert '"$BridgeUrl/api/positions"' in SCRIPT
    assert "/api/trade" not in SCRIPT
    assert "order_send" not in SCRIPT.lower()
    assert "BROKER_TRADING_ENABLED" not in SCRIPT


def test_publisher_does_not_relay_account_identity_or_broker_comments():
    payload_section = SCRIPT.split("$payload =", maxsplit=1)[1]
    assert "account_name" not in payload_section
    assert "accountResponse.data.account" not in payload_section
    assert "accountResponse.data.server" not in payload_section
    assert ".comment" not in payload_section
