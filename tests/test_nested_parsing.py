import pytest
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings

def test_nested_parsing_script():
    loop = AgentExecutionLoop()
    prompt = """Create a folder named nested_test in my workspace.
Inside it, create a folder named level1.
Inside level1, create another folder named level2.
Inside level2, create notes.txt containing exactly Nested filesystem test passed.
Then read the file back and verify its exact path and content."""

    plan = loop._direct_route(prompt)
    assert plan is not None, "Failed to parse deterministic route"
    assert isinstance(plan, list), f"Expected plan to be a list, got {type(plan)}"
    assert len(plan) == 5, f"Expected 5 steps, got {len(plan)}"
    
    from pathlib import Path
    workspace = Path(settings.default_workspace_dir)

    assert plan[0]["step"] == 1
    assert plan[0]["tool"] == "create_directory"
    assert Path(plan[0]["arguments"]["directory"]) == workspace / "nested_test"

    assert plan[1]["step"] == 2
    assert plan[1]["tool"] == "create_directory"
    assert Path(plan[1]["arguments"]["directory"]) == workspace / "nested_test" / "level1"

    assert plan[2]["step"] == 3
    assert plan[2]["tool"] == "create_directory"
    assert Path(plan[2]["arguments"]["directory"]) == workspace / "nested_test" / "level1" / "level2"

    assert plan[3]["step"] == 4
    assert plan[3]["tool"] == "write_file"
    assert Path(plan[3]["arguments"]["filepath"]) == workspace / "nested_test" / "level1" / "level2" / "notes.txt"
    assert plan[3]["arguments"]["content"] == "Nested filesystem test passed"

    assert plan[4]["step"] == 5
    assert plan[4]["tool"] == "read_file"
    assert Path(plan[4]["arguments"]["filepath"]) == workspace / "nested_test" / "level1" / "level2" / "notes.txt"

@pytest.mark.parametrize("prompt, expected_parts", [
    ("Create folder_A in my workspace. Inside it create folder_B. Inside folder_B create folder_C.", ("folder_A", "folder_B", "folder_C")),
    ("Make project_x. Under project_x create src. Inside src create utils. Put helper.txt there.", ("project_x", "src", "utils", "helper.txt")),
    ("Create reports/2026/january and put summary.txt inside january.", ("reports", "2026", "january", "summary.txt")),
    ("Create Alpha. Inside that folder make Beta. There create test.txt.", ("Alpha", "Beta", "test.txt"))
])
def test_nested_parsing_generalizations(prompt, expected_parts):
    loop = AgentExecutionLoop()
    plan = loop._direct_route(prompt)
    assert plan is not None, f"Failed to parse: {prompt}"
    
    assert isinstance(plan, list), f"Expected plan to be a list, got {type(plan)}"
    
    last_step = plan[-1]
    last_args = last_step.get("arguments", {})
    last_path = last_args.get("directory") or last_args.get("filepath")
    
    from pathlib import Path
    workspace = settings.default_workspace_dir
    expected = Path(workspace).joinpath(*expected_parts)
    assert Path(last_path).resolve() == expected.resolve()
