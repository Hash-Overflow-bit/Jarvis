"""Fast, tool-free conversation and drafting.

Ordinary conversation must not enter the agent planner.  The planner is reserved
for requests that explicitly require an external action (files, web, browser,
packages, or source control).  This keeps a simple answer to one model call and
prevents a drafting prompt from accidentally invoking tools.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from core.llm.ollama_client import OllamaError, ollama
from core.llm.prose_hook import prose_hook


_LOCAL_FILE_SUFFIXES = {
    ".csv", ".doc", ".docx", ".json", ".log", ".md", ".pdf", ".py",
    ".txt", ".xlsx", ".xls", ".yaml", ".yml",
}


class ConversationRouter:
    """Deterministically separate tool-free text from actionable requests."""

    # A URL by itself may only be text the user is sharing. A URL paired with
    # an explicit action verb must reach the tool loop rather than the chat
    # model, which would otherwise reply with text instead of performing it.
    _PUBLIC_URL = re.compile(
        r"(?:https?://|www\.|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})[^\s<>()\[\]{}]*",
        re.IGNORECASE,
    )
    _URL_ACTION = re.compile(
        r"\b(?:open|browse|navigate(?:\s+to)?|go\s+to|visit|read|fetch|"
        r"summari[sz]e|extract|find|get)\b",
        re.IGNORECASE,
    )
    _SITE_ALIAS_ACTION = re.compile(
        r"\b(?:open|browse|navigate(?:\s+to)?|go\s+to|visit)\s+(?:the\s+)?"
        r"(?:google|youtube|github|wikipedia|linkedin|reddit)\b",
        re.IGNORECASE,
    )

    _FILE_TARGET = re.compile(
        r"(?:\b(?:file|files|document|documents|folder|directory|workspace|desktop|path)\b|"
        r"(?:^|\s)[A-Za-z0-9_.-]+\.(?:txt|md|csv|json|pdf|docx|xlsx|py)\b)",
        re.IGNORECASE,
    )
    _FILE_ACTION = re.compile(
        r"\b(?:create|make|save|write|append|overwrite|read|open|show|list|scan|"
        r"delete|remove|rename|move|copy|organize)\b",
        re.IGNORECASE,
    )
    _ARTIFACT_SAVE = re.compile(
        r"\b(?:save|export|write|put)\s+(?:this|that|the)\s+"
        r"(?:research|report|document|answer)\b",
        re.IGNORECASE,
    )
    _EXTERNAL_ACTION = re.compile(
        r"\b(?:research|web\s*search|search\s+(?:the\s+)?web|look\s+up\s+online|"
        r"browse|navigate|open\s+(?:the\s+)?(?:website|url)|fill\s+(?:in\s+)?(?:a\s+)?form|"
        r"git\s+(?:clone|pull|push|commit)|poetry\s+(?:add|install)|pip\s+install|"
        r"run\s+(?:this\s+)?(?:command|script)|delegate\s+(?:this\s+)?task)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def _has_public_url(text: str) -> bool:
        """Return True for public URL syntax, never a local filename."""
        match = ConversationRouter._PUBLIC_URL.search(text)
        if not match:
            return False
        candidate = match.group(0)
        if candidate.lower().startswith(("http://", "https://", "www.")):
            return True
        hostname = candidate.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        return not (Path(hostname).suffix.lower() in _LOCAL_FILE_SUFFIXES)

    def requires_agent(self, user_input: str) -> bool:
        """Return True only when the request explicitly needs a tool/action."""
        text = (user_input or "").strip()
        if not text:
            return False
        if self._SITE_ALIAS_ACTION.search(text):
            return True
        if self._has_public_url(text) and self._URL_ACTION.search(text):
            return True
        if self._EXTERNAL_ACTION.search(text):
            return True
        # A follow-up save may not name a filename yet, but it still needs
        # the tool loop so it can bind to the verified prior artifact or fail
        # safely without creating an empty file.
        if self._ARTIFACT_SAVE.search(text):
            return True
        return bool(self._FILE_ACTION.search(text) and self._FILE_TARGET.search(text))


class ConversationService:
    """Generate a normal conversational or drafting response in one LLM call."""

    _ALLOWED_ROLES = {"system", "user", "assistant"}

    @classmethod
    def _clean_history(cls, history: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for message in history:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role in cls._ALLOWED_ROLES and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})
        return messages

    def respond(
        self,
        history: Sequence[dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.7,
    ) -> str:
        """Return verified, non-empty text without exposing tools to the model."""
        messages = self._clean_history(history)
        if not messages or messages[-1]["role"] != "user":
            raise ValueError("Conversation history must end with a user message.")

        response = ollama.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=None,
        )
        if not isinstance(response, dict):
            raise OllamaError("Ollama returned an invalid conversation response.")

        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama returned an empty conversation response.")
        return prose_hook.filter_response(content.strip())
