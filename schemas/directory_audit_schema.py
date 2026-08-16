"""
schemas/directory_audit_schema.py
=================================
Pydantic input/output schemas for the DirectoryAudit tool.
"""

from typing import Optional
from pydantic import BaseModel, Field


class DirectoryAuditInput(BaseModel):
    directory: str = Field(
        ...,
        description="Absolute path to the directory to audit. Must reside inside an approved sandbox root.",
    )
    max_depth: Optional[int] = Field(
        3,
        description="Maximum depth of subdirectories to recursively walk (default is 3).",
    )


class DirectoryAuditOutput(BaseModel):
    tree_representation: str = Field(
        ...,
        description="A text-based tree representing the files and folders inside the directory.",
    )
    folder_count: int = Field(
        ...,
        description="Total number of folders found.",
    )
    file_count: int = Field(
        ...,
        description="Total number of files found.",
    )
