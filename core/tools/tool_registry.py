"""
core/tools/tool_registry.py
===========================
Registry that tracks all registered tools and manages their safe execution.
"""

from typing import Dict, List, Optional, Any
from pydantic import ValidationError
from core.tools.base_tool import BaseTool


class ToolRegistry:
    """
    Manages the collection of tools and routes invocations safely.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registers a tool instance in the registry."""
        if tool.name in self._tools:
            raise ValueError(f"Tool with name '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by its name."""
        return self._tools.get(name)

    def get_all_schemas(self) -> List[dict]:
        """Generates Ollama function schemas for all registered tools."""
        return [tool.to_ollama_schema() for tool in self._tools.values()]

    def execute(self, name: str, raw_args: Dict[str, Any], mode: str = "text") -> Dict[str, Any]:
        """
        Validates arguments against input schema, runs the tool, validates output,
        and returns the result. Includes safety confirmation gates and dry-run modes.

        Args:
            name: Name of the tool to execute.
            raw_args: Raw arguments (dict) from the LLM function call.
            mode: Runtime execution mode ('text' or 'audio').

        Returns:
            A dict with:
                - "success": bool
                - "result": dict (if success is True)
                - "error": str (if success is False)
        """
        tool = self.get(name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool '{name}' not found in registry."
            }

        # 1. Validate Input Data
        # Clean up raw_args to filter out string "null", "none", etc. sent by the LLM
        cleaned_args = {}
        for k, v in raw_args.items():
            if isinstance(v, str) and v.lower() in ("null", "none"):
                continue
            cleaned_args[k] = v

        try:
            input_data = tool.input_schema(**cleaned_args)
        except ValidationError as e:
            return {
                "success": False,
                "error": f"Invalid arguments passed to '{name}': {str(e)}"
            }

        # 1.5 Safety Gates (Milestone 4)
        from core.config import settings
        from core.safety.risk_classifier import risk_classifier
        from core.safety.confirmation_gate import confirmation_gate
        from core.safety.dry_run_wrapper import dry_run_wrapper
        from core.safety.exception_handler import safe_execute
        from core.logging.audit_logger import audit_logger

        def run_async(coro):
            import asyncio
            import nest_asyncio
            nest_asyncio.apply()
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

        # Dry Run Simulation Check
        if settings.dry_run:
            audit_logger.log_action(
                tool_name=name,
                parameters=cleaned_args,
                status="DRY_RUN",
                details="Dry run simulation mode active"
            )
            # Ask for confirmation in dry-run mode too, if configured
            if risk_classifier.should_confirm(name):
                approved = run_async(confirmation_gate.confirm_action(name, cleaned_args, mode=mode))
                if not approved:
                    audit_logger.log_action(
                        tool_name=name,
                        parameters=cleaned_args,
                        status="DENIED",
                        details="User rejected dry-run execution"
                    )
                    return {
                        "success": False,
                        "error": f"Dry-run execution of '{name}' denied by user."
                    }
            return dry_run_wrapper.get_mock_response(name, cleaned_args)

        # Active Confirmation Check
        if risk_classifier.should_confirm(name):
            approved = run_async(confirmation_gate.confirm_action(name, cleaned_args, mode=mode))
            if not approved:
                audit_logger.log_action(
                    tool_name=name,
                    parameters=cleaned_args,
                    status="DENIED",
                    details="User rejected execution"
                )
                return {
                    "success": False,
                    "error": f"Execution of '{name}' denied by user."
                }
        else:
            # Low risk tools bypass the confirmation gate
            audit_logger.log_action(
                tool_name=name,
                parameters=cleaned_args,
                status="BYPASSED",
                details="Low risk action executed automatically"
            )

        # 2. Execute Tool (via exception handler wrapper)
        from opentelemetry import trace
        tracer = trace.get_tracer("jarvis")
        with tracer.start_as_current_span(f"Tool.{name}") as span:
            span.set_attribute("tool.name", name)
            span.set_attribute("tool.args", str(cleaned_args))
            result = run_async(safe_execute(name, cleaned_args, lambda: tool.run(input_data)))
            span.set_attribute("tool.success", result.get("success", False))
            if not result.get("success"):
                span.set_attribute("tool.error", result.get("error", ""))
        
        if not result.get("success"):
            return result

        # 3. Validate Output Data
        try:
            output_data = result.get("result", {})
            # Ensure output matches output_schema
            if not isinstance(output_data, tool.output_schema):
                # Attempt to parse/coerce if it's not the exact class
                output_data = tool.output_schema(**output_data)
            
            return {
                "success": True,
                "result": output_data.model_dump()
            }
        except ValidationError as e:
            return {
                "success": False,
                "error": f"Internal error: Tool '{name}' returned malformed output: {str(e)}"
            }


# Global tool registry singleton
tool_registry = ToolRegistry()

# Register standard tools
from core.tools.file_scanner import FileScanner
from core.tools.file_cleanup import FileCleanup
from core.tools.directory_audit import DirectoryAudit

tool_registry.register(FileScanner())
tool_registry.register(FileCleanup())
tool_registry.register(DirectoryAudit())

# Register Git and Poetry tools (M3+)
from core.tools.git_tool import GitClone, GitPull, GitStatus, GitAdd, GitCommit, GitPush
from core.tools.poetry_tool import PoetryInstall, PoetryAdd, PoetryShow

tool_registry.register(GitClone())
tool_registry.register(GitPull())
tool_registry.register(GitStatus())
tool_registry.register(GitAdd())
tool_registry.register(GitCommit())
tool_registry.register(GitPush())

tool_registry.register(PoetryInstall())
tool_registry.register(PoetryAdd())
tool_registry.register(PoetryShow())

# Register Memory Knowledge Graph tools (M4.5+)
from core.memory.graph_manager import GraphStatus, RebuildKnowledgeGraph, ForgetDocument
tool_registry.register(GraphStatus())
tool_registry.register(RebuildKnowledgeGraph())
tool_registry.register(ForgetDocument())

# Register File Manipulation Tools (M4.5+)
from core.tools.create_directory import CreateDirectory
from core.tools.write_file import WriteFile
tool_registry.register(CreateDirectory())
tool_registry.register(WriteFile())

# Register Dynamic Sub-Agents (M5+)
from core.tools.agent_builder import AgentBuilder
from core.tools.delegate_task import DelegateTask
tool_registry.register(AgentBuilder())
tool_registry.register(DelegateTask())

# Register Model Weight Manager Tool (M6)
from core.tools.weight_tool import WeightManagerTool
tool_registry.register(WeightManagerTool())

