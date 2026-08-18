"""
tests/test_file_tools.py
========================
Unit tests for FileScanner, FileCleanup, and DirectoryAudit tools.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.tools.directory_audit import DirectoryAudit
from core.tools.file_cleanup import FileCleanup
from core.tools.file_scanner import FileScanner
from core.tools.sandbox_enforcer import SandboxEnforcer
from schemas.directory_audit_schema import DirectoryAuditInput
from schemas.file_cleanup_schema import FileCleanupInput
from schemas.file_scanner_schema import FileScannerInput


@pytest.fixture
def temp_sandbox_env():
    """Sets up a mock sandbox environment with various files for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox_path = Path(temp_dir).resolve()
        
        # Create directories
        logs_dir = sandbox_path / "logs"
        logs_dir.mkdir()
        temp_files_dir = sandbox_path / "logs" / "temp"
        temp_files_dir.mkdir()
        
        # Create some files with content
        # 1. logs/info.log
        f1 = logs_dir / "info.log"
        f1.write_text("Hello info log data" * 150)  # ~2.8 KB = ~0.0027 MB
        
        # 2. logs/error.log
        f2 = logs_dir / "error.log"
        f2.write_text("An error occurred!" * 150)  # ~2.7 KB = ~0.0025 MB
        
        # 3. logs/temp/old.tmp
        f3 = temp_files_dir / "old.tmp"
        f3.write_text("temp data " * 50000)   # ~500 KB = ~0.47 MB
        
        # 4. readme.txt
        f4 = sandbox_path / "readme.txt"
        f4.write_text("Readme contents here.")  # 21 bytes
        
        yield sandbox_path, f1, f2, f3, f4


def test_file_scanner_listing_and_filtering(temp_sandbox_env):
    sandbox_path, f1, f2, f3, f4 = temp_sandbox_env
    
    # Configure enforcer to allow our temp sandbox
    with patch("core.tools.file_scanner.enforcer", SandboxEnforcer([sandbox_path])):
        scanner = FileScanner()
        
        # 1. Scan everything (no filters)
        inp = FileScannerInput(directory=str(sandbox_path))
        out = scanner.run(inp)
        assert out.total_count == 4
        # Verify sizes are calculated
        assert out.total_size_mb > 0
        file_paths = [f["path"] for f in out.files]
        assert str(f1) in file_paths
        assert str(f3) in file_paths
        
        # 2. Filter by extension
        inp_ext = FileScannerInput(directory=str(sandbox_path), extension_filter=".log")
        out_ext = scanner.run(inp_ext)
        assert out_ext.total_count == 2
        file_paths_ext = [f["path"] for f in out_ext.files]
        assert str(f1) in file_paths_ext
        assert str(f2) in file_paths_ext
        assert str(f3) not in file_paths_ext
        
        # 3. Filter by size
        # old.tmp is ~10 KB = ~0.0095 MB. Other files are tiny (~20 bytes = 0.00002 MB).
        # Let's filter by min_size_mb=0.005
        inp_size = FileScannerInput(directory=str(sandbox_path), min_size_mb=0.005)
        out_size = scanner.run(inp_size)
        assert out_size.total_count == 1
        assert out_size.files[0]["path"] == str(f3)


def test_directory_audit_tree_generation(temp_sandbox_env):
    sandbox_path, _, _, _, _ = temp_sandbox_env
    
    with patch("core.tools.directory_audit.enforcer", SandboxEnforcer([sandbox_path])):
        audit = DirectoryAudit()
        
        inp = DirectoryAuditInput(directory=str(sandbox_path))
        out = audit.run(inp)
        
        assert out.folder_count == 2  # logs, logs/temp
        assert out.file_count == 4    # info.log, error.log, old.tmp, readme.txt
        assert "logs/" in out.tree_representation
        assert "info.log" in out.tree_representation
        assert "readme.txt" in out.tree_representation


def test_file_cleanup_with_send2trash(temp_sandbox_env):
    sandbox_path, f1, f2, f3, f4 = temp_sandbox_env
    
    with patch("core.tools.file_cleanup.enforcer", SandboxEnforcer([sandbox_path])):
        cleanup = FileCleanup()
        
        # We delete only .log files
        inp = FileCleanupInput(directory=str(sandbox_path), extension_filter=".log")
        
        # Mock send2trash to bypass actual OS recycling bin (since it might not exist in headless environments)
        with patch("core.tools.file_cleanup.send2trash") as mock_send2trash:
            out = cleanup.run(inp)
            assert out.total_freed_mb > 0
            assert len(out.deleted_files) == 2
            assert str(f1) in out.deleted_files
            assert str(f2) in out.deleted_files
            assert mock_send2trash.call_count == 2


def test_file_cleanup_wsl_fallback(temp_sandbox_env):
    sandbox_path, f1, f2, f3, f4 = temp_sandbox_env
    
    # Configure enforcer
    enforcer_mock = SandboxEnforcer([sandbox_path])
    
    with patch("core.tools.file_cleanup.enforcer", enforcer_mock):
        cleanup = FileCleanup()
        
        # Delete readme.txt
        inp = FileCleanupInput(directory=str(sandbox_path), extension_filter=".txt")
        
        # Mock send2trash to fail (raising Exception) to trigger fallback
        with patch("core.tools.file_cleanup.send2trash", side_effect=Exception("WSL no DBus error")):
            out = cleanup.run(inp)
            assert len(out.deleted_files) == 1
            assert out.deleted_files[0] == str(f4)
            
            # Check fallback trash folder was created inside sandbox
            trash_readme = sandbox_path / ".jarvis_trash" / "readme.txt"
            assert trash_readme.exists()
            assert trash_readme.read_text() == "Readme contents here."
            # Original file should have been moved
            assert not f4.exists()


def test_directory_audit_empty_dir(temp_sandbox_env):
    sandbox_path, _, _, _, _ = temp_sandbox_env
    empty_dir = sandbox_path / "empty_folder"
    empty_dir.mkdir()
    
    with patch("core.tools.directory_audit.enforcer", SandboxEnforcer([sandbox_path])):
        audit = DirectoryAudit()
        inp = DirectoryAuditInput(directory=str(empty_dir))
        out = audit.run(inp)
        
        assert out.folder_count == 0
        assert out.file_count == 0
        assert "(empty folder)" in out.tree_representation


def test_file_cleanup_filters(temp_sandbox_env):
    import time
    sandbox_path, f1, f2, f3, f4 = temp_sandbox_env
    # f1: info.log (~0.0027 MB)
    # f2: error.log (~0.0025 MB)
    # f3: old.tmp (~0.47 MB)
    # f4: readme.txt (21 bytes)
    
    # Set f3's modification time to 5 days ago (older than 3 days)
    past_time = time.time() - (5 * 24 * 3600)
    os.utime(str(f3), (past_time, past_time))
    
    # Set f1's modification time to 1 day ago (younger than 3 days)
    recent_time = time.time() - (1 * 24 * 3600)
    os.utime(str(f1), (recent_time, recent_time))

    with patch("core.tools.file_cleanup.enforcer", SandboxEnforcer([sandbox_path])):
        cleanup = FileCleanup()

        # 1. Clean files older than 3 days (only f3 should be matched)
        inp_age = FileCleanupInput(directory=str(sandbox_path), min_age_days=3.0)
        with patch("core.tools.file_cleanup.send2trash") as mock_send2trash:
            out_age = cleanup.run(inp_age)
            assert len(out_age.deleted_files) == 1
            assert out_age.deleted_files[0] == str(f3)
            assert mock_send2trash.call_count == 1

        # 2. Clean files larger than 0.1 MB (only f3 should be matched)
        inp_size = FileCleanupInput(directory=str(sandbox_path), min_size_mb=0.1)
        with patch("core.tools.file_cleanup.send2trash") as mock_send2trash:
            out_size = cleanup.run(inp_size)
            assert len(out_size.deleted_files) == 1
            assert out_size.deleted_files[0] == str(f3)
            assert mock_send2trash.call_count == 1


def test_session_manager_tool_execution(temp_sandbox_env):
    sandbox_path, f1, f2, f3, f4 = temp_sandbox_env
    
    # We will mock ollama.chat to return a tool call first, then return a final response
    from core.state.session_manager import SessionManager
    
    # 1. Instantiate SessionManager with use_tools=True
    session = SessionManager(use_tools=True)
    
    # We mock ollama.chat
    # First call: returns tool_calls
    # Second call: returns natural language text
    mock_responses = [
        # First call return message with tool call
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "file_scanner",
                        "arguments": {
                            "directory": str(sandbox_path),
                            "extension_filter": ".log"
                        }
                    }
                }
            ]
        },
        # Second call response
        {
            "role": "assistant",
            "content": "I scanned the directory and found two log files: info.log and error.log."
        }
    ]
    
    with patch("core.tools.file_scanner.enforcer", SandboxEnforcer([sandbox_path])):
        with patch("core.llm.ollama_client.ollama.chat", side_effect=mock_responses) as mock_chat:
            response = session.chat("Show me the log files.")
            
            # Verify response matches
            assert response == "I scanned the directory and found two log files: info.log and error.log."
            
            # Check mock chat calls
            assert mock_chat.call_count == 2
            
            # Check history:
            # - System prompt
            # - User message
            # - Assistant tool call message
            # - Tool response message
            # - Assistant final response
            assert len(session.history) == 5
            assert session.history[1]["role"] == "user"
            assert session.history[2]["role"] == "assistant"
            assert "tool_calls" in session.history[2]
            assert session.history[3]["role"] == "tool"
            assert "info.log" in session.history[3]["content"]
            assert session.history[4]["role"] == "assistant"


def test_create_directory_and_write_file(temp_sandbox_env):
    sandbox_path, _, _, _, _ = temp_sandbox_env
    
    from core.tools.create_directory import CreateDirectory
    from core.tools.write_file import WriteFile
    from schemas.create_directory_schema import CreateDirectoryInput
    from schemas.write_file_schema import WriteFileInput
    
    # 1. Test CreateDirectory inside sandbox
    creator = CreateDirectory()
    new_dir = sandbox_path / "subfolder"
    inp_create = CreateDirectoryInput(directory=str(new_dir))
    
    with patch("core.tools.create_directory.enforcer", SandboxEnforcer([sandbox_path])):
        res_create = creator.run(inp_create)
        assert res_create.success is True
        assert new_dir.is_dir()

        # Test block outside sandbox
        inp_bad = CreateDirectoryInput(directory="/tmp/bad_folder")
        try:
            creator.run(inp_bad)
            assert False, "Should have raised PermissionError"
        except PermissionError:
            pass

    # 2. Test WriteFile inside sandbox
    writer = WriteFile()
    target_file = new_dir / "notes.txt"
    inp_write = WriteFileInput(filepath=str(target_file), content="Hello Sandbox!")
    
    with patch("core.tools.write_file.enforcer", SandboxEnforcer([sandbox_path])):
        res_write = writer.run(inp_write)
        assert res_write.success is True
        assert target_file.is_file()
        assert target_file.read_text(encoding="utf-8") == "Hello Sandbox!"

        # Test block outside sandbox
        inp_bad_write = WriteFileInput(filepath="/tmp/notes.txt", content="hack")
        try:
            writer.run(inp_bad_write)
            assert False, "Should have raised PermissionError"
        except PermissionError:
            pass


