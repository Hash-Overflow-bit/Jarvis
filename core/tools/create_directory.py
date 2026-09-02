"""
core/tools/create_directory.py
==============================
CreateDirectory tool implementation.
Creates a new folder inside the approved sandbox boundaries.
"""

from pydantic import BaseModel
from core.tools.base_tool import BaseTool
from core.workspace.documents import WorkspaceDocumentError
from core.workspace.filesystem import WorkspaceFilesystem
from schemas.create_directory_schema import CreateDirectoryInput, CreateDirectoryOutput


class CreateDirectory(BaseTool):
    """
    Creates a new directory inside the configured workspace.
    """

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return (
            "Create a new directory inside the configured workspace. "
            "Relative paths and workspace/... paths are accepted."

        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CreateDirectoryInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return CreateDirectoryOutput

   
    def run(self, input_data: CreateDirectoryInput) -> CreateDirectoryOutput:
        try:
            target_dir = WorkspaceFilesystem().create_directory(input_data.directory)
            return CreateDirectoryOutput(
                success=True,
                message=f"Successfully created directory: {target_dir}",
            )
        except (WorkspaceDocumentError, OSError) as e:
            return CreateDirectoryOutput(
                success=False,
                message=f"Failed to create directory '{input_data.directory}': {e}",
            )
