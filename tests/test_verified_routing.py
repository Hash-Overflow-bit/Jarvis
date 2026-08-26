import pytest
import json
from unittest.mock import patch, MagicMock
from core.orchestrator.agent_loop import AgentExecutionLoop

def test_unknown_file_creation_claim_returns_no_evidence():
    """
    Test: Unknown file creation claim returns no-evidence response.
    No write tools are called. No guessed path appears.
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "Did you create a file named annual_financial_summary_2026.pdf for me?"
    
    # Run _direct_route
    res = loop._direct_route(prompt, recalled_facts="")
    
    assert isinstance(res, str)
    assert "I don't have verified evidence that I created annual_financial_summary_2026.pdf" in res
    assert "/Desktop/" not in res # No guessed path

def test_known_successfully_created_file_returns_exact_verified_path():
    """
    Test: Known successfully created file returns its exact verified path.
    """
    loop = AgentExecutionLoop(use_tools=True)
    
    # Mock session history
    loop.history = [
        {
            "role": "assistant",
            "tool_calls": [{
                "function": {
                    "name": "write_file",
                    "arguments": {"filepath": "/Users/m2air/Desktop/Jarvis/annual_financial_summary_2026.pdf"}
                }
            }]
        },
        {
            "role": "tool",
            "name": "write_file",
            "content": json.dumps({"success": True})
        }
    ]
    
    prompt = "Did you create a file named annual_financial_summary_2026.pdf for me?"
    res = loop._direct_route(prompt, recalled_facts="")
    
    assert isinstance(res, str)
    assert "Yes, I have verified evidence that I created annual_financial_summary_2026.pdf" in res
    assert "/Users/m2air/Desktop/Jarvis/annual_financial_summary_2026.pdf" in res

def test_failed_write_never_counts_as_creation():
    """
    Test: Failed write never counts as creation.
    """
    loop = AgentExecutionLoop(use_tools=True)
    
    # Mock session history with failed write
    loop.history = [
        {
            "role": "assistant",
            "tool_calls": [{
                "function": {
                    "name": "write_file",
                    "arguments": {"filepath": "/Users/m2air/Desktop/Jarvis/annual_financial_summary_2026.pdf"}
                }
            }]
        },
        {
            "role": "tool",
            "name": "write_file",
            "content": json.dumps({"success": False, "error": "Permission denied"})
        }
    ]
    
    prompt = "Did you create annual_financial_summary_2026.pdf?"
    res = loop._direct_route(prompt, recalled_facts="")
    
    assert isinstance(res, str)
    assert "I don't have verified evidence that I created annual_financial_summary_2026.pdf" in res

def test_does_file_exist_generates_file_scanner_call():
    """
    Test: "Does file exist?" generates file_scanner call instead of relying only on memory.
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "Does annual_financial_summary_2026.pdf currently exist?"
    
    plan = loop._direct_route(prompt, recalled_facts="")
    
    assert isinstance(plan, list)
    assert len(plan) == 1
    assert plan[0]["tool"] == "file_scanner"
    assert plan[0]["arguments"]["query"] == "annual_financial_summary_2026.pdf"

def test_recalled_facts_knowledge_graph_fallback():
    """
    Test: If session history is empty, it checks recalled_facts for provenance.
    """
    loop = AgentExecutionLoop(use_tools=True)
    loop.history = []
    
    prompt = "Where did you save annual_financial_summary_2026.pdf?"
    recalled_facts = "- [Agent] wrote file [annual_financial_summary_2026.pdf] at path [/workspace/annual_financial_summary_2026.pdf]"
    
    res = loop._direct_route(prompt, recalled_facts=recalled_facts)
    
    assert isinstance(res, str)
    assert "Yes, I have verified evidence that I created annual_financial_summary_2026.pdf" in res
    assert "/workspace/annual_financial_summary_2026.pdf" in res

def test_does_file_exist_synthesis_exact_match():
    """
    Test: scanner success + exact file present -> YES + path
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "Does manual_exists_test.txt exist on my Desktop?"
    
    # Mock completed steps from a successful file_scanner run
    completed_steps = [{
        "step": 1,
        "tool": "file_scanner",
        "arguments": {"directory": "/Users/m2air/Desktop"},
        "result": {
            "files": [
                {"name": "other_file.txt", "path": "/Users/m2air/Desktop/other_file.txt"},
                {"name": "manual_exists_test.txt", "path": "/Users/m2air/Desktop/manual_exists_test.txt"}
            ]
        }
    }]
    
    res = loop._synthesize_final_response(prompt, completed_steps, recalled_facts="")
    
    assert "Yes. manual_exists_test.txt exists on your Desktop at /Users/m2air/Desktop/manual_exists_test.txt." in res

def test_does_file_exist_synthesis_no_match():
    """
    Test: scanner success + no match -> NO
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "Does manual_exists_test.txt exist on my Desktop?"
    
    completed_steps = [{
        "step": 1,
        "tool": "file_scanner",
        "arguments": {"directory": "/Users/m2air/Desktop"},
        "result": {
            "files": [
                {"name": "other_file.txt", "path": "/Users/m2air/Desktop/other_file.txt"}
            ]
        }
    }]
    
    res = loop._synthesize_final_response(prompt, completed_steps, recalled_facts="")
    
    assert "No. I verified your Desktop and manual_exists_test.txt does not exist there." in res

def test_does_file_exist_synthesis_partial_match_does_not_count():
    """
    Test: partial filename match does not count as exact match
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "Does manual_exists_test.txt exist on my Desktop?"
    
    completed_steps = [{
        "step": 1,
        "tool": "file_scanner",
        "arguments": {"directory": "/Users/m2air/Desktop"},
        "result": {
            "files": [
                {"name": "old_manual_exists_test.txt", "path": "/Users/m2air/Desktop/old_manual_exists_test.txt"}
            ]
        }
    }]
    
    res = loop._synthesize_final_response(prompt, completed_steps, recalled_facts="")
    
    assert "No. I verified your Desktop and manual_exists_test.txt does not exist there." in res

def test_does_file_exist_synthesis_scanner_failure():
    """
    Test: scanner failure -> returns unable-to-verify
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "Does manual_exists_test.txt exist on my Desktop?"
    
    completed_steps = [{
        "step": 1,
        "tool": "file_scanner",
        "arguments": {"directory": "/Users/m2air/Desktop"},
        "result": None # Failed execution
    }]
    
    res = loop._synthesize_final_response(prompt, completed_steps, recalled_facts="")
    
    assert "I couldn't verify the file's existence." in res

