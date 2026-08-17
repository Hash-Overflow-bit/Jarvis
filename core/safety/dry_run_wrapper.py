"""
core/safety/dry_run_wrapper.py
==============================
Dry-run simulator for safely mocking tool side-effects during testing.
"""

from typing import Dict, Any


class DryRunWrapper:
    """Generates mock success outputs for tools when running in simulation mode."""

    def get_mock_response(self, tool_name: str, parameters: dict) -> dict:
        """Returns a simulated successful return dict for the given tool."""
        msg = f"[DRY RUN] Simulated execution of '{tool_name}' with parameters {parameters}."
        
        # Customize outputs based on expected tool schema models
        if tool_name == "file_scanner":
            return {
                "success": True,
                "files": [
                    {"path": "info.log", "size_bytes": 1024, "modified_time": "2026-08-16T12:00:00Z"},
                    {"path": "error.log", "size_bytes": 512, "modified_time": "2026-08-16T12:05:00Z"}
                ],
                "scan_summary": f"Dry Run Scan: 2 files found matching criteria."
            }

        elif tool_name == "directory_audit":
            return {
                "success": True,
                "tree_output": ".\n├── info.log\n└── error.log\n",
                "total_files": 2,
                "total_size_bytes": 1536
            }

        elif tool_name == "file_cleanup":
            return {
                "success": True,
                "files_removed": ["temp.tmp"],
                "space_saved_bytes": 2048,
                "details": "[DRY RUN] Would have moved 1 temporary file to the trash."
            }

        elif tool_name in ["git_clone", "git_pull", "git_add", "git_commit", "git_push"]:
            return {
                "success": True,
                "stdout": f"[DRY RUN] Simulated Git command '{tool_name}' succeeded.",
                "stderr": "",
                "returncode": 0
            }

        elif tool_name == "git_status":
            return {
                "success": True,
                "stdout": "On branch main\nYour branch is up to date with 'origin/main'.\n\nnothing to commit, working tree clean",
                "stderr": "",
                "returncode": 0
            }

        elif tool_name in ["poetry_install", "poetry_add"]:
            return {
                "success": True,
                "stdout": f"[DRY RUN] Simulated Poetry package manager operation succeeded.",
                "stderr": "",
                "returncode": 0
            }

        elif tool_name == "poetry_show":
            return {
                "success": True,
                "stdout": "dependency-package1 (1.0.0)\ndependency-package2 (2.1.4)",
                "stderr": "",
                "returncode": 0
            }

        # Default fallback
        return {
            "success": True,
            "message": msg
        }


# Global dry run simulator singleton
dry_run_wrapper = DryRunWrapper()
