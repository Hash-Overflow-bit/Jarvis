"""
core/tools/background_runner.py
===============================
Async subprocess manager for non-blocking command execution.
"""

import asyncio
import os
from typing import Any


class BackgroundRunner:
    """
    Asynchronously executes a subprocess command.
    Captures stdout, stderr, exit code, and handles timeouts.
    """

    async def run(
        self,
        cmd: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 300,
    ) -> dict[str, Any]:
        """
        Runs a command asynchronously.

        Args:
            cmd: Command list, e.g., ["git", "clone", "url"].
            cwd: Working directory for execution.
            env: Custom environment variables.
            timeout: Max execution time in seconds.

        Returns:
            A dict with:
                - "success": bool
                - "stdout": str
                - "stderr": str
                - "returncode": int
                - "error": str (optional)
        """
        # Merge system environment to inherit PATH (critical for finding git, poetry, etc.)
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        # In WSL/macOS, poetry/git might be installed in user directories,
        # so let's make sure the path contains common bin dirs
        if "PATH" in full_env:
            paths = full_env["PATH"].split(os.pathsep)
            user_bin = os.path.expanduser("~/.local/bin")
            if user_bin not in paths:
                paths.insert(0, user_bin)
            full_env["PATH"] = os.pathsep.join(paths)

        try:
            # Execute the subprocess without shell=True for security
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=full_env,
            )

            # Wait for the process to complete with timeout
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                # Terminate and clean up if it timed out
                try:
                    proc.terminate()
                    await proc.wait()
                except OSError:
                    pass
                return {
                    "success": False,
                    "error": f"Process timed out after {timeout} seconds.",
                    "stdout": "",
                    "stderr": "",
                    "returncode": -1,
                }

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            return {
                "success": proc.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": proc.returncode,
            }

        except FileNotFoundError as e:
            return {
                "success": False,
                "error": f"Executable not found: {str(e)}",
                "stdout": "",
                "stderr": "",
                "returncode": -1,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to execute command: {str(e)}",
                "stdout": "",
                "stderr": "",
                "returncode": -1,
            }


# Global background runner instance
background_runner = BackgroundRunner()
