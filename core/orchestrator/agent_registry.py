"""
core/orchestrator/agent_registry.py
===================================
In-memory registry that tracks dynamically loaded sub-agents and their metadata.
"""

from datetime import datetime
from typing import Dict, List, Any
from crewai import Agent


class AgentRegistry:
    """Tracks dynamically loaded sub-agents and their configurations."""

    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, agent: Agent, capabilities: List[str]) -> None:
        self._agents[name] = {
            "agent": agent,
            "capabilities": capabilities,
            "loaded_at": datetime.utcnow().isoformat(),
            "status": "active"
        }

    def get(self, name: str) -> Any:
        if name in self._agents:
            return self._agents[name]
        for k, v in self._agents.items():
            if k.lower() == name.lower():
                return v
        return None

    def list_all(self) -> List[Dict[str, Any]]:
        # Omit raw agent object when listing for clean JSON audits
        return [
            {
                "name": k,
                "capabilities": v["capabilities"],
                "loaded_at": v["loaded_at"],
                "status": v["status"]
            }
            for k, v in self._agents.items()
        ]

    def deregister(self, name: str) -> None:
        self._agents.pop(name, None)


agent_registry = AgentRegistry()
