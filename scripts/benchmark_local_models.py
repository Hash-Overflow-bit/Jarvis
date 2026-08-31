import os
import json
import time
import argparse
import yaml
from pathlib import Path
from core.config import settings
from core.llm.ollama_client import OllamaClient

def setup_benchmark_env():
    """Validates the environment before running benchmarks."""
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

def run_benchmarks():
    """Runs the predefined benchmark cases for both models."""
    if not setup_benchmark_env():
        print("Benchmark aborted due to environment validation failure.")
        return
        
    print("\n[INFO] Both models are available. Proceeding with benchmark...")
    
    with open("benchmarks/local_model_cases.yaml", "r") as f:
        data = yaml.safe_load(f)
        cases = data.get("cases", [])
        
    print(f"[INFO] Loaded {len(cases)} benchmark cases from YAML.")
    assert len(cases) == 50, f"Expected 50 benchmark cases, but found {len(cases)}"
    
    metrics = []
    
    # Here we would normally iterate over models and cases
    # For now, this is a dry-run scaffolding.
    print("[INFO] Scaffolding complete. Real benchmark execution requires the Windows test environment.")
    print("Metrics structure ready for D7.")
    
if __name__ == "__main__":
    run_benchmarks()
