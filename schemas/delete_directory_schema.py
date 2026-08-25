"""
schemas/delete_directory_schema.py
==================================
Pydantic input/output schemas for the DeleteDirectory tool.
"""

from pydantic import BaseModel, Field


class DeleteDirectoryInput(BaseModel):
    directory: str = Field(
        ...,
        description="Absolute path to the directory/folder to delete. Must reside inside approved sandbox boundaries.",
    )


class DeleteDirectoryOutput(BaseModel):
    success: bool = Field(
        ...,
        description="True if the directory was successfully deleted and verified removed, False otherwise.",
    )
    message: str = Field(
        ...,
        description="Detail message of success or failure.",
    )
