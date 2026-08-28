[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8001"
)

$ErrorActionPreference = "Stop"

try {
    $response = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 8
} catch {
    throw "The Bridge health endpoint is unreachable at $BaseUrl. Confirm MT5 and the Bridge worker are running."
}

if ($response.success -ne $true) {
    throw "The Bridge responded but is not connected to MT5. Check the VaultMarkets login and Bridge logs."
}

if ($response.data.connectionState -ne "CONNECTED") {
    throw "The Bridge state is $($response.data.connectionState), not CONNECTED."
}

Write-Host "WealthBuilder Bridge is connected and read-only access is ready." -ForegroundColor Green
Write-Host "Broker: $($response.data.broker)"
Write-Host "Terminal: $($response.data.terminalVersion)"
