"""
core/tools/web_search.py
========================
Web Search Tool for Jarvis.
Retrieves real search engine results (title, snippet, url) for research-backed writing.

Rules:
- Never fabricate search results or URLs.
- If internet is unavailable or query fails, returns success=False with warning.
"""

import re
import json
import logging
import urllib.parse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import requests

from core.tools.base_tool import BaseTool

logger = logging.getLogger("jarvis_web_search")


class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query term to look up online.")


class WebSearchResultItem(BaseModel):
    title: str = Field(..., description="Title of the search result page.")
    url: str = Field(..., description="Full URL of the source.")
    snippet: str = Field(..., description="Content snippet from the source.")


class WebSearchOutput(BaseModel):
    success: bool = Field(..., description="Whether search succeeded.")
    query: str = Field(..., description="Original search query.")
    results: List[Dict[str, str]] = Field(default_factory=list, description="List of search result items.")
    warning: Optional[str] = Field(None, description="Warning or error message if search failed.")


class WebSearch(BaseTool):
    """
    Searches the web for real-time information, documentation, and sources.
    """

    name: str = "web_search"
    description: str = (
        "Use when user wants to research online topics, current information, or retrieve external sources. "
        "Arguments: {'query': '<search_query>'}"
    )
    input_schema: type[BaseModel] = WebSearchInput
    output_schema: type[BaseModel] = WebSearchOutput

    @staticmethod
    def _clean_query(raw_query: str) -> str:
        """Strips conversational instruction filler words from search query."""
        q = raw_query.strip()
        patterns = [
            r"\b(?:and\s+)?(?:write|generate|create|prepare|give\s+me)\s+(?:a\s+)?(?:short\s+)?(?:comparison\s+)?(?:report|summary|article|essay|email)\b.*$",
            r"\b(?:with|including)\s+(?:real\s+)?(?:sources|links|references|citations)\b.*$",
            r"\b(?:please|can\s+you|help\s+me)\b"
        ]
        for p in patterns:
            q = re.sub(p, "", q, flags=re.IGNORECASE).strip()

        q = q.rstrip(".!?,;: ")
        return q if q else raw_query.strip()

    def _fetch_ddg_results(self, search_term: str) -> List[Dict[str, str]]:
        """Executes HTTP request to DuckDuckGo HTML endpoint and parses result items."""
        results: List[Dict[str, str]] = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_term)}"
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", class_="result__url", limit=5):
                    raw_href = a.get("href", "")
                    title_node = a.find_parent("div", class_="result__body")
                    if title_node:
                        title_elt = title_node.find("a", class_="result__a")
                        snippet_elt = title_node.find("a", class_="result__snippet")
                        title = title_elt.get_text(strip=True) if title_elt else "Search Result"
                        snippet = snippet_elt.get_text(strip=True) if snippet_elt else ""
                        clean_url = raw_href
                        if "uddg=" in raw_href:
                            try:
                                clean_url = urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
                            except Exception:
                                pass
                        if clean_url and clean_url.startswith("http"):
                            results.append({
                                "title": title,
                                "url": clean_url,
                                "snippet": snippet
                            })
        except Exception as e:
            logger.warning(f"Web search HTTP query failed for '{search_term}': {e}")
        return results

    def run(self, input_data: WebSearchInput) -> WebSearchOutput:
        raw_query = input_data.query.strip()
        if not raw_query:
            return WebSearchOutput(
                success=False,
                query=raw_query,
                results=[],
                warning="Search query was empty."
            )

        cleaned_query = self._clean_query(raw_query)
        results = self._fetch_ddg_results(cleaned_query)

        # Fallback: Try with raw query if cleaned query returned 0 results
        if not results and cleaned_query != raw_query:
            results = self._fetch_ddg_results(raw_query)

        # Fallback: Try key nouns if still 0 results
        if not results:
            words = [w for w in re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", cleaned_query) if w.lower() not in ("research", "current", "suitable", "write", "report", "with", "from", "and", "the", "for")]
            if len(words) >= 2:
                fallback_q = " ".join(words[:5])
                results = self._fetch_ddg_results(fallback_q)

        if results:
            return WebSearchOutput(
                success=True,
                query=raw_query,
                results=results,
                warning=None
            )
        else:
            return WebSearchOutput(
                success=False,
                query=raw_query,
                results=[],
                warning=f"Could not retrieve online sources for '{raw_query}'."
            )
