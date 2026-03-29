param(
    [switch]$All
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$reportDir = Join-Path $repoRoot "backend\data\test-reports"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

Get-ChildItem -Path $reportDir -File -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match '^precommit-summary-\d{8}-\d{6}\.md$' -or
        $_.Name -match '^backend-pytest-\d{8}-\d{6}\.log$' -or
        $_.Name -match '^frontend-build-\d{8}-\d{6}\.log$' -or
        $_.Name -match '^backend-junit-\d{8}-\d{6}\.xml$'
    } |
    Remove-Item -Force

$latestSummaryPath = Join-Path $reportDir "precommit-summary-latest.md"
$backendLogPath = Join-Path $reportDir "backend-pytest.log"
$backendJunitPath = Join-Path $reportDir "backend-junit.xml"
$frontendLogPath = Join-Path $reportDir "frontend-build.log"

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at .venv\Scripts\python.exe"
}

function Get-StagedFiles {
    $files = git diff --cached --name-only --diff-filter=ACMR
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read staged files."
    }

    return @($files | Where-Object { $_ -and $_.Trim() })
}

function Test-FileMatch {
    param(
        [string[]]$Files,
        [string[]]$Patterns
    )

    foreach ($file in $Files) {
        foreach ($pattern in $Patterns) {
            if ($file -match $pattern) {
                return $true
            }
        }
    }

    return $false
}

function Invoke-NativeStep {
    param(
        [string]$Name,
        [string]$LogPath,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Name"
    $startedAt = Get-Date
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        & $Command 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $LogPath | Out-Host
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $finishedAt = Get-Date
    return [pscustomobject]@{
        Name = $Name
        ExitCode = $exitCode
        DurationSeconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 2)
        LogPath = $LogPath
    }
}

$stagedFiles = if ($All) { @("backend/", "frontend/") } else { Get-StagedFiles }

$runBackend = $All -or (Test-FileMatch -Files $stagedFiles -Patterns @(
    "^backend/",
    "^requirements\.txt$",
    "^backend/requirements\.txt$",
    "^backend/setup\.py$"
))

$runFrontend = $All -or (Test-FileMatch -Files $stagedFiles -Patterns @(
    "^frontend/",
    "^package\.json$",
    "^package-lock\.json$"
))

if (-not $runBackend -and -not $runFrontend) {
    $skipLines = @(
        "# Pre-commit Summary",
        "",
        "No backend/frontend changes detected.",
        "",
        "Staged files:",
        ""
    )

    if ($stagedFiles.Count -eq 0) {
        $skipLines += "- (none)"
    } else {
        $skipLines += ($stagedFiles | ForEach-Object { "- $_" })
    }

    $skipLines | Set-Content -Path $latestSummaryPath
    Write-Host "No backend/frontend changes detected. Skipping pre-commit checks."
    exit 0
}

$results = @()
$failed = $false

if ($runBackend) {
    $results += Invoke-NativeStep -Name "backend pytest" -LogPath $backendLogPath -Command {
        & $pythonExe -m pytest backend/tests --junitxml $backendJunitPath
    }
    if ($results[-1].ExitCode -ne 0) {
        $failed = $true
    }
}

if ($runFrontend) {
    $results += Invoke-NativeStep -Name "frontend build" -LogPath $frontendLogPath -Command {
        npm --prefix frontend run build
    }
    if ($results[-1].ExitCode -ne 0) {
        $failed = $true
    }
}

$summaryLines = @(
    "# Pre-commit Summary",
    "",
    "- Timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")",
    "- Backend checks: $(if ($runBackend) { "enabled" } else { "skipped" })",
    "- Frontend checks: $(if ($runFrontend) { "enabled" } else { "skipped" })",
    "",
    "## Staged Files",
    ""
)

if ($stagedFiles.Count -eq 0) {
    $summaryLines += "- (none)"
} else {
    $summaryLines += ($stagedFiles | ForEach-Object { "- $_" })
}

$summaryLines += ""
$summaryLines += "## Results"
$summaryLines += ""
$summaryLines += ($results | ForEach-Object {
    "- $($_.Name): $(if ($_.ExitCode -eq 0) { "PASS" } else { "FAIL" }) ($($_.DurationSeconds)s) -> $($_.LogPath)"
})

$summaryLines | Set-Content -Path $latestSummaryPath

if ($failed) {
    Write-Host ""
    Write-Host "pre-commit checks failed. Review the logs in backend\data\test-reports."
    exit 1
}

Write-Host ""
Write-Host "pre-commit checks passed."
exit 0
