"""Search-first web research with strict source and citation boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from core.config import settings
from core.llm.ollama_client import OllamaError, ollama


class ResearchUnavailable(Exception):
    """Raised when online evidence cannot be retrieved."""


class SearchBackend(Protocol):
    def search(self, query: str) -> list[dict[str, str]]: ...


class DuckDuckGoBackend:
    """Adapter around the existing provider with a small stable interface."""

    def search(self, query: str) -> list[dict[str, str]]:
        from core.tools.web_search import WebSearch, WebSearchInput

        output = WebSearch().run(WebSearchInput(query=query))
        if not output.success:
            raise ResearchUnavailable(output.warning or "Search connectivity is unavailable.")
        return output.results


@dataclass(frozen=True)
class ResearchSource:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class ResearchResult:
    query: str
    report: str
    sources: tuple[ResearchSource, ...]


class ResearchRouter:
    _PATTERN = re.compile(
        r"\b(?:research|investigate|web\s*search|search\s+(?:the\s+)?web|"
        r"look\s+up\s+online|find\s+(?:current|latest)\s+information)\b",
        re.IGNORECASE,
    )
    _SAVE_REFERENCE = re.compile(
        r"^\s*(?:please\s+)?(?:save|export|write|put)\s+"
        r"(?:this|that|the)\s+(?:research|report|document|answer)\b",
        re.IGNORECASE,
    )

    def matches(self, user_input: str) -> bool:
        # "Save this research" refers to an artifact already generated in
        # this session.  It is not a new web-research request.
        text = user_input or ""
        return not self._SAVE_REFERENCE.search(text) and bool(self._PATTERN.search(text))

    def query(self, user_input: str) -> str:
        text = (user_input or "").strip()
        text = re.sub(
            r"^(?:please\s+)?(?:research|investigate|web\s*search(?:\s+for)?|"
            r"search\s+(?:the\s+)?web(?:\s+for)?|look\s+up\s+online)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.split(
            r"\b(?:and\s+)?(?:save|export|write\s+(?:it|the\s+report))\b",
            text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return text.strip(" .,:;?!") or (user_input or "").strip()


class ResearchService:
    URL_PATTERN = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
    CITATION_PATTERN = re.compile(r"\[(\d+)\]")

    def __init__(self, backend: SearchBackend | None = None, *, max_sources: int = 8):
        self.backend = backend or DuckDuckGoBackend()
        self.max_sources = max_sources

    def _normalize_sources(self, raw_results: list[dict[str, str]]) -> list[ResearchSource]:
        sources: list[ResearchSource] = []
        seen_urls: set[str] = set()
        for item in raw_results:
            url = str(item.get("url", "")).strip().rstrip(".,;:")
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            if url in seen_urls:
                continue
            title = str(item.get("title", "")).strip() or parsed.netloc
            snippet = str(item.get("snippet", "")).strip()
            if not snippet:
                continue
            sources.append(ResearchSource(title=title, url=url, snippet=snippet))
            seen_urls.add(url)
            if len(sources) >= self.max_sources:
                break
        return sources

    def _ground_output(self, raw_output: str, sources: list[ResearchSource]) -> str:
        allowed_urls = {source.url for source in sources}
        grounded = raw_output.strip()
        for found in self.URL_PATTERN.findall(grounded):
            cleaned = found.rstrip(".,;:")
            if cleaned not in allowed_urls:
                grounded = grounded.replace(found, "[unverified link removed]")

        valid_indexes = set(range(1, len(sources) + 1))
        grounded = self.CITATION_PATTERN.sub(
            lambda match: match.group(0)
            if int(match.group(1)) in valid_indexes
            else "[invalid citation removed]",
            grounded,
        )

        source_lines = [
            f"[{index}] {source.title} — {source.url}"
            for index, source in enumerate(sources, 1)
        ]
        return (
            grounded
            + "\n\nSources\n"
            + "\n".join(source_lines)
            + "\n\nVerification note: This is an AI synthesis of retrieved search snippets; "
              "open the cited sources before using it for high-stakes decisions."
        )

    def research(self, user_input: str, *, model: str | None = None) -> ResearchResult:
        router = ResearchRouter()
        query = router.query(user_input)
        try:
            raw_results = self.backend.search(query)
        except ResearchUnavailable:
            raise
        except Exception as exc:
            raise ResearchUnavailable(f"Search connectivity failed: {exc}") from exc

        sources = self._normalize_sources(raw_results)
        if not sources:
            raise ResearchUnavailable(
                f"No usable online sources were retrieved for '{query}'."
            )

        evidence = "\n\n".join(
            f"[{index}] {source.title}\nURL: {source.url}\nEvidence: {source.snippet}"
            for index, source in enumerate(sources, 1)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Write a concise research answer using only the supplied search evidence. "
                    "Cite factual claims with [1], [2], etc. Do not invent facts, sources, "
                    "rankings, companies, dates, quotes, or URLs. If the evidence is incomplete, "
                    "state the limitation explicitly."
                ),
            },
            {
                "role": "user",
                "content": f"Research request: {user_input}\n\nRetrieved evidence:\n{evidence}",
            },
        ]
        response = ollama.chat(
            messages=messages,
            model=model or settings.ollama_model,
            temperature=0.2,
            tools=None,
        )
        if not isinstance(response, dict) or not isinstance(response.get("content"), str):
            raise OllamaError("Ollama returned an invalid research response.")
        raw_report = response["content"].strip()
        if not raw_report:
            raise OllamaError("Ollama returned an empty research response.")
        report = self._ground_output(raw_report, sources)
        if re.search(r"\b(?:save|export)\b", user_input, re.IGNORECASE):
            report += (
                "\n\nNote: The research was returned in chat and was not automatically saved. "
                "Use a separate workspace save command after reviewing it."
            )
        return ResearchResult(query=query, report=report, sources=tuple(sources))
