"""Small, non-destructive filesystem operations confined to the workspace."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.config import settings
from core.workspace.documents import WorkspaceBoundaryError, WorkspaceDocumentError


class WorkspaceFilesystem:
    def __init__(self, root: Path | None = None, *, max_entries: int = 500):
        self.root = Path(root or settings.default_workspace_dir).resolve()
        self.max_entries = max_entries

    def resolve(self, requested_path: str | Path | None = None) -> Path:
        raw = str(requested_path or "workspace").strip()
        normalized = raw.replace("\\", "/")
        lowered = normalized.lower()
        if lowered in {"", ".", "workspace", "the workspace"}:
            candidate = self.root
        elif lowered.startswith("workspace/"):
            candidate = self.root / normalized.split("/", 1)[1]
        else:
            supplied = Path(raw).expanduser()
            candidate = supplied if supplied.is_absolute() else self.root / supplied
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceBoundaryError(
                f"Path '{resolved}' is outside the configured workspace '{self.root}'."
            ) from exc
        return resolved

    def create_directory(self, requested_path: str | Path) -> Path:
        path = self.resolve(requested_path)
        if path == self.root:
            raise WorkspaceDocumentError("The workspace already exists.")
        if path.exists():
            raise WorkspaceDocumentError(f"Path already exists at '{path}'.")
        path.mkdir(parents=True, exist_ok=False)
        if not path.is_dir():
            raise WorkspaceDocumentError(f"Directory verification failed for '{path}'.")
        return path

    def scan_files(
        self,
        requested_path: str | Path | None = None,
        *,
        extension_filter: str | None = None,
        min_size_mb: float | None = None,
    ) -> list[dict]:
        directory = self.resolve(requested_path)
        if not directory.exists():
            raise WorkspaceDocumentError(f"Directory '{directory}' does not exist.")
        if not directory.is_dir():
            raise WorkspaceDocumentError(f"Path '{directory}' is not a directory.")

        extension = None
        if extension_filter:
            extension = extension_filter.lower()
            if not extension.startswith("."):
                extension = f".{extension}"

        files: list[dict] = []
        for candidate in sorted(directory.rglob("*"), key=lambda path: str(path).lower()):
            if len(files) >= self.max_entries:
                raise WorkspaceDocumentError(
                    f"Workspace listing exceeds the {self.max_entries}-file safety limit."
                )
            if candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            try:
                resolved.relative_to(self.root)
            except ValueError:
                continue
            if extension and resolved.suffix.lower() != extension:
                continue
            stat = resolved.stat()
            size_mb = stat.st_size / (1024 * 1024)
            if min_size_mb is not None and size_mb < min_size_mb:
                continue
            files.append({
                "name": resolved.name,
                "path": str(resolved),
                "relative_path": str(resolved.relative_to(self.root)),
                "size_mb": round(size_mb, 4),
                "modified_date": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return files
