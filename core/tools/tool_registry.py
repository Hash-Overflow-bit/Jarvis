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

    def register_alias(self, alias_name: str, tool: BaseTool) -> None:
        """Registers an alias name mapping to an existing tool instance."""
        if alias_name in self._tools:
            return
        self._tools[alias_name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by its name."""
        return self._tools.get(name)

    def get_all_schemas(self) -> List[dict]:
        """Generates Ollama function schemas for all registered tools."""
        unique_tools = {id(tool): tool for tool in self._tools.values()}
        return [tool.to_ollama_schema() for tool in unique_tools.values()]

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

        # 1.1 Argument normalization — map common LLM naming variants to schema fields
        # LLMs frequently output slightly different parameter names than the schema expects.
        # This mapping catches the most common mismatches to prevent validation errors.
        _ARG_ALIASES = {
            "repo_url": "url",
            "repository_url": "url",
            "clone_url": "url",
            "file_path": "filepath",
            "file": "filepath",
            "path": "filepath",
            "dir": "directory",
            "dir_path": "directory",
            "folder": "directory",
            "folder_path": "directory",
            "msg": "commit_message",
            "message": "commit_message",
            "pkg": "package_name",
            "package": "package_name",
        }
        # Only remap if the schema doesn't already have the key but does have the alias target
        schema_fields = set(tool.input_schema.model_fields.keys())
        normalized_args = {}
        for k, v in cleaned_args.items():
            if k not in schema_fields and k in _ARG_ALIASES:
                target = _ARG_ALIASES[k]
                if target in schema_fields and target not in cleaned_args:
                    normalized_args[target] = v
                    continue
            normalized_args[k] = v
        cleaned_args = normalized_args

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
            if risk_classifier.should_confirm(name, cleaned_args):
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
        if risk_classifier.should_confirm(name, cleaned_args):
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

# Default capability profile: non-destructive, daily workspace operations only.
# Destructive deletion, Git/package mutation, dynamic sub-agents, model-weight
# changes and browser automation are intentionally not registered. Bounded
# reasoning-only sub-agents are an exception: they receive no external tools.
from core.tools.file_scanner import FileScanner
from core.tools.create_directory import CreateDirectory
from core.tools.write_file import WriteFile
from core.tools.read_file import ReadFile
from core.tools.agent_builder import AgentBuilder
from core.tools.delegate_task import DelegateTask
from core.tools.public_web import FetchURL, OpenURL
from core.tools.open_instruction_urls import OpenInstructionURLs

file_scanner_tool = FileScanner()
tool_registry.register(file_scanner_tool)
tool_registry.register_alias("list_dir", file_scanner_tool)
tool_registry.register(CreateDirectory())
tool_registry.register(WriteFile())
tool_registry.register(ReadFile())
tool_registry.register(AgentBuilder())
tool_registry.register(DelegateTask())
tool_registry.register(FetchURL())
tool_registry.register(OpenURL())
tool_registry.register(OpenInstructionURLs())

# Kept for backward-compatible internal writing workflows. User research is
# routed through ResearchService before the generic planner.
from core.tools.web_search import WebSearch
tool_registry.register(WebSearch())
