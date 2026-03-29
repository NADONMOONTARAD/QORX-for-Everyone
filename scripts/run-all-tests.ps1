$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$reportDir = Join-Path $repoRoot "backend\data\test-reports"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

Get-ChildItem -Path $reportDir -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^all-tests-summary-\d{8}-\d{6}\.md$' } |
    Remove-Item -Force

$latestSummaryPath = Join-Path $reportDir "all-tests-summary-latest.md"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Name"
    $startedAt = Get-Date
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        & $Command 2>&1 | ForEach-Object { "$_" } | Out-Host
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $finishedAt = Get-Date

    return [pscustomobject]@{
        Name = $Name
        ExitCode = $exitCode
        DurationSeconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 2)
    }
}

$results = @()
$results += Invoke-Step -Name "pre-commit suite" -Command { npm run test }
$results += Invoke-Step -Name "playwright e2e suite" -Command { npm run test:e2e }

$failed = $results | Where-Object { $_.ExitCode -ne 0 }

$summaryLines = @(
    "# Full Test Summary",
    "",
    "- Timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")",
    "",
    "## Results",
    "",
    "- pre-commit suite: $(if ($results[0].ExitCode -eq 0) { 'PASS' } else { 'FAIL' }) ($($results[0].DurationSeconds)s)",
    "- playwright e2e suite: $(if ($results[1].ExitCode -eq 0) { 'PASS' } else { 'FAIL' }) ($($results[1].DurationSeconds)s)",
    "",
    "## Reports",
    "",
    "- Pre-commit latest: $(Join-Path $reportDir 'precommit-summary-latest.md')",
    "- E2E latest: $(Join-Path $reportDir 'e2e-summary-latest.md')",
    "- Playwright HTML: $(Join-Path $reportDir 'playwright-report\index.html')",
    "- Backend JUnit: $(Join-Path $reportDir 'backend-junit.xml')"
)

$summaryLines | Set-Content -Path $latestSummaryPath

if ($failed) {
    Write-Host ""
    Write-Host "full test run completed with failures. Review backend\data\test-reports."
    exit 1
}

Write-Host ""
Write-Host "full test run passed."
exit 0
