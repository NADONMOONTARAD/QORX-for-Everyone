$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

git config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure core.hooksPath."
}

Write-Host "Git hooks installed."
Write-Host "Active hooks path: .githooks"
Write-Host "The pre-commit hook will now run before each commit."
