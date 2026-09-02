"""
core/tools/file_scanner.py
==========================
FileScanner tool implementation.
Scans folders and lists files with metadata inside sandbox roots.
"""

from typing import Type
from core.tools.base_tool import BaseTool
from core.workspace.filesystem import WorkspaceFilesystem
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
        files_list = WorkspaceFilesystem().scan_files(
            input_data.directory,
            extension_filter=input_data.extension_filter,
            min_size_mb=input_data.min_size_mb,
        )
        total_size_mb = sum(item["size_mb"] for item in files_list)

        return FileScannerOutput(
            files=files_list,
            total_count=len(files_list),
            total_size_mb=round(total_size_mb, 4),
        )
