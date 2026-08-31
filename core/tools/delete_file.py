"""
core/tools/delete_file.py
=========================
DeleteFile tool implementation.
Deletes a file inside approved sandbox boundaries and verifies its removal.
"""

from send2trash import send2trash
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.delete_file_schema import DeleteFileInput, DeleteFileOutput

class DeleteFile(BaseTool[DeleteFileInput, DeleteFileOutput]):
    """
    Deletes a file at any specified path on the filesystem.
    Sends to system trash or removes recursively if trash is unsupported.
    """

    @property
    def name(self) -> str:
        return "delete_file"

    @property
    def description(self) -> str:
        return (
            "Deletes/removes a specified file from the filesystem. "
            "Requires an absolute file path argument like 'filepath'."
        )

    @property
    def input_schema(self) -> type[DeleteFileInput]:
        return DeleteFileInput

    @property
    def output_schema(self) -> type[DeleteFileOutput]:
        return DeleteFileOutput

    def run(self, input_data: DeleteFileInput) -> DeleteFileOutput:
        try:
            target_file = enforcer.validate(input_data.filepath)
            
            if not target_file.exists():
                return DeleteFileOutput(
                    success=False,
                    message=f"Target file '{input_data.filepath}' does not exist.",
                )
                
            if not target_file.is_file():
                return DeleteFileOutput(
                    success=False,
                    message=f"Path '{input_data.filepath}' is a directory, not a file.",
                )

            # Attempt send2trash first
            try:
                send2trash(str(target_file))
            except Exception:
                # Fallback to unlink
                target_file.unlink()

            # Physical post-condition verification
            if target_file.exists():
                return DeleteFileOutput(
                    success=False,
                    message=f"Post-condition failure: File '{target_file}' still exists after deletion.",
                )

            return DeleteFileOutput(
                success=True,
                message=f"Successfully deleted file: {target_file}",
            )
        except Exception as e:
            return DeleteFileOutput(
                success=False,
                message=f"Failed to delete file '{input_data.filepath}': {e}",
            )
