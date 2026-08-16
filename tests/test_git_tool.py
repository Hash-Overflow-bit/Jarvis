"""
tests/test_git_tool.py
======================
Unit tests for GitClone, GitPull, GitStatus, GitAdd, GitCommit, GitPush.
Uses a local bare Git repository in a temporary workspace to test offline.
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest

from core.tools.sandbox_enforcer import enforcer
from core.tools.git_tool import GitClone, GitPull, GitStatus, GitAdd, GitCommit, GitPush
from schemas.git_tool_schema import (
    GitCloneInput,
    GitPullInput,
    GitStatusInput,
    GitAddInput,
    GitCommitInput,
    GitPushInput,
)


@pytest.fixture
def temp_git_env(monkeypatch):
    """Sets up a temporary directory structure mimicking the workspace."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir).resolve()
        workspace_dir = temp_path / "workspace"
        workspace_dir.mkdir()

        # Initialize a local bare repository inside the temp workspace
        bare_repo_path = workspace_dir / "bare.git"
        os.makedirs(bare_repo_path)
        subprocess.run(["git", "init", "--bare", str(bare_repo_path)], check=True)

        # Set environment variables so settings returns them dynamically
        monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(workspace_dir))

        # Temporarily mutate the global enforcer's allowed roots
        old_roots = enforcer.allowed_roots
        enforcer.allowed_roots = [workspace_dir]

        try:
            yield workspace_dir, bare_repo_path
        finally:
            enforcer.allowed_roots = old_roots


def test_local_git_workflow(temp_git_env):
    workspace_dir, bare_repo_path = temp_git_env

    # 1. Test GitClone
    clone_tool = GitClone()
    clone_inp = GitCloneInput(url=str(bare_repo_path), target_dir_name="clone_dir")
    clone_out = clone_tool.run(clone_inp)

    assert clone_out.success is True
    assert "Successfully cloned" in clone_out.message
    assert clone_out.resolved_path == str(workspace_dir / "clone_dir")
    assert (workspace_dir / "clone_dir" / ".git").is_dir()

    # 2. Test GitStatus (Clean)
    status_tool = GitStatus()
    status_inp = GitStatusInput(repo_path=clone_out.resolved_path)
    status_out = status_tool.run(status_inp)
    assert status_out.success is True
    assert "clean" in status_out.status_summary.lower()

    # 3. Test GitAdd
    # Create a file to add
    test_file = Path(clone_out.resolved_path) / "test.txt"
    test_file.write_text("Hello Git World")

    add_tool = GitAdd()
    add_inp = GitAddInput(repo_path=clone_out.resolved_path, file_pattern="test.txt")
    add_out = add_tool.run(add_inp)
    assert add_out.success is True

    # 4. Test GitCommit
    commit_tool = GitCommit()
    commit_inp = GitCommitInput(repo_path=clone_out.resolved_path, commit_message="feat: first commit")
    commit_out = commit_tool.run(commit_inp)
    assert commit_out.success is True
    assert any(x in commit_out.message.lower() for x in ["first commit", "file changed", "root-commit"])

    # 5. Test GitPush
    push_tool = GitPush()
    # Git defaults to master or main depending on config. Try pushing both.
    push_inp = GitPushInput(repo_path=clone_out.resolved_path, branch="master")
    push_out = push_tool.run(push_inp)
    if not push_out.success:
        push_inp.branch = "main"
        push_out = push_tool.run(push_inp)

    assert push_out.success is True

    # 6. Test GitPull
    # Clone a second directory to pull modifications
    clone_inp2 = GitCloneInput(url=str(bare_repo_path), target_dir_name="clone_dir2")
    clone_out2 = clone_tool.run(clone_inp2)
    assert clone_out2.success is True
    assert (workspace_dir / "clone_dir2" / "test.txt").exists()

    # Pull in the second directory (should say already up to date)
    pull_tool = GitPull()
    pull_inp = GitPullInput(repo_path=clone_out2.resolved_path)
    pull_out = pull_tool.run(pull_inp)
    assert pull_out.success is True
