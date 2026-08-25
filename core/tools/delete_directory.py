"""
core/tools/delete_directory.py
==============================
DeleteDirectory tool implementation.
Deletes a folder/directory inside approved sandbox boundaries and verifies its removal.
"""

import shutil
from pathlib import Path
from send2trash import send2trash
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.delete_directory_schema import DeleteDirectoryInput, DeleteDirectoryOutput


class DeleteDirectory(BaseTool[DeleteDirectoryInput, DeleteDirectoryOutput]):
    """
    Deletes a folder/directory at any specified path on the filesystem.
    Sends to system trash or removes recursively if trash is unsupported.
    """

    @property
    def name(self) -> str:
        return "delete_directory"

    @property
    def description(self) -> str:
        return (
            "Deletes/removes a specified directory/folder from the filesystem. "
            "Requires an absolute directory path argument like 'directory'."
        )

    @property
    def input_schema(self) -> type[DeleteDirectoryInput]:
        return DeleteDirectoryInput

    @property
    def output_schema(self) -> type[DeleteDirectoryOutput]:
        return DeleteDirectoryOutput

    def run(self, input_data: DeleteDirectoryInput) -> DeleteDirectoryOutput:
        try:
            target_dir = enforcer.validate(input_data.directory)
            if not target_dir.exists():
                return DeleteDirectoryOutput(
                    success=False,
                    message=f"Target directory '{input_data.directory}' does not exist.",
                )

            # Attempt send2trash first
            try:
                send2trash(str(target_dir))
            except Exception:
                # Fallback to shutil.rmtree
                if target_dir.is_dir():
                    shutil.rmtree(str(target_dir))
                else:
                    target_dir.unlink()

            # Physical post-condition verification
            if target_dir.exists():
                return DeleteDirectoryOutput(
                    success=False,
                    message=f"Post-condition failure: Directory '{target_dir}' still exists after deletion.",
                )

            return DeleteDirectoryOutput(
                success=True,
                message=f"Successfully deleted directory: {target_dir}",
            )
        except Exception as e:
            return DeleteDirectoryOutput(
                success=False,
                message=f"Failed to delete directory '{input_data.directory}': {e}",
            )
