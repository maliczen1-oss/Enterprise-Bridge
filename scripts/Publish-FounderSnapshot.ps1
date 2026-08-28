[CmdletBinding()]
param(
    [string]$RelayUrl = $env:WEALTHBUILDER_RELAY_URL,
    [string]$RelayToken = $env:WEALTHBUILDER_RELAY_TOKEN,
    [string]$BridgeUrl = "http://127.0.0.1:8001",
    [string]$BridgeToken = $env:BRIDGE_AUTH_TOKEN,
    [switch]$Continuous,
    [ValidateRange(15, 3600)]
    [int]$IntervalSeconds = 60
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
        $openedAt = $null
        if ($null -ne $_.time) {
            $openedAt = [DateTimeOffset]::FromUnixTimeSeconds([long]$_.time).UtcDateTime.ToString("o")
        }
        [ordered]@{
            ticket       = [string]$_.ticket
            symbol       = [string]$_.symbol
            side         = if ([string]$_.type -in @("0", "BUY", "buy")) { "BUY" } else { "SELL" }
            volume       = [double]$_.volume
            priceOpen    = [double]$_.price_open
            priceCurrent = Convert-ToNullableNumber $_.price_current
            profit       = Convert-ToNullableNumber $_.profit
            stopLoss     = $null
            takeProfit   = $null
            openedAt     = $openedAt
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
        -Headers $relayHeaders -ContentType "application/json" -Body $body -TimeoutSec 15
    if (-not $result.success) { throw "The remote service did not accept the snapshot." }
    Write-Host "Read-only founder snapshot accepted at $($result.acceptedAt)." -ForegroundColor Green
}

do {
    try { Publish-Snapshot }
    catch { Write-Error "Snapshot relay failed: $($_.Exception.Message)" -ErrorAction Continue }
    if ($Continuous) { Start-Sleep -Seconds $IntervalSeconds }
} while ($Continuous)
