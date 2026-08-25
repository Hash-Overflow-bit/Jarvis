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
            # Since /sandbox is auto-fixed to the workspace directory by the sanitizer,
            # we must expect the fixed path, not the raw /sandbox path.
            from core.config import settings
            expected_path = str(settings.default_workspace_dir).replace("\\", "/").rstrip("/") + "/"
            mock_exec.assert_called_once_with("file_scanner", {"directory": expected_path}, mode="text")


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
                    "arguments": {"filepath": "/workspace/file.txt", "content": "hello"}
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


def test_agent_loop_sanitizer_auto_remap_subagent():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "LedgerBookkeeper",
            "arguments": {"task": "Scan transactions"}
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "delegate_task"
    assert sanitized[0]["arguments"]["agent_name"] == "LedgerBookkeeper"
    assert sanitized[0]["arguments"]["task_description"] == "Scan transactions"


def test_agent_loop_sanitizer_reject_invalid_tool():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "csv_parser",
            "arguments": {}
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 0


def test_agent_loop_tool_call_leakage_recovery():
    loop = AgentExecutionLoop()
    # Mock LLM returning a raw tool call string in fallback mode
    mock_chat_res = {
        "role": "assistant",
        "content": 'Jarvis: {"name": "write_file", "parameters": {"filepath": "agents/test_leak.json", "content": "{\\"role\\": \\"CEO\\"}"}}'
    }

    mock_empty_plan = {
        "role": "assistant",
        "content": ""
    }

    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=[mock_empty_plan, mock_chat_res]):
        with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": True, "result": {}}) as mock_exec:
            res = loop.run("Create agents/test_leak.json containing role CEO")
            assert "Created file: agents/test_leak.json" in res
            mock_exec.assert_called_once_with("write_file", {"filepath": "agents/test_leak.json", "content": '{"role": "CEO"}'})


def test_agent_loop_sanitizer_auto_remap_skyvern_local():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "skyvern_tool",
            "arguments": {"url": "", "navigation_goal": "create a folder named hey on desktop"}
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "create_directory"
    assert "hey" in sanitized[0]["arguments"]["directory"]


def test_agent_loop_sanitizer_auto_remap_invalid_delegate_task():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "delegate_task",
            "arguments": {
                "agent_name": "FileManagementToolkit",
                "task_description": "Create a new folder named 'hey' on the user's desktop."
            }
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "create_directory"
    assert "hey" in sanitized[0]["arguments"]["directory"]

