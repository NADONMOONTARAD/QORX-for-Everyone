$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$reportDir = Join-Path $repoRoot "backend\data\test-reports"
$screenshotDir = Join-Path $reportDir "e2e-screenshots"
$playwrightOutputDir = Join-Path $reportDir "playwright-output"
$playwrightReportDir = Join-Path $reportDir "playwright-report"
$playwrightJunitPath = Join-Path $reportDir "playwright-junit.xml"

New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

Get-ChildItem -Path $reportDir -File -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match '^e2e-summary-\d{8}-\d{6}\.md$' -or
        $_.Name -match '^e2e-live-report-\d{8}\.md$'
    } |
    Remove-Item -Force

foreach ($path in @($screenshotDir, $playwrightOutputDir, $playwrightReportDir)) {
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
    }
}

if (Test-Path $playwrightJunitPath) {
    Remove-Item -Force $playwrightJunitPath
}

$latestSummaryPath = Join-Path $reportDir "e2e-summary-latest.md"

$targetBaseUrl = if ($env:E2E_BASE_URL -and $env:E2E_BASE_URL.Trim()) {
    $env:E2E_BASE_URL.Trim()
} else {
    "http://127.0.0.1:3100 (local production build)"
}

$dataMode = "live database"

Write-Host ""
Write-Host "==> playwright e2e"
$startedAt = Get-Date
& npm run test:e2e:raw
$exitCode = $LASTEXITCODE
$finishedAt = Get-Date
$durationSeconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 2)

$tests = 0
$failures = 0
$skipped = 0
$passed = 0
$suiteTime = $durationSeconds

if (Test-Path $playwrightJunitPath) {
    [xml]$junit = Get-Content $playwrightJunitPath
    if ($junit.testsuites) {
        $tests = [int]$junit.testsuites.tests
        $failures = [int]$junit.testsuites.failures
        $skipped = [int]$junit.testsuites.skipped
        $suiteTime = [math]::Round([double]$junit.testsuites.time, 2)
    } elseif ($junit.testsuite) {
        $tests = [int]$junit.testsuite.tests
        $failures = [int]$junit.testsuite.failures
        $skipped = [int]$junit.testsuite.skipped
        $suiteTime = [math]::Round([double]$junit.testsuite.time, 2)
    }
}

$passed = [math]::Max($tests - $failures - $skipped, 0)
$status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }

$summaryLines = @(
    "# E2E Summary",
    "",
    "- Timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")",
    "- Target: $targetBaseUrl",
    "- Data mode: $dataMode",
    "- Result: $status",
    "- Playwright: $passed/$tests passed, $failures failed, $skipped skipped ($suiteTime s)",
    "- Raw command duration: $durationSeconds s",
    "",
    "## Coverage",
    "",
    "- Dashboard render/filter/sort/search via Playwright bot",
    "- Stock detail page with live stock data",
    "- REIT stock detail page",
    "- Unknown ticker empty state",
    "- Admin entry-point gate only",
    "",
    "## Notes",
    "",
    "- Full Google OAuth admin login is not automated yet; the report only captures the admin gate or shell entry state.",
    "- Use E2E_BASE_URL=https://your-deployed-site.example.com before npm run test:e2e when you want to test the deployed site instead of local build.",
    "",
    "## Artifacts",
    "",
    "- JUnit: $playwrightJunitPath",
    "- HTML report: $(Join-Path $playwrightReportDir 'index.html')",
    "- Screenshot folder: $screenshotDir"
)

function Add-ScreenshotSection {
    param(
        [string[]]$Lines,
        [string]$Title,
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        $absolutePath = Join-Path $screenshotDir $candidate
        if (Test-Path $absolutePath) {
            $relativePath = "./e2e-screenshots/$candidate"
            $Lines += ""
            $Lines += "### $Title"
            $Lines += ""
            $Lines += "![]($relativePath)"
            break
        }
    }

    return $Lines
}

$summaryLines += ""
$summaryLines += "## Screenshots"

$summaryLines = Add-ScreenshotSection -Lines $summaryLines -Title "Dashboard Home" -Candidates @("01-dashboard-home-live.png")
$summaryLines = Add-ScreenshotSection -Lines $summaryLines -Title "Dashboard Filter" -Candidates @("04-dashboard-filter-industry-live.png", "03-dashboard-filter-sector-live.png")
$summaryLines = Add-ScreenshotSection -Lines $summaryLines -Title "Stock Detail" -Candidates @("09-stock-amzn-live.png")
$summaryLines = Add-ScreenshotSection -Lines $summaryLines -Title "REIT Detail" -Candidates @("10-stock-o-reit-live.png")
$summaryLines = Add-ScreenshotSection -Lines $summaryLines -Title "Admin Gate" -Candidates @("12-admin-login-gate-live.png", "12-admin-shell-live.png")

$summaryLines | Set-Content -Path $latestSummaryPath

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "e2e checks failed. Review backend\data\test-reports."
    exit $exitCode
}

Write-Host ""
Write-Host "e2e checks passed."
exit 0
