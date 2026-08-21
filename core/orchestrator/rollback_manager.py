"""
core/orchestrator/rollback_manager.py
====================================
Rolls back failed or broken custom sub-agents by removing their entries
from agents_blueprint.yaml and deregistering them from memory.
"""

import yaml
from pathlib import Path
from core.orchestrator.agent_registry import agent_registry


class RollbackManager:
    """Handles rollback of custom sub-agents from both registry memory and YAML blueprint files."""

    def revert(self, name: str, yaml_path: Path) -> None:
        # 1. Deregister from memory registry
        agent_registry.deregister(name)

        # 2. Remove entry from YAML blueprint file
        if not yaml_path.exists():
            return

        try:
            with open(yaml_path, 'r') as file:
                config = yaml.safe_load(file) or {}

            agents_list = config.get("custom_sub_agents", [])
            # Filter out the reverted agent
            updated_list = [a for a in agents_list if a["name"] != name]
            config["custom_sub_agents"] = updated_list

            with open(yaml_path, 'w') as file:
                yaml.safe_dump(config, file, default_flow_style=False)
        except Exception as e:
            print(f"[Rollback] Warning: Failed to revert blueprint entry: {e}")


rollback_manager = RollbackManager()
