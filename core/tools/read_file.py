"""
core/tools/read_file.py
=======================
Jarvis tool to read the contents of files from the local filesystem.
"""

from typing import Type, Optional
from pydantic import BaseModel, Field
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer


class ReadFileInput(BaseModel):
    filepath: str = Field(..., description="The absolute or relative path of the file to read (use forward slashes).")


class ReadFileOutput(BaseModel):
    success: bool
    content: str
    error: Optional[str] = None


class ReadFile(BaseTool[ReadFileInput, ReadFileOutput]):
    """
    Reads the text contents of a file inside sandbox-approved paths.
    """

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the text content of a file from the local filesystem. Use this when "
            "you need to read, view, parse, check, or load a file's content (such as "
            "a CSV, MD, TXT, or JSON file)."
        )

    @property
    def input_schema(self) -> Type[ReadFileInput]:
        return ReadFileInput

    @property
    def output_schema(self) -> Type[ReadFileOutput]:
        return ReadFileOutput

    def run(self, input_data: ReadFileInput) -> ReadFileOutput:
        try:
            # Enforce sandbox and get absolute path
            resolved_path = enforcer.validate(input_data.filepath)

            if not resolved_path.exists():
                return ReadFileOutput(
                    success=False,
                    content="",
                    error=f"File '{input_data.filepath}' does not exist."
                )

            if not resolved_path.is_file():
                return ReadFileOutput(
                    success=False,
                    content="",
                    error=f"Path '{input_data.filepath}' is a directory, not a file."
                )

            # Read content with UTF-8 encoding
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return ReadFileOutput(
                success=True,
                content=content
            )

        except PermissionError as pe:
            return ReadFileOutput(
                success=False,
                content="",
                error=f"Access denied to file: {pe}"
            )
        except Exception as e:
            return ReadFileOutput(
                success=False,
                content="",
                error=f"Failed to read file: {e}"
            )
