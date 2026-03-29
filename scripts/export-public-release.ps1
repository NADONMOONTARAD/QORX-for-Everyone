param(
    [string]$Destination
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $Destination) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $parentDir = Split-Path -Parent $repoRoot
    $repoName = Split-Path -Leaf $repoRoot
    $Destination = Join-Path $parentDir "$repoName-public-$timestamp"
}

$destinationRoot = [System.IO.Path]::GetFullPath($Destination)
$normalizedRepoRoot = [System.IO.Path]::GetFullPath($repoRoot)

$repoRootWithSeparator = $normalizedRepoRoot.TrimEnd('\') + '\'
$destinationWithSeparator = $destinationRoot.TrimEnd('\') + '\'

if (
    $destinationRoot.Equals($normalizedRepoRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $destinationWithSeparator.StartsWith($repoRootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)
) {
    throw "Destination must be outside the repository root."
}

New-Item -ItemType Directory -Force -Path $destinationRoot | Out-Null

$excludeDirNames = @(
    ".git",
    ".venv",
    ".vscode",
    "node_modules",
    ".next",
    ".next-e2e",
    ".cache",
    ".gemini"
)

$excludeRelativePaths = @(
    "backend\data\test-reports",
    "frontend\.next",
    "frontend\.next-e2e",
    "frontend\node_modules"
)

$excludeFiles = @(
    ".env",
    "frontend\.env.local",
    "backend-pytest.log",
    "backend-junit.xml",
    "frontend-build.log",
    "playwright-junit.xml",
    "precommit-summary-latest.md",
    "e2e-summary-latest.md",
    "all-tests-summary-latest.md"
)

function Test-ExcludedDirectory {
    param([string]$SourcePath)

    $name = Split-Path -Leaf $SourcePath
    if ($excludeDirNames -contains $name) {
        return $true
    }

    foreach ($relative in $excludeRelativePaths) {
        $fullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $relative))
        if ($SourcePath.Equals($fullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Copy-FilteredDirectory {
    param(
        [string]$SourceDir,
        [string]$TargetDir
    )

    if (Test-ExcludedDirectory -SourcePath $SourceDir) {
        return
    }

    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {
        $sourcePath = $_.FullName
        $targetPath = Join-Path $TargetDir $_.Name

        if ($_.PSIsContainer) {
            Copy-FilteredDirectory -SourceDir $sourcePath -TargetDir $targetPath
            return
        }

        $relativePath = $sourcePath.Substring($repoRoot.Length).TrimStart('\')
        if ($excludeFiles -contains $relativePath) {
            return
        }

        Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
    }
}

Copy-FilteredDirectory -SourceDir $repoRoot -TargetDir $destinationRoot

$notePath = Join-Path $destinationRoot "PUBLIC-RELEASE-NOTES.txt"
$noteLines = @(
    "Public export generated from: $repoRoot",
    "Generated at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")",
    "",
    "Excluded by export:",
    "- .git history and editor folders",
    "- Local secret env files (.env, frontend/.env.local)",
    "- Dependencies and build caches",
    "- Test reports and generated artifacts"
)
$noteLines | Set-Content -Path $notePath

Write-Host "Public release export created at: $destinationRoot"
