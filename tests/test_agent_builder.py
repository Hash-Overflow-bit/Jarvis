"""
tests/test_agent_builder.py
===========================
Unit tests for the AgentBuilder tool, hot-loader, and rollback mechanism.
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from core.config import settings
from core.tools.agent_builder import AgentBuilder, AgentBuilderInput
from core.orchestrator.agent_registry import agent_registry


@pytest.fixture
def temp_blueprint(tmp_path):
    blueprint_file = tmp_path / "agents_blueprint.yaml"
    with patch("core.config._Settings.agents_blueprint_path", new_callable=PropertyMock, return_value=blueprint_file):
        yield blueprint_file


def test_agent_builder_success(temp_blueprint):
    builder = AgentBuilder()
    input_data = AgentBuilderInput(
        name="LogCleanerAgent",
        role="System Log Analyst",
        goal="Locate and clear non-critical temporary log files",
        backstory="An automated system utility expert",
        tools=["FileManagementToolkit.list_dir"]
    )

    # Patch baseline runner to return success
    with patch("core.tools.agent_builder.baseline_runner.test", return_value={"success": True, "result": "success"}):
        output = builder.run(input_data)
        assert output.success is True
        assert output.agent == "LogCleanerAgent"
        
        # Check registry
        registered = agent_registry.get("LogCleanerAgent")
        assert registered is not None
        assert registered["capabilities"] == ["FileManagementToolkit.list_dir"]
        
        # Verify YAML entry exists
        with open(temp_blueprint, "r") as f:
            data = yaml.safe_load(f)
        assert len(data["custom_sub_agents"]) == 1
        assert data["custom_sub_agents"][0]["name"] == "LogCleanerAgent"


def test_agent_builder_failure_rollback(temp_blueprint):
    builder = AgentBuilder()
    input_data = AgentBuilderInput(
        name="FailedAgent",
        role="Failed role",
        goal="Failed goal",
        backstory="Failed backstory",
        tools=[]
    )

    # Patch baseline runner to return failure
    with patch("core.tools.agent_builder.baseline_runner.test", return_value={"success": False, "error": "LLM failed"}):
        output = builder.run(input_data)
        assert output.success is False
        assert "Baseline test failed" in output.details
        
        # Check registry (should be empty/deregistered)
        assert agent_registry.get("FailedAgent") is None
        
        # Verify YAML entry is removed/rolled back
        if temp_blueprint.exists():
            with open(temp_blueprint, "r") as f:
                data = yaml.safe_load(f)
            assert len(data.get("custom_sub_agents", [])) == 0
