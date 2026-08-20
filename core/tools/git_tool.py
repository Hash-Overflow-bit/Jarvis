"""
core/tools/git_tool.py
======================
Git tools implementing clone, pull, status, add, commit, and push operations.
"""

import asyncio
from typing import Type
from pathlib import Path
from pydantic import BaseModel
from core.config import settings
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from core.tools.background_runner import background_runner
from schemas.git_tool_schema import (
    GitCloneInput,
    GitCloneOutput,
    GitPullInput,
    GitPullOutput,
    GitStatusInput,
    GitStatusOutput,
    GitAddInput,
    GitAddOutput,
    GitCommitInput,
    GitCommitOutput,
    GitPushInput,
    GitPushOutput,
)


def run_async(coro):
    """Utility to run async coroutines in a synchronous method."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # Fallback using nest_asyncio if the event loop is already running
        import nest_asyncio
        nest_asyncio.apply()
    return loop.run_until_complete(coro)


class GitClone(BaseTool[GitCloneInput, GitCloneOutput]):
    """Clones a remote git repository into the workspace."""

    @property
    def name(self) -> str:
        return "git_clone"

    @property
    def description(self) -> str:
        return "Clone a remote Git repository into the workspace using an HTTPS URL."

    @property
    def input_schema(self) -> Type[GitCloneInput]:
        return GitCloneInput

    @property
    def output_schema(self) -> Type[GitCloneOutput]:
        return GitCloneOutput

    def run(self, input_data: GitCloneInput) -> GitCloneOutput:
        url = input_data.url.strip()

        # Inject git token for non-interactive HTTPS auth if present
        if settings.git_token and "github.com" in url and "oauth2:" not in url:
            url = url.replace("https://", f"https://oauth2:{settings.git_token}@")

        # Resolve target directory
        if input_data.target_dir_name:
            target_path = settings.default_workspace_dir / input_data.target_dir_name
        else:
            # Extract repository name from URL
            repo_name = url.rstrip("/").split("/")[-1]
            # Strip oauth info if present in parsed name
            if "@" in repo_name:
                repo_name = repo_name.split("@")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            target_path = settings.default_workspace_dir / repo_name

        try:
            validated_path = enforcer.validate(target_path)
        except PermissionError as e:
            return GitCloneOutput(success=False, message=str(e))

        # Make sure parent directory exists
        validated_path.parent.mkdir(parents=True, exist_ok=True)

        if validated_path.exists() and any(validated_path.iterdir()):
            return GitCloneOutput(
                success=False,
                message=f"Target directory '{validated_path}' already exists and is not empty.",
            )

        cmd = ["git", "clone", url, str(validated_path), "--depth=1"]
        # Set terminal prompt to 0 to prevent blocking on credentials prompts
        env = {"GIT_TERMINAL_PROMPT": "0"}

        result = run_async(background_runner.run(cmd, env=env))

        if result["success"]:
            return GitCloneOutput(
                success=True,
                message=f"Successfully cloned repository into {validated_path.name}",
                resolved_path=str(validated_path),
            )
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Unknown error occurred.")
            # Redact token from error messages if printed
            if settings.git_token:
                error_msg = error_msg.replace(settings.git_token, "********")
            return GitCloneOutput(
                success=False,
                message=f"Failed to clone repository: {error_msg}",
            )


class GitPull(BaseTool[GitPullInput, GitPullOutput]):
    """Pulls the latest changes from the remote repository."""

    @property
    def name(self) -> str:
        return "git_pull"

    @property
    def description(self) -> str:
        return "Pull the latest commits from the remote repository branch (fast-forward only)."

    @property
    def input_schema(self) -> Type[GitPullInput]:
        return GitPullInput

    @property
    def output_schema(self) -> Type[GitPullOutput]:
        return GitPullOutput

    def run(self, input_data: GitPullInput) -> GitPullOutput:
        try:
            validated_path = enforcer.validate(input_data.repo_path)
        except PermissionError as e:
            return GitPullOutput(success=False, message=str(e))

        if not (validated_path / ".git").is_dir():
            return GitPullOutput(
                success=False,
                message=f"Directory '{validated_path}' is not a valid Git repository.",
            )

        # Pull fast-forward only to prevent merge commits from hanging or creating conflicts
        cmd = ["git", "pull", "--ff-only"]
        env = {"GIT_TERMINAL_PROMPT": "0"}
        result = run_async(background_runner.run(cmd, cwd=str(validated_path), env=env))

        if result["success"]:
            return GitPullOutput(
                success=True,
                message=result.get("stdout", "Repository is up to date."),
            )
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Failed to pull.")
            if "CONFLICT" in error_msg or "Automatic merge failed" in error_msg:
                error_msg = "Merge conflict detected. Pull aborted to preserve safety."
            return GitPullOutput(
                success=False,
                message=f"Failed to pull: {error_msg}",
            )


class GitStatus(BaseTool[GitStatusInput, GitStatusOutput]):
    """Gets the status of the repository."""

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Check the status of the local repository (untracked, modified, or staged files)."

    @property
    def input_schema(self) -> Type[GitStatusInput]:
        return GitStatusInput

    @property
    def output_schema(self) -> Type[GitStatusOutput]:
        return GitStatusOutput

    def run(self, input_data: GitStatusInput) -> GitStatusOutput:
        try:
            validated_path = enforcer.validate(input_data.repo_path)
        except PermissionError as e:
            return GitStatusOutput(success=False, status_summary=str(e))

        if not (validated_path / ".git").is_dir():
            return GitStatusOutput(
                success=False,
                status_summary=f"Directory '{validated_path}' is not a valid Git repository.",
            )

        cmd = ["git", "status", "--short"]
        result = run_async(background_runner.run(cmd, cwd=str(validated_path)))

        if result["success"]:
            summary = result.get("stdout", "").strip() or "No changes detected (working directory clean)."
            return GitStatusOutput(success=True, status_summary=summary)
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Failed to get status.")
            return GitStatusOutput(success=False, status_summary=error_msg)


class GitAdd(BaseTool[GitAddInput, GitAddOutput]):
    """Stages files in the repository."""

    @property
    def name(self) -> str:
        return "git_add"

    @property
    def description(self) -> str:
        return "Stage modified or untracked files in the repository to prepare for a commit."

    @property
    def input_schema(self) -> Type[GitAddInput]:
        return GitAddInput

    @property
    def output_schema(self) -> Type[GitAddOutput]:
        return GitAddOutput

    def run(self, input_data: GitAddInput) -> GitAddOutput:
        try:
            validated_path = enforcer.validate(input_data.repo_path)
        except PermissionError as e:
            return GitAddOutput(success=False, message=str(e))

        if not (validated_path / ".git").is_dir():
            return GitAddOutput(
                success=False,
                message=f"Directory '{validated_path}' is not a valid Git repository.",
            )

        pattern = input_data.file_pattern.strip() or "."
        cmd = ["git", "add", pattern]
        result = run_async(background_runner.run(cmd, cwd=str(validated_path)))

        if result["success"]:
            return GitAddOutput(
                success=True,
                message=f"Successfully staged pattern '{pattern}' in repository.",
            )
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Failed to stage files.")
            return GitAddOutput(
                success=False,
                message=f"Failed to stage files: {error_msg}",
            )


class GitCommit(BaseTool[GitCommitInput, GitCommitOutput]):
    """Commits staged changes."""

    @property
    def name(self) -> str:
        return "git_commit"

    @property
    def description(self) -> str:
        return "Commit staged changes in the local repository with a commit message."

    @property
    def input_schema(self) -> Type[GitCommitInput]:
        return GitCommitInput

    @property
    def output_schema(self) -> Type[GitCommitOutput]:
        return GitCommitOutput

    def run(self, input_data: GitCommitInput) -> GitCommitOutput:
        try:
            validated_path = enforcer.validate(input_data.repo_path)
        except PermissionError as e:
            return GitCommitOutput(success=False, message=str(e))

        if not (validated_path / ".git").is_dir():
            return GitCommitOutput(
                success=False,
                message=f"Directory '{validated_path}' is not a valid Git repository.",
            )

        cmd = ["git", "commit", "-m", input_data.commit_message]
        
        # Configure user name/email temporarily for commit if not set globally on machine
        env = {
            "GIT_AUTHOR_NAME": settings.git_user_name,
            "GIT_AUTHOR_EMAIL": settings.git_user_email,
            "GIT_COMMITTER_NAME": settings.git_user_name,
            "GIT_COMMITTER_EMAIL": settings.git_user_email,
        }

        result = run_async(background_runner.run(cmd, cwd=str(validated_path), env=env))

        if result["success"]:
            return GitCommitOutput(
                success=True,
                message=result.get("stdout", "Changes committed successfully."),
            )
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Failed to commit.")
            if "nothing to commit" in result.get("stdout", "").lower():
                return GitCommitOutput(
                    success=False,
                    message="Nothing staged to commit. Run git_add first.",
                )
            return GitCommitOutput(
                success=False,
                message=f"Failed to commit: {error_msg}",
            )


class GitPush(BaseTool[GitPushInput, GitPushOutput]):
    """Pushes committed changes."""

    @property
    def name(self) -> str:
        return "git_push"

    @property
    def description(self) -> str:
        return "Push committed local changes to the remote branch."

    @property
    def input_schema(self) -> Type[GitPushInput]:
        return GitPushInput

    @property
    def output_schema(self) -> Type[GitPushOutput]:
        return GitPushOutput

    def run(self, input_data: GitPushInput) -> GitPushOutput:
        try:
            validated_path = enforcer.validate(input_data.repo_path)
        except PermissionError as e:
            return GitPushOutput(success=False, message=str(e))

        if not (validated_path / ".git").is_dir():
            return GitPushOutput(
                success=False,
                message=f"Directory '{validated_path}' is not a valid Git repository.",
            )

        branch = input_data.branch.strip() or "main"
        cmd = ["git", "push", "origin", branch]
        env = {"GIT_TERMINAL_PROMPT": "0"}
        result = run_async(background_runner.run(cmd, cwd=str(validated_path), env=env))

        if result["success"]:
            return GitPushOutput(
                success=True,
                message=result.get("stdout", f"Successfully pushed commits to remote branch '{branch}'."),
            )
        else:
            error_msg = result.get("stderr", "") or result.get("error", "Failed to push.")
            return GitPushOutput(
                success=False,
                message=f"Failed to push: {error_msg}",
            )
