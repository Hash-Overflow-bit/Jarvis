import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.writing.pipeline import WritingPipeline
from core.config import settings

def test_extraction_pathing_and_directory_creation(tmp_path):
    """
    Verifies deterministic plans correctly preserve Windows workspace sources,
    build nested paths via pathlib, and prepend create_directory.
    """
    desktop = tmp_path / "workspace"
    workspace = tmp_path / "workspace"
    desktop.mkdir()
    workspace.mkdir(exist_ok=True)
    
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)):
        
        prompt = "Read employees.csv from my workspace. Extract only the Name and Salary fields. Save the result inside company_exports/hr/json on my workspace as employees_clean.json."
        
        loop = AgentExecutionLoop()
        plan = loop._direct_route(prompt, "")
        
        assert plan is not None
        assert len(plan) == 4
        
        # Step 1: read_file from desktop
        assert plan[0]["tool"] == "read_file"
        source_path = Path(plan[0]["arguments"]["filepath"])
        assert str(desktop) in str(source_path)
        assert source_path.name == "employees.csv"
        
        # Step 2: extract_data
        assert plan[1]["tool"] == "extract_data"
        
        # Step 3: create_directory (nested)
        assert plan[2]["tool"] == "create_directory"
        dir_path = Path(plan[2]["arguments"]["directory"])
        assert str(desktop) in str(dir_path)
        assert dir_path.name == "json"
        assert dir_path.parent.name == "hr"
        assert dir_path.parent.parent.name == "company_exports"
        
        # Step 4: write_file
        assert plan[3]["tool"] == "write_file"
        dest_path = Path(plan[3]["arguments"]["filepath"])
        assert str(desktop) in str(dest_path)
        assert dest_path.name == "employees_clean.json"
        assert dest_path.parent.name == "json"

def test_extraction_fails_gracefully_if_read_fails(tmp_path):
    desktop = tmp_path / "workspace"
    desktop.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)):
        
        prompt = "Read missing.csv from my workspace. Extract names. Save to workspace as out.json."
        loop = AgentExecutionLoop()
        
        # Should halt on read_file and never reach write_file
        result = loop.run(prompt)
        
        assert "Execution halted" in result
        assert "missing.csv" in result
        assert not (desktop / "out.json").exists()

def test_extraction_permission_error_halts(tmp_path):
    desktop = tmp_path / "workspace"
    desktop.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    
    from core.tools.tool_registry import tool_registry
    original_execute = tool_registry.execute
    
    def mock_execute(name, args, mode='text'):
        if name == 'read_file':
            return {'success': False, 'error': 'Disk read error (Permission Error)'}
        return original_execute(name, args, mode)

    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)), \
         patch.object(tool_registry, 'execute', side_effect=mock_execute):
        
        prompt = "Read secret.csv from my workspace. Extract names. Save to workspace as out.json."
        loop = AgentExecutionLoop()
        result = loop.run(prompt)
        
        assert "Execution halted" in result
        assert "secret.csv" in result or "Disk read error" in result
        assert not (desktop / "out.json").exists()

def test_extraction_existing_empty_file(tmp_path):
    desktop = tmp_path / "workspace"
    desktop.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    
    empty_file = desktop / "empty.csv"
    empty_file.touch()
    
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)):
        
        prompt = "Read empty.csv from my workspace. Extract names. Save to workspace as out.json."
        loop = AgentExecutionLoop()
        result = loop.run(prompt)
        
        assert (desktop / "out.json").exists()
        content = (desktop / "out.json").read_text()
        assert "No source text was provided for extraction" in content

def test_extraction_valid_file(tmp_path):
    desktop = tmp_path / "workspace"
    desktop.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    
    valid_file = desktop / "valid.csv"
    valid_file.write_text("Name,Age\nAlice,30\nBob,25")
    
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)):
        
        prompt = "Read valid.csv from my workspace. Extract names. Save to workspace as out.json."
        loop = AgentExecutionLoop()
        result = loop.run(prompt)
        
        assert (desktop / "out.json").exists()
        content = (desktop / "out.json").read_text()
        assert "Alice" in content or "names" in content

def test_extraction_multiple_sources_one_fails(tmp_path):
    desktop = tmp_path / "workspace"
    desktop.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    
    file1 = desktop / "file1.csv"
    file1.write_text("Name\nAlice")
    
    # file2 is missing
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)):
        
        prompt = "Read file1.csv and file2.csv from my workspace. Extract names. Save to workspace as out.json."
        loop = AgentExecutionLoop()
        result = loop.run(prompt)
        
        assert "Execution halted" in result
        assert "file2.csv" in result
        assert not (desktop / "out.json").exists()

