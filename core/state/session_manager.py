"""
core/state/session_manager.py
=============================
Conversational state machine for Jarvis.

Responsibilities:
- Maintains the full conversation history as a list of role/content dicts
- Trims history to SESSION_MAX_TURNS to prevent context window overflow
- Routes user input through Ollama and returns the assistant response
- Provides a clean reset() method for starting a new session

Design notes:
- History format follows the Ollama /api/chat spec:
    [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]
- System prompt is always kept as history[0] and never trimmed
"""

import datetime
from typing import Optional

from core.config import settings
from core.llm.ollama_client import ollama, OllamaError


class SessionManager:
    """
    Manages a multi-turn conversation with the Ollama LLM.
    Import and use the module-level `session` singleton,
    or create a new instance for isolated sub-sessions.
    """

    def __init__(
        self,
        model: str = None,
        system_prompt: str = None,
        max_turns: int = None,
    ):
        self.model = model or settings.ollama_model
        self.system_prompt = system_prompt or settings.jarvis_system_prompt
        self.max_turns = max_turns or settings.session_max_turns
        self._started_at = datetime.datetime.utcnow()

        # History always starts with the system prompt
        self.history: list[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

    # ------------------------------------------------------------------
    # Core chat method
    # ------------------------------------------------------------------

    def chat(self, user_input: str, temperature: float = 0.7) -> str:
        """
        Send user input to the LLM and return the assistant's response.
        Automatically appends both the user message and assistant reply
        to the conversation history.

        Args:
            user_input:   The user's message (transcribed speech or typed text).
            temperature:  Sampling temperature passed to Ollama.

        Returns:
            The assistant's response text.

        Raises:
            OllamaError: If Ollama is not running or the request fails.
        """
        # Append user message
        self.history.append({"role": "user", "content": user_input})

        # Call Ollama
        response = ollama.chat(
            messages=self.history,
            model=self.model,
            temperature=temperature,
        )

        # Append assistant response
        self.history.append({"role": "assistant", "content": response})

        # Trim history to prevent context window overflow
        self._trim_history()

        return response

    def chat_stream(self, user_input: str, temperature: float = 0.7):
        """
        Streaming version of chat(). Yields text chunks as they arrive.
        Use this for lower-latency TTS (start speaking before full response arrives).

        Note: History is updated only after the full response is collected.
        """
        self.history.append({"role": "user", "content": user_input})

        full_response = ""
        for chunk in ollama.chat(
            messages=self.history,
            model=self.model,
            stream=True,
            temperature=temperature,
        ):
            full_response += chunk
            yield chunk

        # Update history with complete response
        self.history.append({"role": "assistant", "content": full_response})
        self._trim_history()

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        """
        Keeps the system prompt + last max_turns * 2 messages (user + assistant pairs).
        Prevents the context window from growing indefinitely in long sessions.
        """
        # history[0] is always the system prompt
        # Each turn = 2 messages (user + assistant)
        max_messages = (self.max_turns * 2) + 1  # +1 for system prompt
        if len(self.history) > max_messages:
            system_prompt_msg = self.history[0]
            trimmed = self.history[-(self.max_turns * 2):]
            self.history = [system_prompt_msg] + trimmed

    def reset(self) -> None:
        """Start a completely fresh conversation (keeps system prompt)."""
        self.history = [{"role": "system", "content": self.system_prompt}]
        self._started_at = datetime.datetime.utcnow()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def turn_count(self) -> int:
        """Number of completed user/assistant turn pairs."""
        # Subtract 1 for system prompt, divide by 2 for pairs
        return max(0, (len(self.history) - 1) // 2)

    @property
    def session_duration(self) -> datetime.timedelta:
        return datetime.datetime.utcnow() - self._started_at

    def last_user_message(self) -> Optional[str]:
        for msg in reversed(self.history):
            if msg["role"] == "user":
                return msg["content"]
        return None

    def last_assistant_message(self) -> Optional[str]:
        for msg in reversed(self.history):
            if msg["role"] == "assistant":
                return msg["content"]
        return None

    def __repr__(self) -> str:
        return (
            f"<SessionManager model={self.model!r} "
            f"turns={self.turn_count} "
            f"duration={self.session_duration}>"
        )


# ---------------------------------------------------------------------------
# Default singleton — use this in most places
# ---------------------------------------------------------------------------
session = SessionManager()
