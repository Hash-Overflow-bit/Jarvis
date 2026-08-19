"""
tests/test_agent_loop.py
========================
Unit tests for the AgentExecutionLoop orchestrator.
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from core.orchestrator.agent_loop import AgentExecutionLoop


def test_agent_loop_generate_plan():
    loop = AgentExecutionLoop()
    
    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "file_scanner",
                    "arguments": {"directory": "/sandbox"}
                }
            ]
        })
    }
    
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_plan_res) as mock_chat:
        plan = loop._generate_plan("Scan the sandbox folder", "No facts")
        assert len(plan) == 1
        assert plan[0]["tool"] == "file_scanner"
        assert plan[0]["arguments"] == {"directory": "/sandbox"}


def test_agent_loop_generate_plan_native_fallback():
    loop = AgentExecutionLoop()
    
    # Mocking native function tool_calls dictionary format
    mock_native_res = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "directory_audit",
                    "arguments": {"directory": "/sandbox/folder"}
                }
            }
        ]
    }
    
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_native_res) as mock_chat:
        plan = loop._generate_plan("Audit folder", "")
        assert len(plan) == 1
        assert plan[0]["tool"] == "directory_audit"
        assert plan[0]["arguments"] == {"directory": "/sandbox/folder"}


def test_agent_loop_reflect_and_replan():
    loop = AgentExecutionLoop()
    
    mock_reflection_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "create_directory",
                    "arguments": {"directory": "/sandbox/fixed"}
                }
            ]
        })
    }
    
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_reflection_res) as mock_chat:
        revised = loop._reflect_and_replan(
            user_goal="Create a folder",
            failed_step={"step": 1, "tool": "create_directory", "arguments": {"directory": "/bad_path"}},
            error_message="Permission Denied",
            completed_steps=[]
        )
        assert len(revised) == 1
        assert revised[0]["tool"] == "create_directory"
        assert revised[0]["arguments"] == {"directory": "/sandbox/fixed"}


def test_agent_loop_execution_success():
    loop = AgentExecutionLoop()
    
    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "file_scanner",
                    "arguments": {"directory": "/sandbox"}
                }
            ]
        })
    }
    
    mock_tool_res = {
        "success": True,
        "result": {"files": ["file1.txt"]}
    }
    
    mock_synth_res = {
        "role": "assistant",
        "content": "I successfully scanned the folder and found file1.txt."
    }
    
    # Mock calls sequentially
    mock_chat_responses = [mock_plan_res, mock_synth_res]
    
    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=mock_chat_responses):
        with patch("core.orchestrator.agent_loop.tool_registry.execute", return_value=mock_tool_res) as mock_exec:
            res = loop.run("Scan files")
            assert "file1.txt" in res
            mock_exec.assert_called_once_with("file_scanner", {"directory": "/sandbox"}, mode="text")


def test_agent_loop_execution_with_reflection():
    loop = AgentExecutionLoop()
    
    # Step 1: initial plan
    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "write_file",
                    "arguments": {"filepath": "/bad/file.txt", "content": "hello"}
                }
            ]
        })
    }
    
    # Step 2: tool execution failure (returns success=False)
    mock_failed_exec = {
        "success": False,
        "error": "PermissionError"
    }
    
    # Step 3: reflector replanning
    mock_replan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "write_file",
                    "arguments": {"filepath": "/sandbox/file.txt", "content": "hello"}
                }
            ]
        })
    }
    
    # Step 4: tool execution success (returns success=True)
    mock_success_exec = {
        "success": True,
        "result": {"message": "success"}
    }
    
    # Step 5: final synthesis
    mock_synth_res = {
        "role": "assistant",
        "content": "Fixed and written successfully."
    }
    
    mock_chat_responses = [mock_plan_res, mock_replan_res, mock_synth_res]
    mock_tool_responses = [mock_failed_exec, mock_success_exec]
    
    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=mock_chat_responses):
        with patch("core.orchestrator.agent_loop.tool_registry.execute", side_effect=mock_tool_responses) as mock_exec:
            res = loop.run("Save hello to file")
            assert "written successfully" in res
            assert mock_exec.call_count == 2
