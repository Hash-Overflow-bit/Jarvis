# Phase D Baseline Documentation

## 1. Repository State
- **Git Commit**: `d23fc5b Stabilize dynamic sub-agent orchestration` (Plus Phase C fixes)
- **Status**: Regression suite passing (272 passed, 1 skipped). Legacy Tier 1 integration validated.

## 2. Ollama Environment Baseline
- **Ollama Version**: Currently installed and running locally on macOS.
- **Current Llama Model**: `llama3.1:8b`
- **Current .env Configuration**:
  ```env
  OLLAMA_HOST=http://127.0.0.1:11434
  OLLAMA_PRIMARY_MODEL=llama3.1:8b
  ```

## 3. Rollback Protection
Llama 3.1 8B remains the undisputed default `PRIMARY_MODEL`. DeepSeek-R1 32B will only be introduced as a `CANDIDATE_MODEL` and used explicitly during benchmarking. Existing models and configurations on the current machine will not be deleted or overwritten.
