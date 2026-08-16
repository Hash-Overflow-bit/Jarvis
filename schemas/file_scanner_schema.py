"""
schemas/file_scanner_schema.py
==============================
Pydantic input/output schemas for the FileScanner tool.
"""

from typing import Optional
from pydantic import BaseModel, Field


class FileScannerInput(BaseModel):
    directory: str = Field(
        ...,
        description="Absolute path to the directory to scan. Must reside inside an approved sandbox root.",
    )
    extension_filter: Optional[str] = Field(
        None,
        description="Filter files by extension (e.g. '.log', '.tmp'). Case-insensitive.",
    )
    min_size_mb: Optional[float] = Field(
        None,
        description="Minimum file size in megabytes.",
    )


class FileScannerOutput(BaseModel):
    files: list[dict] = Field(
        ...,
        description="List of file objects, each containing: name, path, size_mb, modified_date.",
    )
    total_count: int = Field(
        ...,
        description="Total number of files matching the filters.",
    )
    total_size_mb: float = Field(
        ...,
        description="Combined size of all matching files in megabytes.",
    )
