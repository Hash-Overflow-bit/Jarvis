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
            self.system_prompt += (
                f"\n\nSecurity Sandbox & Workspace Configuration:\n"
                f"- You only have access to these authorized local directories: {roots_str}.\n"
                f"- When the user references 'sandbox', map it to '{example_sandbox}'.\n"
                f"- When the user references 'workspace', map it to '{settings.default_workspace_dir}'.\n"
                f"- You are fully authorized to clone Git repositories and manage Poetry/pip packages inside the workspace directory.\n"
                f"- Never use placeholder paths like '/path/to/sandbox' or './sandbox'."
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

        # Query local knowledge memory before executing Ollama chat
        chat_messages = list(self.history)
        injected_context = ""
        has_facts = False
        
        if settings.graph_enabled:
            try:
                from core.memory.recall import recall
                recall_result = recall(user_input, hops=settings.max_graph_hops, top_k=settings.graph_top_k)
                if recall_result.facts:
                    injected_context = recall_result.as_text()
                    # Inject at index 1 (right after the system prompt at history[0])
                    chat_messages.insert(1, {"role": "system", "content": injected_context})
                    has_facts = True
                    print(f"\n[🧠 Memory] Recalled {len(recall_result.facts)} facts in {recall_result.latency_ms:.1f}ms")
                else:
                    print("\n[🧠 Memory] No memory matches found.")
            except Exception as e:
                print(f"\n[🧠 Memory Error] Failed recall: {e}")

        # Call Ollama with tools registered if allowed
        from core.tools.tool_registry import tool_registry
        from core.llm.function_call_handler import function_call_handler
        import json

        has_tools = self.use_tools and bool(tool_registry.get_all_schemas())
        response_msg = ollama.chat(
            messages=chat_messages,
            model=self.model,
            temperature=temperature,
            tools=tool_registry.get_all_schemas() if has_tools else None,
        )

        # Fallback if response_msg is a string (e.g. mocked or legacy format)
        if isinstance(response_msg, str):
            response_msg = {"role": "assistant", "content": response_msg}

        if not isinstance(response_msg, dict):
            raise OllamaError("Expected dictionary response from Ollama")

        # Append assistant response
        self.history.append(response_msg)

        # Check if Ollama requested a tool call
        tool_calls = response_msg.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    tool_result = function_call_handler.handle_tool_call(tool_call, mode=mode)
                    function_info = tool_call.get("function")
                    function_name = ""
                    if isinstance(function_info, dict):
                        function_name = function_info.get("name", "")
                    self.history.append({
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(tool_result),
                    })
            
            # Re-assemble follow up messages with the injected context to maintain consistency
            followup_messages = list(self.history)
            if settings.graph_enabled and has_facts:
                followup_messages.insert(1, {"role": "system", "content": injected_context})

            # Submit updated history with tool result back to Ollama for summary
            followup_msg = ollama.chat(
                messages=followup_messages,
                model=self.model,
                temperature=temperature,
            )
            
            if isinstance(followup_msg, str):
                followup_msg = {"role": "assistant", "content": followup_msg}
                
            if not isinstance(followup_msg, dict):
                raise OllamaError("Expected dictionary response from Ollama")

            self.history.append(followup_msg)
            self._trim_history()
            return followup_msg.get("content", "") or ""
        else:
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
