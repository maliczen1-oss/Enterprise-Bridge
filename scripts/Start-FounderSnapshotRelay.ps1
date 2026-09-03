[CmdletBinding()]
param(
    [switch]$Once,
    [ValidateRange(15, 3600)]
    [int]$IntervalSeconds = 60,
    [ValidateRange(5, 120)]
    [int]$RelayTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Enterprise Bridge .env file was not found."
}

$authLine = Get-Content -LiteralPath $envPath |
    Where-Object { $_ -match '^AUTH_TOKEN=' } |
    Select-Object -First 1

if (-not $authLine) {
    throw "AUTH_TOKEN is missing from the Enterprise Bridge .env file."
}

$bridgeToken = $authLine.Substring("AUTH_TOKEN=".Length).Trim().Trim('"').Trim("'")
$relayUrl = [Environment]::GetEnvironmentVariable("WEALTHBUILDER_RELAY_URL", "Process")
$relayToken = [Environment]::GetEnvironmentVariable("WEALTHBUILDER_RELAY_TOKEN", "Process")
if ([string]::IsNullOrWhiteSpace($relayUrl)) {
    $relayUrl = [Environment]::GetEnvironmentVariable("WEALTHBUILDER_RELAY_URL", "User")
}
if ([string]::IsNullOrWhiteSpace($relayToken)) {
    $relayToken = [Environment]::GetEnvironmentVariable("WEALTHBUILDER_RELAY_TOKEN", "User")
}

$publisherParameters = @{
    RelayUrl            = $relayUrl
    RelayToken          = $relayToken
    BridgeToken         = $bridgeToken
    IntervalSeconds     = $IntervalSeconds
    RelayTimeoutSeconds = $RelayTimeoutSeconds
}

if (-not $Once) {
    $publisherParameters.Continuous = $true
}

& (Join-Path $PSScriptRoot "Publish-FounderSnapshot.ps1") @publisherParameters
