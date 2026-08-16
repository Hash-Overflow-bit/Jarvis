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

    def execute(self, name: str, raw_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates arguments against input schema, runs the tool, validates output,
        and returns the result.

        Args:
            name: Name of the tool to execute.
            raw_args: Raw arguments (dict) from the LLM function call.

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

        # 2. Execute Tool
        try:
            output_data = tool.run(input_data)
        except PermissionError as e:
            # Explicitly catch sandbox security violations
            return {
                "success": False,
                "error": f"Security boundary violation: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error in tool '{name}': {str(e)}"
            }

        # 3. Validate Output Data
        try:
            # Ensure output matches output_schema
            if not isinstance(output_data, tool.output_schema):
                # Attempt to parse/coerce if it's not the exact class
                output_data = tool.output_schema(**output_data.model_dump())
            
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

