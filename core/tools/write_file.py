"""
core/tools/write_file.py
========================
WriteFile tool implementation.
Writes text content to a file inside the approved sandbox boundaries.
"""

from typing import Type
from core.tools.base_tool import BaseTool
from core.workspace.documents import WorkspaceDocuments, WorkspaceDocumentError
from schemas.write_file_schema import WriteFileInput, WriteFileOutput


class WriteFile(BaseTool[WriteFileInput, WriteFileOutput]):
    """
    Writes verified UTF-8 text inside the configured workspace only.
    """

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write UTF-8 text to a document inside the configured workspace. "
            "Create mode never overwrites; overwrite and append must be explicit."
        )

    @property
    def input_schema(self) -> Type[WriteFileInput]:
        return WriteFileInput

    @property
    def output_schema(self) -> Type[WriteFileOutput]:
        return WriteFileOutput


    def run(self, input_data: WriteFileInput) -> WriteFileOutput:
        try:
            receipt = WorkspaceDocuments().write_text(
                input_data.filepath,
                input_data.content,
                mode=input_data.mode,
            )
            return WriteFileOutput(
                success=True,
                message=(
                    f"Successfully wrote {receipt.byte_count} bytes to: {receipt.path} "
                    f"(SHA-256: {receipt.sha256})"
                ),
                path=str(receipt.path),
                byte_count=receipt.byte_count,
                sha256=receipt.sha256,
            )
        except (WorkspaceDocumentError, OSError) as e:
            return WriteFileOutput(
                success=False,
                message=f"Failed to write file '{input_data.filepath}': {e}",
            )
