import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.writing.pipeline import WritingPipeline
from core.config import settings

def test_extraction_pathing_and_directory_creation(tmp_path):
    """
    Verifies deterministic plans correctly preserve Windows Desktop sources,
    build nested paths via pathlib, and prepend create_directory.
    """
    desktop = tmp_path / "Desktop"
    workspace = tmp_path / "workspace"
    desktop.mkdir()
    workspace.mkdir()
    
    with patch.object(settings.__class__, 'desktop_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)):
        
        prompt = "Read employees.csv from my Desktop. Extract only the Name and Salary fields. Save the result inside company_exports/hr/json on my Desktop as employees_clean.json."
        
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
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    with patch.object(settings.__class__, 'desktop_dir', property(lambda self: desktop)), \
         patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: workspace)):
        
        prompt = "Read missing.csv from my Desktop. Extract names. Save to Desktop as out.json."
        loop = AgentExecutionLoop()
        
        # Should halt on read_file and never reach write_file
        result = loop.run(prompt)
        
        assert "Execution halted" in result
        assert "missing.csv" in result
        assert not (desktop / "out.json").exists()
