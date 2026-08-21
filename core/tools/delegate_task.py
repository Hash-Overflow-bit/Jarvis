"""
core/tools/delegate_task.py
===========================
Tool to delegate a complex task to a registered sub-agent (CrewAI Agent).
"""

import asyncio
from typing import Type
from pydantic import BaseModel, Field
from crewai import Task, Crew, Process
from core.tools.base_tool import BaseTool
from core.orchestrator.agent_registry import agent_registry


class DelegateTaskInput(BaseModel):
    agent_name: str = Field(..., description="The exact name of the sub-agent to delegate to (e.g. 'WebsiteBuilderAgent')")
    task_description: str = Field(..., description="A detailed description of the task for the sub-agent to perform")
    expected_output: str = Field(..., description="A clear description of the expected output format or deliverable")


class DelegateTaskOutput(BaseModel):
    success: bool
    result: str
    error: str = ""


class DelegateTask(BaseTool[DelegateTaskInput, DelegateTaskOutput]):
    """
    Delegates a complex task to a dynamically built sub-agent.
    """

    @property
    def name(self) -> str:
        return "delegate_task"

    @property
    def description(self) -> str:
        return (
            "Delegates a specialized task to a previously built sub-agent. "
            "Use this tool to assign work to agents you created with agent_builder."
        )

    @property
    def input_schema(self) -> Type[DelegateTaskInput]:
        return DelegateTaskInput

    @property
    def output_schema(self) -> Type[DelegateTaskOutput]:
        return DelegateTaskOutput

    def run(self, input_data: DelegateTaskInput) -> DelegateTaskOutput:
        # Retrieve the agent from the registry
        registry_entry = agent_registry.get(input_data.agent_name)
        if not registry_entry:
            return DelegateTaskOutput(
                success=False,
                result="",
                error=f"Sub-agent '{input_data.agent_name}' not found. You must build it first using agent_builder."
            )
        
        agent_instance = registry_entry.get("agent")
        if not agent_instance:
            return DelegateTaskOutput(
                success=False,
                result="",
                error=f"Sub-agent '{input_data.agent_name}' is corrupted or missing its CrewAI instance."
            )

        # Build the task and crew
        task = Task(
            description=input_data.task_description,
            expected_output=input_data.expected_output,
            agent=agent_instance
        )

        crew = Crew(
            agents=[agent_instance],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

        # Kickoff the crew execution synchronously (since run() is called by the executor thread)
        try:
            result = crew.kickoff()
            return DelegateTaskOutput(
                success=True,
                result=str(result)
            )
        except Exception as e:
            return DelegateTaskOutput(
                success=False,
                result="",
                error=f"Task execution failed: {str(e)}"
            )
