"""
schemas/delete_file_schema.py
=============================
Pydantic input/output schemas for the DeleteFile tool.
"""

from pydantic import BaseModel, Field

class DeleteFileInput(BaseModel):
    filepath: str = Field(
        ...,
        description="Absolute path to the file to delete. Must reside inside an approved sandbox root.",
    )

class DeleteFileOutput(BaseModel):
    success: bool = Field(..., description="True if deleted successfully")
    message: str = Field(..., description="Detail message of success or failure")
