"""
schemas/write_file_schema.py
============================
Pydantic input/output schemas for the WriteFile tool.
"""

from pydantic import BaseModel, Field


class WriteFileInput(BaseModel):
    filepath: str = Field(
        ...,
        description="Absolute path to the file to write. Must reside inside an approved sandbox root.",
    )
    content: str = Field(
        default="",
        description="Text content to write to the file.",
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
