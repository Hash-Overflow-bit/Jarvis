"""
core/orchestrator/worktree_orchestrator.py
==========================================
Manages isolated Git worktrees for parallel agent execution.
Prevents workspace file locks and keeps the git history clean.
"""

import os
import shutil
import subprocess
import logging
from pathlib import Path
from multiprocessing import Process
from core.config import settings

logger = logging.getLogger("worktree_orchestrator")


class GitWorktreeOrchestrator:
    """
    Orchestrates parallel coding workflows by checking out clean, isolated
    git worktrees in which CrewAI or LangGraph agents can execute independently.
    """

    def __init__(self, repo_path: Path | None = None):
        self.repo_path = repo_path or settings._project_root
        # Isolated worktree directories are placed inside workspace/worktrees/
        self.worktrees_root = settings.default_workspace_dir / "worktrees"
        self.worktrees_root.mkdir(parents=True, exist_ok=True)

    def _run_git(self, args: list[str], cwd: Path | None = None) -> str:
        """Helper to run a git command safely and return standard output."""
        cwd_path = cwd or self.repo_path
        cmd = ["git"] + args
        result = subprocess.run(
            cmd, cwd=cwd_path, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def create_worktree(self, branch_name: str, base_commit: str = "main") -> Path:
        """
        Creates a clean, isolated git worktree for the target branch name.
        If the branch already exists, checks it out. Otherwise, creates it.
        """
        worktree_path = self.worktrees_root / branch_name

        # Clean up any existing directory conflicts first
        if worktree_path.exists():
            self.remove_worktree(branch_name)

        logger.info(f"Creating isolated Git worktree for branch '{branch_name}' at: {worktree_path}")

        # Check if the branch exists in the repository
        try:
            branches = self._run_git(["branch", "--list", branch_name])
        except Exception:
            branches = ""

        if branch_name in branches.split():
            # Checkout existing branch
            self._run_git(["worktree", "add", str(worktree_path), branch_name])
        else:
            # Create a new branch and check it out
            self._run_git(["worktree", "add", "-b", branch_name, str(worktree_path), base_commit])

        return worktree_path

    def remove_worktree(self, branch_name: str):
        """Removes the git worktree and deletes all its files."""
        worktree_path = self.worktrees_root / branch_name
        logger.info(f"Removing Git worktree at: {worktree_path}")

        try:
            # Tell git to remove the worktree registration
            self._run_git(["worktree", "remove", str(worktree_path), "--force"])
        except Exception as e:
            logger.warning(f"Git failed to remove worktree '{branch_name}': {e}")

        # Force clean up directories
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

    def run_agent_parallel(
        self, agent_fn, args: tuple, branch_name: str, base_commit: str = "main"
    ) -> Process:
        """
        Spins up a separate Process to run an agent function inside the checked-out worktree.
        Sets default workspace env variables locally inside the process to ensure isolation.

        Args:
            agent_fn: Function to execute. Must accept `worktree_path` as its first argument.
            args: Supporting arguments to pass to `agent_fn`.
            branch_name: Target branch name for isolation.
            base_commit: Baseline branch/commit to branch off of.
        """
        worktree_path = self.create_worktree(branch_name, base_commit)

        def process_wrapper(w_path, fn, fn_args):
            # Isolate the environment variables inside this child process
            os.environ["DEFAULT_WORKSPACE_DIR"] = str(w_path)
            try:
                fn(w_path, *fn_args)
            except Exception as e:
                logger.error(f"Parallel execution failed on branch '{branch_name}': {e}")
                raise e

        p = Process(target=process_wrapper, args=(worktree_path, agent_fn, args))
        p.start()
        return p

    def merge_and_cleanup(self, branch_name: str, target_branch: str = "main"):
        """
        Commits all modifications inside the worktree, merges it back to target_branch,
        and deletes the temporary worktree files.
        """
        worktree_path = self.worktrees_root / branch_name
        if not worktree_path.exists():
            logger.error(f"Cannot merge, worktree path does not exist: {worktree_path}")
            return

        logger.info(f"Merging changes from '{branch_name}' into '{target_branch}'...")

        try:
            # 1. Commit everything in the worktree
            self._run_git(["add", "."], cwd=worktree_path)
            status = self._run_git(["status", "--porcelain"], cwd=worktree_path)
            if status:
                self._run_git(
                    ["commit", "-m", f"feat: parallel work from agent on {branch_name}"],
                    cwd=worktree_path,
                )
                logger.info(f"Committed changes on '{branch_name}'.")

            # 2. Merge back to main branch in main repository
            self._run_git(["checkout", target_branch])
            self._run_git(["merge", branch_name])
            logger.info(f"Merged '{branch_name}' into '{target_branch}' successfully.")
        except Exception as e:
            logger.error(f"Failed to merge worktree changes: {e}")
            raise e
        finally:
            # 3. Cleanup worktree registration and files
            self.remove_worktree(branch_name)
            try:
                self._run_git(["branch", "-d", branch_name])
            except Exception as e:
                logger.warning(f"Could not delete branch '{branch_name}': {e}")
