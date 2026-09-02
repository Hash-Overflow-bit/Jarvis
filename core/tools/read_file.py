"""
core/tools/read_file.py
=======================
Jarvis tool to read the contents of files from the local filesystem.
"""

from typing import Type, Optional
from pydantic import BaseModel, Field
from core.tools.base_tool import BaseTool
from core.workspace.documents import WorkspaceDocuments, WorkspaceDocumentError


class ReadFileInput(BaseModel):
    filepath: str = Field(..., description="The absolute or relative path of the file to read (use forward slashes).")


class ReadFileOutput(BaseModel):
    success: bool
    content: str
    error: Optional[str] = None
    path: Optional[str] = None
    byte_count: int = 0
    sha256: Optional[str] = None


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
            "Read UTF-8 text from a document inside the configured workspace. Use this when "
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
            content, receipt = WorkspaceDocuments().read_text(input_data.filepath)
            return ReadFileOutput(
                success=True,
                content=content,
                path=str(receipt.path),
                byte_count=receipt.byte_count,
                sha256=receipt.sha256,
            )
        except (WorkspaceDocumentError, OSError) as e:
            return ReadFileOutput(
                success=False,
                content="",
                error=f"Failed to read workspace document: {e}"
            )
