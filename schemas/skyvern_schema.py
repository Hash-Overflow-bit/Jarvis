"""
schemas/skyvern_schema.py
===========================
Pydantic input/output schemas for the SkyvernTool browser automation.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SkyvernTaskInput(BaseModel):
    url: str = Field(
        ...,
        description="The target web portal URL to navigate to (e.g. 'https://quotes.toscrape.com' or 'https://portal.example.com')."
    )
    navigation_goal: str = Field(
        ...,
        description="Detailed plain text description of the browser task for visual navigation (e.g. 'Log in with credentials, navigate to Invoices, and download PDF')."
    )
    extracted_fields: Optional[List[str]] = Field(
        default=None,
        description="Optional list of specific visual field names to extract from the webpage (e.g. ['quote', 'author', 'total_amount'])."
    )
    download_dir: Optional[str] = Field(
        default=None,
        description="Optional target directory path to save downloaded files. Defaults to the OS Desktop directory."
    )


class SkyvernTaskOutput(BaseModel):
    success: bool = Field(
        ...,
        description="True if the Skyvern browser task completed successfully, False otherwise."
    )
    task_id: str = Field(
        ...,
        description="Unique task identifier returned by the Skyvern engine."
    )
    status: str = Field(
        ...,
        description="Final execution status (e.g. 'completed', 'failed', 'timeout')."
    )
    extracted_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured JSON data visually extracted from the webpage."
    )
    downloaded_files: List[str] = Field(
        default_factory=list,
        description="List of absolute file paths saved on the filesystem."
    )
    message: str = Field(
        ...,
        description="Detailed message summarizing task execution or error details."
    )
