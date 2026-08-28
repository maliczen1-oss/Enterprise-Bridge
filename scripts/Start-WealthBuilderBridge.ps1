[CmdletBinding()]
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $repositoryRoot ".env"
$virtualPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw "Bridge configuration is missing. Copy .env.example to .env and add the founder-only credentials."
}

if (-not (Test-Path -LiteralPath $virtualPython)) {
    throw "Bridge Python environment is missing. Create .venv and install requirements.txt first."
}

$terminal = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
if (-not $terminal) {
    throw "MetaTrader 5 is not running. Open the VaultMarkets MT5 terminal and sign in first."
}

if ($CheckOnly) {
    Write-Host "WealthBuilder Bridge prerequisites are ready." -ForegroundColor Green
    exit 0
}

Set-Location -LiteralPath $repositoryRoot
Write-Host "Starting WealthBuilder Bridge in founder research mode..." -ForegroundColor Cyan
& $virtualPython -m bridge
exit $LASTEXITCODE
