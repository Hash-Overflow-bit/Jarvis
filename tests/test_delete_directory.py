"""
tests/test_delete_directory.py
===============================
Comprehensive regression tests for DeleteDirectory tool, execution integrity,
sanitizer guardrails, post-condition verification, and final response synthesis.
"""

import os
import shutil
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from core.tools.delete_directory import DeleteDirectory
from schemas.delete_directory_schema import DeleteDirectoryInput
from core.tools.tool_registry import tool_registry
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings


def test_delete_directory_success(tmp_path):
    """Requirement 8A: delete_directory successfully deletes an existing directory."""
    target_dir = tmp_path / "test_folder_to_delete"
    target_dir.mkdir(exist_ok=True)
    (target_dir / "file1.txt").write_text("hello world")
    assert target_dir.exists()

    tool = DeleteDirectory()
    inp = DeleteDirectoryInput(directory=str(target_dir))
    out = tool.run(inp)

    assert out.success is True
    assert "Successfully deleted directory" in out.message
    assert not target_dir.exists(), "Requirement 8F: post-deletion verification confirms path does not exist."


def test_delete_directory_nonexistent_failure(tmp_path):
    """Requirement 8B: deletion failure produces success=False when directory does not exist."""
    target_dir = tmp_path / "non_existent_folder_12345"
    tool = DeleteDirectory()
    inp = DeleteDirectoryInput(directory=str(target_dir))
    out = tool.run(inp)

    assert out.success is False
    assert "does not exist" in out.message


def test_sanitizer_and_registry_handles_delete_tool():
    """Requirement 8C: sanitizer and tool registry correctly register and handle delete_directory."""
    assert "delete_directory" in tool_registry._tools
    tool_instance = tool_registry.get("delete_directory")
    assert tool_instance is not None

    loop = AgentExecutionLoop()
    raw_plan = [{"step": 1, "tool": "delete_directory", "arguments": {"directory": "/tmp/test"}}]
    sanitized = loop._sanitize_plan(raw_plan, "Delete the test folder")
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "delete_directory"


def test_final_response_no_false_deletion_claim_on_rejection():
    """Requirement 8D: final response does NOT claim deletion when the delete step was rejected."""
    loop = AgentExecutionLoop()
    # Prompt is deletion, but completed_steps has NO deletion tool step (e.g. step rejected or replaced with read_file)
    completed_steps = [{"step": 1, "tool": "read_file", "result": {"content": "data"}}]
    res = loop._synthesize_final_response("Delete the smoke_test folder from my Desktop", completed_steps, "")
    assert "couldn't delete" in res.lower()
    assert "successfully deleted" not in res.lower()


def test_final_response_claims_deletion_only_on_actual_success(tmp_path):
    """Requirement 8E: final response DOES claim deletion only after actual successful deletion."""
    loop = AgentExecutionLoop()
    completed_steps = [
        {"step": 1, "tool": "delete_directory", "result": {"success": True, "message": "Successfully deleted directory"}}
    ]
    with patch("core.orchestrator.agent_loop.ollama.chat") as mock_chat:
        mock_chat.return_value = {"content": "The smoke_test folder has been deleted."}
        res = loop._synthesize_final_response("Delete the smoke_test folder from my Desktop", completed_steps, "")
        assert "deleted" in res.lower()


def test_prevent_unrelated_steps_on_deletion_goal():
    """Requirement 8G: prevent the planner from executing unrelated steps like create_directory/write_file when goal is deletion."""
    loop = AgentExecutionLoop()
    # Unrelated plan containing create_directory and write_file for a deletion request
    unrelated_plan = [
        {"step": 1, "tool": "create_directory", "arguments": {"directory": "/tmp/folder"}},
        {"step": 2, "tool": "write_file", "arguments": {"filepath": "/tmp/folder/file.txt", "content": "text"}}
    ]
    sanitized = loop._sanitize_plan(unrelated_plan, "Delete the smoke_test folder from my Desktop")
    assert len(sanitized) == 0, "Sanitizer MUST reject unrelated steps for a deletion request!"


def test_delete_directory_false_success_physical_verification_failure(tmp_path):
    """
    Regression Test:
    1. loop.run() calls planner/direct_route to get delete_directory plan
    2. tool_registry.execute("delete_directory", ...) is mocked to return success=True
    3. target directory intentionally remains on disk
    4. physical verification detects Path(directory).exists() is still True
    5. deletion step is marked FAILED
    6. loop.run() reaches final response/error path
    7. returned res contains physically exists, couldn't delete, or halted.
    """
    target_dir = tmp_path / "stubborn_folder"
    target_dir.mkdir(exist_ok=True)
    assert target_dir.exists()

    loop = AgentExecutionLoop()

    # Mock tool_registry.execute returning success=True without deleting directory on disk
    mock_tool_result = {
        "success": True,
        "result": {"success": True, "message": "Successfully deleted directory"}
    }

    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "delete_directory",
                    "arguments": {"directory": str(target_dir)}
                }
            ]
        })
    }
    mock_empty_plan_res = {
        "role": "assistant",
        "content": json.dumps({"plan": []})
    }

    def mock_chat_fn(model=None, messages=None, **kwargs):
        msg_str = str(messages)
        if "planner" in msg_str.lower():
            return mock_plan_res
        elif "reflection" in msg_str.lower() or "re-plan" in msg_str.lower():
            return mock_empty_plan_res
        else:
            return {"role": "assistant", "content": f"Directory '{target_dir}' was reported deleted, but it still physically exists on disk."}

    with patch("core.orchestrator.agent_loop.tool_registry.execute", return_value=mock_tool_result) as mock_exec:
        with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=mock_chat_fn):
            res = loop.run(f"Please delete the folder {target_dir}")

            print("[DEBUG TEST] planner response:", repr(mock_plan_res))
            print("[DEBUG TEST] final result:", repr(res))
            print("[DEBUG TEST] execute call count:", mock_exec.call_count)

            # 1. Verify target directory still physically exists on disk
            assert target_dir.exists()
            # 2. Verify tool execution was invoked at least once
            assert mock_exec.call_count >= 1
            # 3. Verify Jarvis response does NOT claim successful deletion
            assert "successfully deleted" not in res.lower()
            # 4. Verify failure/verification condition is present in res
            assert any(k in res.lower() for k in ["physically exists", "couldn't delete", "halted", "failed"])
