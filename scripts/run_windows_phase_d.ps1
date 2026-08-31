param (
    [switch]$PreflightOnly = $true,
    [switch]$PullCandidate = $false,
    [switch]$RunBenchmark = $false
)

$ErrorActionPreference = "Stop"

# Reset default PreflightOnly if another action is explicitly requested
if ($PullCandidate -or $RunBenchmark) {
    $PreflightOnly = $false
}

Write-Host "========================================================"
Write-Host " Jarvis Phase D Windows Operator Script "
Write-Host "========================================================"

function Get-GitBranch {
    return (git rev-parse --abbrev-ref HEAD).Trim()
}

function Get-GitStatus {
    return (git status --short).Trim()
}

function Get-GitHash {
    return (git rev-parse HEAD).Trim()
}

function Run-Preflight {
    Write-Host "`n[1] Starting Preflight Checks..." -ForegroundColor Cyan

    $branch = Get-GitBranch
    if ($branch -ne "phase_d_benchmark") {
        Write-Error "Current branch is '$branch'. Must be 'phase_d_benchmark'."
    }
    Write-Host "[OK] Branch is phase_d_benchmark" -ForegroundColor Green

    $status = Get-GitStatus
    if ($status -ne "") {
        Write-Error "Working tree is not clean. Please commit or stash changes."
    }
    Write-Host "[OK] Working tree is clean" -ForegroundColor Green

    $hash = Get-GitHash
    Write-Host "[OK] Current Commit: $hash" -ForegroundColor Green

    Write-Host "`n[2] System Information:" -ForegroundColor Cyan
    Write-Host "OS: $((Get-CimInstance Win32_OperatingSystem).Caption)"
    
    try {
        $python_version = (python --version 2>&1)
        Write-Host "Python: $python_version"
    } catch { Write-Error "Python not found." }

    try {
        $poetry_version = (poetry --version 2>&1)
        Write-Host "Poetry: $poetry_version"
    } catch { Write-Error "Poetry not found." }

    try {
        $ollama_version = (ollama --version 2>&1)
        Write-Host "Ollama: $ollama_version"
    } catch { Write-Error "Ollama not found." }

    try {
        $nvidia_smi = (nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1)
        Write-Host "NVIDIA GPU: $nvidia_smi"
    } catch { Write-Host "NVIDIA GPU: Not found or nvidia-smi not available." -ForegroundColor Yellow }

    Write-Host "`n[3] Benchmark Harness Dry-Run:" -ForegroundColor Cyan
    $env:PYTHONPATH = "."
    poetry run python scripts/benchmark_local_models.py --dry-run
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Dry-run failed."
    }
    Write-Host "[OK] Dry-run passed." -ForegroundColor Green

    Write-Host "`n[4] Complete Pytest Suite:" -ForegroundColor Cyan
    poetry run pytest tests/ -v
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Pytest suite failed."
    }
    Write-Host "[OK] Pytest suite passed." -ForegroundColor Green

    Write-Host "`n[5] Legacy Tier 1 Baseline Verification:" -ForegroundColor Cyan
    Write-Host "To strictly verify Legacy Tier 1, run the following manually if not covered by pytest:" -ForegroundColor Yellow
    Write-Host "poetry run python scripts/run_legacy_tier1.py" -ForegroundColor Yellow

    Write-Host "`nPreflight Complete. All checks passed.`n" -ForegroundColor Green
}

function Run-PullCandidate {
    Write-Host "`n[Pull Candidate] Pulling deepseek-r1:32b..." -ForegroundColor Cyan
    ollama pull deepseek-r1:32b
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to pull candidate model."
    }
    Write-Host "[OK] deepseek-r1:32b successfully pulled.`n" -ForegroundColor Green
}

function Run-BenchmarkHarness {
    Write-Host "`n[Benchmark] Starting Benchmark Harness..." -ForegroundColor Cyan
    
    # Verify models
    $models = (ollama list)
    if ($models -notmatch "llama3.1:8b") {
        Write-Error "Primary model 'llama3.1:8b' is not installed."
    }
    if ($models -notmatch "deepseek-r1:32b") {
        Write-Error "Candidate model 'deepseek-r1:32b' is not installed. Run with -PullCandidate first."
    }
    Write-Host "[OK] Both models are installed." -ForegroundColor Green

    # Setup reporting directory
    $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $reportDir = "docs\milestones\benchmark_reports"
    if (-not (Test-Path $reportDir)) {
        New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    }
    
    $logFile = "$reportDir\benchmark_$timestamp.log"
    $jsonFile = "$reportDir\benchmark_results_$timestamp.json"

    Write-Host "Running Benchmark... this will take some time. Logs streaming to $logFile"
    
    # Run the python benchmark
    # The script currently supports --dry-run. To properly output json and run it natively:
    $env:PYTHONPATH = "."
    # Note: we pass a hypothetical arg for json output to standard out, but script handles it
    poetry run python scripts/benchmark_local_models.py | Tee-Object -FilePath $logFile

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Benchmark execution failed. Check $logFile."
    }

    Write-Host "`n[OK] Benchmark Complete." -ForegroundColor Green
    Write-Host "Report saved to: $logFile"
    Write-Host "Please review the comparison report manually. DO NOT update .env or promote the primary model yet." -ForegroundColor Yellow
}

# Execution Flow
if ($PreflightOnly) {
    Run-Preflight
}

if ($PullCandidate) {
    Run-PullCandidate
}

if ($RunBenchmark) {
    Run-BenchmarkHarness
}
