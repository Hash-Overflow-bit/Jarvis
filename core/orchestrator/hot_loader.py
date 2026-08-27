"""
core/orchestrator/hot_loader.py
===============================
Loads dynamic custom sub-agent definitions from the YAML blueprint file
and instantiates them as active CrewAI Agent primitives.
"""

import yaml
from pathlib import Path
from crewai import Agent

from core.config import settings
from core.orchestrator.tool_mapper import load_approved_tools


class HotLoader:
    """Reads the LLM-generated configuration file and spawns the dynamic sub-agent."""

    def load(self, yaml_path: Path, agent_name: str) -> Agent:
        if not yaml_path.exists():
            raise FileNotFoundError(f"Blueprint file not found at '{yaml_path}'")

        with open(yaml_path, 'r') as file:
            config = yaml.safe_load(file) or {}

        agents_list = config.get("custom_sub_agents", [])
        target_config = next((a for a in agents_list if a["name"] == agent_name), None)

        if not target_config:
            raise ValueError(f"Agent '{agent_name}' not found in the blueprint configuration.")

        # Load safe tools mapped from the template definitions
        allowed_tools = load_approved_tools(target_config.get("tools", []))

        from crewai import LLM
        # Use CrewAI's native LLM wrapper and route via ollama_chat/ to enable true tool-calling
        crew_llm = LLM(
            model=f"ollama_chat/{settings.ollama_model}",
            base_url=settings.ollama_base_url,
            api_key="NA"
        )

        react_rule = (
            "3. Do NOT output raw JSON as your final answer. You must use the 'Action:' and 'Action Input:' syntax strictly.\n"
            if allowed_tools else
            "3. No tools are assigned to you. Do NOT emit 'Action:' or 'Action Input:'. Answer directly in plain text with the final response.\n"
        )

        # Inject Workspace Context and strict ReAct Instructions for Local LLMs
        system_context = (
            f"\n\n[SYSTEM ENVIRONMENT CONTEXT]\n"
            f"You are operating on a local machine. Your primary workspace directory is: {settings.default_workspace_dir}\n"
            f"If you need to access files and no absolute path is given, assume this workspace directory.\n\n"
            f"[CRITICAL EXECUTION RULES]\n"
            f"1. You MUST always use your available tools to interact with the file system. Never assume or hallucinate file contents.\n"
            f"2. You MUST parse tool outputs carefully. If a tool returns a list of files or file content, read it and use that exact data in your next steps.\n"
            f"{react_rule}"
            f"4. CRITICAL: You MUST NOT invent, pretend, or claim that any installation, package download, model training, or external system action occurred unless you have successfully executed a tool that directly performed it and verified its output. If the task is simple summarization, simply summarize the text without proposing or claiming any model training or package setup."
        )

        dynamic_agent = Agent(
            role=target_config["role"],
            goal=target_config["goal"],
            backstory=target_config["backstory"] + system_context,
            verbose=target_config.get("verbose", True),
            allow_delegation=target_config.get("allow_delegation", False),
            tools=allowed_tools,
            llm=crew_llm
        )

        return dynamic_agent


hot_loader = HotLoader()
