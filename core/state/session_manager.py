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
from core.conversation.service import ConversationRouter, ConversationService
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
        self.conversation_system_prompt = self.system_prompt
        self.max_turns = max_turns or settings.session_max_turns
        self.use_tools = use_tools
        self.conversation_router = ConversationRouter()
        self.conversation_service = ConversationService()
        self._started_at = datetime.datetime.now(datetime.timezone.utc)

        # Inform the LLM of the authorized sandbox & workspace directories so it does not use placeholders
        if self.use_tools:
            workspace = settings.default_workspace_dir
            self.system_prompt += (
                "\n\nControlled Workspace Configuration:\n"
                f"- The only authorized location for document and filesystem actions is '{workspace}'.\n"
                f"- Map both 'workspace' and relative file paths to '{workspace}'.\n"
                "- Do not target Desktop, Documents, home, or any path outside the workspace.\n"
                "- Never invent placeholder paths. If the requested path is ambiguous, ask the user."
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

        use_agent = self.use_tools and self.conversation_router.requires_agent(user_input)

        if use_agent:
            from core.orchestrator.deterministic_filesystem import DeterministicFilesystemRouter
            deterministic = DeterministicFilesystemRouter().try_handle(user_input)
            if deterministic is not None:
                response = deterministic.response
                self.history.append({"role": "assistant", "content": response})
                self._trim_history()
                return response

            from core.research.service import ResearchRouter, ResearchService, ResearchUnavailable
            if ResearchRouter().matches(user_input):
                try:
                    response = ResearchService().research(user_input, model=self.model).report
                except ResearchUnavailable as exc:
                    response = (
                        "I could not complete grounded web research because online sources "
                        f"were unavailable: {exc}"
                    )
                self.history.append({"role": "assistant", "content": response})
                self._trim_history()
                return response

            # Memory integration for tool workflows is retained here.  Normal
            # conversation remains one deterministic model call; persistent
            # memory is integrated separately by the memory capability gate.
            record_conversation_turn = None
            try:
                from core.memory.chat_memory import learn_from_message, record_conversation_turn
                learn_from_message(user_input)
            except Exception:
                record_conversation_turn = None

            from core.orchestrator.agent_loop import AgentExecutionLoop
            loop = AgentExecutionLoop(use_tools=True, history=self.history)
            try:
                response = loop.run(user_input, mode=mode)
            except Exception:
                self.history.pop()
                raise
            # Add final response as assistant role to history for next turns
            self.history.append({"role": "assistant", "content": response})
            self._trim_history()
            if record_conversation_turn is not None:
                try:
                    record_conversation_turn(user_input, response)
                except Exception:
                    pass
            return response
        else:
            conversation_history = list(self.history)
            conversation_history[0] = {
                "role": "system",
                "content": self.conversation_system_prompt,
            }
            if settings.local_memory_enabled:
                try:
                    from core.memory.local_memory import LocalMemoryService

                    local_memory = LocalMemoryService()
                    forget_response = local_memory.handle_forget_command(user_input)
                    if forget_response is not None:
                        self.history.append({"role": "assistant", "content": forget_response})
                        self._trim_history()
                        return forget_response
                    local_memory.capture(user_input)
                    memory_context = local_memory.format_context(local_memory.recall(user_input))
                    if memory_context:
                        conversation_history.insert(
                            1, {"role": "system", "content": memory_context}
                        )
                except Exception:
                    # Memory must never block the primary conversation path.
                    pass
            try:
                answer = self.conversation_service.respond(
                    conversation_history,
                    model=self.model,
                    temperature=temperature,
                )
            except Exception:
                self.history.pop()
                raise
            self.history.append({"role": "assistant", "content": answer})
            self._trim_history()
            return answer


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
