"""
core/orchestrator/tool_mapper.py
================================
Maps YAML string declarations to safe, pre-verified local tools.
Supports both standard LangChain community toolkits and custom Jarvis registry tools.
"""

from typing import List, Any
from langchain_community.agent_toolkits import FileManagementToolkit
from crewai.tools import BaseTool as CrewBaseTool


class JarvisCrewTool(CrewBaseTool):
    """CrewAI-compatible wrapper for custom or LangChain tools."""
    func: Any = None

    def _run(self, **kwargs) -> Any:
        if self.func:
            try:
                return self.func(**kwargs)
            except Exception as e:
                return f"Error executing tool: {e}"
        return "Tool execution failed: No function bound."


def wrap_jarvis_tool(jarvis_tool) -> JarvisCrewTool:
    """Wraps a custom Jarvis BaseTool into a CrewAI-compatible Tool."""
    def run_wrapper(**kwargs):
        input_instance = jarvis_tool.input_schema(**kwargs)
        output_instance = jarvis_tool.run(input_instance)
        return output_instance.model_dump()

    return JarvisCrewTool(
        name=jarvis_tool.name,
        description=jarvis_tool.description,
        args_schema=jarvis_tool.input_schema,
        func=run_wrapper
    )


def wrap_langchain_tool(lc_tool) -> JarvisCrewTool:
    """Wraps a standard LangChain Tool into a CrewAI-compatible Tool."""
    clean_name = lc_tool.name.replace(" ", "_").replace("-", "_")
    return JarvisCrewTool(
        name=clean_name,
        description=lc_tool.description,
        args_schema=lc_tool.args_schema,
        func=lambda **kwargs: lc_tool.invoke(kwargs)
    )


def load_approved_tools(tool_names: List[str]) -> List[JarvisCrewTool]:
    """Maps YAML string declarations to safe, pre-verified local tools."""
    from core.config import settings
    
    # If sandbox mode is disabled, grant full access to the filesystem (root_dir=None)
    # If enabled, lock them into the default workspace directory
    target_root = None if not settings.sandbox_mode else str(settings.default_workspace_dir)
    
    toolkit = FileManagementToolkit(
        root_dir=target_root
    )
    all_toolkit_tools = toolkit.get_tools()
    
    selected_tools = []
    for t_name in tool_names:
        if t_name.startswith("FileManagementToolkit."):
            base_name = t_name.split(".")[-1]
            for t in all_toolkit_tools:
                if base_name in t.name:
                    selected_tools.append(wrap_langchain_tool(t))
        else:
            from core.tools.tool_registry import tool_registry
            j_tool = tool_registry.get(t_name)
            if j_tool:
                selected_tools.append(wrap_jarvis_tool(j_tool))
            else:
                for t in all_toolkit_tools:
                    if t_name in t.name:
                        selected_tools.append(wrap_langchain_tool(t))

    return selected_tools
