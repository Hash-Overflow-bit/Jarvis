"""
core/writing/sources.py
======================
Standard Evidence & Source Model for grounded research and document-based writing.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class EvidenceSource:
    source_type: str  # "web" | "local_file" | "user_input"
    title: str = ""
    location: str = ""
    url: str = ""
    content: str = ""
    verified: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "title": self.title,
            "location": self.location,
            "url": self.url,
            "content": self.content,
            "verified": self.verified
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceSource":
        return cls(
            source_type=data.get("source_type", "user_input"),
            title=data.get("title", ""),
            location=data.get("location", ""),
            url=data.get("url", ""),
            content=data.get("content", ""),
            verified=data.get("verified", True)
        )


def format_sources_for_prompt(sources: List[EvidenceSource]) -> str:
    """Format evidence sources into a clear, structured text block for LLM prompts."""
    if not sources:
        return "No external or document evidence provided."

    formatted = []
    for idx, s in enumerate(sources, 1):
        lines = [f"[Source {idx}] Type: {s.source_type}"]
        if s.title:
            lines.append(f"Title: {s.title}")
        if s.location:
            lines.append(f"Location: {s.location}")
        if s.url:
            lines.append(f"URL: {s.url}")
        lines.append(f"Verified: {s.verified}")
        lines.append(f"Content Snippet:\n{s.content}")
        formatted.append("\n".join(lines))

    return "\n\n---\n\n".join(formatted)
