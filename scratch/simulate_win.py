from pathlib import Path
import os
import json
from unittest.mock import patch

def test_simulate():
    # simulate a windows path
    target_dir = Path("C:\\Users\\m2air\\AppData\\Local\\Temp\\stubborn_folder")
    
    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "delete_directory",
                    "arguments": {"directory": str(target_dir)}
                }
            ]
        })
    }
    
    # how does sanitize plan handle it?
    from core.orchestrator.agent_loop import AgentExecutionLoop
    loop = AgentExecutionLoop()
    plan = json.loads(mock_plan_res["content"]).get("plan", [])
    
    # simulate the replace logic
    for step in plan:
        args = step.get("arguments", {})
        for key, val in args.items():
            if isinstance(val, str):
                if ('/' in val or '\\' in val) and not val.startswith('http'):
                    val = val.replace('\\', '/')
                args[key] = val
    
    print("Sanitized plan:", plan)
    dir_to_del = plan[0]["arguments"]["directory"]
    
    is_abs = os.path.isabs(dir_to_del) or dir_to_del.startswith("/")
    print("Is abs:", is_abs)
    
    # In _run_traced:
    from core.config import settings
    target_fp = str(settings.default_workspace_dir / dir_to_del) if not is_abs else dir_to_del
    print("Target fp:", target_fp)

test_simulate()
