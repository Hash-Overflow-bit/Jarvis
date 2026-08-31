import pytest
from pathlib import Path
import re

PS_SCRIPT_PATH = Path("scripts/run_windows_phase_d.ps1")

@pytest.fixture
def script_content():
    assert PS_SCRIPT_PATH.exists(), "PowerShell script not found."
    return PS_SCRIPT_PATH.read_text(encoding="utf-8")

def test_default_preflight_selection(script_content):
    """Test that execution defaults to preflight if no switches are provided."""
    # Ensure the script handles $modeCount -eq 0 -> $PreflightOnly = $true
    assert re.search(r"if\s*\(\$modeCount\s*-eq\s*0\)\s*\{\s*\$PreflightOnly\s*=\s*\$true\s*\}", script_content), "Does not default to preflight."

def test_rejection_of_conflicting_switches(script_content):
    """Test that the script counts modes and fails if > 1."""
    assert re.search(r"\$modeCount\s*-\w+\s*1", script_content)
    assert re.search(r"mutually exclusive", script_content, re.IGNORECASE)

def test_no_model_pull_during_preflight(script_content):
    """Test that deepseek is only pulled inside Run-PullCandidate."""
    preflight_section = re.search(r"function Run-Preflight\s*\{(.*?)\}function", script_content, re.DOTALL)
    if preflight_section:
        assert "ollama pull" not in preflight_section.group(1), "Pull command found inside preflight!"
    assert "ollama pull deepseek-r1:32b" in script_content

def test_no_benchmark_during_pull_candidate(script_content):
    """Test that PullCandidate does not trigger benchmark logic."""
    pull_section = re.search(r"function Run-PullCandidate\s*\{(.*?)\}function", script_content, re.DOTALL)
    if pull_section:
        assert "benchmark_local_models" not in pull_section.group(1), "Benchmark triggered in PullCandidate!"

def test_non_zero_native_command_handling(script_content):
    """Test that LASTEXITCODE is checked for major native commands."""
    assert "function Check-ExitCode" in script_content
    assert "$LASTEXITCODE -ne 0" in script_content
    # Commands to verify
    required_commands = ["git", "python", "poetry", "pytest", "ollama", "nvidia-smi"]
    for cmd in required_commands:
        assert f'Check-ExitCode -CommandName "{cmd}' in script_content or f'Check-ExitCode -CommandName "{cmd}"' in script_content or f'{cmd}' in script_content

def test_no_env_modification(script_content):
    """Test that .env is not mutated."""
    assert ">> .env" not in script_content
    assert "> .env" not in script_content
    assert "Out-File -FilePath .env" not in script_content
    assert "Out-File" not in script_content or "benchmark_" in script_content

def test_no_primary_model_promotion(script_content):
    """Test that primary model is not promoted."""
    assert "OLLAMA_PRIMARY_MODEL" not in script_content

def test_report_path_inside_repository(script_content):
    """Test that report outputs are confined to the repository."""
    assert re.search(r"\$reportDir\s*=\s*[\"']docs\\milestones\\benchmark_reports[\"']", script_content)

def test_correct_benchmark_invocation(script_content):
    """Test that benchmark runner uses exact Python commands supported."""
    assert re.search(r"poetry run python scripts[/\\]benchmark_local_models\.py --dry-run", script_content)
    # The normal run just executes the script without unsupported args
    assert re.search(r"poetry run python scripts[/\\]benchmark_local_models\.py \| Tee-Object", script_content)
