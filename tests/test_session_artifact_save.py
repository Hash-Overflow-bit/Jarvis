"""Regression coverage for saving a report in a later chat turn."""

from pathlib import Path
from unittest.mock import patch

from core.config import settings
from core.research.service import ResearchResult, ResearchSource
from core.state.session_manager import SessionManager


def _write_to_disk(tool_name, arguments, **_kwargs):
    """Small verified stand-in for the write tool used by this integration test."""
    assert tool_name == "write_file"
    target = Path(arguments["filepath"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(arguments["content"], encoding="utf-8")
    return {"success": True, "result": {"message": "written"}}


def test_research_then_save_uses_exact_prior_report_and_directory(tmp_path):
    workspace = tmp_path / "workspace"
    reports = workspace / "reports"
    reports.mkdir(parents=True)
    report = "Grounded finding [1].\n\nSources\n[1] Source — https://example.com"
    research_result = ResearchResult(
        query="project planning",
        report=report,
        sources=(ResearchSource("Source", "https://example.com", "Evidence"),),
    )

    with patch.object(
        settings.__class__, "default_workspace_dir", property(lambda _self: workspace)
    ), patch(
        "core.research.service.ResearchService.research", return_value=research_result
    ), patch(
        "core.orchestrator.agent_loop_legacy.tool_registry.execute",
        side_effect=_write_to_disk,
    ) as execute, patch(
        "core.orchestrator.agent_loop.ollama.chat",
        return_value={"content": "Saved."},
    ):
        session = SessionManager(use_tools=True, system_prompt="Be concise.")
        assert session.chat("Research project planning") == report
        session.session_artifacts["last_created_directory"] = str(reports)

        session.chat("Save this report in that directory as planning_report.md")

    saved_file = reports / "planning_report.md"
    assert saved_file.read_text(encoding="utf-8") == report
    write_call = execute.call_args
    assert write_call.args[1]["content"] == report
    assert write_call.args[1]["filepath"] == str(saved_file)
    assert session.session_artifacts["last_generated_document"]["saved"] is True


def test_save_reference_without_prior_artifact_creates_no_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with patch.object(
        settings.__class__, "default_workspace_dir", property(lambda _self: workspace)
    ), patch("core.orchestrator.agent_loop_legacy.tool_registry.execute") as execute:
        session = SessionManager(use_tools=True, system_prompt="Be concise.")
        response = session.chat("Save this report as missing_report.md")

    assert "no verified generated report" in response.lower()
    assert not (workspace / "missing_report.md").exists()
    execute.assert_not_called()


def test_reset_discards_report_artifact_state():
    session = SessionManager(use_tools=True, system_prompt="Be concise.")
    session.session_artifacts["last_generated_document"] = {"content": "old report"}

    session.reset()

    assert "last_generated_document" not in session.session_artifacts


def test_deterministic_directory_creation_is_available_to_later_turn(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with patch.object(
        settings.__class__, "default_workspace_dir", property(lambda _self: workspace)
    ):
        session = SessionManager(use_tools=True, system_prompt="Be concise.")
        session.chat("Create a folder named reports in the workspace.")

    assert session.session_artifacts["last_created_directory"] == str(workspace / "reports")
