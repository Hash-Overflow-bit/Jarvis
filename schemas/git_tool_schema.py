"""
schemas/git_tool_schema.py
==========================
Pydantic input and output models for Git tools.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# --- Git Clone ---
class GitCloneInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    url: str = Field(
        ...,
        description="The HTTPS URL of the Git repository to clone (e.g. 'https://github.com/tiangolo/fastapi').",
        alias="url"
    )
    target_dir_name: Optional[str] = Field(
        None,
        description="Optional folder name inside the workspace. If omitted, uses the repository name."
    )


class GitCloneOutput(BaseModel):
    success: bool = Field(..., description="Whether the repository was cloned successfully.")
    message: str = Field(..., description="Details/stdout of the operation.")
    resolved_path: Optional[str] = Field(None, description="The absolute path to the cloned repository.")


# --- Git Pull ---
class GitPullInput(BaseModel):
    repo_path: str = Field(
        ...,
        description="The absolute path to the repository directory to pull changes."
    )


class GitPullOutput(BaseModel):
    success: bool = Field(..., description="Whether the pull succeeded.")
    message: str = Field(..., description="Details/stdout of the operation.")


# --- Git Status ---
class GitStatusInput(BaseModel):
    repo_path: str = Field(
        ...,
        description="The absolute path to the repository directory."
    )


class GitStatusOutput(BaseModel):
    success: bool = Field(..., description="Whether status was read successfully.")
    status_summary: str = Field(..., description="Summary/stdout of git status.")


# --- Git Add ---
class GitAddInput(BaseModel):
    repo_path: str = Field(..., description="The absolute path to the repository directory.")
    file_pattern: str = Field(
        ".",
        description="The file pattern to stage (default is '.', which stages all files)."
    )


class GitAddOutput(BaseModel):
    success: bool = Field(..., description="Whether git add succeeded.")
    message: str = Field(..., description="Details of the add operation.")


# --- Git Commit ---
class GitCommitInput(BaseModel):
    repo_path: str = Field(..., description="The absolute path to the repository directory.")
    commit_message: str = Field(..., description="The commit message description.")


class GitCommitOutput(BaseModel):
    success: bool = Field(..., description="Whether git commit succeeded.")
    message: str = Field(..., description="Details of the commit operation.")


# --- Git Push ---
class GitPushInput(BaseModel):
    repo_path: str = Field(..., description="The absolute path to the repository directory.")
    branch: str = Field(
        "main",
        description="The remote branch to push to (default is 'main')."
    )


class GitPushOutput(BaseModel):
    success: bool = Field(..., description="Whether git push succeeded.")
    message: str = Field(..., description="Details of the push operation.")
