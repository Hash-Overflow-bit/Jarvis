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
        model: str | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        use_tools: bool = True,
    ):
        self.model = model or settings.ollama_model
        self.system_prompt = system_prompt or settings.jarvis_system_prompt
        self.max_turns = max_turns or settings.session_max_turns
        self.use_tools = use_tools
        self._started_at = datetime.datetime.now(datetime.timezone.utc)

        # Inform the LLM of the authorized sandbox & workspace directories so it does not use placeholders
        if self.use_tools:
            allowed_dirs = list(settings.sandbox_roots)
            try:
                workspace = settings.default_workspace_dir
                if workspace not in allowed_dirs:
                    allowed_dirs.append(workspace)
            except Exception:
                pass

            roots_str = ", ".join(f"'{r}'" for r in allowed_dirs)
            example_sandbox = settings.sandbox_roots[0] if settings.sandbox_roots else ""
            
            # Extract actual desktop path if present in allowed roots
            desktop_path = ""
            for r in allowed_dirs:
                r_str = str(r)
                if "desktop" in r_str.lower() and not r_str.lower().endswith("sandbox"):
                    desktop_path = r_str
                    break
            if not desktop_path:
                for r in allowed_dirs:
                    if "desktop" in str(r).lower():
                        desktop_path = str(r)
                        break

            self.system_prompt += (
                f"\n\nSecurity Sandbox & Workspace Configuration:\n"
                f"- You only have access to these authorized local directories: {roots_str}.\n"
                f"- When the user references 'sandbox', map it to '{example_sandbox}'.\n"
                f"- When the user references 'workspace', map it to '{settings.default_workspace_dir}'.\n"
            )
            if desktop_path:
                self.system_prompt += f"- When the user references 'desktop', map it to '{desktop_path}'.\n"
                
            self.system_prompt += (
                f"- You are fully authorized to clone Git repositories and manage Poetry/pip packages inside the workspace directory.\n"
                f"- Never use placeholder paths like '/path/to/sandbox' or './sandbox' or '/path/to/desktop'."
            )


        # History always starts with the system prompt
        self.history: list[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

    # ------------------------------------------------------------------
    # Core chat method
    # ------------------------------------------------------------------

    def chat(self, user_input: str, temperature: float = 0.7, mode: str = "text") -> str:
        """
        Send user input to the LLM and return the assistant's response.
        Automatically appends both the user message and assistant reply
        to the conversation history.

        Args:
            user_input:   The user's message (transcribed speech or typed text).
            temperature:  Sampling temperature passed to Ollama.
            mode:         Runtime execution mode ('text' or 'audio').

        Returns:
            The assistant's response text.

        Raises:
            OllamaError: If Ollama is not running or the request fails.
        """
        # Append user message
        self.history.append({"role": "user", "content": user_input})

        # Asynchronously extract and save conversational facts to the knowledge graph
        import threading
        try:
            from core.memory.chat_memory import learn_from_message
            threading.Thread(target=learn_from_message, args=(user_input,), daemon=True).start()
        except Exception:
            pass

        if self.use_tools:

            from core.orchestrator.agent_loop import AgentExecutionLoop
            loop = AgentExecutionLoop(use_tools=True, history=self.history)
            response = loop.run(user_input, mode=mode)
            # Add final response as assistant role to history for next turns
            self.history.append({"role": "assistant", "content": response})
            self._trim_history()
            return response
        else:
            # Direct conversational response without tools
            chat_messages = list(self.history)
            injected_context = ""
            if settings.graph_enabled:
                try:
                    from core.memory.recall import recall
                    recall_result = recall(user_input, hops=settings.max_graph_hops, top_k=settings.graph_top_k)
                    if recall_result.facts:
                        injected_context = recall_result.as_text()
                        chat_messages.insert(1, {"role": "system", "content": injected_context})
                except Exception as e:
                    print(f"\n[🧠 Memory Error] Failed recall: {e}")

            response_msg = ollama.chat(
                messages=chat_messages,
                model=self.model,
                temperature=temperature,
            )

            if isinstance(response_msg, str):
                response_msg = {"role": "assistant", "content": response_msg}

            if not isinstance(response_msg, dict):
                raise OllamaError("Expected dictionary response from Ollama")

            self.history.append(response_msg)
            self._trim_history()
            return response_msg.get("content", "") or ""

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
        self._started_at = datetime.datetime.now(datetime.timezone.utc)

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
        return datetime.datetime.now(datetime.timezone.utc) - self._started_at

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
