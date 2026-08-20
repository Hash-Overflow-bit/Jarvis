"""
core/tools/file_scanner.py
==========================
FileScanner tool implementation.
Scans folders and lists files with metadata inside sandbox roots.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Type
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.file_scanner_schema import FileScannerInput, FileScannerOutput


class FileScanner(BaseTool[FileScannerInput, FileScannerOutput]):
    """
    Scans a sandbox-approved directory, filters by size and extension,
    and returns a summary of matching files.
    """

    @property
    def name(self) -> str:
        return "file_scanner"

    @property
    def description(self) -> str:
        return (
            "Scan files in an approved sandbox directory. Use this when the user "
            "wants to search for files, see what files exist, filter files by extension "
            "or size, or list files inside a directory."
        )

    @property
    def input_schema(self) -> Type[FileScannerInput]:
        return FileScannerInput

    @property
    def output_schema(self) -> Type[FileScannerOutput]:
        return FileScannerOutput

    def run(self, input_data: FileScannerInput) -> FileScannerOutput:
        # Validate the target directory path using sandbox enforcer
        target_dir = enforcer.validate(input_data.directory)

        if not target_dir.is_dir():
            raise FileNotFoundError(f"Target directory '{target_dir}' does not exist or is not a folder.")

        files_list = []
        total_size_mb = 0.0

        # Normalise extension filter to start with a dot if provided
        ext_filter = None
        if input_data.extension_filter:
            ext = input_data.extension_filter.strip().lower()
            ext_filter = ext if ext.startswith(".") else f".{ext}"

        # os.walk by default does not follow symlinks, avoiding escaping and loops
        for root, _, files in os.walk(target_dir):
            for file_name in files:
                file_path = Path(root) / file_name
                try:
                    # Enforce sandbox rules on each individual file path
                    resolved_file_path = enforcer.validate(file_path)
                except PermissionError:
                    # Ignore and skip files escaping the sandbox boundary (e.g. symlinks pointing outside)
                    continue

                # Apply extension filter
                if ext_filter and resolved_file_path.suffix.lower() != ext_filter:
                    continue

                try:
                    stat_info = resolved_file_path.stat()
                except FileNotFoundError:
                    # File might have been deleted during scan, skip it
                    continue

                size_mb = stat_info.st_size / (1024 * 1024)

                # Apply size filter
                if input_data.min_size_mb is not None and size_mb < input_data.min_size_mb:
                    continue

                mod_date = datetime.fromtimestamp(stat_info.st_mtime).isoformat()

                files_list.append({
                    "name": file_name,
                    "path": str(resolved_file_path),
                    "size_mb": round(size_mb, 4),
                    "modified_date": mod_date,
                })
                total_size_mb += size_mb

        return FileScannerOutput(
            files=files_list,
            total_count=len(files_list),
            total_size_mb=round(total_size_mb, 4),
        )
