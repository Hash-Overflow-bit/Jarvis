"""
core/tools/write_file.py
========================
WriteFile tool implementation.
Writes text content to a file inside the approved sandbox boundaries.
"""

import os
from pathlib import Path
from typing import Type
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.write_file_schema import WriteFileInput, WriteFileOutput


class WriteFile(BaseTool[WriteFileInput, WriteFileOutput]):
    """
    Writes content to a file at any path the OS user has permission to access.
    When sandbox mode is disabled (default), there are no path restrictions.
    """

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Writes text content to a file at any specified absolute path on the filesystem. "
            "Creates the file if it does not exist, or overwrites it if it does. "
            "Also creates any missing parent directories automatically."
        )

    @property
    def input_schema(self) -> Type[WriteFileInput]:
        return WriteFileInput

    @property
    def output_schema(self) -> Type[WriteFileOutput]:
        return WriteFileOutput


    def run(self, input_data: WriteFileInput) -> WriteFileOutput:
        import hashlib
        from core.config import settings
        try:
            # 1. Resolve and Validate Path Globally against Sandbox
            target_file = enforcer.validate(input_data.filepath)
            
            # 2. Enforce Workspace-Only Policy for Writes
            workspace = Path(settings.default_workspace_dir).resolve()
            try:
                target_file.relative_to(workspace)
            except ValueError:
                return WriteFileOutput(
                    success=False,
                    message=f"BLOCKED_OUTSIDE_WORKSPACE: Path '{target_file}' is outside the configured workspace '{workspace}'. Writing to Desktop or other external paths is not permitted. Please ask the user to configure a different workspace if needed."
                )
            
            # 3. File existence check based on mode
            file_exists = target_file.exists()
            mode = getattr(input_data, 'mode', 'create')
            
            if mode == 'create' and file_exists:
                return WriteFileOutput(
                    success=False,
                    message=f"File already exists at '{target_file}'. Mode is 'create'. Explicitly use 'overwrite' if you intend to replace it.",
                )
                
            # 4. Ensure parent directories exist
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # 5. Write content
            file_mode = "a" if mode == "append" else "w"
            with open(target_file, file_mode, encoding="utf-8") as f:
                f.write(input_data.content)
                
            # 6. Physical verification and Receipt Generation
            if not target_file.exists():
                return WriteFileOutput(
                    success=False,
                    message=f"Post-condition failure: File '{target_file}' was not found on disk after writing.",
                )
                
            # Reopen the file to verify its contents
            with open(target_file, "rb") as f:
                actual_bytes = f.read()
                file_hash = hashlib.sha256(actual_bytes).hexdigest()

            return WriteFileOutput(
                success=True,
                message=f"Successfully wrote {len(actual_bytes)} bytes to: {target_file} (SHA-256: {file_hash})",
            )
        except Exception as e:
            return WriteFileOutput(
                success=False,
                message=f"Failed to write file '{input_data.filepath}': {e}",
            )
