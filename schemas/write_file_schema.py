"""
schemas/write_file_schema.py
============================
Pydantic input/output schemas for the WriteFile tool.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class WriteFileInput(BaseModel):
    filepath: str = Field(
        ...,
        description="Workspace-relative or absolute workspace path of the document to write.",
    )
    content: str = Field(
        default="",
        description="Text content to write to the file.",
    )
    mode: Literal["create", "overwrite", "append"] = Field(
        default="create",
        description="Write mode: 'create' (fails if file exists), 'overwrite' (replaces existing file), or 'append' (adds to existing file).",
    )


class WriteFileOutput(BaseModel):
    success: bool = Field(
        ...,
        description="True if the file was successfully written, False otherwise.",
    )
    message: str = Field(
        ...,
        description="Detail message of success or failure.",
    )
    path: Optional[str] = None
    byte_count: int = 0
    sha256: Optional[str] = None
