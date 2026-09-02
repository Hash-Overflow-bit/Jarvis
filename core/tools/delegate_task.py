"""
core/tools/delegate_task.py
===========================
Tool to delegate a complex task to a registered sub-agent.
"""

from typing import Type
import re
from pydantic import BaseModel, Field
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
        # Resolve the agent adapter (supports name normalization and on-demand blueprint autoloading)
        agent_adapter = agent_registry.load_if_needed(input_data.agent_name)
        if not agent_adapter:
            return DelegateTaskOutput(
                success=False,
                result="",
                error=f"Sub-agent '{input_data.agent_name}' not found. You must build it first using agent_builder."
            )

        # A browser-capable sub-agent never receives a general browser.  It
        # can request only this narrow, parent-mediated operation: open the
        # explicit public URLs in one workspace instruction file.
        if "open_public_urls" in agent_adapter.capabilities:
            instruction_file = self._instruction_file_from_task(input_data.task_description)
            if instruction_file is not None:
                from core.tools.tool_registry import tool_registry

                execution = tool_registry.execute(
                    "open_instruction_urls", {"instruction_file": instruction_file}
                )
                if execution.get("success"):
                    result = execution.get("result", {})
                    return DelegateTaskOutput(
                        success=True,
                        result=str(result.get("message", "Opened reviewed public URLs.")),
                    )
                return DelegateTaskOutput(
                    success=False,
                    result="",
                    error=str(execution.get("error", "Could not open instruction-file URLs.")),
                )


        try:
            result = agent_adapter.run(input_data.task_description, input_data.expected_output)
            return DelegateTaskOutput(
                success=True,
                result=result
            )
        except Exception as e:
            return DelegateTaskOutput(
                success=False,
                result="",
                error=f"Task execution failed: {str(e)}"
            )

    @staticmethod
    def _instruction_file_from_task(task_description: str) -> str | None:
        """Accept only an explicit request to open URLs from one local file."""
        match = re.fullmatch(
            r"\s*(?:open|browse|visit)\s+(?:the\s+)?(?:public\s+)?URLs?\s+"
            r"(?:listed\s+)?(?:in|from)\s+['\"]?([A-Za-z0-9_./\\-]+\.(?:txt|md))['\"]?\s*[.!]?\s*",
            task_description or "",
            re.IGNORECASE,
        )
        return match.group(1) if match else None
