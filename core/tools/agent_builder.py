"""
core/tools/agent_builder.py
===========================
Jarvis tool to dynamically build, hot-load, and register new custom sub-agents
using the YAML blueprint schema and CrewAI factory loop.
"""

import yaml
import asyncio
from typing import List, Type
from pydantic import BaseModel, Field
from core.config import settings
from core.tools.base_tool import BaseTool
from core.orchestrator.hot_loader import hot_loader
from core.orchestrator.agent_registry import agent_registry
from core.orchestrator.baseline_runner import baseline_runner
from core.orchestrator.rollback_manager import rollback_manager
from core.orchestrator.subagent_runner import SubagentPolicyError, validate_capabilities


class AgentBuilderInput(BaseModel):
    name: str = Field(
        default="CustomSubAgent",
        description="The name of the sub-agent (PascalCase, e.g. LogCleanerAgent)"
    )
    role: str = Field(
        default="Automated Task Specialist",
        description="The role of the sub-agent"
    )
    goal: str = Field(
        default="Produce a grounded specialist response for an assigned reasoning task.",
        description="The goal of the sub-agent"
    )
    backstory: str = Field(
        default="An expert local reasoning specialist with no external tools or autonomous actions.",
        description="The backstory of the sub-agent"
    )
    tools: List[str] = Field(
        default_factory=list,
        description="Must be empty. Local sub-agents never receive tools."
    )
    framework: str = Field(
        default="local",
        description="Bounded local runtime. Legacy values are mapped to local."
    )
    capabilities: List[str] = Field(
        default_factory=list,
        description="List of capabilities specializing in"
    )


class AgentBuilderOutput(BaseModel):
    success: bool
    agent: str
    details: str


class AgentBuilder(BaseTool[AgentBuilderInput, AgentBuilderOutput]):
    """
    Dynamically builds, hot-loads, and registers new custom sub-agents.
    """

    @property
    def name(self) -> str:
        return "agent_builder"

    @property
    def description(self) -> str:
        return (
            "Generates and hot-loads a new custom sub-agent configuration into the active Jarvis workspace. "
            "Requires confirmation approval before proceeding."
        )

    @property
    def input_schema(self) -> Type[AgentBuilderInput]:
        return AgentBuilderInput

    @property
    def output_schema(self) -> Type[AgentBuilderOutput]:
        return AgentBuilderOutput

    def run(self, input_data: AgentBuilderInput) -> AgentBuilderOutput:
        # Validate before any persistent change. A sub-agent is deliberately a
        # reasoning profile, never an autonomous tool/container/browser worker.
        if not input_data.name.replace("_", "").replace("-", "").replace(" ", "").isalnum():
            return AgentBuilderOutput(success=False, agent=input_data.name, details="Agent name may contain letters, numbers, spaces, hyphens, and underscores only.")
        if input_data.tools:
            return AgentBuilderOutput(success=False, agent=input_data.name, details="Sub-agents cannot be given arbitrary tools, filesystem access, shell access, browser automation, or nested delegation. The open_public_urls capability is parent-mediated and only opens reviewed public URLs from one workspace instruction file.")
        try:
            capabilities = validate_capabilities(input_data.capabilities)
        except SubagentPolicyError as exc:
            return AgentBuilderOutput(success=False, agent=input_data.name, details=str(exc))
        blueprint_path = settings.agents_blueprint_path
        blueprint_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Parse existing YAML blueprint or start fresh
        try:
            if blueprint_path.exists():
                with open(blueprint_path, "r") as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}
        except Exception as e:
            return AgentBuilderOutput(
                success=False,
                agent=input_data.name,
                details=f"Failed to read blueprint configuration file: {e}"
            )

        agents_list = config.setdefault("custom_sub_agents", [])

        # Prevent duplicate registrations in the same blueprint
        updated_list = [a for a in agents_list if a["name"] != input_data.name]
        
        new_agent = {
            "name": input_data.name,
            "role": input_data.role,
            "goal": input_data.goal,
            "backstory": input_data.backstory,
            "verbose": False,
            "allow_delegation": False,
            "tools": [],
            "framework": "local",
            "capabilities": list(capabilities)
        }
        updated_list.append(new_agent)
        config["custom_sub_agents"] = updated_list

        # 2. Write updated configuration block
        try:
            with open(blueprint_path, "w") as f:
                yaml.safe_dump(config, f, default_flow_style=False)
        except Exception as e:
            return AgentBuilderOutput(
                success=False,
                agent=input_data.name,
                details=f"Failed to write to blueprint configuration file: {e}"
            )

        # 3. Hot-load dynamic agent primitives into memory
        try:
            agent_instance = hot_loader.load(blueprint_path, input_data.name)
        except Exception as e:
            rollback_manager.revert(input_data.name, blueprint_path)
            return AgentBuilderOutput(
                success=False,
                agent=input_data.name,
                details=f"Failed to hot-load sub-agent specs: {e}"
            )

        # 4. Register dynamically
        agent_registry.register(input_data.name, agent_instance, list(capabilities))

        # 5. Run baseline smoke test execution
        try:
            test_result = asyncio.run(baseline_runner.test(agent_instance))

        except Exception as e:
            test_result = {"success": False, "error": str(e)}

        if not test_result.get("success"):
            rollback_manager.revert(input_data.name, blueprint_path)
            return AgentBuilderOutput(
                success=False,
                agent=input_data.name,
                details=f"Baseline test failed: {test_result.get('error')}"
            )

        return AgentBuilderOutput(
            success=True,
            agent=input_data.name,
            details=f"Bounded local sub-agent '{input_data.name}' built and verified. It can only perform: {', '.join(capabilities)}."
        )
