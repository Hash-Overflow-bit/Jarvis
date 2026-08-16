"""
core/tools/poetry_tool.py
=========================
Poetry tools implementing install, add, and show operations.
Includes fallback support for pip requirements.txt in non-Poetry repos.
"""

import os
import platform
from pathlib import Path
from pydantic import BaseModel
from core.config import settings
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from core.tools.background_runner import background_runner
from core.tools.git_tool import run_async
from schemas.poetry_tool_schema import (
    PoetryInstallInput,
    PoetryInstallOutput,
    PoetryAddInput,
    PoetryAddOutput,
    PoetryShowInput,
    PoetryShowOutput,
)


class PoetryInstall(BaseTool):
    """Installs project dependencies using Poetry or falls back to pip venv."""

    @property
    def name(self) -> str:
        return "poetry_install"

    @property
    def description(self) -> str:
        return (
            "Install dependency packages for a project. "
            "Uses Poetry if pyproject.toml exists; falls back to an isolated pip venv if only requirements.txt exists."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return PoetryInstallInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return PoetryInstallOutput

    def run(self, input_data: PoetryInstallInput) -> PoetryInstallOutput:
        try:
            validated_path = enforcer.validate(input_data.project_path)
        except PermissionError as e:
            return PoetryInstallOutput(success=False, message=str(e))

        if not validated_path.is_dir():
            return PoetryInstallOutput(
                success=False,
                message=f"Project directory '{validated_path}' does not exist.",
            )

        pyproject_path = validated_path / "pyproject.toml"
        requirements_path = validated_path / "requirements.txt"

        # Case 1: Poetry project exists
        if pyproject_path.is_file():
            cmd = ["poetry", "install", "--no-interaction"]
            result = run_async(background_runner.run(cmd, cwd=str(validated_path), timeout=600))

            if result["success"]:
                return PoetryInstallOutput(
                    success=True,
                    message=f"Successfully installed Poetry dependencies: {result.get('stdout', '')}",
                )
            else:
                error_msg = result.get("stderr", "") or result.get("error", "Poetry install failed.")
                return PoetryInstallOutput(
                    success=False,
                    message=f"Poetry installation failed: {error_msg}",
                )

        # Case 2: Standard pip project (requirements.txt fallback)
        elif requirements_path.is_file():
            # Create isolated virtualenv in settings.poetry_venv_path / project_name
            project_name = validated_path.name
            venv_dir = settings.poetry_venv_path / project_name
            venv_dir.parent.mkdir(parents=True, exist_ok=True)

            # Determine pip path inside the new venv
            is_windows = platform.system() == "Windows"
            pip_name = "pip.exe" if is_windows else "pip"
            python_name = "python.exe" if is_windows else "python"
            
            bin_dir = "Scripts" if is_windows else "bin"
            venv_pip_path = venv_dir / bin_dir / pip_name
            venv_python_path = venv_dir / bin_dir / python_name

            # 1. Create virtual environment
            if not venv_dir.exists():
                create_venv_cmd = ["python3" if not is_windows else "python", "-m", "venv", str(venv_dir)]
                venv_res = run_async(background_runner.run(create_venv_cmd))
                if not venv_res["success"]:
                    return PoetryInstallOutput(
                        success=False,
                        message=f"Failed to create isolated venv: {venv_res.get('error') or venv_res.get('stderr')}",
                    )

            # 2. Run pip install
            pip_cmd = [str(venv_pip_path), "install", "-r", str(requirements_path)]
            pip_res = run_async(background_runner.run(pip_cmd, timeout=600))

            if pip_res["success"]:
                return PoetryInstallOutput(
                    success=True,
                    message=(
                        f"Isolated virtualenv created at '{venv_dir}'. "
                        f"Successfully installed requirements.txt dependencies: {pip_res.get('stdout', '')}"
                    ),
                )
            else:
                error_msg = pip_res.get("stderr", "") or pip_res.get("error", "Pip install failed.")
                return PoetryInstallOutput(
                    success=False,
                    message=f"Pip installation failed: {error_msg}",
                )

        # Case 3: Neither config file found
        else:
            return PoetryInstallOutput(
                success=False,
                message=f"No dependency configuration files (pyproject.toml or requirements.txt) found in '{validated_path}'.",
            )


class PoetryAdd(BaseTool):
    """Adds a package dependency to pyproject.toml."""

    @property
    def name(self) -> str:
        return "poetry_add"

    @property
    def description(self) -> str:
        return "Add a package dependency to the Poetry project configuration."

    @property
    def input_schema(self) -> type[BaseModel]:
        return PoetryAddInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return PoetryAddOutput

    def run(self, input_data: PoetryAddInput) -> PoetryAddOutput:
        try:
            validated_path = enforcer.validate(input_data.project_path)
        except PermissionError as e:
            return PoetryAddOutput(success=False, message=str(e))

        if not (validated_path / "pyproject.toml").is_file():
            return PoetryAddOutput(
                success=False,
                message=f"Directory '{validated_path}' does not contain a valid pyproject.toml Poetry file.",
            )

        cmd = ["poetry", "add", input_data.package_name, "--no-interaction"]
        result = run_async(background_runner.run(cmd, cwd=str(validated_path)))

        if result["success"]:
            return PoetryAddOutput(
                success=True,
                message=f"Successfully added package '{input_data.package_name}': {result.get('stdout', '')}",
            )
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Poetry add failed.")
            return PoetryAddOutput(
                success=False,
                message=f"Poetry add failed: {error_msg}",
            )


class PoetryShow(BaseTool):
    """Shows the dependencies of the Poetry project."""

    @property
    def name(self) -> str:
        return "poetry_show"

    @property
    def description(self) -> str:
        return "Show the installed dependencies of the Poetry project as a tree."

    @property
    def input_schema(self) -> type[BaseModel]:
        return PoetryShowInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return PoetryShowOutput

    def run(self, input_data: PoetryShowInput) -> PoetryShowOutput:
        try:
            validated_path = enforcer.validate(input_data.project_path)
        except PermissionError as e:
            return PoetryShowOutput(success=False, dependencies_tree=str(e))

        if not (validated_path / "pyproject.toml").is_file():
            return PoetryShowOutput(
                success=False,
                dependencies_tree=f"Directory '{validated_path}' does not contain a valid pyproject.toml Poetry file.",
            )

        cmd = ["poetry", "show", "--tree"]
        result = run_async(background_runner.run(cmd, cwd=str(validated_path)))

        if result["success"]:
            tree = result.get("stdout", "").strip() or "No dependencies installed."
            return PoetryShowOutput(success=True, dependencies_tree=tree)
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Poetry show failed.")
            return PoetryShowOutput(success=False, dependencies_tree=error_msg)
