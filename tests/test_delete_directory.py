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
    1. delete_directory tool returns success=True
    2. target directory still physically exists on disk
    3. AgentExecutionLoop physical verification marks tool_success as False
    4. Jarvis does not claim the folder was successfully deleted.
    """
    target_dir = tmp_path / "stubborn_folder"
    target_dir.mkdir(exist_ok=True)
    assert target_dir.exists()

    loop = AgentExecutionLoop()

    # Mock tool_registry.execute to simulate a tool claiming success=True without actually deleting the directory
    mock_tool_result = {
        "success": True,
        "result": {"success": True, "message": "Fake deletion success"}
    }

    # Mock ollama chat for reflection if it gets called
    mock_chat_res = {
        "role": "assistant",
        "content": json.dumps({"plan": []})
    }

    with patch("core.orchestrator.agent_loop.tool_registry.execute", return_value=mock_tool_result):
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_chat_res):
            res = loop.run(f"Delete the folder {target_dir}")

            # 1. Verify target directory still exists
            assert target_dir.exists()
            # 2. Verify Jarvis does NOT claim successful deletion
            assert "successfully deleted" not in res.lower()
            assert "halted" in res.lower() or "physically exists" in res.lower() or "couldn't delete" in res.lower()

