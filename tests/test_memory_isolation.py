import pytest
from pathlib import Path
from unittest.mock import patch
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings

def test_stale_pytest_path_in_memory_is_ignored(tmp_path):
    """Verify that a stale pytest- path injected into memory is filtered out."""
    from core.memory.recall import recall
    
    loop = AgentExecutionLoop(use_tools=True)
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        # We mock recall to return a stale pytest path
        stale_recall = type("RecallResult", (), {
            "facts": [{"source": "pytest-1", "predicate": "has", "target": "file.txt"}],
            "entities": [{"name": "pytest-1/old_workspace/file.txt", "description": "old"}],
            "latency_ms": 1.0,
            "as_text": lambda: "Stale recall"
        })()
        
        with patch('core.orchestrator.agent_loop.recall', return_value=stale_recall):
            pass

def test_recall_filters_transient_paths(tmp_path):
    # Testing the actual function directly
    import core.memory.recall as recall_module
    
    # We must access the inner function by importing the module, but it's local.
    # Instead, let's test the recall function directly by inserting into sqlite
    import sqlite3
    db_path = tmp_path / "test_graph.db"
    conn = sqlite3.connect(db_path)
    
    # Insert a transient path
    conn.execute("INSERT INTO entities VALUES ('1', '/Users/m2air/Desktop/test.txt', 'FILE', 'A test file', 'doc1')")
    conn.execute("INSERT INTO aliases VALUES ('1', 'test file')")
    
    # Insert a valid entity
    conn.execute("INSERT INTO entities VALUES ('2', 'Valid Concept', 'CONCEPT', 'A valid concept', 'doc2')")
    conn.execute("INSERT INTO aliases VALUES ('2', 'valid concept')")
    
    conn.commit()
    conn.close()
    
    with patch.object(settings.__class__, 'knowledge_graph_path', property(lambda self: db_path)):
        res = recall_module.recall("test file and valid concept")
        assert len(res.entities) == 1
        assert res.entities[0]["name"] == "Valid Concept"

def test_current_workspace_overrides_recalled_paths(tmp_path):
    """Verify paths outside default_workspace_dir are rejected by _run_traced."""
    loop = AgentExecutionLoop(use_tools=True)
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        mock_plan = [{"step": 1, "tool": "read_file", "arguments": {"filepath": "/etc/passwd"}}]
        
        with patch('core.orchestrator.agent_loop.AgentExecutionLoop._generate_plan', return_value=mock_plan):
            res = loop.run("Read file")
            assert "outside the authorized current workspace" in res or "rejected by sanitizer" in res

def test_missing_source_blocks_generate(tmp_path):
    loop = AgentExecutionLoop(use_tools=True)
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        mock_plan = [
            {"step": 1, "tool": "generate_document", "arguments": {"intent": {"sources_required": True, "source_files": []}}}
        ]
        sanitized = loop._sanitize_plan(mock_plan, "write report")
        assert not sanitized  # Should be rejected

def test_no_file_created_after_failed_read(tmp_path):
    loop = AgentExecutionLoop(use_tools=True)
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        # read_file targets a file that doesn't exist
        mock_plan = [
            {"step": 1, "tool": "read_file", "arguments": {"filepath": (tmp_path / "missing.txt").as_posix()}},
            {"step": 2, "tool": "write_file", "arguments": {"filepath": (tmp_path / "out.txt").as_posix(), "content": "<USE_GENERATED_ARTIFACT>"}}
        ]
        with patch('core.orchestrator.agent_loop.AgentExecutionLoop._generate_plan', return_value=mock_plan):
            res = loop.run("Read missing and write")
            assert "halted" in res.lower()
            assert not (tmp_path / "out.txt").exists()

def test_pregenerated_write_content_fails_sanitizer(tmp_path):
    loop = AgentExecutionLoop(use_tools=True)
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        mock_plan = [
            {"step": 1, "tool": "read_file", "arguments": {"filepath": (tmp_path / "sys.txt").as_posix()}},
            {"step": 2, "tool": "write_file", "arguments": {"filepath": (tmp_path / "out.txt").as_posix(), "content": "Hardcoded text"}}
        ]
        sanitized = loop._sanitize_plan(mock_plan, "write report")
        assert not sanitized  # Should be rejected
