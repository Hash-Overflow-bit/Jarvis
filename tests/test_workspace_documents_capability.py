"""Acceptance tests for Capability 3: controlled workspace documents."""

import pytest

from core.tools.read_file import ReadFile, ReadFileInput
from core.tools.write_file import WriteFile
from core.workspace.documents import WorkspaceBoundaryError, WorkspaceDocumentError, WorkspaceDocuments
from schemas.write_file_schema import WriteFileInput


def test_relative_paths_are_rooted_in_workspace(tmp_path):
    documents = WorkspaceDocuments(root=tmp_path)
    assert documents.resolve("notes/today.md") == (tmp_path / "notes" / "today.md").resolve()
    assert documents.resolve("workspace/notes.md") == (tmp_path / "notes.md").resolve()


@pytest.mark.parametrize("path", ["../escape.md", "workspace/../../escape.md"])
def test_traversal_is_blocked(tmp_path, path):
    with pytest.raises(WorkspaceBoundaryError):
        WorkspaceDocuments(root=tmp_path).resolve(path)


def test_absolute_path_outside_workspace_is_blocked(tmp_path):
    outside = tmp_path.parent / "outside.md"
    with pytest.raises(WorkspaceBoundaryError):
        WorkspaceDocuments(root=tmp_path).resolve(outside)


def test_symlink_escape_is_blocked(tmp_path):
    outside = tmp_path.parent / "outside-docs"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks are not available in this environment")
    with pytest.raises(WorkspaceBoundaryError):
        WorkspaceDocuments(root=tmp_path).resolve("linked/escape.md")


def test_create_read_overwrite_append_with_receipts(tmp_path):
    documents = WorkspaceDocuments(root=tmp_path)
    created = documents.write_text("report.md", "alpha", mode="create")
    assert created.byte_count == 5
    assert len(created.sha256) == 64

    text, read_receipt = documents.read_text("report.md")
    assert text == "alpha"
    assert read_receipt.sha256 == created.sha256

    overwritten = documents.write_text("report.md", "beta", mode="overwrite")
    appended = documents.write_text("report.md", " gamma", mode="append")
    assert overwritten.sha256 != created.sha256
    assert documents.read_text("report.md")[0] == "beta gamma"
    assert appended.byte_count == len("beta gamma".encode())


def test_create_never_silently_overwrites(tmp_path):
    documents = WorkspaceDocuments(root=tmp_path)
    documents.write_text("report.md", "original")
    with pytest.raises(WorkspaceDocumentError, match="already exists"):
        documents.write_text("report.md", "replacement")
    assert (tmp_path / "report.md").read_text() == "original"


def test_binary_and_unsupported_files_are_rejected(tmp_path):
    (tmp_path / "binary.txt").write_bytes(b"hello\x00world")
    documents = WorkspaceDocuments(root=tmp_path)
    with pytest.raises(WorkspaceDocumentError, match="Binary"):
        documents.read_text("binary.txt")
    with pytest.raises(WorkspaceDocumentError, match="Unsupported"):
        documents.write_text("script.exe", "no")


def test_size_limit_applies_to_read_and_write(tmp_path):
    documents = WorkspaceDocuments(root=tmp_path, max_bytes=4)
    with pytest.raises(WorkspaceDocumentError, match="limit"):
        documents.write_text("large.txt", "12345")
    (tmp_path / "large.txt").write_text("12345")
    with pytest.raises(WorkspaceDocumentError, match="limit"):
        documents.read_text("large.txt")


def test_read_and_write_tools_share_the_same_workspace_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(tmp_path))
    write_result = WriteFile().run(
        WriteFileInput(filepath="workspace/tool.md", content="verified", mode="create")
    )
    assert write_result.success is True
    assert write_result.path == str((tmp_path / "tool.md").resolve())

    read_result = ReadFile().run(ReadFileInput(filepath="tool.md"))
    assert read_result.success is True
    assert read_result.content == "verified"
    assert read_result.sha256 == write_result.sha256


def test_tools_cannot_read_or_write_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(workspace))

    read_result = ReadFile().run(ReadFileInput(filepath=str(outside)))
    write_result = WriteFile().run(
        WriteFileInput(filepath=str(outside), content="changed", mode="overwrite")
    )
    assert read_result.success is False
    assert write_result.success is False
    assert outside.read_text() == "secret"
