import pytest
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings

def test_nested_parsing_script():
    loop = AgentExecutionLoop()
    prompt = """Create a folder named nested_test on my Desktop.
Inside it, create a folder named level1.
Inside level1, create another folder named level2.
Inside level2, create notes.txt containing exactly Nested filesystem test passed.
Then read the file back and verify its exact path and content."""

    plan = loop._direct_route(prompt)
    assert plan is not None, "Failed to parse deterministic route"
    assert isinstance(plan, list), f"Expected plan to be a list, got {type(plan)}"
    assert len(plan) == 5, f"Expected 5 steps, got {len(plan)}"
    
    desktop = str(settings.desktop_dir)
    assert plan[0] == {"step": 1, "tool": "create_directory", "arguments": {"directory": f"{desktop}/nested_test"}}
    assert plan[1] == {"step": 2, "tool": "create_directory", "arguments": {"directory": f"{desktop}/nested_test/level1"}}
    assert plan[2] == {"step": 3, "tool": "create_directory", "arguments": {"directory": f"{desktop}/nested_test/level1/level2"}}
    assert plan[3] == {"step": 4, "tool": "write_file", "arguments": {"filepath": f"{desktop}/nested_test/level1/level2/notes.txt", "content": "Nested filesystem test passed"}}
    assert plan[4] == {"step": 5, "tool": "read_file", "arguments": {"filepath": f"{desktop}/nested_test/level1/level2/notes.txt"}}

@pytest.mark.parametrize("prompt, expected_last_path", [
    ("Create A on Desktop. Inside it create B. Inside B create C.", "/A/B/C"),
    ("Make project_x. Under project_x create src. Inside src create utils. Put helper.txt there.", "/project_x/src/utils/helper.txt"),
    ("Create reports/2026/january and put summary.txt inside january.", "/reports/2026/january/summary.txt"),
    ("Create Alpha. Inside that folder make Beta. There create test.txt.", "/Alpha/Beta/test.txt")
])
def test_nested_parsing_generalizations(prompt, expected_last_path):
    loop = AgentExecutionLoop()
    plan = loop._direct_route(prompt)
    assert plan is not None, f"Failed to parse: {prompt}"
    
    assert isinstance(plan, list), f"Expected plan to be a list, got {type(plan)}"
    
    last_step = plan[-1]
    last_args = last_step.get("arguments", {})
    last_path = last_args.get("directory") or last_args.get("filepath")
    
    desktop = str(settings.desktop_dir)
    assert last_path == desktop + expected_last_path
