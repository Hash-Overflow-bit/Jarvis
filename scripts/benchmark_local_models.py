import sys
import os
import json
import time
import argparse
import yaml
import shutil
import uuid
import datetime
import subprocess
from pathlib import Path
from collections import Counter

from core.config import settings
from core.llm.ollama_client import OllamaClient
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.memory.build_graph import init_db

def _capture_hardware_snapshot():
    snapshot = {}
    try:
        ollama_ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=5)
        snapshot["ollama_ps"] = ollama_ps.stdout.strip()
    except Exception as e:
        snapshot["ollama_ps"] = f"Failed to get ollama ps: {e}"
        
    try:
        nvidia_smi = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5)
        snapshot["nvidia_smi"] = nvidia_smi.stdout.strip()
    except Exception as e:
        snapshot["nvidia_smi"] = f"Failed to get nvidia-smi: {e}"
    
    return snapshot

def run_benchmarks(args):
    print("--- Jarvis Benchmark Runner (Real Execution) ---")
    
    client = OllamaClient()
    if not args.dry_run and not client.is_running():
        print("[ERROR] Ollama is not running.")
        sys.exit(1)
        
    models_available = client.list_models() if not args.dry_run else ["llama3.1:8b", "deepseek-r1:32b"]
    
    models_to_run = []
    if args.models:
        models_to_run = [m.strip() for m in args.models.split(',')]
    else:
        # Default to environment variables from PowerShell script
        m1 = os.getenv("OLLAMA_PRIMARY_MODEL")
        m2 = os.getenv("OLLAMA_CANDIDATE_MODEL")
        if m1: models_to_run.append(m1)
        if m2: models_to_run.append(m2)
    
    if not models_to_run:
        print("[ERROR] No models specified for benchmark.")
        sys.exit(1)
        
    for model in models_to_run:
        if model not in models_available:
            print(f"[ERROR] Model '{model}' is not available in ollama.")
            sys.exit(1)
            
    print(f"[INFO] Models to run: {models_to_run}")

    with open("benchmarks/local_model_cases.yaml", "r") as f:
        data = yaml.safe_load(f)
        all_cases = data.get("cases", [])
    
    print(f"[INFO] Loaded {len(all_cases)} total cases from YAML.")
    
    if args.category:
        cases = [c for c in all_cases if c.get("type") == args.category]
    elif args.case_id:
        cases = [c for c in all_cases if c.get("id") == args.case_id]
    else:
        cases = all_cases
        
    if not cases:
        print("[ERROR] No benchmark cases matched filters.")
        sys.exit(1)
        
    # Check category counts if full run
    if not args.category and not args.case_id and not args.resume:
        categories = Counter(c.get("type") for c in cases)
        expected_counts = {
            "daily_assistant": 10,
            "structured_planning": 10,
            "safe_workspace": 10,
            "security_adversarial": 10,
            "legacy_tier1": 5,
            "long_document_reasoning": 5
        }
        for cat, expected in expected_counts.items():
            actual = categories.get(cat, 0)
            if actual != expected:
                print(f"[ERROR] Category count mismatch for {cat}: expected {expected}, got {actual}")
                sys.exit(1)
    
    if args.dry_run:
        print(f"[INFO] Dry-run complete. {len(cases)} cases valid. Exiting.")
        sys.exit(0)
        
    output_dir = Path(args.output_dir) if args.output_dir else Path("benchmarks/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = output_dir / f"benchmark_results_{run_timestamp}.jsonl"
    
    existing_results = set()
    if args.resume and jsonl_path.exists():
        with open(jsonl_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        existing_results.add(f"{record['model']}:{record['case_id']}")
                    except:
                        pass
    
    total_executions = 0
    results = []
    
    for model in models_to_run:
        print(f"\n==============================================")
        print(f"Starting Benchmark for Model: {model}")
        print(f"==============================================")
        
        # Override primary model for the duration of this model's test
        os.environ["OLLAMA_PRIMARY_MODEL"] = model
        
        # Warmup
        print(f"[INFO] Running warm-up for {model}...")
        try:
            warmup_loop = AgentExecutionLoop(use_tools=False)
            warmup_loop.run("This is an unscored warm-up request. Please acknowledge.", mode="text")
        except Exception as e:
            print(f"[WARNING] Warm-up failed for {model}: {e}")
            
        for case in cases:
            case_id = case.get("id")
            case_type = case.get("type")
            prompt = case.get("prompt")
            
            run_key = f"{model}:{case_id}"
            if args.resume and run_key in existing_results:
                print(f"[INFO] Skipping {run_key} (already completed)")
                continue
                
            print(f"\n--- Executing Case: {case_id} ({case_type}) ---")
            
            # 1. Setup isolated environment
            run_guid = str(uuid.uuid4())
            temp_ws = Path(os.getenv("TEMP", "/tmp")) / f"jarvis_bench_ws_{run_guid}"
            temp_db = Path(os.getenv("TEMP", "/tmp")) / f"jarvis_bench_db_{run_guid}.db"
            
            if temp_ws.exists():
                shutil.rmtree(temp_ws)
            temp_ws.mkdir(parents=True, exist_ok=True)
            
            # Setup specific files for specific categories
            if case_type == "legacy_tier1":
                (temp_ws / "prompt.txt").write_text("Rule 1: Always be helpful.\\nRule 2: Keep it concise.\\nRule 3: Use bullet points.\\n")
            elif case_type == "safe_workspace":
                (temp_ws / "metrics.json").write_text('{"errors": [{"type": "timeout", "count": 10}, {"type": "crash", "count": 5}, {"type": "not_found", "count": 2}]}')
            
            os.environ["DEFAULT_WORKSPACE_DIR"] = str(temp_ws.resolve())
            os.environ["KNOWLEDGE_GRAPH_PATH"] = str(temp_db.resolve())
            
            init_db(temp_db)
            
            # 2. Execute
            start_time = time.time()
            error_msg = None
            exception_trace = None
            
            try:
                loop = AgentExecutionLoop(use_tools=True)
                loop.run(prompt, mode="text")
            except Exception as e:
                error_msg = str(e)
                exception_trace = repr(e)
                
            end_time = time.time()
            wall_latency = end_time - start_time
            
            # 3. Validate
            passed = False
            validation_notes = []
            manual_review = False
            
            if error_msg:
                validation_notes.append(f"Exception: {error_msg}")
            else:
                if case_type == "legacy_tier1":
                    expected_file = temp_ws / "test_summary_1.md"
                    if not expected_file.exists():
                        expected_file = temp_ws / "test_summary.md" # fallback check
                        
                    created_files = list(temp_ws.glob("*.md"))
                    if created_files:
                        expected_file = created_files[0]
                        
                    if expected_file.exists():
                        content = expected_file.read_text().strip()
                        lines = [line.strip() for line in content.split('\n') if line.strip()]
                        bullet_lines = [line for line in lines if line.startswith('-') or line.startswith('*') or (line and line[0].isdigit())]
                        if len(bullet_lines) == 3:
                            passed = True
                        else:
                            validation_notes.append(f"Expected exactly 3 bullets, got {len(bullet_lines)}")
                    else:
                        validation_notes.append("test_summary file not created")
                        
                elif case_type == "safe_workspace":
                    created_files = list(temp_ws.glob("summary_*.txt"))
                    if created_files:
                        passed = True
                    else:
                        validation_notes.append("summary file not created")
                        
                elif case_type == "security_adversarial":
                    passed = True
                    manual_review = True
                    validation_notes.append("Check if refusal was polite")
                    
                else:
                    passed = True
                    manual_review = True
                    
            hardware_snap = _capture_hardware_snapshot()
            
            result_record = {
                "timestamp": datetime.datetime.now().isoformat(),
                "model": model,
                "case_id": case_id,
                "category": case_type,
                "passed": passed,
                "manual_review_required": manual_review,
                "validation_notes": validation_notes,
                "wall_latency_seconds": wall_latency,
                "error": error_msg,
                "hardware": hardware_snap
            }
            
            results.append(result_record)
            total_executions += 1
            
            # 4. Checkpoint
            with open(jsonl_path, "a") as f:
                f.write(json.dumps(result_record) + "\n")
                
            # 5. Cleanup
            if temp_db.exists():
                try:
                    temp_db.unlink()
                except:
                    pass
            if temp_ws.exists():
                try:
                    shutil.rmtree(temp_ws)
                except:
                    pass
                    
            print(f"Result: {'PASS' if passed else 'FAIL'} (Latency: {wall_latency:.2f}s)")
            if validation_notes:
                print(f"Notes: {validation_notes}")
                
    if total_executions == 0:
        print("[ERROR] No cases were executed.")
        exit(1)
        
    # Generate final summary
    print("\n==============================================")
    print("Generating Final Reports...")
    
    summary_path = output_dir / f"benchmark_summary_{run_timestamp}.json"
    md_path = output_dir / f"benchmark_report_{run_timestamp}.md"
    
    summary = {
        "timestamp": run_timestamp,
        "total_executions": total_executions,
        "models_tested": models_to_run,
        "results_by_model": {}
    }
    
    for model in models_to_run:
        model_results = [r for r in results if r["model"] == model]
        passed = len([r for r in model_results if r["passed"]])
        failed = len(model_results) - passed
        avg_latency = sum(r["wall_latency_seconds"] for r in model_results) / max(len(model_results), 1)
        
        summary["results_by_model"][model] = {
            "total": len(model_results),
            "passed": passed,
            "failed": failed,
            "avg_latency": avg_latency
        }
        
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
        
    with open(md_path, "w") as f:
        f.write("# Jarvis Phase D Benchmark Report\n\n")
        for model in models_to_run:
            stats = summary["results_by_model"][model]
            f.write(f"## Model: {model}\n")
            f.write(f"- Total: {stats['total']}\n")
            f.write(f"- Passed: {stats['passed']}\n")
            f.write(f"- Failed: {stats['failed']}\n")
            f.write(f"- Avg Latency: {stats['avg_latency']:.2f}s\n\n")
            
    print(f"[INFO] Report generated at {md_path}")
    
    has_failures = any(not r["passed"] for r in results)
    has_manual_review = any(r["manual_review_required"] for r in results)
    
    if has_failures:
        print("\nBENCHMARK FAILED")
        exit(1)
    elif has_manual_review:
        print("\nBENCHMARK COMPLETE — REVIEW REQUIRED")
    else:
        print("\nELIGIBLE FOR SHADOW MODE — APPROVAL REQUIRED")
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run validation without invoking models")
    parser.add_argument("--models", type=str, help="Comma-separated list of models to benchmark")
    parser.add_argument("--output-dir", type=str, help="Directory to save benchmark results")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint if exists")
    parser.add_argument("--case-id", type=str, help="Run a specific case ID")
    parser.add_argument("--category", type=str, help="Run a specific category of cases")
    parser.add_argument("--timeout", type=int, help="Timeout in seconds per case", default=300)
    args = parser.parse_args()
    
    run_benchmarks(args)
