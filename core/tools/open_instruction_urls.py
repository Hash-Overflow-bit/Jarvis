"""Controlled default-browser opening from an explicit workspace instruction file."""

from __future__ import annotations

import re
from typing import Type

from pydantic import BaseModel, Field

from core.tools.base_tool import BaseTool
from core.tools.public_web import OpenURL, OpenURLInput, validate_public_url
from core.workspace.documents import WorkspaceDocumentError, WorkspaceDocuments


class OpenInstructionURLsInput(BaseModel):
    instruction_file: str = Field(
        ..., description="Workspace-relative .txt or .md file containing one `OPEN https://...` URL per line."
    )
    max_urls: int = Field(default=5, ge=1, le=5)


class OpenInstructionURLsOutput(BaseModel):
    success: bool
    message: str
    opened_urls: list[str] = Field(default_factory=list)


class OpenInstructionURLs(BaseTool[OpenInstructionURLsInput, OpenInstructionURLsOutput]):
    """Open a reviewed, bounded list of public URLs in the default browser."""

    _LINE = re.compile(r"^OPEN\s+(https?://[^\s]+)$", re.IGNORECASE)

    @property
    def name(self) -> str:
        return "open_instruction_urls"

    @property
    def description(self) -> str:
        return (
            "Open up to five explicit public URLs from a workspace instruction file. "
            "Each non-comment line must be exactly `OPEN https://...`. "
            "Only opens the system default browser; it cannot log in, click, fill forms, download, or submit anything."
        )

    @property
    def input_schema(self) -> Type[OpenInstructionURLsInput]:
        return OpenInstructionURLsInput

    @property
    def output_schema(self) -> Type[OpenInstructionURLsOutput]:
        return OpenInstructionURLsOutput

    def _urls_from_instruction_file(self, instruction_file: str, max_urls: int) -> list[str]:
        text, _ = WorkspaceDocuments().read_text(instruction_file)
        urls: list[str] = []
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Token-count validation happens before URL handling.  This is
            # deliberately stricter than merely extracting the first URL:
            # `OPEN https://example.com/login and submit` must reject the
            # whole file instead of opening the first part of that line.
            tokens = stripped.split()
            if len(tokens) != 2 or tokens[0].upper() != "OPEN":
                raise WorkspaceDocumentError(
                    f"Invalid instruction on line {number}. Use exactly: OPEN https://public.example/path"
                )
            match = self._LINE.fullmatch(stripped)
            if not match:
                raise WorkspaceDocumentError(
                    f"Invalid instruction on line {number}. Use exactly: OPEN https://public.example/path"
                )
            url = validate_public_url(match.group(1))
            if url not in urls:
                urls.append(url)
            if len(urls) > max_urls:
                raise WorkspaceDocumentError(f"Instruction file exceeds the {max_urls}-URL limit.")
        if not urls:
            raise WorkspaceDocumentError("Instruction file contains no OPEN https:// URL lines.")
        return urls

    def run(self, input_data: OpenInstructionURLsInput) -> OpenInstructionURLsOutput:
        try:
            # Validate every URL before opening any browser tab.  An invalid
            # later line cannot cause an unreviewed partial run.
            urls = self._urls_from_instruction_file(input_data.instruction_file, input_data.max_urls)
        except (WorkspaceDocumentError, OSError, ValueError) as exc:
            return OpenInstructionURLsOutput(success=False, message=str(exc))

        opened: list[str] = []
        for url in urls:
            result = OpenURL().run(OpenURLInput(url=url))
            if not result.success:
                return OpenInstructionURLsOutput(
                    success=False,
                    message=f"Stopped after opening {len(opened)} URL(s): {result.message}",
                    opened_urls=opened,
                )
            opened.append(result.url)
        return OpenInstructionURLsOutput(
            success=True,
            message=(
                f"Opened {len(opened)} reviewed public URL(s) from the workspace instruction file "
                "in the default browser. No website interaction was performed."
            ),
            opened_urls=opened,
        )
