[CmdletBinding()]
param(
    [string]$RelayUrl = $env:WEALTHBUILDER_RELAY_URL,
    [string]$RelayToken = $env:WEALTHBUILDER_RELAY_TOKEN,
    [string]$BridgeUrl = "http://127.0.0.1:8001",
    [string]$BridgeToken = $env:BRIDGE_AUTH_TOKEN,
    [switch]$Continuous,
    [ValidateRange(15, 3600)]
    [int]$IntervalSeconds = 60,
    [ValidateRange(5, 120)]
    [int]$RelayTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RelayUrl)) { throw "WEALTHBUILDER_RELAY_URL is required." }
if ($RelayUrl -notmatch '^https://') { throw "The remote relay URL must use HTTPS." }
if ([string]::IsNullOrWhiteSpace($RelayToken) -or $RelayToken.Length -lt 32) {
    throw "WEALTHBUILDER_RELAY_TOKEN must contain at least 32 characters."
}
if ([string]::IsNullOrWhiteSpace($BridgeToken)) { throw "BRIDGE_AUTH_TOKEN is required." }
if ($BridgeUrl -notmatch '^http://(127\.0\.0\.1|localhost)(:\d+)?$') {
    throw "BridgeUrl must point to the local loopback interface."
}

$bridgeHeaders = @{ Authorization = "Bearer $BridgeToken"; Accept = "application/json" }
$relayHeaders = @{ Authorization = "Bearer $RelayToken"; Accept = "application/json" }

function Convert-ToNullableNumber([object]$Value) {
    if ($null -eq $Value) { return $null }
    return [double]$Value
}

function Convert-ToPositionSide([object]$Value) {
    $normalized = ([string]$Value).Trim().ToUpperInvariant()
    if ($normalized -in @("0", "BUY", "POSITION_TYPE_BUY")) { return "BUY" }
    if ($normalized -in @("1", "SELL", "POSITION_TYPE_SELL")) { return "SELL" }
    throw "Position direction is not recognized; snapshot publication stopped."
}

function Convert-ToIsoTimestamp([object]$Value) {
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) { return $null }
    $unixSeconds = 0L
    if ([long]::TryParse([string]$Value, [ref]$unixSeconds)) {
        return [DateTimeOffset]::FromUnixTimeSeconds($unixSeconds).UtcDateTime.ToString("o")
    }
    $timestamp = [DateTimeOffset]::MinValue
    if ([DateTimeOffset]::TryParse([string]$Value, [ref]$timestamp)) {
        return $timestamp.UtcDateTime.ToString("o")
    }
    throw "Position opening time is not recognized; snapshot publication stopped."
}

function Publish-Snapshot {
    $health = Invoke-RestMethod -Uri "$BridgeUrl/health" -Method Get -TimeoutSec 10
    if (-not $health.success -or $health.data.connectionState -ne "CONNECTED") {
        throw "Enterprise Bridge is not connected to MT5."
    }
    $accountResponse = Invoke-RestMethod -Uri "$BridgeUrl/api/account" -Method Get -Headers $bridgeHeaders -TimeoutSec 10
    $positionsResponse = Invoke-RestMethod -Uri "$BridgeUrl/api/positions" -Method Get -Headers $bridgeHeaders -TimeoutSec 10
    if (-not $accountResponse.success -or -not $positionsResponse.success) {
        throw "The Bridge did not return a complete read-only snapshot."
    }

    $positions = @($positionsResponse.data | ForEach-Object {
        [ordered]@{
            ticket       = [string]$_.ticket
            symbol       = [string]$_.symbol
            side         = Convert-ToPositionSide $_.type
            volume       = [double]$_.volume
            priceOpen    = [double]$_.price_open
            priceCurrent = Convert-ToNullableNumber $_.price_current
            profit       = Convert-ToNullableNumber $_.profit
            stopLoss     = Convert-ToNullableNumber $_.stop_loss
            takeProfit   = Convert-ToNullableNumber $_.take_profit
            openedAt     = Convert-ToIsoTimestamp $_.time
        }
    })

    $capturedAt = [DateTime]::UtcNow.ToString("o")
    $payload = [ordered]@{
        version    = 1
        snapshotId = [guid]::NewGuid().ToString()
        capturedAt = $capturedAt
        bridge     = [ordered]@{
            connected       = $true
            state           = $health.data.connectionState
            broker          = $health.data.broker
            terminalVersion = [string]$health.data.terminalVersion
        }
        account    = [ordered]@{
            balance    = [double]$accountResponse.data.balance
            equity     = [double]$accountResponse.data.equity
            margin     = Convert-ToNullableNumber $accountResponse.data.margin
            freeMargin = Convert-ToNullableNumber $accountResponse.data.free_margin
            currency   = [string]$accountResponse.data.currency
        }
        positions  = $positions
    }

    $body = $payload | ConvertTo-Json -Depth 6 -Compress
    $result = Invoke-RestMethod -Uri "$($RelayUrl.TrimEnd('/'))/api/worker/snapshot" -Method Post `
        -Headers $relayHeaders -ContentType "application/json" -Body $body -TimeoutSec $RelayTimeoutSeconds
    if (-not $result.success) { throw "The remote service did not accept the snapshot." }
    Write-Host "Read-only founder snapshot accepted at $($result.acceptedAt)." -ForegroundColor Green
}

do {
    try { Publish-Snapshot }
    catch {
        if (-not $Continuous) { throw }
        Write-Error "Snapshot relay failed: $($_.Exception.Message)" -ErrorAction Continue
    }
    if ($Continuous) { Start-Sleep -Seconds $IntervalSeconds }
} while ($Continuous)
