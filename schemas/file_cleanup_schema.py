"""
schemas/file_cleanup_schema.py
==============================
Pydantic input/output schemas for the FileCleanup tool.
"""

from typing import Optional
from pydantic import BaseModel, Field


class FileCleanupInput(BaseModel):
    directory: str = Field(
        ...,
        description="Absolute path to the directory to clean. Must reside inside an approved sandbox root.",
    )
    extension_filter: Optional[str] = Field(
        None,
        description="Filter files by extension to delete (e.g. '.log', '.tmp'). Case-insensitive.",
    )
    min_age_days: Optional[float] = Field(
        None,
        description="Minimum age of the file in days since last modified.",
    )
    min_size_mb: Optional[float] = Field(
        None,
        description="Minimum file size in megabytes to delete.",
    )


class FileCleanupOutput(BaseModel):
    status: str = Field(
        ...,
        description="Summary of the cleanup operation.",
    )
    deleted_files: list[str] = Field(
        ...,
        description="Paths of the files that were successfully moved to trash.",
    )
    total_freed_mb: float = Field(
        ...,
        description="Total size in megabytes of files moved to trash.",
    )
