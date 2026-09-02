"""Stable public router entry point.

The verified execution engine is kept separately so it cannot be truncated by a
partial deployment. This layer exports its public helpers and applies the
current bounded-routing policy.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from core.orchestrator import agent_loop_legacy as _legacy

_parse_file_write_intent = _legacy._parse_file_write_intent
_parse_pure_read_intent = _legacy._parse_pure_read_intent
_parse_artifact_status_intent = _legacy._parse_artifact_status_intent
ollama = _legacy.ollama
tool_registry = _legacy.tool_registry
settings = _legacy.settings
logger = _legacy.logger
recall = _legacy.recall


def _recall_proxy(*args, **kwargs):
    # Tests and callers may replace this module's recall function.
    return recall(*args, **kwargs)


_legacy.recall = _recall_proxy


def _public_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s<>()]+", text or "", re.IGNORECASE)
    if not match:
        return None
    url = match.group(0).rstrip(".,;:!?")
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


class AgentExecutionLoop(_legacy.AgentExecutionLoop):
    """Verified execution loop with small, explicit current-policy adapters."""

    def _direct_route(self, user_input: str, recalled_facts: str = ""):
        url = _public_url(user_input)
        lowered = (user_input or "").lower()
        if url and re.search(r"\b(open|browse|navigate|go to|visit)\b", lowered):
            if any(word in lowered for word in ("read", "summarize", "extract", "find", "get")):
                return [{"step": 1, "tool": "fetch_url", "arguments": {"url": url}}]
            return [{"step": 1, "tool": "open_url", "arguments": {"url": url}}]

        plan = super()._direct_route(user_input, recalled_facts)
        if not isinstance(plan, list):
            return plan
        for step in plan:
            if step.get("tool") != "agent_builder":
                continue
            args = step.setdefault("arguments", {})
            caps = args.get("capabilities", [])
            normalized: list[str] = []
            for capability in caps:
                value = str(capability).lower()
                if "summar" in value:
                    mapped = "summarize"
                elif "analy" in value:
                    mapped = "analyze"
                elif "classif" in value or "categoriz" in value:
                    mapped = "classify"
                elif "plan" in value or "organ" in value:
                    mapped = "plan"
                else:
                    continue
                if mapped not in normalized:
                    normalized.append(mapped)
            if normalized:
                args["capabilities"] = normalized
        return plan
