from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "Publish-FounderSnapshot.ps1"
).read_text(encoding="utf-8")

LAUNCHER = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "Start-FounderSnapshotRelay.ps1"
).read_text(encoding="utf-8")

WINDOWS_LAUNCHER = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "Start-FounderSnapshotRelay.cmd"
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


def test_publisher_includes_bounded_h1_research_history_for_certification():
    assert "Get-VerifiedResearchHistory" in SCRIPT
    assert "timeframe=H1&count=10000" in SCRIPT
    assert 'version    = 3' in SCRIPT
    assert 'research   = $research' in SCRIPT


def test_publisher_does_not_relay_account_identity_or_broker_comments():
    payload_section = SCRIPT.split("$payload =", maxsplit=1)[1]
    assert "account_name" not in payload_section
    assert "accountResponse.data.account" not in payload_section
    assert "accountResponse.data.server" not in payload_section
    assert ".comment" not in payload_section


def test_one_shot_failures_are_not_reported_as_success():
    assert "if (-not $Continuous) { throw }" in SCRIPT
    assert "RelayTimeoutSeconds" in SCRIPT


def test_launcher_loads_secrets_without_putting_them_on_the_command_line():
    assert 'Join-Path $repoRoot ".env"' in LAUNCHER
    assert 'GetEnvironmentVariable("WEALTHBUILDER_RELAY_TOKEN", "User")' in LAUNCHER
    assert "BridgeToken         = $bridgeToken" in LAUNCHER
    assert "Write-Host $bridgeToken" not in LAUNCHER
    assert '-File "%~dp0Start-FounderSnapshotRelay.ps1"' in WINDOWS_LAUNCHER
    assert "exit /b %ERRORLEVEL%" in WINDOWS_LAUNCHER
