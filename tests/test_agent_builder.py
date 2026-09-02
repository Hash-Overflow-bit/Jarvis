from unittest.mock import AsyncMock, patch
import yaml

from core.orchestrator.agent_registry import agent_registry
from core.tools.agent_builder import AgentBuilder, AgentBuilderInput


def test_builder_persists_bounded_profile(tmp_path):
    agent_registry._agents.clear()
    with patch.object(__import__("core.config", fromlist=["settings"]).settings.__class__, "agents_blueprint_path", new=property(lambda _: tmp_path / "agents.yaml")), patch("core.tools.agent_builder.baseline_runner.test", new=AsyncMock(return_value={"success": True, "result": "success"})):
        result = AgentBuilder().run(AgentBuilderInput(name="BriefAgent", role="Brief writer", goal="Summarize supplied text", capabilities=["summarize"]))
    assert result.success
    saved = yaml.safe_load((tmp_path / "agents.yaml").read_text())
    profile = saved["custom_sub_agents"][0]
    assert profile["framework"] == "local"
    assert profile["tools"] == []
    assert profile["allow_delegation"] is False
    assert profile["capabilities"] == ["summarize"]


def test_builder_rejects_tools_and_unknown_capability_without_writing(tmp_path):
    path = tmp_path / "agents.yaml"
    with patch.object(__import__("core.config", fromlist=["settings"]).settings.__class__, "agents_blueprint_path", new=property(lambda _: path)):
        tools = AgentBuilder().run(AgentBuilderInput(name="UnsafeAgent", tools=["read_file"], capabilities=["summarize"]))
        unknown = AgentBuilder().run(AgentBuilderInput(name="UnsafeAgent", capabilities=["browse"]))
    assert not tools.success and "cannot be given tools" in tools.details
    assert not unknown.success and "Unsupported" in unknown.details
    assert not path.exists()
