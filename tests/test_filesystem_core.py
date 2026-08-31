"""
tests/test_filesystem_core.py
=============================
Regression tests for the deterministic filesystem core pipeline.
"""
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.tools.path_resolver import PathResolver
from core.tools.sandbox_enforcer import SandboxEnforcer
from core.tools.write_file import WriteFile
from schemas.write_file_schema import WriteFileInput
from core.tools.read_file import ReadFile, ReadFileInput
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.orchestrator.agent_loop import AgentExecutionLoop

# ──────────────────────────────────────────────────────────────────────
# Test 1: PathResolver aliases (desktop, documents, home)
# ──────────────────────────────────────────────────────────────────────
def test_path_resolver_aliases():
    """PathResolver must map aliases correctly."""
    home = Path.home()
    
    # Desktop
    desktop_res = PathResolver.resolve("desktop/test.txt")
    assert "desktop" in str(desktop_res).lower()
    
    # Home
    home_res = PathResolver.resolve("~/test.txt")
    assert str(home_res) == str(home / "test.txt")
    
    # Prevent username hallucination
    hallucinated = PathResolver.resolve("/Users/username/Desktop/test.txt")
    assert "username" not in str(hallucinated)

# ──────────────────────────────────────────────────────────────────────
# Test 2: Path Traversal Protection
# ──────────────────────────────────────────────────────────────────────
def test_sandbox_path_traversal():
    """SandboxEnforcer must prevent traversing out of the sandbox."""
    enforcer = SandboxEnforcer(allowed_roots=[Path("/tmp/jarvis_sandbox")])
    with pytest.raises(PermissionError):
        enforcer.validate("/tmp/jarvis_sandbox/../../etc/passwd")

# ──────────────────────────────────────────────────────────────────────
# Test 3: Directory vs File Errors (read_file)
# ──────────────────────────────────────────────────────────────────────
def test_read_file_directory_error(tmp_path):
    """ReadFile should return a clear error if asked to read a directory."""
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    
    tool = ReadFile()
    with patch("core.tools.read_file.enforcer.validate", return_value=test_dir):
        result = tool.run(ReadFileInput(filepath=str(test_dir)))
        assert result.success is False
        assert "is a directory" in result.error

def test_read_file_missing_error(tmp_path):
    """ReadFile should return a clear error if file does not exist."""
    missing = tmp_path / "missing.txt"
    tool = ReadFile()
    with patch("core.tools.read_file.enforcer.validate", return_value=missing):
        result = tool.run(ReadFileInput(filepath=str(missing)))
        assert result.success is False
        assert "does not exist" in result.error

# ──────────────────────────────────────────────────────────────────────
# Test 4: WriteFile Create vs Overwrite vs Append
# ──────────────────────────────────────────────────────────────────────
def test_write_file_create_prevents_overwrite(tmp_path):
    """WriteFile mode 'create' must fail if file exists."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("initial")
    
    tool = WriteFile()
    from core.config import settings
    with patch("core.tools.write_file.enforcer.validate", return_value=test_file), \
         patch.object(settings.__class__, "default_workspace_dir", property(lambda self: tmp_path)):
        result = tool.run(WriteFileInput(filepath=str(test_file), content="new", mode="create"))
        assert result.success is False
        assert "File already exists" in result.message

def test_write_file_overwrite_succeeds(tmp_path):
    """WriteFile mode 'overwrite' must succeed if file exists."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("initial")
    
    tool = WriteFile()
    from core.config import settings
    with patch("core.tools.write_file.enforcer.validate", return_value=test_file), \
         patch.object(settings.__class__, "default_workspace_dir", property(lambda self: tmp_path)):
        result = tool.run(WriteFileInput(filepath=str(test_file), content="new", mode="overwrite"))
        assert result.success is True
        assert test_file.read_text() == "new"

def test_write_file_append(tmp_path):
    """WriteFile mode 'append' must append to the file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello ")
    
    tool = WriteFile()
    from core.config import settings
    with patch("core.tools.write_file.enforcer.validate", return_value=test_file), \
         patch.object(settings.__class__, "default_workspace_dir", property(lambda self: tmp_path)):
        result = tool.run(WriteFileInput(filepath=str(test_file), content="world", mode="append"))
        assert result.success is True
        assert test_file.read_text() == "hello world"

# ──────────────────────────────────────────────────────────────────────
# Test 5: Exact Previous-Artifact Saving
# ──────────────────────────────────────────────────────────────────────
@patch("core.tools.tool_registry.tool_registry.execute")
def test_exact_artifact_saving(mock_exec):
    """If USE_GENERATED_ARTIFACT is passed, it should inject exact artifact content."""
    mock_exec.return_value = {"success": True, "result": {"message": "Success"}}
    
    loop = AgentExecutionLoop()
    loop.session_artifacts["last_generated_document"] = {"content": "Exact Artifact Content"}
    
    loop.run("write a file", mode="text")
    # For testing, we mock _generate_plan to return a write_file step with USE_GENERATED_ARTIFACT
    loop._generate_plan = MagicMock(return_value=[
        {"step": 1, "tool": "write_file", "arguments": {"filepath": "test.txt", "content": "<USE_GENERATED_ARTIFACT>"}}
    ])
    
    loop.run("test artifact save", mode="text")
    
    # The path will be sanitized into an absolute path on Desktop
    args = mock_exec.call_args.args
    kwargs = mock_exec.call_args.kwargs
    assert args[0] == "write_file"
    assert "test.txt" in args[1]["filepath"]
    assert args[1]["content"] == "Exact Artifact Content"
    assert kwargs.get("mode") == "text"

# ──────────────────────────────────────────────────────────────────────
# Test 6: Missing Artifact Creating No File
# ──────────────────────────────────────────────────────────────────────
@patch("core.tools.tool_registry.tool_registry.execute")
def test_missing_artifact_creates_no_file(mock_exec):
    """If USE_GENERATED_ARTIFACT is passed but no artifact exists, execution must halt."""
    loop = AgentExecutionLoop()
    # Ensure no artifact exists
    loop.session_artifacts.pop("last_generated_document", None)
    
    loop._generate_plan = MagicMock(return_value=[
        {"step": 1, "tool": "write_file", "arguments": {"filepath": "test.txt", "content": "<USE_GENERATED_ARTIFACT>"}}
    ])
    
    result = loop.run("test missing artifact", mode="text")
    
    # tool_registry should NOT be called for write_file
    mock_exec.assert_not_called()
    assert "filesystem error" in result.lower() or "no generated document" in result.lower()

# ──────────────────────────────────────────────────────────────────────
# Test 7: Failed Mutation Causes No Replanning
# ──────────────────────────────────────────────────────────────────────
@patch("core.tools.tool_registry.tool_registry.execute")
def test_failed_mutation_halts_execution(mock_exec):
    """If a filesystem tool fails, the loop must return immediately and not proceed."""
    # Mock execute to fail
    mock_exec.return_value = {"success": False, "error": "Disk full during write"}
    
    loop = AgentExecutionLoop()
    loop._generate_plan = MagicMock(return_value=[
        {"step": 1, "tool": "write_file", "arguments": {"filepath": "test.txt", "content": "data"}},
        {"step": 2, "tool": "web_search", "arguments": {"query": "something"}}
    ])
    
    result = loop.run("test fail", mode="text")
    
    # web_search should NOT be executed
    assert mock_exec.call_count == 1
    assert "filesystem error" in result.lower()


