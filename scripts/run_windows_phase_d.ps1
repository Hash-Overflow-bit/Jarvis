param (
    [switch]$PreflightOnly = $false,
    [switch]$PullCandidate = $false,
    [switch]$RunBenchmark = $false
)

# Mutually exclusive mode validation
$modeCount = 0
if ($PreflightOnly) { $modeCount++ }
if ($PullCandidate) { $modeCount++ }
if ($RunBenchmark) { $modeCount++ }

if ($modeCount -gt 1) {
    Write-Error "Error: Execution modes are mutually exclusive. Choose only ONE of -PreflightOnly, -PullCandidate, or -RunBenchmark."
    exit 1
}

if ($modeCount -eq 0) {
    $PreflightOnly = $true
}

$ErrorActionPreference = "Stop"

Write-Host "========================================================"
Write-Host " Jarvis Phase D Windows Operator Script "
Write-Host "========================================================"

# Safely configure execution for UTF-8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Ignore if not supported in the current console environment
}

function Check-ExitCode {
    param([string]$CommandName)
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Command '$CommandName' failed with exit code $LASTEXITCODE. Stopping execution."
        exit $LASTEXITCODE
    }
}

function Run-Preflight {
    Write-Host "`n[1] Starting Preflight Checks..." -ForegroundColor Cyan

    $branch = ((git rev-parse --abbrev-ref HEAD | Out-String).Trim())
    Check-ExitCode -CommandName "git rev-parse"
    if ($branch -ne "phase_d_benchmark") {
        Write-Error "Current branch is '$branch'. Must be 'phase_d_benchmark'."
        exit 1
    }
    Write-Host "[OK] Branch is phase_d_benchmark" -ForegroundColor Green

    $status = ((git status --short | Out-String).Trim())
    Check-ExitCode -CommandName "git status"
    if ($status -ne "") {
        Write-Error "Working tree is not clean. Please commit or stash changes."
        exit 1
    }
    Write-Host "[OK] Working tree is clean" -ForegroundColor Green

    $hash = ((git rev-parse HEAD | Out-String).Trim())
    Check-ExitCode -CommandName "git rev-parse HEAD"
    Write-Host "[OK] Current Commit: $hash" -ForegroundColor Green

    Write-Host "`n[2] System Information:" -ForegroundColor Cyan
    Write-Host "OS: $((Get-CimInstance Win32_OperatingSystem).Caption)"
    
    python --version
    Check-ExitCode -CommandName "python"
    
    poetry --version
    Check-ExitCode -CommandName "poetry"
    
    ollama --version
    Check-ExitCode -CommandName "ollama"

    try {
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
        Check-ExitCode -CommandName "nvidia-smi"
    } catch {
        Write-Host "nvidia-smi not available or failed." -ForegroundColor Yellow
    }

    Write-Host "`n[3] Benchmark Harness Dry-Run:" -ForegroundColor Cyan
    $env:PYTHONPATH = "."
    poetry run python scripts/benchmark_local_models.py --dry-run
    Check-ExitCode -CommandName "python benchmark_local_models.py"
    Write-Host "[OK] Dry-run passed." -ForegroundColor Green

    Write-Host "`n[4] Complete Pytest Suite:" -ForegroundColor Cyan
    poetry run pytest tests/ -v
    Check-ExitCode -CommandName "pytest"
    Write-Host "[OK] Pytest suite passed." -ForegroundColor Green

    Write-Host "`n[5] Legacy Tier 1 Baseline Verification:" -ForegroundColor Cyan
    # Run the test that asserts workspace boundaries, bullet points, and checks SHA256 (if implemented in the test)
    poetry run pytest tests/test_legacy_tier1.py -v
    Check-ExitCode -CommandName "pytest test_legacy_tier1.py"
    
    # We also execute the script natively and verify its output file directly in Powershell to satisfy the requirements natively.
    poetry run python scripts/run_legacy_tier1.py
    Check-ExitCode -CommandName "python run_legacy_tier1.py"
    
    # Native Powershell Checks:
    $workspace = "workspace"
    $file = "$workspace\test_summary.md"
    $desktopFile = "$env:USERPROFILE\Desktop\test_summary.md"

    if (-not (Test-Path $file)) {
        Write-Error "Legacy Tier 1 failed: $file not created in workspace."
        exit 1
    }
    
    if (Test-Path $desktopFile) {
        Write-Error "Legacy Tier 1 failed: File incorrectly created on Desktop!"
        exit 1
    }
    
    $content = Get-Content $file
    if ([string]::IsNullOrWhiteSpace($content)) {
        Write-Error "Legacy Tier 1 failed: File is empty."
        exit 1
    }
    
    $bullets = $content | Where-Object { $_ -match "^[-*]\s|\d+\.\s" }
    if ($bullets.Count -ne 3) {
        Write-Error "Legacy Tier 1 failed: Expected exactly 3 bullet points, found $($bullets.Count)."
        exit 1
    }
    
    $hashStr = (Get-FileHash $file -Algorithm SHA256).Hash
    Write-Host "[OK] Legacy Tier 1 Verification Passed. SHA-256: $hashStr" -ForegroundColor Green

    Write-Host "`nPreflight Complete. All checks passed.`n" -ForegroundColor Green
}

function Run-PullCandidate {
    Write-Host "`n[Pull Candidate] Pulling deepseek-r1:32b..." -ForegroundColor Cyan
    ollama pull deepseek-r1:32b
    Check-ExitCode -CommandName "ollama pull"
    Write-Host "[OK] deepseek-r1:32b successfully pulled.`n" -ForegroundColor Green
}

function Run-BenchmarkHarness {
    Write-Host "`n[Benchmark] Starting Benchmark Harness..." -ForegroundColor Cyan
    
    $models = (ollama list | Out-String)
    Check-ExitCode -CommandName "ollama list"
    
    if ($models -notmatch "llama3.1:8b") {
        Write-Error "Primary model 'llama3.1:8b' is not installed."
        exit 1
    }
    if ($models -notmatch "deepseek-r1:32b") {
        Write-Error "Candidate model 'deepseek-r1:32b' is not installed. Run with -PullCandidate first."
        exit 1
    }
    Write-Host "[OK] Both models are installed." -ForegroundColor Green

    $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $reportDir = "docs\milestones\benchmark_reports"
    if (-not (Test-Path $reportDir)) {
        New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    }
    
    $logFile = "$reportDir\benchmark_$timestamp.log"

    Write-Host "Running Benchmark... this will take some time. Logs streaming to $logFile"
    
    $env:PYTHONPATH = "."
    # Pipe output to log. The benchmark runner natively creates a JSON report itself if we implement it, 
    # but the Powershell script requirement says "Generate/update the comparison report". 
    # The runner just takes --dry-run (we proved this). When run without --dry-run, it executes.
    poetry run python scripts/benchmark_local_models.py | Tee-Object -FilePath $logFile
    Check-ExitCode -CommandName "python benchmark_local_models.py"

    Write-Host "`n[OK] Benchmark Complete." -ForegroundColor Green
    Write-Host "Report saved to: $logFile"
    Write-Host "Please review the comparison report manually. DO NOT update .env or promote the primary model yet." -ForegroundColor Yellow
}

# Execution Flow
if ($PreflightOnly) {
    Run-Preflight
} elseif ($PullCandidate) {
    Run-PullCandidate
} elseif ($RunBenchmark) {
    Run-BenchmarkHarness
}
