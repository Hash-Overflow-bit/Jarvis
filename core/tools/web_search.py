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


from abc import ABC, abstractmethod
from bs4 import BeautifulSoup

class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, timeout: tuple = (5, 15)) -> List[Dict[str, str]]:
        pass

class DuckDuckGoLiteProvider(SearchProvider):
    def search(self, query: str, timeout: tuple = (5, 15)) -> List[Dict[str, str]]:
        results = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://duckduckgo.com/",
            }
            url = "https://lite.duckduckgo.com/lite/"
            data = {"q": query}
            resp = requests.post(url, headers=headers, data=data, timeout=timeout)
            logger.debug(f"Search provider=DDG_Lite query={query!r} status={resp.status_code} bytes={len(resp.content)}")
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tr in soup.find_all("tr"):
                    td = tr.find("td", class_="result-snippet")
                    if td:
                        snippet = td.get_text(strip=True)
                        # The title and URL are usually in the PREVIOUS tr
                        prev_tr = tr.find_previous_sibling("tr")
                        if prev_tr:
                            a_tag = prev_tr.find("a", class_="result-link")
                            if a_tag:
                                title = a_tag.get_text(strip=True)
                                clean_url = a_tag.get("href", "")
                                if clean_url.startswith("//"):
                                    clean_url = "https:" + clean_url
                                if clean_url.startswith("http"):
                                    results.append({
                                        "title": title,
                                        "url": clean_url,
                                        "snippet": snippet,
                                        "provider": "DuckDuckGoLite"
                                    })
                                    if len(results) >= 5:
                                        break
            elif resp.status_code == 202:
                logger.warning(f"DDG Lite returned HTTP 202 (Bot Challenge) for query '{query}'.")
            
            if not results and resp.status_code == 200:
                logger.debug(f"DDG Lite returned 0 results. HTML prefix: {resp.text[:500]!r}")
                
        except Exception as e:
            logger.warning(f"DDG Lite HTTP query failed for '{query}': {type(e).__name__}: {e}")
        return results

class DuckDuckGoHTMLProvider(SearchProvider):
    def search(self, query: str, timeout: tuple = (5, 15)) -> List[Dict[str, str]]:
        results = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://duckduckgo.com/",
            }
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            resp = requests.get(url, headers=headers, timeout=timeout)
            logger.debug(f"Search provider=DDG_HTML query={query!r} status={resp.status_code} bytes={len(resp.content)}")
            
            if resp.status_code == 200:
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
                                "snippet": snippet,
                                "provider": "DuckDuckGoHTML"
                            })
            elif resp.status_code == 202:
                logger.warning(f"DDG HTML returned HTTP 202 (Bot Challenge) for query '{query}'.")
            
            if not results and resp.status_code == 200:
                logger.debug(f"DDG HTML returned 0 results. HTML prefix: {resp.text[:500]!r}")
                
        except Exception as e:
            logger.warning(f"DDG HTML HTTP query failed for '{query}': {type(e).__name__}: {e}")
        return results

class WebSearch(BaseTool):
    """
    Searches the web for real-time information, documentation, and sources.
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Use when user wants to research online topics, current information, or retrieve external sources. "
            "Arguments: {'query': '<search_query>'}"
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return WebSearchInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return WebSearchOutput

    @staticmethod
    def _clean_query(raw_query: str) -> str:
        """
        Aggressively strips writing instructions, save-to-file directives,
        formatting/output structure requests, recommendation/conclusion clauses,
        and source-display instructions from the search query.
        
        Goal: The search engine should only receive topical search terms,
        never output/formatting instructions.
        """
        q = raw_query.strip()
        # Strip leading action verbs
        q = re.sub(r"^(?:research|investigate|find\s+info\s+on|search\s+for|look\s+up)\s+", "", q, flags=re.IGNORECASE).strip()

        # Iteratively strip directive clauses (order matters: broadest last)
        directive_patterns = [
            # Save/file instructions
            r"\.\s*save\s+.*$",
            r"\s+save\s+(?:the\s+)?(?:complete\s+)?(?:report|file|document|result).*$",
            r"\s+(?:as|to)\s+\S+\.(?:md|txt|json|csv|pdf)(?:\s+.*)?$",
            r"\s+on\s+my\s+(?:desktop|documents?).*$",
            r"\s+to\s+(?:my\s+)?desktop.*$",
            r"\s+(?:export|output)\s+(?:to|as)\s+.*$",
            # Writing/report structure instructions
            r"\s+(?:and\s+)?(?:write|generate|create|prepare|give\s+me|make|build|produce|draft)\s+.*$",
            r"\.\s*(?:write|generate|create|prepare|give\s+me|make|build|produce|draft)\s+.*$",
            # Formatting/structure instructions
            r"\s+with\s+(?:executive\s+)?summary.*$",
            r"\s+with\s+(?:an?\s+)?(?:introduction|conclusion|recommendation|limitation).*$",
            r"\s+with\s+(?:a\s+)?(?:comparison\s+)?table.*$",
            r"\s+with\s+(?:detailed\s+)?analysis.*$",
            r"\s+with\s+(?:real\s+)?(?:sources|links|references|citations).*$",
            # Conclusion/recommendation clauses
            r"\s+end\s+with\s+.*$",
            r"\s+conclude\s+with\s+.*$",
            r"\s+recommend\s+the\s+best.*$",
            # "Clearly mark" instructions
            r"\.\s*clearly\s+mark\s+.*$",
            r"\s+clearly\s+mark\s+.*$",
            # Filler
            r"\b(?:please|can\s+you|help\s+me)\b",
            # "Use official documentation" instructions (task meta, not search terms)
            r"\.\s*use\s+official\s+(?:documentation|repositories).*$",
            r"\s+use\s+official\s+(?:documentation|repositories)\s+(?:or\s+official\s+repositories\s+)?wherever\s+possible.*$",
        ]
        for d in directive_patterns:
            q = re.sub(d, "", q, flags=re.IGNORECASE).strip()

        # Strip comparison criteria lists that follow "compare" (these are for output, not search)
        q = re.sub(r"\.\s*compare\s+.*$", "", q, flags=re.IGNORECASE).strip()

        q = q.rstrip(".!?,;: ")
        return q if q else raw_query.strip()

    @staticmethod
    def decompose_multi_entity_queries(raw_query: str) -> List[str]:
        """
        For multi-entity comparison requests, decomposes into targeted per-entity
        search queries. Returns a list of search queries (one per entity).
        If no known entities are detected, returns a single cleaned query.
        """
        cleaned = WebSearch._clean_query(raw_query)
        known_frameworks = {
            "crewai": "CrewAI", "langgraph": "LangGraph", "autogen": "AutoGen",
            "llamaindex": "LlamaIndex", "semantic kernel": "Semantic Kernel",
            "ag2": "AG2", "botpress": "Botpress"
        }
        detected = []
        combined = (cleaned + " " + raw_query).lower()
        for key, name in known_frameworks.items():
            if key in combined:
                detected.append(name)

        if len(detected) >= 2:
            # Generate targeted per-entity queries
            queries = []
            for entity in detected:
                queries.append(f"{entity} official documentation local models offline multi-agent")
                queries.append(f"{entity} github repository")
            return queries
        elif cleaned:
            return [cleaned]
        return [raw_query.strip()]

    @staticmethod
    def _rank_sources_by_priority(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Sorts search results by source priority hierarchy:
        Priority 1: Official docs / GitHub repositories (e.g. docs.*, *.github.io, github.com)
        Priority 2: Primary vendor/project domains (e.g. crewai.com, langchain.com, llamaindex.ai)
        Priority 3: Secondary sources
        """
        def get_priority(item: Dict[str, str]) -> int:
            url = item.get("url", "").lower()
            title = item.get("title", "").lower()
            if "docs." in url or "github.io" in url or "github.com" in url or "documentation" in title:
                return 1
            if any(domain in url for domain in ("crewai.com", "langchain.com", "llamaindex.ai", "microsoft.com", "autogen")):
                return 2
            return 3

        return sorted(results, key=get_priority)

    def run(self, input_data: WebSearchInput) -> WebSearchOutput:
        raw_query = input_data.query.strip()
        if not raw_query:
            return WebSearchOutput(
                success=False,
                query=raw_query,
                results=[],
                warning="Search query was empty."
            )

        providers = [DuckDuckGoLiteProvider(), DuckDuckGoHTMLProvider()]
        all_results = []
        
        for provider in providers:
            all_results = provider.search(raw_query)
            if all_results:
                break
            
        # Deterministic retry: try shorter key-noun query
        if not all_results:
            cleaned_query = self._clean_query(raw_query)
            words = [w for w in re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", cleaned_query) if w.lower() not in (
                "research", "current", "suitable", "write", "report", "with", "from",
                "and", "the", "for", "official", "documentation", "save", "complete",
                "structured", "executive", "summary", "recommendation", "conclusion",
                "comparison", "detailed", "analysis", "sources", "real"
            )]
            if len(words) >= 2:
                fallback_q = " ".join(words[:5])
                for provider in providers:
                    all_results = provider.search(fallback_q)
                    if all_results:
                        break

        # Sort results by official docs -> official repo -> primary vendor -> secondary sources
        all_results = self._rank_sources_by_priority(all_results)

        if all_results:
            return WebSearchOutput(
                success=True,
                query=raw_query,
                results=all_results,
                warning=None
            )
        else:
            return WebSearchOutput(
                success=False,
                query=raw_query,
                results=[],
                warning=f"Could not retrieve online sources for '{raw_query}'."
            )

if __name__ == "__main__":
    import sys
    query = "AI warehouse inventory optimization"
    print(f"Python Version: {sys.version}")
    print(f"Testing Query: {query}\n")
    
    providers = [
        ("DuckDuckGoLite", DuckDuckGoLiteProvider()),
        ("DuckDuckGoHTML", DuckDuckGoHTMLProvider())
    ]
    
    for name, provider in providers:
        print(f"=== Provider: {name} ===")
        try:
            # We bypass the default timeout for the diagnostic or keep it standard
            results = provider.search(query)
            # To get HTTP status and response size, we perform a manual log-like call
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }
            if name == "DuckDuckGoLite":
                resp = requests.post("https://lite.duckduckgo.com/lite/", headers=headers, data={"q": query}, timeout=10)
            else:
                resp = requests.get(f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}", headers=headers, timeout=10)
            
            print(f"HTTP Status: {resp.status_code}")
            print(f"Response Size: {len(resp.content)} bytes")
            print(f"Parsed Result Count: {len(results)}")
            if results:
                print("First 3 URLs:")
                for r in results[:3]:
                    print(f"  - {r.get('url')}")
            else:
                print("No results parsed.")
        except Exception as e:
            print(f"Exact Exception: {type(e).__name__}: {e}")
        print()
