import os
import json
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys

# To allow importing from scripts directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.benchmark_local_models import run_benchmarks

class DummyArgs:
    def __init__(self):
        self.dry_run = False
        self.models = "modelA,modelB"
        self.output_dir = "tests/test_benchmark_output"
        self.resume = False
        self.case_id = None
        self.category = None
        self.timeout = 300

@pytest.fixture
def mock_ollama_client():
    with patch("scripts.benchmark_local_models.OllamaClient") as mock_cls:
        client = mock_cls.return_value
        client.is_running.return_value = True
        client.list_models.return_value = ["modelA", "modelB", "modelC"]
        yield client

@pytest.fixture
def mock_hardware():
    with patch("scripts.benchmark_local_models._capture_hardware_snapshot") as m:
        m.return_value = {"ollama_ps": "mock", "nvidia_smi": "mock"}
        yield m

@pytest.fixture
def clean_env():
    orig_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(orig_env)

@pytest.fixture
def mock_agent_loop():
    with patch("scripts.benchmark_local_models.AgentExecutionLoop") as mock_cls:
        loop = mock_cls.return_value
        yield loop

def test_benchmark_runner_full_suite_execution(mock_ollama_client, mock_hardware, mock_agent_loop, clean_env, tmp_path):
    args = DummyArgs()
    args.output_dir = str(tmp_path)
    
    # Run the benchmark
    try:
        run_benchmarks(args)
    except SystemExit as e:
        # We expect it to complete and exit with 0, or it might not exit depending on the script
        pass

    # Check that 100 cases were run (50 * 2)
    # Plus 2 warmups
    assert mock_agent_loop.run.call_count == 102
    
    # Verify outputs
    jsonl_files = list(tmp_path.glob("*.jsonl"))
    assert len(jsonl_files) == 1
    
    lines = jsonl_files[0].read_text().strip().split("\n")
    assert len(lines) == 100 # Warmups are not saved

def test_benchmark_runner_model_failure(mock_ollama_client, clean_env, tmp_path):
    args = DummyArgs()
    args.models = "nonexistent_model"
    args.output_dir = str(tmp_path)
    
    with pytest.raises(SystemExit) as excinfo:
        run_benchmarks(args)
    assert excinfo.value.code == 1

def test_benchmark_runner_zero_execution(mock_ollama_client, clean_env, tmp_path):
    args = DummyArgs()
    args.category = "nonexistent_category"
    args.output_dir = str(tmp_path)
    
    with pytest.raises(SystemExit) as excinfo:
        run_benchmarks(args)
    assert excinfo.value.code == 1

def test_benchmark_checkpoint_resume(mock_ollama_client, mock_hardware, mock_agent_loop, clean_env, tmp_path):
    args = DummyArgs()
    args.output_dir = str(tmp_path)
    
    # Create a fake checkpoint file that marks 50 cases for modelA as done
    run_timestamp = "20990101_120000"
    with patch("scripts.benchmark_local_models.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value.strftime.return_value = run_timestamp
        mock_datetime.datetime.now.return_value.isoformat.return_value = "2099-01-01T12:00:00"
        
        jsonl_path = tmp_path / f"benchmark_results_{run_timestamp}.jsonl"
        with open(jsonl_path, "w") as f:
            for i in range(1, 11):
                f.write(json.dumps({"model": "modelA", "case_id": f"daily_assistant_{i}"}) + "\n")
        
        args.resume = True
        
        # It should run 90 scored cases + 2 warmups
        try:
            run_benchmarks(args)
        except SystemExit:
            pass
            
        assert mock_agent_loop.run.call_count == 92
