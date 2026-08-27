"""
core/orchestrator/agent_registry.py
===================================
In-memory registry that tracks dynamically loaded sub-agents and their metadata.
"""

from datetime import datetime
from typing import Dict, List, Any
import logging

logger = logging.getLogger("agent_registry")


class CrewAIAgentAdapter:
    """Stable callable contract for CrewAI agents."""
    def __init__(self, agent_instance, expected_output="Task completion report", capabilities=None):
        self.agent_instance = agent_instance
        self.expected_output = expected_output
        self.capabilities = capabilities or []

    def run(self, task_description: str) -> str:
        from crewai import Task, Crew, Process
        import asyncio
        import nest_asyncio
        from core.config import settings

        # Build capabilities task contract to prevent semantic drift and hallucinations
        contract = ""
        if self.capabilities:
            if "summarize" in self.capabilities:
                contract = (
                    "\n\n[CAPABILITY CONTRACT: SUMMARIZE]\n"
                    "1. Summarize only the supplied text. Preserve its original meaning.\n"
                    "2. Do NOT introduce external facts, training details, or mock setup claims.\n"
                    "3. Do NOT discuss actions, files, tools, or implementation.\n"
                    "4. Return ONLY the concise grounded summary."
                )
            elif "analyze" in self.capabilities:
                contract = (
                    "\n\n[CAPABILITY CONTRACT: ANALYZE]\n"
                    "1. Provide a grounded analysis of the supplied material only.\n"
                    "2. Do NOT introduce external assumptions or mock claims."
                )
            elif "classify" in self.capabilities:
                contract = (
                    "\n\n[CAPABILITY CONTRACT: CLASSIFY]\n"
                    "1. Classify the supplied material only.\n"
                    "2. Return only the classification category."
                )

        full_task_desc = task_description + contract

        assigned_tools = getattr(self.agent_instance, "tools", []) or []
        num_tools = len(assigned_tools)
        branch = "DIRECT_LLM" if num_tools == 0 else "CREWAI"


        # 1. NO-TOOLS PATH: If agent has no tools, execute via direct LLM call
        # to avoid ReAct loop prompting/hallucinations entirely.
        if branch == "DIRECT_LLM":
            prompt_instruction = (
                "Use only facts and numbers explicitly provided in the current task description or input text.\n"
                "If required information or data is missing or not present in the input, explicitly state that it cannot be determined and state exactly what is missing.\n"
                "Do NOT estimate, infer, or invent fake metrics, percentages, averages, financial values, dates, counts, or performance figures.\n"
                "Do not introduce external facts. Do not mention tools or files. Answer directly with the grounded result."
            )
            system_prompt = (
                f"Role: {self.agent_instance.role}\n"
                f"Goal: {self.agent_instance.goal}\n"
                f"No tools are available for this task. Do not emit Action or Action Input.\n"
                f"STRICT GROUNDING & MISSING DATA CONTRACT:\n{prompt_instruction}\n"
                f"Answer directly with the requested result."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_task_desc}
            ]
            response = self.agent_instance.llm.call(messages=messages)
            res_str = str(response).strip()
            
            # Clean any leftover ReAct headers if present in raw LLM output
            if "Action:" in res_str:
                parts = res_str.split("Action Input:")
                if len(parts) > 1:
                    res_str = parts[-1].strip()
                else:
                    res_str = res_str.split("Action:")[0].strip()
            return res_str

        # 2. STANDARD TOOLS PATH
        task = Task(
            description=full_task_desc,
            expected_output=self.expected_output,
            agent=self.agent_instance
        )

        crew = Crew(
            agents=[self.agent_instance],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            nest_asyncio.apply()
            result = loop.run_until_complete(crew.kickoff_async())
        else:
            result = loop.run_until_complete(crew.kickoff_async())

        final_res = str(result)

        # 3. FAILURE VALIDATION: Scan final output for invalid tool/action errors
        cleaned_res = final_res.lower()
        has_tool_error = (
            ("action '" in cleaned_res and "exist" in cleaned_res) or
            "toolfailurereason" in cleaned_res or
            "invalid tool" in cleaned_res
        )

        if has_tool_error:
            # Retry once using the strict direct no-tools prompt path
            system_prompt = (
                f"Role: {self.agent_instance.role}\n"
                f"Goal: {self.agent_instance.goal}\n"
                f"Backstory: {self.agent_instance.backstory}\n"
                f"CRITICAL: You must answer directly in plain text. Do NOT use tools or output Action/Action Input."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_task_desc}
            ]
            try:
                retry_res = self.agent_instance.llm.call(messages=messages)
                retry_cleaned = str(retry_res).lower()
                if "action '" in retry_cleaned and "exist" in retry_cleaned:
                    raise ValueError(f"Delegated agent execution failed with tool/action errors: {retry_res}")
                return str(retry_res).strip()
            except Exception as e:
                raise ValueError(f"Delegated agent execution failed with tool/action errors: {e}")

        return final_res


class AgentRegistry:
    """Tracks dynamically loaded sub-agents and their configurations."""

    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}

    def _normalize(self, name: str) -> str:
        """Strip spaces, underscores, hyphens, and trailing 'agent' suffix."""
        n = name.lower().replace(" ", "").replace("_", "").replace("-", "")
        if n.endswith("agent"):
            n = n[:-5]
        return n

    def register(self, name: str, agent: Any, capabilities: List[str]) -> None:
        from crewai import Agent as CrewAgent
        if isinstance(agent, CrewAgent) or type(agent).__name__ == "Agent":
            adapter = CrewAIAgentAdapter(agent, capabilities=capabilities)
        else:
            adapter = agent

        self._agents[name] = {
            "agent": agent,
            "adapter": adapter,
            "capabilities": capabilities,
            "loaded_at": datetime.utcnow().isoformat(),
            "status": "active"
        }

    def get(self, name: str) -> Any:
        target = self._normalize(name)
        if name in self._agents:
            return self._agents[name]
        for k, v in self._agents.items():
            if self._normalize(k) == target:
                return v
        return None

    def load_if_needed(self, name: str) -> Any:
        """Resolve name by checking in-memory first, and if missing, autoload from blueprint."""
        entry = self.get(name)
        if entry:
            return entry.get("adapter")

        from core.config import settings
        import yaml
        blueprint_path = settings.agents_blueprint_path
        if blueprint_path.exists():
            try:
                with open(blueprint_path, "r") as f:
                    config = yaml.safe_load(f) or {}
                agents_list = config.get("custom_sub_agents", [])
                
                target_norm = self._normalize(name)
                target_config = next((a for a in agents_list if self._normalize(a["name"]) == target_norm), None)
                
                if target_config:
                    from core.orchestrator.hot_loader import hot_loader
                    agent_instance = hot_loader.load(blueprint_path, target_config["name"])
                    self.register(target_config["name"], agent_instance, target_config.get("capabilities", []))
                    
                    return self.get(target_config["name"]).get("adapter")
            except Exception as e:
                logger.warning(f"Failed to auto-load agent {name} from blueprint: {e}")
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
        # Support normalized deletion
        target = self._normalize(name)
        keys_to_remove = [k for k in self._agents if self._normalize(k) == target]
        for k in keys_to_remove:
            self._agents.pop(k, None)


agent_registry = AgentRegistry()
