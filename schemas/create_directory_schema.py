"""
schemas/create_directory_schema.py
==================================
Pydantic input/output schemas for the CreateDirectory tool.
"""

from pydantic import BaseModel, Field


class CreateDirectoryInput(BaseModel):
    directory: str = Field(
        ...,
        description="Workspace-relative or absolute workspace path of the directory to create.",
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
