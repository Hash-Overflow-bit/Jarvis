"""
core/tools/directory_audit.py
=============================
DirectoryAudit tool implementation.
Generates a structured text tree representing folders and files.
"""

from pathlib import Path
from pydantic import BaseModel
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from schemas.directory_audit_schema import DirectoryAuditInput, DirectoryAuditOutput


class DirectoryAudit(BaseTool):
    """
    Generates a tree-view report of files and folders recursively inside sandbox limits.
    """

    @property
    def name(self) -> str:
        return "directory_audit"

    @property
    def description(self) -> str:
        return (
            "Generate a tree-view text diagram of a directory structure. "
            "Use this when the user asks for a folder structure, tree view, or directory map."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return DirectoryAuditInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return DirectoryAuditOutput

    def run(self, input_data: DirectoryAuditInput) -> DirectoryAuditOutput:
        # Validate target directory path
        target_dir = enforcer.validate(input_data.directory)

        if not target_dir.is_dir():
            raise FileNotFoundError(f"Target directory '{target_dir}' does not exist or is not a folder.")

        max_depth = input_data.max_depth if input_data.max_depth is not None else 3

        # Build tree representation
        tree_text, folder_count, file_count = self._build_tree(target_dir, current_depth=0, max_depth=max_depth)

        # Prepend the root folder name to make it look like a standard tree output
        root_name = target_dir.name or str(target_dir)
        full_tree = f"{root_name}/\n{tree_text}" if tree_text else f"{root_name}/\n  (empty folder)\n"

        return DirectoryAuditOutput(
            tree_representation=full_tree,
            folder_count=folder_count,
            file_count=file_count,
        )

    def _build_tree(self, dir_path: Path, current_depth: int, max_depth: int, prefix: str = "") -> tuple[str, int, int]:
        """
        Recursively builds the text representation of the directory tree.
        """
        if current_depth >= max_depth:
            return "", 0, 0

        try:
            # Enforce sandbox boundary check on containing folder
            enforcer.validate(dir_path)
        except PermissionError:
            return f"{prefix}└── [Security Blocked]\n", 0, 0

        if not dir_path.is_dir():
            return "", 0, 0

        try:
            # List contents and sort: directories first, then files (alphabetically)
            entries = sorted(
                list(dir_path.iterdir()),
                key=lambda e: (not e.is_dir(), e.name.lower())
            )
        except Exception as e:
            return f"{prefix}└── [Error: {str(e)}]\n", 0, 0

        # Filter out hidden entries (starting with dot) except for .jarvis_trash
        entries = [
            e for e in entries 
            if not e.name.startswith(".") or e.name == ".jarvis_trash"
        ]

        tree_str = ""
        folder_count = 0
        file_count = 0

        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "

            try:
                # Enforce safety check on child entry
                resolved_entry = enforcer.validate(entry)
            except PermissionError:
                tree_str += f"{prefix}{connector}{entry.name} [Security Blocked]\n"
                continue

            if resolved_entry.is_dir():
                tree_str += f"{prefix}{connector}{resolved_entry.name}/\n"
                folder_count += 1
                
                next_prefix = prefix + ("    " if is_last else "│   ")
                subtree_str, sub_folders, sub_files = self._build_tree(
                    resolved_entry, current_depth + 1, max_depth, next_prefix
                )
                tree_str += subtree_str
                folder_count += sub_folders
                file_count += sub_files
            else:
                tree_str += f"{prefix}{connector}{resolved_entry.name}\n"
                file_count += 1

        return tree_str, folder_count, file_count
