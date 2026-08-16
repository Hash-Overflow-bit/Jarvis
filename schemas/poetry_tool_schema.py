"""
schemas/poetry_tool_schema.py
=============================
Pydantic input and output models for Poetry tools.
"""

from pydantic import BaseModel, Field


# --- Poetry Install ---
class PoetryInstallInput(BaseModel):
    project_path: str = Field(
        ...,
        description="The absolute path to the directory containing pyproject.toml (or requirements.txt)."
    )


class PoetryInstallOutput(BaseModel):
    success: bool = Field(..., description="Whether the installation succeeded.")
    message: str = Field(..., description="Details/stdout of the installation.")


# --- Poetry Add ---
class PoetryAddInput(BaseModel):
    project_path: str = Field(..., description="The absolute path to the directory containing pyproject.toml.")
    package_name: str = Field(..., description="The name of the package to add (e.g. 'requests').")


class PoetryAddOutput(BaseModel):
    success: bool = Field(..., description="Whether the package was added successfully.")
    message: str = Field(..., description="Details/stdout of the operation.")


# --- Poetry Show ---
class PoetryShowInput(BaseModel):
    project_path: str = Field(..., description="The absolute path to the directory containing pyproject.toml.")


class PoetryShowOutput(BaseModel):
    success: bool = Field(..., description="Whether the dependencies list was read successfully.")
    dependencies_tree: str = Field(..., description="Formatted dependency tree structure.")
