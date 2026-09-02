"""Registry for bounded local sub-agent profiles."""
from datetime import datetime
import logging
from typing import Any, Dict, List
import yaml
from core.config import settings
from core.orchestrator.subagent_runner import LocalSubagent, validate_capabilities

logger = logging.getLogger("agent_registry")


class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}

    def _normalize(self, name: str) -> str:
        value = name.lower().replace(" ", "").replace("_", "").replace("-", "")
        return value[:-5] if value.endswith("agent") else value

    def register(self, name: str, agent: LocalSubagent, capabilities: List[str]) -> None:
        self._agents[name] = {"agent": agent, "adapter": agent, "capabilities": list(capabilities),
                              "loaded_at": datetime.utcnow().isoformat(), "status": "active"}

    def get(self, name: str) -> Any:
        target = self._normalize(name)
        if name in self._agents:
            return self._agents[name]
        return next((entry for key, entry in self._agents.items() if self._normalize(key) == target), None)

    def load_if_needed(self, name: str) -> LocalSubagent | None:
        entry = self.get(name)
        if entry:
            return entry["adapter"]
        path = settings.agents_blueprint_path
        if not path.exists():
            return None
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            target = next((item for item in config.get("custom_sub_agents", [])
                           if self._normalize(item.get("name", "")) == self._normalize(name)), None)
            if not target:
                return None
            if target.get("tools"):
                raise ValueError("tool-enabled legacy agents cannot be delegated")
            agent = LocalSubagent(target["name"], target["role"], target["goal"], target.get("backstory", ""),
                                  validate_capabilities(target.get("capabilities", [])))
            self.register(agent.name, agent, list(agent.capabilities))
            return agent
        except Exception as exc:
            logger.warning("Failed to load bounded sub-agent %s: %s", name, exc)
            return None

    def list_all(self) -> List[Dict[str, Any]]:
        return [{"name": name, "capabilities": entry["capabilities"], "loaded_at": entry["loaded_at"], "status": entry["status"]}
                for name, entry in self._agents.items()]

    def deregister(self, name: str) -> None:
        target = self._normalize(name)
        for key in [key for key in self._agents if self._normalize(key) == target]:
            self._agents.pop(key, None)


agent_registry = AgentRegistry()
