"""Safe blueprint loader for bounded local sub-agent profiles."""
from pathlib import Path
import yaml
from core.orchestrator.subagent_runner import LocalSubagent, validate_capabilities


class HotLoader:
    def load(self, yaml_path: Path, agent_name: str) -> LocalSubagent:
        config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        item = next((agent for agent in config.get("custom_sub_agents", []) if agent.get("name") == agent_name), None)
        if not item:
            raise ValueError(f"Agent '{agent_name}' not found in blueprint configuration.")
        if item.get("tools"):
            raise ValueError("Sub-agents cannot be configured with tools.")
        return LocalSubagent(item["name"], item["role"], item["goal"], item.get("backstory", ""),
                             validate_capabilities(item.get("capabilities", [])))


hot_loader = HotLoader()
