"""
core/tools/create_directory.py
==============================
CreateDirectory tool implementation.
Creates a new folder inside the approved sandbox boundaries.
"""

import os
from pathlib import Path
from typing import Type
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.create_directory_schema import CreateDirectoryInput, CreateDirectoryOutput


class CreateDirectory(BaseTool[CreateDirectoryInput, CreateDirectoryOutput]):
    """
    Creates a new directory at any path the OS user has permission to access.
    When sandbox mode is disabled (default), there are no path restrictions.
    """

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return (
            "Creates a new directory/folder at any specified path on the filesystem. "
            "Accepts full absolute paths like C:\\Users\\your_username\\Desktop\\MyFolder or "
            "/Users/your_username/Desktop/MyFolder. "
            "Creates all missing parent directories automatically."

        )

    @property
    def input_schema(self) -> Type[CreateDirectoryInput]:
        return CreateDirectoryInput

    @property
    def output_schema(self) -> Type[CreateDirectoryOutput]:
        return CreateDirectoryOutput

    def run(self, input_data: CreateDirectoryInput) -> CreateDirectoryOutput:
        try:
            # Validate path (raises PermissionError if sandbox is ON and path is outside)
            target_dir = enforcer.validate(input_data.directory)
            # Create directory and any missing parent directories
            target_dir.mkdir(parents=True, exist_ok=True)
            return CreateDirectoryOutput(
                success=True,
                message=f"Successfully created directory: {target_dir}",
            )
        except Exception as e:
            return CreateDirectoryOutput(
                success=False,
                message=f"Failed to create directory '{input_data.directory}': {e}",
            )
