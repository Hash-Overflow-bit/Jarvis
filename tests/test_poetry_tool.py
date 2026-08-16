"""
tests/test_poetry_tool.py
=========================
Unit tests for PoetryInstall, PoetryAdd, PoetryShow.
Uses mocked subprocess runs to test installation, addition, and package showing logic.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
import pytest

from core.tools.sandbox_enforcer import enforcer
from core.tools.poetry_tool import PoetryInstall, PoetryAdd, PoetryShow
from schemas.poetry_tool_schema import (
    PoetryInstallInput,
    PoetryAddInput,
    PoetryShowInput,
)


@pytest.fixture
def temp_poetry_env(monkeypatch):
    """Sets up temporary workspace and venv cache folders for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir).resolve()
        workspace_dir = temp_path / "workspace"
        workspace_dir.mkdir()

        venvs_dir = temp_path / "venvs"
        venvs_dir.mkdir()

        # Set environment variables so settings returns them dynamically
        monkeypatch.setenv("DEFAULT_WORKSPACE_DIR", str(workspace_dir))
        monkeypatch.setenv("POETRY_VENV_PATH", str(venvs_dir))

        # Temporarily mutate the global enforcer's allowed roots
        old_roots = enforcer.allowed_roots
        enforcer.allowed_roots = [workspace_dir, venvs_dir]

        try:
            yield workspace_dir, venvs_dir
        finally:
            enforcer.allowed_roots = old_roots


def test_poetry_install_poetry_project(temp_poetry_env):
    workspace_dir, venvs_dir = temp_poetry_env
    project_path = workspace_dir / "my_project"
    project_path.mkdir()

    # Create dummy pyproject.toml
    (project_path / "pyproject.toml").write_text("[tool.poetry]")

    mock_run = AsyncMock(return_value={"success": True, "stdout": "dependencies installed"})
    with patch("core.tools.background_runner.background_runner.run", mock_run):
        tool = PoetryInstall()
        inp = PoetryInstallInput(project_path=str(project_path))
        out = tool.run(inp)

        assert out.success is True
        assert "dependencies" in out.message
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["poetry", "install", "--no-interaction"]


def test_poetry_install_pip_fallback(temp_poetry_env):
    workspace_dir, venvs_dir = temp_poetry_env
    project_path = workspace_dir / "my_pip_project"
    project_path.mkdir()

    # Create dummy requirements.txt
    (project_path / "requirements.txt").write_text("requests==2.31.0")

    mock_run = AsyncMock(return_value={"success": True, "stdout": "pip success"})
    with patch("core.tools.background_runner.background_runner.run", mock_run):
        tool = PoetryInstall()
        inp = PoetryInstallInput(project_path=str(project_path))
        out = tool.run(inp)

        assert out.success is True
        assert "Isolated virtualenv" in out.message
        
        # Check that it called venv creation first, and then pip install
        assert mock_run.call_count == 2
        assert "venv" in mock_run.call_args_list[0][0][0]
        assert "pip" in mock_run.call_args_list[1][0][0][0]


def test_poetry_add(temp_poetry_env):
    workspace_dir, venvs_dir = temp_poetry_env
    project_path = workspace_dir / "my_project"
    project_path.mkdir()
    (project_path / "pyproject.toml").write_text("[tool.poetry]")

    mock_run = AsyncMock(return_value={"success": True, "stdout": "package added"})
    with patch("core.tools.background_runner.background_runner.run", mock_run):
        tool = PoetryAdd()
        inp = PoetryAddInput(project_path=str(project_path), package_name="requests")
        out = tool.run(inp)

        assert out.success is True
        assert mock_run.call_args[0][0] == ["poetry", "add", "requests", "--no-interaction"]


def test_poetry_show(temp_poetry_env):
    workspace_dir, venvs_dir = temp_poetry_env
    project_path = workspace_dir / "my_project"
    project_path.mkdir()
    (project_path / "pyproject.toml").write_text("[tool.poetry]")

    mock_run = AsyncMock(return_value={"success": True, "stdout": "requests 2.31.0"})
    with patch("core.tools.background_runner.background_runner.run", mock_run):
        tool = PoetryShow()
        inp = PoetryShowInput(project_path=str(project_path))
        out = tool.run(inp)

        assert out.success is True
        assert "requests" in out.dependencies_tree
        assert mock_run.call_args[0][0] == ["poetry", "show", "--tree"]
