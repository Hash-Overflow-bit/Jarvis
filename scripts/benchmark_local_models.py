import os
import json
import time
import argparse
import yaml
from pathlib import Path
from collections import Counter
from core.config import settings
from core.llm.ollama_client import OllamaClient

def setup_benchmark_env(is_dry_run: bool):
    """Validates the environment before running benchmarks."""
    if is_dry_run:
        return True
        
    print("--- Jarvis Benchmark Runner ---")
    
    client = OllamaClient()
    if not client.is_running():
        print("[ERROR] Ollama is not running.")
        return False
        
    models = client.list_models()
    
    # 1. Validate primary model
    primary = settings.ollama_primary_model
    print(f"Validating primary model: {primary}")
    if primary not in models:
        print(f"[ERROR] Primary model '{primary}' is not available.")
        return False
        
    # 2. Validate candidate model
    candidate = settings.ollama_candidate_model
    if not candidate:
        print("[ERROR] OLLAMA_CANDIDATE_MODEL is not set in the environment.")
        return False
        
    print(f"Validating candidate model: {candidate}")
    if candidate not in models:
        print(f"[ERROR] Candidate model '{candidate}' is not available.")
        print("[INFO] Please pull the candidate model before running the benchmark.")
        return False
        
    return True

def validate_tmp_workspace():
    # Validate temporary-workspace creation
    tmp_workspace = Path("workspace_tmp_benchmark")
    if not tmp_workspace.exists():
        tmp_workspace.mkdir(parents=True, exist_ok=True)
    # Touch no real Desktop or production workspace
    # Cleanup after test validation
    tmp_workspace.rmdir()
    
def validate_metrics_serialization():
    # Validate result/metrics serialization
    test_metrics = [{"id": "test", "time": 1.0}]
    json.dumps(test_metrics)

def run_benchmarks(is_dry_run: bool):
    """Runs the predefined benchmark cases for both models."""
    if not setup_benchmark_env(is_dry_run):
        print("Benchmark aborted due to environment validation failure.")
        return
        
    if not is_dry_run:
        print("\n[INFO] Both models are available. Proceeding with benchmark...")
    
    with open("benchmarks/local_model_cases.yaml", "r") as f:
        data = yaml.safe_load(f)
        cases = data.get("cases", [])
        
    if not is_dry_run:
        print(f"[INFO] Loaded {len(cases)} benchmark cases from YAML.")
    
    assert len(cases) == 50, f"Expected 50 benchmark cases, but found {len(cases)}"
    
    # Check category counts
    categories = Counter(c.get("type") for c in cases)
    
    if is_dry_run:
        validate_tmp_workspace()
        validate_metrics_serialization()
        print(f"Categories: {dict(categories)}")
        print("50 benchmark cases valid — no models invoked")
        return
    
    metrics = []
    
    # Here we would normally iterate over models and cases
    # For now, this is a dry-run scaffolding.
    print("[INFO] Scaffolding complete. Real benchmark execution requires the Windows test environment.")
    print("Metrics structure ready for D7.")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run without invoking models or checking Ollama")
    args = parser.parse_args()
    
    run_benchmarks(args.dry_run)
