"""
Regression tests for mixed nested-filesystem + content-generation workflows.

These tests verify that _direct_route correctly handles prompts containing:
- Nested directory creation
- Content generation (generate_document)
- Save-as with contextual path resolution
- Read-back verification

And that pure filesystem prompts are NOT regressed.
"""
import pytest
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings
from unittest.mock import patch


@pytest.fixture
def loop():
    return AgentExecutionLoop(use_tools=True)


# ---------------------------------------------------------------------------
# Mixed nested folder + Markdown generation + save + read
# ---------------------------------------------------------------------------
def test_nested_folder_markdown_generation(loop):
    """
    Prompt: Create report_test -> create reports inside it -> generate report -> save inside reports -> read back.
    Expected tools: create_directory x2, generate_document, write_file, read_file
    """
    prompt = (
        "Create a folder named report_test on my Desktop. "
        "Inside it, create a folder named reports. "
        "Generate a short project status report with the sections Summary, Progress, Risks, and Next Steps, "
        "and save it inside reports as project_status.md. "
        "Then read the saved report back and verify its exact path and content."
    )
    plan = loop._direct_route(prompt)
    assert plan is not None, "Direct route returned None"
    assert isinstance(plan, list), f"Expected list, got {type(plan)}"

    tools = [step["tool"] for step in plan]
    assert tools == [
        "create_directory",
        "create_directory",
        "generate_document",
        "write_file",
        "read_file",
    ], f"Unexpected tool sequence: {tools}"

    # Verify directory paths
    assert "report_test" in plan[0]["arguments"]["directory"]
    assert "report_test/reports" in plan[1]["arguments"]["directory"].replace("\\", "/")

    # Verify write path resolves to reports subfolder
    write_path = plan[3]["arguments"]["filepath"].replace("\\", "/")
    assert write_path.endswith("report_test/reports/project_status.md"), f"Unexpected write path: {write_path}"
    assert plan[3]["arguments"]["content"] == "<USE_GENERATED_ARTIFACT>"

    # Verify read path matches write path
    assert plan[4]["arguments"]["filepath"] == plan[3]["arguments"]["filepath"]


# ---------------------------------------------------------------------------
# Mixed nested folder + JSON structured data generation + save + read
# ---------------------------------------------------------------------------
def test_nested_folder_json_generation(loop):
    """
    Prompt: Create data_export_test -> create exports -> generate structured data -> save as JSON -> read back.
    """
    prompt = (
        "Create a folder named data_export_test on my Desktop. "
        "Inside it, create a folder named exports. "
        "Generate structured data for three sample projects with the fields name, status, owner, and budget, "
        "and save it inside exports as projects.json. "
        "Then read the JSON file back and verify that all three records were saved correctly."
    )
    plan = loop._direct_route(prompt)
    assert plan is not None
    assert isinstance(plan, list)

    tools = [step["tool"] for step in plan]
    assert tools == [
        "create_directory",
        "create_directory",
        "generate_document",
        "write_file",
        "read_file",
    ], f"Unexpected tool sequence: {tools}"

    # Verify JSON output format for structured data
    gen_intent = plan[2]["arguments"]["intent"]
    assert gen_intent["output_format"] == "json", f"Expected json format, got {gen_intent['output_format']}"

    # Verify write path
    write_path = plan[3]["arguments"]["filepath"].replace("\\", "/")
    assert write_path.endswith("data_export_test/exports/projects.json"), f"Unexpected write path: {write_path}"


# ---------------------------------------------------------------------------
# Mixed nested folder + plain text generation + save + read
# ---------------------------------------------------------------------------
def test_nested_folder_text_generation(loop):
    """
    Prompt: Create notes_project -> create drafts -> generate text -> save as .txt -> read back.
    """
    prompt = (
        "Create a folder named notes_project on my Desktop. "
        "Inside it, create a folder named drafts. "
        "Generate a short summary of automated testing best practices, "
        "and save it inside drafts as testing_notes.txt. "
        "Then read the file back."
    )
    plan = loop._direct_route(prompt)
    assert plan is not None
    assert isinstance(plan, list)

    tools = [step["tool"] for step in plan]
    assert tools == [
        "create_directory",
        "create_directory",
        "generate_document",
        "write_file",
        "read_file",
    ], f"Unexpected tool sequence: {tools}"

    write_path = plan[3]["arguments"]["filepath"].replace("\\", "/")
    assert write_path.endswith("notes_project/drafts/testing_notes.txt"), f"Unexpected write path: {write_path}"


# ---------------------------------------------------------------------------
# Mixed nested folder + CSV generation + save + read
# ---------------------------------------------------------------------------
def test_nested_folder_csv_generation(loop):
    """
    Prompt: Create analytics -> create output -> generate CSV data -> save -> read back.
    """
    prompt = (
        "Create a folder named analytics on my Desktop. "
        "Inside it, create a folder named output. "
        "Generate structured data for five quarterly sales records with the fields quarter, revenue, and region, "
        "and save it inside output as sales.csv. "
        "Then read the file back."
    )
    plan = loop._direct_route(prompt)
    assert plan is not None
    assert isinstance(plan, list)

    tools = [step["tool"] for step in plan]
    assert tools == [
        "create_directory",
        "create_directory",
        "generate_document",
        "write_file",
        "read_file",
    ], f"Unexpected tool sequence: {tools}"

    write_path = plan[3]["arguments"]["filepath"].replace("\\", "/")
    assert write_path.endswith("analytics/output/sales.csv"), f"Unexpected write path: {write_path}"


# ---------------------------------------------------------------------------
# Pure nested filesystem (regression guard -- must NOT break)
# ---------------------------------------------------------------------------
def test_pure_nested_filesystem_not_regressed(loop):
    """
    Ensure that prompts with ONLY filesystem operations still work.
    """
    prompt = (
        "Create a folder named recovery_test on my Desktop. "
        "Inside it, create step1.txt containing exactly First step complete."
    )
    plan = loop._direct_route(prompt)
    assert plan is not None
    assert isinstance(plan, list)
    assert len(plan) == 2

    assert plan[0]["tool"] == "create_directory"
    assert "recovery_test" in plan[0]["arguments"]["directory"]

    assert plan[1]["tool"] == "write_file"
    assert "recovery_test/step1.txt" in plan[1]["arguments"]["filepath"].replace("\\", "/")
    assert plan[1]["arguments"]["content"] == "First step complete"


# ---------------------------------------------------------------------------
# Context resolution: save-as resolves from accumulated directory context
# ---------------------------------------------------------------------------
def test_save_as_resolves_from_context(loop):
    """
    Verify that 'save it inside docs as X.md' resolves to the correct absolute path
    using the directory context accumulated during clause parsing.
    """
    prompt = (
        "Create a folder named project_alpha on my Desktop. "
        "Inside it, create a folder named docs. "
        "Generate a brief project overview, "
        "and save it inside docs as overview.md."
    )
    plan = loop._direct_route(prompt)
    assert plan is not None

    write_steps = [s for s in plan if s["tool"] == "write_file"]
    assert len(write_steps) == 1

    write_path = write_steps[0]["arguments"]["filepath"].replace("\\", "/")
    expected_suffix = "project_alpha/docs/overview.md"
    assert write_path.endswith(expected_suffix), (
        f"Expected path ending with '{expected_suffix}', got '{write_path}'"
    )


# ---------------------------------------------------------------------------
# Synthesis truth: only current-run tools should be claimed
# ---------------------------------------------------------------------------
@patch("core.orchestrator.agent_loop.ollama.chat")
def test_synthesis_filters_stale_claims(mock_ollama_chat, loop):
    """
    If completed_steps contains only create_directory, the synthesis must NOT
    claim file creation or generation happened.
    """
    completed_steps = [
        {"step": 1, "tool": "create_directory", "arguments": {"directory": "/fake/desktop/test_dir"}, "result": {"success": True}}
    ]
    
    # Simulate LLM producing a hallucinated claim
    mock_ollama_chat.return_value = {
        "content": (
            "I created the folder test_dir.\n"
            "I also generated a short project status report.\n"
            "The file was saved file at /workspace/file.txt.\n"
            "Everything is complete."
        )
    }
    
    response = loop._synthesize_final_response(
        "Create test_dir and generate a report",
        completed_steps,
        ""
    )
    
    # The generation claim should be filtered out
    assert "generated" not in response.lower() or "generate_document" in str(completed_steps)
    # The stale /workspace/file.txt claim should be filtered out
    assert "/workspace/file.txt" not in response
    # The folder creation claim should survive (it's in completed_steps)
    assert "folder" in response.lower() or "test_dir" in response.lower() or "complete" in response.lower()
