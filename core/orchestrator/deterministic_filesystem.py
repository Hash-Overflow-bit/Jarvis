"""Deterministic parser for small, safe workspace filesystem requests."""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.workspace.documents import WorkspaceDocumentError, WorkspaceDocuments
from core.workspace.filesystem import WorkspaceFilesystem


@dataclass(frozen=True)
class DeterministicFilesystemResult:
    response: str


class DeterministicFilesystemRouter:
    """Handle supported one-action commands without an LLM planner."""

    _DOCUMENT = r"[A-Za-z0-9_./\\ -]+\.(?:txt|md|csv|json|yaml|yml|log)"

    def __init__(self):
        self.documents = WorkspaceDocuments
        self.filesystem = WorkspaceFilesystem

    @staticmethod
    def _unquote(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            return value[1:-1]
        return value

    def try_handle(self, user_input: str) -> DeterministicFilesystemResult | None:
        text = (user_input or "").strip()
        if not text:
            return None
        if re.search(
            r"\band\s+(?:then\s+)?(?:create|make|write|save|overwrite|append|read|list|show|open)\b",
            text,
            re.IGNORECASE,
        ):
            # Never execute a partial interpretation of a compound workflow.
            return None

        try:
            mkdir = re.fullmatch(
                r"(?:create|make)\s+(?:a\s+)?(?:folder|directory)\s+(?:named\s+)?"
                r"(?P<path>[A-Za-z0-9_./\\ -]+?)(?:\s+in\s+(?:the\s+)?workspace)?[.!]?",
                text,
                re.IGNORECASE,
            )
            if mkdir:
                path = self.filesystem().create_directory(self._unquote(mkdir.group("path")))
                return DeterministicFilesystemResult(f"Created workspace directory: {path}")

            listing = re.fullmatch(
                r"(?:list|show)(?:\s+me)?\s+(?:the\s+)?(?:(?P<kind>[A-Za-z0-9]+)\s+)?"
                r"(?:files|documents|contents)"
                r"(?:\s+(?:in|inside|from)\s+(?:the\s+)?(?P<path>[A-Za-z0-9_./\\ -]+))?[.!]?",
                text,
                re.IGNORECASE,
            )
            if listing:
                target = self._unquote(listing.group("path") or "workspace")
                kind = listing.group("kind")
                extension = f".{kind}" if kind and kind.lower() != "workspace" else None
                files = self.filesystem().scan_files(target, extension_filter=extension)
                if not files:
                    return DeterministicFilesystemResult("The requested workspace directory is empty.")
                lines = [f"- {item['relative_path']} ({item['size_mb']:.4f} MB)" for item in files]
                return DeterministicFilesystemResult("Workspace files:\n" + "\n".join(lines))

            read = re.fullmatch(
                rf"(?:read|show|open)\s+(?:the\s+)?(?:file|document\s+)?(?P<path>{self._DOCUMENT})[.!]?",
                text,
                re.IGNORECASE,
            )
            if read:
                content, receipt = self.documents().read_text(self._unquote(read.group("path")))
                return DeterministicFilesystemResult(
                    f"{content}\n\n[Verified: {receipt.path} | SHA-256: {receipt.sha256}]"
                )

            append = re.fullmatch(
                rf"append\s+(?P<content>[\s\S]+?)\s+to\s+(?P<path>{self._DOCUMENT})[.!]?",
                text,
                re.IGNORECASE,
            )
            if append:
                receipt = self.documents().write_text(
                    self._unquote(append.group("path")),
                    self._unquote(append.group("content")),
                    mode="append",
                )
                return DeterministicFilesystemResult(
                    f"Appended and verified {receipt.byte_count} bytes at: {receipt.path}"
                )

            write = re.fullmatch(
                rf"(?P<action>create|write|save|overwrite)\s+(?:a\s+)?(?:file|document\s+)?"
                rf"(?:named\s+)?(?P<path>{self._DOCUMENT})\s+"
                r"(?:with\s+(?:content|text)|containing)\s*:?\s*(?P<content>.+)",
                text,
                re.IGNORECASE,
            )
            if write:
                action = write.group("action").lower()
                mode = "overwrite" if action == "overwrite" else "create"
                receipt = self.documents().write_text(
                    self._unquote(write.group("path")),
                    self._unquote(write.group("content")),
                    mode=mode,
                )
                return DeterministicFilesystemResult(
                    f"Wrote and verified {receipt.byte_count} bytes at: {receipt.path} "
                    f"(SHA-256: {receipt.sha256})"
                )
        except (WorkspaceDocumentError, OSError) as exc:
            return DeterministicFilesystemResult(f"Workspace action was not performed: {exc}")

        return None
