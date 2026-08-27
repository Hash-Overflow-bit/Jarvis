"""
core/orchestrator/baseline_runner.py
====================================
Runs a simple baseline smoke test on newly loaded custom sub-agents.
Enforces a configurable timeout to prevent infinite loops.
"""

import asyncio
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process
from core.config import settings


class BaselineRunner:
    """Executes a baseline smoke test task on a newly loaded CrewAI agent."""

    async def test(self, agent: Agent) -> Dict[str, Any]:
        # Assign a simple diagnostic task to the agent
        test_task = Task(
            description="Return exactly the text: success\nDo not use any tools.",
            expected_output="exactly success",
            agent=agent
        )

        crew = Crew(
            agents=[agent],
            tasks=[test_task],
            process=Process.sequential,
            verbose=False
        )

        try:
            # Execute kickoff in a separate thread to avoid blocking the event loop
            # and wrap it in asyncio.wait_for to enforce the baseline timeout
            result = await asyncio.wait_for(
                asyncio.to_thread(crew.kickoff),
                timeout=settings.agent_baseline_timeout
            )
            
            cleaned_res = str(result).strip(" '\".").lower()
            # Catch ReAct parsing / Action errors that get captured in final response
            if "action" in cleaned_res and ("exist" in cleaned_res or "error" in cleaned_res or "invalid" in cleaned_res):
                return {
                    "success": False,
                    "error": f"Baseline test triggered a tool/action error: '{result}'"
                }
            if cleaned_res != "success":
                return {
                    "success": False,
                    "error": f"Baseline test returned unexpected output: '{result}'"
                }

            return {
                "success": True,
                "result": str(result)
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Baseline test timed out after {settings.agent_baseline_timeout} seconds."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Baseline test execution failed: {str(e)}"
            }


baseline_runner = BaselineRunner()
