"""
core/tools/write_file.py
========================
WriteFile tool implementation.
Writes text content to a file inside the approved sandbox boundaries.
"""

import os
from pathlib import Path
from pydantic import BaseModel
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.write_file_schema import WriteFileInput, WriteFileOutput


class WriteFile(BaseTool):
    """
    Writes content to a file at any path the OS user has permission to access.
    When sandbox mode is disabled (default), there are no path restrictions.
    """

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Writes text content to a file at any specified path on the filesystem. "
            "Accepts full absolute paths like /Users/wilson/Desktop/notes.txt or "
            "C:\\Users\\wmjar\\Desktop\\notes.txt. "
            "Creates the file if it does not exist, or overwrites it if it does. "
            "Also creates any missing parent directories automatically."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return WriteFileInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return WriteFileOutput


    def run(self, input_data: WriteFileInput) -> WriteFileOutput:
        try:
            # Validate path (raises PermissionError if sandbox is ON and path is outside)
            target_file = enforcer.validate(input_data.filepath)
            # Ensure parent directories exist
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(input_data.content)

            return WriteFileOutput(
                success=True,
                message=f"Successfully wrote content to: {target_file}",
            )
        except Exception as e:
            return WriteFileOutput(
                success=False,
                message=f"Failed to write file '{input_data.filepath}': {e}",
            )
