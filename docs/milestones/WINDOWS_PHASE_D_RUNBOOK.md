# Phase D DeepSeek-R1 32B Benchmark Runbook (Windows 11)

This runbook provides the exact commands required to execute the Phase D benchmark on the client's Windows 11 Poetry environment.

## 1. Preparation
Open a PowerShell terminal and checkout the isolated benchmark branch:

```powershell
git fetch origin
git checkout phase_d_benchmark
```

## 2. Install Dependencies
Ensure your local Poetry environment is up to date:

```powershell
poetry install
```

## 3. Run Preflight
The default execution mode runs a strict preflight suite. This will dry-run the benchmark, run the full Pytest suite, verify Legacy Tier 1 integration, and ensure your system meets all constraints:

```powershell
.\scripts\run_windows_phase_d.ps1 -PreflightOnly
```
*(Or simply run `.\scripts\run_windows_phase_d.ps1` as Preflight is the default mode).*

## 4. Pull Candidate Model
Only once the preflight passes (exit code 0), explicitly pull the DeepSeek model:

```powershell
.\scripts\run_windows_phase_d.ps1 -PullCandidate
```
*Note: This will download a large 32B parameter model (roughly 19GB) into your Ollama instance.*

## 5. Execute Benchmark
Once both `llama3.1:8b` and `deepseek-r1:32b` are installed, trigger the full 50-case comparative benchmark harness:

```powershell
.\scripts\run_windows_phase_d.ps1 -RunBenchmark
```

## 6. Review Reports
The script streams execution logs to standard output and writes them directly into the report directory. You can locate your generated logs and metrics at:

```text
docs\milestones\benchmark_reports\
```

**STOP:** DO NOT update your `.env` or promote the primary model. You must manually review the generated report and wait for shadow testing approval before proceeding.

## 7. Recovering from Failures
If a command returns a non-zero exit code, the operator script will immediately halt. 
- **Not on phase_d_benchmark:** Check out the correct branch (`git checkout phase_d_benchmark`).
- **Working Tree Not Clean:** Stash or commit your modifications (`git stash`).
- **Missing Models:** Rerun with `-PullCandidate` to ensure Ollama has the candidate model. If the primary model is missing, run `ollama pull llama3.1:8b`.
- **Python/Poetry Failures:** Ensure `python` and `poetry` are correctly added to your Windows PATH.
