"""Stable public router entry point.

The verified execution engine is kept separately so it cannot be truncated by a
partial deployment. This layer exports its public helpers and applies the
current bounded-routing policy.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from core.orchestrator import agent_loop_legacy as _legacy

_parse_file_write_intent = _legacy._parse_file_write_intent
_parse_pure_read_intent = _legacy._parse_pure_read_intent
_parse_artifact_status_intent = _legacy._parse_artifact_status_intent
ollama = _legacy.ollama
tool_registry = _legacy.tool_registry
settings = _legacy.settings
logger = _legacy.logger
prose_hook = _legacy.prose_hook
recall = _legacy.recall
record_action = _legacy.record_action


def _recall_proxy(*args, **kwargs):
    return recall(*args, **kwargs)


def _record_action_proxy(*args, **kwargs):
    return record_action(*args, **kwargs)


_legacy.recall = _recall_proxy
_legacy.record_action = _record_action_proxy


_LOCAL_FILE_SUFFIXES = {
    ".csv", ".doc", ".docx", ".json", ".log", ".md", ".pdf", ".py",
    ".txt", ".xlsx", ".xls", ".yaml", ".yml",
}


def _public_url(text: str) -> str | None:
    match = re.search(
        r"(?:https?://|www\.|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})[^\s<>()\[\]{}]*",
        text or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    candidate = match.group(0)
    # A bare local filename (for example ``notes.txt``) resembles a hostname
    # to a permissive URL regex.  Treat it as a file reference unless the user
    # supplied an explicit URL form.  This boundary keeps filesystem tasks out
    # of the browser/fetch tool path.
    if not candidate.lower().startswith(("http://", "https://", "www.")):
        hostname = candidate.rstrip(".,;:!?)]}").split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if Path(hostname).suffix.lower() in _LOCAL_FILE_SUFFIXES:
            return None
    from core.tools.public_web import normalize_public_url

    url = normalize_public_url(match.group(0))
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


_SITE_ALIASES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "wikipedia": "https://www.wikipedia.org",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
}


def _site_alias_url(text: str) -> str | None:
    """Return a URL only for a clearly requested, known public site."""
    match = re.search(
        r"\b(?:open|browse|navigate(?:\s+to)?|go\s+to|visit)\s+(?:the\s+)?"
        r"([A-Za-z]+)\b",
        text or "",
        re.IGNORECASE,
    )
    return _SITE_ALIASES.get(match.group(1).lower()) if match else None


class AgentExecutionLoop(_legacy.AgentExecutionLoop):
    """Verified execution loop with small, explicit current-policy adapters."""

    _ARTIFACT_SAVE = re.compile(
        r"^\s*(?:please\s+)?(?:save|export|write|put)\s+(?:this|that|the)\s+"
        r"(?:research|report|document|answer)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        use_tools: bool = True,
        history: list[dict] | None = None,
        session_artifacts: dict | None = None,
    ):
        super().__init__(use_tools=use_tools, history=history)
        if session_artifacts is not None:
            # Keep the same object: the next turn must receive the generated
            # text and directory references from this turn.
            self.session_artifacts = session_artifacts

    def _direct_route(self, user_input: str, recalled_facts: str = ""):
        artifact_save = bool(self._ARTIFACT_SAVE.search(user_input or ""))
        if artifact_save:
            artifact = self.session_artifacts.get("last_generated_document")
            content = artifact.get("content") if isinstance(artifact, dict) else None
            if not isinstance(content, str) or not content.strip():
                return (
                    "I cannot save that because this session has no verified generated "
                    "report yet. No file was created. Generate or research the report first."
                )
            if re.search(r"\bthat\s+(?:directory|folder)\b", user_input, re.IGNORECASE):
                directory = self.session_artifacts.get("last_created_directory")
                if not isinstance(directory, str) or not directory.strip():
                    return (
                        "I have the report, but this session has no verified previous directory "
                        "to resolve 'that directory'. No file was created. Please name a workspace "
                        "directory or create one first."
                    )

        url = _public_url(user_input) or _site_alias_url(user_input)
        lowered = (user_input or "").lower()
        read_only_verbs = ("read", "fetch", "summarize", "summarise", "extract", "find", "get")
        browser_verbs = ("open", "browse", "navigate", "go to", "visit")
        blocked_web_action_patterns = (
            r"\blog\s+in\b", r"\blogin\b", r"\bsign\s+in\b", r"\bfill\b",
            r"\bsubmit\b", r"\bclick\b", r"\bupload\b", r"\bdownload\b",
            r"\bpurchase\b", r"\bbuy\b", r"\bpay\b", r"\bcheckout\b", r"\bbook\b",
        )
        if url:
            if any(re.search(pattern, lowered) for pattern in blocked_web_action_patterns):
                return (
                    "I can open a public URL in your default browser or read its public text, "
                    "but I cannot log in, fill forms, click through a site, download files, "
                    "or submit anything."
                )
            read_only_web = any(
                re.search(rf"\b{re.escape(verb)}\b", lowered)
                for verb in read_only_verbs
            )
            open_web = any(
                re.search(rf"\b{re.escape(verb)}\b", lowered)
                for verb in browser_verbs
            )
            if read_only_web or open_web:
                tool = "fetch_url" if read_only_web else "open_url"
                return [{"step": 1, "tool": tool, "arguments": {"url": url}}]

            # Do not let the legacy router interpret a bare pasted URL as a
            # request for browser automation. The user must use an action verb.
            return None

        plan = super()._direct_route(user_input, recalled_facts)
        if not isinstance(plan, list):
            return plan

        # Resolve conversational references such as "save this report in that
        # directory" to the directory verified in the earlier turn.
        if artifact_save and re.search(r"\bthat\s+(?:directory|folder)\b", user_input, re.IGNORECASE):
            directory = self.session_artifacts.get("last_created_directory")
            if isinstance(directory, str) and directory.strip():
                for step in plan:
                    if step.get("tool") == "write_file":
                        arguments = step.setdefault("arguments", {})
                        filename = Path(str(arguments.get("filepath", "research_report.md"))).name
                        arguments["filepath"] = str(Path(directory) / filename)
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
                elif "open" in value or "browser" in value or "website" in value:
                    mapped = "open_public_urls"
                else:
                    continue
                if mapped not in normalized:
                    normalized.append(mapped)
            if normalized:
                args["capabilities"] = normalized
        return plan

    def _synthesize_final_response(self, user_input, completed_steps, recalled_facts):
        """Report an OS browser handoff directly from the verified tool result."""
        if len(completed_steps) == 1 and completed_steps[0].get("tool") == "open_url":
            result = completed_steps[0].get("result", {})
            if isinstance(result, dict) and result.get("success"):
                url = result.get("url") or completed_steps[0].get("arguments", {}).get("url", "the URL")
                return prose_hook.filter_response(
                    f"Opened {url} in your default browser. I did not interact with the website."
                )
            message = result.get("message") if isinstance(result, dict) else None
            return prose_hook.filter_response(
                f"I could not open the public URL{f': {message}' if message else '.'}"
            )
        return super()._synthesize_final_response(user_input, completed_steps, recalled_facts)
