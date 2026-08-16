"""
core/tools/file_cleanup.py
==========================
FileCleanup tool implementation.
Safely moves matching files to system trash (or fallbacks to local .jarvis_trash) inside sandbox.
"""

import os
import time
import shutil
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel
from send2trash import send2trash
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.file_cleanup_schema import FileCleanupInput, FileCleanupOutput


class FileCleanup(BaseTool):
    """
    Cleans up files matching specific filters (age, size, extension)
    by moving them to the recycle bin/trash, or fallbacks to `.jarvis_trash/`.
    """

    @property
    def name(self) -> str:
        return "file_cleanup"

    @property
    def description(self) -> str:
        return (
            "Safely delete files in an approved sandbox directory based on criteria "
            "(age, size, extension). Files are moved to trash, not permanently deleted."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return FileCleanupInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return FileCleanupOutput

    def run(self, input_data: FileCleanupInput) -> FileCleanupOutput:
        # Validate the target directory path using sandbox enforcer
        target_dir = enforcer.validate(input_data.directory)

        if not target_dir.is_dir():
            raise FileNotFoundError(f"Target directory '{target_dir}' does not exist or is not a folder.")

        # Normalise extension filter to start with a dot if provided
        ext_filter = None
        if input_data.extension_filter:
            ext = input_data.extension_filter.strip().lower()
            ext_filter = ext if ext.startswith(".") else f".{ext}"

        current_time = time.time()
        files_to_delete = []
        total_size_bytes = 0

        # Scan for candidate files
        for root, _, files in os.walk(target_dir):
            for file_name in files:
                # Do not trash the trash itself
                if ".jarvis_trash" in root:
                    continue

                file_path = Path(root) / file_name
                try:
                    # Enforce sandbox rules on each path
                    resolved_file_path = enforcer.validate(file_path)
                except PermissionError:
                    continue

                # Filter by extension
                if ext_filter and resolved_file_path.suffix.lower() != ext_filter:
                    continue

                try:
                    stat_info = resolved_file_path.stat()
                except FileNotFoundError:
                    continue

                size_bytes = stat_info.st_size
                size_mb = size_bytes / (1024 * 1024)

                # Filter by min size
                if input_data.min_size_mb is not None and size_mb < input_data.min_size_mb:
                    continue

                # Filter by min age (days)
                if input_data.min_age_days is not None:
                    age_seconds = current_time - stat_info.st_mtime
                    age_days = age_seconds / (24 * 3600)
                    if age_days < input_data.min_age_days:
                        continue

                files_to_delete.append(resolved_file_path)
                total_size_bytes += size_bytes

        deleted_files = []
        total_freed_bytes = 0

        # Perform trashing
        for file_path in files_to_delete:
            try:
                # Resolve and re-verify path just before action
                resolved_path = enforcer.validate(file_path)
                file_size = resolved_path.stat().st_size
            except (PermissionError, FileNotFoundError):
                continue

            try:
                # Try standard OS trash
                send2trash(str(resolved_path))
                deleted_files.append(str(resolved_path))
                total_freed_bytes += file_size
            except Exception:
                # Fallback: Move to local .jarvis_trash in the approved sandbox root containing the file
                moved = False
                for root in enforcer.allowed_roots:
                    try:
                        # Determine relative path from sandbox root
                        rel_path = resolved_path.relative_to(root)
                        trash_dir = root / ".jarvis_trash"
                        target_trash_path = trash_dir / rel_path
                        
                        # Create directory structure in trash
                        target_trash_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Handle collision if file already exists in trash
                        if target_trash_path.exists():
                            target_trash_path = target_trash_path.with_name(
                                f"{target_trash_path.stem}_{int(time.time())}{target_trash_path.suffix}"
                            )
                            
                        shutil.move(str(resolved_path), str(target_trash_path))
                        deleted_files.append(str(resolved_path))
                        total_freed_bytes += file_size
                        moved = True
                        break
                    except ValueError:
                        continue
                
                if not moved:
                    # If it somehow was not relative to any root, do not delete it to remain safe
                    continue

        total_freed_mb = total_freed_bytes / (1024 * 1024)
        status_msg = (
            f"Successfully trashed {len(deleted_files)} files. "
            f"Freed {total_freed_mb:.4f} MB."
        )

        return FileCleanupOutput(
            status=status_msg,
            deleted_files=deleted_files,
            total_freed_mb=round(total_freed_mb, 4),
        )
