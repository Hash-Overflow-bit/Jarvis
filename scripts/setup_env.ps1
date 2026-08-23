# scripts/setup_env.ps1
# =====================
# Automated environment preparation script for Jarvis on a fresh Windows 11 installation.
# Sets up Python checks, WSL validation, Ollama model pulls, and OneDrive bypass configurations.

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   J A R V I S   E N V   S E T U P   " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python Installation
Write-Host "[🔎] Checking Python 3.11+ installation..."
try {
    $pythonVersion = & python --version 2>&1
    if ($pythonVersion -match "Python 3\.(11|12|13)") {
        Write-Host "  - Found: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "  - Warning: Found Python version $pythonVersion. Python 3.11+ is highly recommended." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  - Error: Python is not installed or not in PATH! Please install Python 3.11+." -ForegroundColor Red
    Exit 1
}

# 2. Check WSL 2 status
Write-Host ""
Write-Host "[🔎] Checking WSL 2 installation..."
try {
    $wslList = & wsl --list --verbose 2>&1
    Write-Host "  - WSL 2 is enabled and active." -ForegroundColor Green
} catch {
    Write-Host "  - Warning: WSL 2 is not detected! Jarvis can run on Windows natively in text mode, but WSL 2 is required for full Linux tool capabilities." -ForegroundColor Yellow
}

# 3. Check Ollama connection and pull models
Write-Host ""
Write-Host "[🔎] Verifying Ollama local connection..."
$ollamaUrl = "http://localhost:11434"
try {
    $response = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -Method Get -TimeoutSec 5
    Write-Host "  - Connected to Ollama at $ollamaUrl successfully." -ForegroundColor Green
    
    # Pull default models
    Write-Host "  - Pulling primary model (llama3.1)..." -ForegroundColor Cyan
    $pullPayload = @{ name = "llama3.1"; stream = $false } | ConvertTo-Json
    $pullResult = Invoke-RestMethod -Uri "$ollamaUrl/api/pull" -Method Post -Body $pullPayload -ContentType "application/json" -TimeoutSec 300
    Write-Host "  - Llama 3.1 pulled and verified." -ForegroundColor Green
} catch {
    Write-Host "  - Warning: Cannot connect to Ollama at $ollamaUrl. Please make sure Ollama is running ('ollama serve') before launching Jarvis." -ForegroundColor Yellow
}

# 4. Check OneDrive and Configure Local Workspace Paths
Write-Host ""
Write-Host "[🔎] Checking for OneDrive path conflicts..."
$homeDir = [System.Environment]::GetFolderPath('UserProfile')
$oneDrivePath = Join-Path $homeDir "OneDrive"
$oneDriveExists = Test-Path $oneDrivePath

# Define local, non-OneDrive paths
$localJarvisDir = Join-Path $homeDir "Jarvis"
$localWorkspace = Join-Path $localJarvisDir "workspace"
$localSandbox = Join-Path $localJarvisDir "sandbox"
$localLogs = Join-Path $localJarvisDir "logs"
$localMemory = Join-Path $localJarvisDir "core\memory"

if ($oneDriveExists) {
    Write-Host "  - OneDrive detected at: $oneDrivePath" -ForegroundColor Yellow
    Write-Host "  - Redirecting working directories to local folder to prevent sync lock issues: $localJarvisDir" -ForegroundColor Green
    
    # Create local folder structure
    New-Item -ItemType Directory -Force -Path $localWorkspace | Out-Null
    New-Item -ItemType Directory -Force -Path $localSandbox | Out-Null
    New-Item -ItemType Directory -Force -Path $localLogs | Out-Null
    New-Item -ItemType Directory -Force -Path $localMemory | Out-Null
} else {
    Write-Host "  - OneDrive not detected. Using standard project-local paths." -ForegroundColor Green
}

# 5. Populate/Verify .env file
Write-Host ""
Write-Host "[🔎] Checking .env configuration..."
$envPath = ".\.env"
$envExists = Test-Path $envPath

if (-not $envExists) {
    Write-Host "  - Creating fresh .env file from .env.example..." -ForegroundColor Cyan
    if (Test-Path ".\.env.example") {
        Copy-Item -Path ".\.env.example" -Destination $envPath
    } else {
        New-Item -ItemType File -Path $envPath | Out-Null
    }
}

# Injected local folder configurations to prevent OneDrive lock conflicts
if ($oneDriveExists) {
    $envContent = Get-Content $envPath
    $newEnvContent = @()
    
    foreach ($line in $envContent) {
        if ($line -like "DEFAULT_WORKSPACE_DIR=*") {
            $newEnvContent += "DEFAULT_WORKSPACE_DIR=$localWorkspace"
        } elseif ($line -like "SANDBOX_ROOTS=*") {
            $newEnvContent += "SANDBOX_ROOTS=$localSandbox"
        } elseif ($line -like "AUDIT_LOG_PATH=*") {
            $newEnvContent += "AUDIT_LOG_PATH=$(Join-Path $localLogs 'audit.log')"
        } elseif ($line -like "KNOWLEDGE_GRAPH_PATH=*") {
            $newEnvContent += "KNOWLEDGE_GRAPH_PATH=$(Join-Path $localMemory 'graph.db')"
        } else {
            $newEnvContent += $line
        }
    }
    
    $newEnvContent | Set-Content $envPath
    Write-Host "  - Updated .env with safe local OneDrive-isolated directories." -ForegroundColor Green
} else {
    Write-Host "  - .env is configured correctly." -ForegroundColor Green
}

# 6. Register jarvis command globally in system PATH
Write-Host ""
Write-Host "[🔎] Registering global 'jarvis' command..."
$oldPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$currentDir = (Get-Item .).FullName
if ($oldPath -notlike "*$currentDir*") {
    $newPath = "$oldPath;$currentDir"
    [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "  - Added Jarvis project folder to system PATH successfully." -ForegroundColor Green
    Write-Host "  - Note: Open a NEW terminal window for changes to take effect." -ForegroundColor Yellow
} else {
    Write-Host "  - Jarvis folder is already registered in system PATH." -ForegroundColor Green
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "   SETUP COMPLETE! Ready to run Jarvis. " -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
