$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$reportDir = Join-Path $repoRoot "backend\data\test-reports"

if (-not (Test-Path $reportDir)) {
    Write-Host "No test report directory found."
    exit 0
}

Get-ChildItem -Path $reportDir -File -Force |
    Where-Object { $_.Name -ne ".gitkeep" } |
    Remove-Item -Force

Get-ChildItem -Path $reportDir -Directory -Force -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

Write-Host "Test reports cleaned."
