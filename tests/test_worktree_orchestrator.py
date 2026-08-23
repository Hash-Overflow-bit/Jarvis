"""
tests/test_worktree_orchestrator.py
===================================
Unit tests for the GitWorktreeOrchestrator class.
"""

import os
import shutil
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from core.orchestrator.worktree_orchestrator import GitWorktreeOrchestrator


@pytest.fixture
def mock_repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    # Initialize fake git directory structure
    git_dir = repo_dir / ".git"
    git_dir.mkdir()
    return repo_dir


def test_worktree_orchestrator_init(mock_repo, monkeypatch):
    monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(mock_repo / "workspace"))
    orchestrator = GitWorktreeOrchestrator(repo_path=mock_repo)
    assert orchestrator.repo_path == mock_repo
    assert orchestrator.worktrees_root == mock_repo / "workspace" / "worktrees"
    assert orchestrator.worktrees_root.exists()


@patch("subprocess.run")
def test_create_worktree(mock_run, mock_repo, monkeypatch):
    monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(mock_repo / "workspace"))
    orchestrator = GitWorktreeOrchestrator(repo_path=mock_repo)

    # Mock git branch list to return nothing (meaning branch doesn't exist)
    mock_run.return_value = MagicMock(stdout="  main", returncode=0)

    branch = "feature-test"
    worktree_path = orchestrator.create_worktree(branch)

    # Check correct path created inside worktrees root
    assert worktree_path == orchestrator.worktrees_root / branch

    # Check git worktree add was called with correct branch and path arguments
    mock_run.assert_any_call(
        ["git", "worktree", "add", "-b", branch, str(worktree_path), "main"],
        cwd=mock_repo,
        capture_output=True,
        text=True,
        check=True,
    )


@patch("subprocess.run")
def test_remove_worktree(mock_run, mock_repo, monkeypatch):
    monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(mock_repo / "workspace"))
    orchestrator = GitWorktreeOrchestrator(repo_path=mock_repo)

    branch = "feature-test"
    worktree_path = orchestrator.worktrees_root / branch
    worktree_path.mkdir(parents=True, exist_ok=True)

    # Mock removal
    mock_run.return_value = MagicMock(stdout="", returncode=0)

    orchestrator.remove_worktree(branch)

    # Ensure git worktree remove command was run
    mock_run.assert_called_with(
        ["git", "worktree", "remove", str(worktree_path), "--force"],
        cwd=mock_repo,
        capture_output=True,
        text=True,
        check=True,
    )

    # Path should be fully cleaned up
    assert not worktree_path.exists()
