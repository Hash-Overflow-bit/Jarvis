"""
schemas/create_directory_schema.py
==================================
Pydantic input/output schemas for the CreateDirectory tool.
"""

from pydantic import BaseModel, Field


class CreateDirectoryInput(BaseModel):
    directory: str = Field(
        ...,
        description="Absolute path to the directory to create. Must reside inside an approved sandbox root.",
    )


class CreateDirectoryOutput(BaseModel):
    success: bool = Field(
        ...,
        description="True if the directory was successfully created, False otherwise.",
    )
    message: str = Field(
        ...,
        description="Detail message of success or failure.",
    )
