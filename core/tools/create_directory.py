"""
core/tools/create_directory.py
==============================
CreateDirectory tool implementation.
Creates a new folder inside the approved sandbox boundaries.
"""

import os
from pathlib import Path
from pydantic import BaseModel
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.create_directory_schema import CreateDirectoryInput, CreateDirectoryOutput


class CreateDirectory(BaseTool):
    """
    Creates a new directory inside the approved sandbox boundaries.
    """

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return (
            "Creates a new directory/folder at the specified path. "
            "The path must reside inside an approved sandbox root."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CreateDirectoryInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return CreateDirectoryOutput

    def run(self, input_data: CreateDirectoryInput) -> CreateDirectoryOutput:
        # Validate the target directory path using sandbox enforcer
        target_dir = enforcer.validate(input_data.directory)

        try:
            # Create directory and any missing parent directories
            target_dir.mkdir(parents=True, exist_ok=True)
            return CreateDirectoryOutput(
                success=True,
                message=f"Successfully created directory: {target_dir}",
            )
        except Exception as e:
            return CreateDirectoryOutput(
                success=False,
                message=f"Failed to create directory '{target_dir}': {e}",
            )
