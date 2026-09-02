"""Acceptance tests for Capability 4: deterministic filesystem workflows."""

from unittest.mock import patch

from core.orchestrator.deterministic_filesystem import DeterministicFilesystemRouter
from core.state.session_manager import SessionManager
from core.tools.tool_registry import tool_registry


def _router(tmp_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(tmp_path))
    return DeterministicFilesystemRouter()


def test_create_write_read_append_and_list_flow(tmp_path, monkeypatch):
    router = _router(tmp_path, monkeypatch)

    created = router.try_handle("Create a folder named daily in the workspace")
    assert created is not None and "Created workspace directory" in created.response

    written = router.try_handle(
        'Create a file daily/notes.md with content "First item"'
    )
    assert written is not None and "Wrote and verified" in written.response

    appended = router.try_handle('Append "\nSecond item" to daily/notes.md')
    assert appended is not None and "Appended and verified" in appended.response

    read = router.try_handle("Read daily/notes.md")
    assert read is not None
    assert "First item\nSecond item" in read.response
    assert "SHA-256" in read.response

    listing = router.try_handle("List the files in workspace")
    assert listing is not None and "daily/notes.md" in listing.response


def test_create_mode_does_not_overwrite_existing_file(tmp_path, monkeypatch):
    router = _router(tmp_path, monkeypatch)
    router.try_handle("Create file notes.txt with content original")
    result = router.try_handle("Create file notes.txt with content replacement")
    assert result is not None and "not performed" in result.response
    assert (tmp_path / "notes.txt").read_text() == "original"


def test_ambiguous_or_multi_action_prompt_is_not_partially_executed(tmp_path, monkeypatch):
    router = _router(tmp_path, monkeypatch)
    result = router.try_handle(
        "Create a folder named one and create a folder named two"
    )
    assert result is None
    assert not (tmp_path / "one").exists()
    assert not (tmp_path / "two").exists()


def test_outside_workspace_action_is_rejected(tmp_path, monkeypatch):
    router = _router(tmp_path / "workspace", monkeypatch)
    result = router.try_handle("Create file ../outside.txt with content no")
    assert result is not None
    assert "outside the configured workspace" in result.response
    assert not (tmp_path / "outside.txt").exists()


def test_session_uses_deterministic_path_without_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(tmp_path))
    session = SessionManager(use_tools=True, system_prompt="Be concise.")

    with patch("core.conversation.service.ollama.chat") as direct_chat:
        response = session.chat("Create file todo.md with content buy milk")

    direct_chat.assert_not_called()
    assert (tmp_path / "todo.md").read_text() == "buy milk"
    assert "Wrote and verified" in response
    assert session.turn_count == 1


def test_default_registry_excludes_destructive_and_expansive_tools():
    for disabled in (
        "delete_directory", "delete_file", "file_cleanup", "git_push",
        "poetry_install", "weight_manager",
        "skyvern_tool",
    ):
        assert tool_registry.get(disabled) is None

    for enabled in ("list_dir", "create_directory", "read_file", "write_file", "agent_builder", "delegate_task"):
        assert tool_registry.get(enabled) is not None


def test_registry_alias_does_not_duplicate_tool_schema():
    schemas = tool_registry.get_all_schemas()
    names = [schema["function"]["name"] for schema in schemas]
    assert len(names) == len(set(names))
