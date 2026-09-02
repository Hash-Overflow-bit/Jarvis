"""Baseline validation for bounded local sub-agents."""
import asyncio
from typing import Any, Dict
from core.config import settings


class BaselineRunner:
    async def test(self, agent: Any) -> Dict[str, Any]:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(agent.run, "Return exactly: success", "exactly the word success"),
                timeout=settings.agent_baseline_timeout,
            )
            if result.strip(" '\".").lower() != "success":
                return {"success": False, "error": f"Baseline returned unexpected output: {result!r}"}
            return {"success": True, "result": result}
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Baseline timed out after {settings.agent_baseline_timeout} seconds."}
        except Exception as exc:
            return {"success": False, "error": f"Baseline execution failed: {exc}"}


baseline_runner = BaselineRunner()
