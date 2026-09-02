"""Boundary-safe, verified text document access inside one workspace."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.config import settings


class WorkspaceDocumentError(Exception):
    """Base error for controlled workspace documents."""


class WorkspaceBoundaryError(WorkspaceDocumentError):
    """Raised when a requested path escapes the configured workspace."""


@dataclass(frozen=True)
class DocumentReceipt:
    path: Path
    byte_count: int
    sha256: str


class WorkspaceDocuments:
    """Read and write UTF-8 documents without ever leaving the workspace."""

    DEFAULT_EXTENSIONS = {
        ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"
    }

    def __init__(
        self,
        root: Path | None = None,
        *,
        max_bytes: int | None = None,
        allowed_extensions: set[str] | None = None,
    ):
        self.root = Path(root or settings.default_workspace_dir).resolve()
        self.max_bytes = max_bytes or settings.workspace_max_document_bytes
        configured = allowed_extensions or settings.workspace_document_extensions
        self.allowed_extensions = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in (configured or self.DEFAULT_EXTENSIONS)
        }

    def resolve(self, requested_path: str | Path) -> Path:
        raw = str(requested_path or "").strip()
        if not raw:
            raise WorkspaceDocumentError("A document path is required.")

        normalized = raw.replace("\\", "/")
        lowered = normalized.lower()
        if lowered == "workspace":
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
        if resolved == self.root:
            raise WorkspaceDocumentError("A file path is required, not the workspace directory.")
        return resolved

    def _validate_extension(self, path: Path) -> None:
        if path.suffix.lower() not in self.allowed_extensions:
            allowed = ", ".join(sorted(self.allowed_extensions))
            raise WorkspaceDocumentError(
                f"Unsupported document type '{path.suffix or '<none>'}'. Allowed: {allowed}."
            )

    @staticmethod
    def _receipt(path: Path, data: bytes) -> DocumentReceipt:
        return DocumentReceipt(
            path=path,
            byte_count=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def read_text(self, requested_path: str | Path) -> tuple[str, DocumentReceipt]:
        path = self.resolve(requested_path)
        if not path.exists():
            raise WorkspaceDocumentError(f"File '{path}' does not exist.")
        if not path.is_file():
            raise WorkspaceDocumentError(f"Path '{path}' is a directory, not a file.")
        self._validate_extension(path)

        size = path.stat().st_size
        if size > self.max_bytes:
            raise WorkspaceDocumentError(
                f"Document is {size} bytes; limit is {self.max_bytes} bytes."
            )
        data = path.read_bytes()
        if b"\x00" in data:
            raise WorkspaceDocumentError("Binary content is not supported by read_file.")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise WorkspaceDocumentError("Document is not valid UTF-8 text.") from exc
        return text, self._receipt(path, data)

    def write_text(
        self,
        requested_path: str | Path,
        content: str,
        *,
        mode: str = "create",
    ) -> DocumentReceipt:
        if mode not in {"create", "overwrite", "append"}:
            raise WorkspaceDocumentError(f"Unsupported write mode '{mode}'.")
        if not isinstance(content, str):
            raise WorkspaceDocumentError("Document content must be text.")

        path = self.resolve(requested_path)
        self._validate_extension(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "create" and path.exists():
            raise WorkspaceDocumentError(
                f"File already exists at '{path}'. Use overwrite explicitly to replace it."
            )

        existing = b""
        if mode == "append" and path.exists():
            if not path.is_file():
                raise WorkspaceDocumentError(f"Path '{path}' is not a file.")
            existing = path.read_bytes()
            if b"\x00" in existing:
                raise WorkspaceDocumentError("Cannot append text to a binary file.")

        encoded = content.encode("utf-8")
        expected = existing + encoded if mode == "append" else encoded
        if len(expected) > self.max_bytes:
            raise WorkspaceDocumentError(
                f"Result would be {len(expected)} bytes; limit is {self.max_bytes} bytes."
            )

        if mode == "create":
            try:
                with path.open("xb") as handle:
                    handle.write(expected)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as exc:
                raise WorkspaceDocumentError(
                    f"File already exists at '{path}'. Use overwrite explicitly to replace it."
                ) from exc
        else:
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
                ) as handle:
                    temporary_path = Path(handle.name)
                    handle.write(expected)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, path)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

        actual = path.read_bytes()
        if actual != expected:
            raise WorkspaceDocumentError(
                f"Post-write verification failed for '{path}'; content does not match."
            )
        return self._receipt(path, actual)
