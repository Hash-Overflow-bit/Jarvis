"""Acceptance tests for Capability 1: normal conversation and drafting."""

from unittest.mock import patch

import pytest

from core.conversation.service import ConversationRouter
from core.llm.ollama_client import OllamaError
from core.state.session_manager import SessionManager


def _public_dns(*_args, **_kwargs):
    return [(None, None, None, None, ("93.184.216.34", 0))]


@pytest.mark.parametrize(
    "prompt",
    [
        "Hello, how are you?",
        "Create a three-step plan for organizing my workday.",
        "Draft a concise email declining tomorrow's meeting.",
        "Rewrite this paragraph in a professional tone: we need it now.",
        "Summarize the following pasted text in two bullets: Alpha. Beta.",
    ],
)
def test_router_keeps_conversation_and_drafting_tool_free(prompt):
    assert ConversationRouter().requires_agent(prompt) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "Create a folder named invoices in the workspace.",
        "Read workspace/report.md and summarize it.",
        "Research the latest AI project-management tools online.",
        "Navigate to example.com and fill the form.",
        "Run this command: git status",
    ],
)
def test_router_sends_explicit_external_actions_to_agent(prompt):
    assert ConversationRouter().requires_agent(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        "Open https://example.com",
        "Please visit www.example.com/docs.",
        "Read https://example.com and summarize it.",
    ],
)
def test_router_sends_explicit_public_url_actions_to_agent(prompt):
    assert ConversationRouter().requires_agent(prompt) is True


def test_session_open_url_executes_the_browser_tool_not_the_chat_model():
    session = SessionManager(use_tools=True, system_prompt="Be concise.")

    with patch(
        "core.tools.public_web.socket.getaddrinfo", side_effect=_public_dns
    ), patch(
        "core.tools.public_web.webbrowser.open", return_value=True
    ) as open_browser, patch("core.orchestrator.agent_loop.ollama.chat") as llm:
        result = session.chat("Open https://example.com/docs")

    open_browser.assert_called_once_with("https://example.com/docs", new=2)
    llm.assert_not_called()
    assert result == (
        "Opened https://example.com/docs in your default browser. "
        "I did not interact with the website."
    )


def test_tool_enabled_session_uses_one_direct_call_for_normal_chat():
    session = SessionManager(use_tools=True, system_prompt="Be concise.")
    reply = {"role": "assistant", "content": "1. Prioritize.\n2. Focus.\n3. Review."}

    with patch("core.conversation.service.ollama.chat", return_value=reply) as chat:
        result = session.chat("Create a three-step plan for organizing my workday.")

    assert result == reply["content"]
    chat.assert_called_once()
    assert chat.call_args.kwargs["tools"] is None
    assert chat.call_args.kwargs["messages"][0] == {
        "role": "system", "content": "Be concise."
    }
    assert session.turn_count == 1


def test_direct_chat_preserves_multi_turn_history():
    session = SessionManager(use_tools=True, system_prompt="Remember this conversation.")
    responses = [
        {"role": "assistant", "content": "I will remember BLUE-7."},
        {"role": "assistant", "content": "The code is BLUE-7."},
    ]
    with patch("core.conversation.service.ollama.chat", side_effect=responses) as chat:
        session.chat("The session code is BLUE-7.")
        answer = session.chat("What is the session code?")

    assert answer == "The code is BLUE-7."
    second_messages = chat.call_args_list[1].kwargs["messages"]
    assert [message["role"] for message in second_messages] == [
        "system", "user", "assistant", "user"
    ]
    assert session.turn_count == 2


def test_failed_direct_chat_does_not_poison_history():
    session = SessionManager(use_tools=True, system_prompt="Be concise.")
    with patch("core.conversation.service.ollama.chat", return_value={"role": "assistant", "content": ""}):
        with pytest.raises(OllamaError, match="empty conversation response"):
            session.chat("Hello")

    assert session.history == [{"role": "system", "content": session.system_prompt}]
    assert session.turn_count == 0


def test_reset_clears_direct_conversation_history():
    session = SessionManager(use_tools=True, system_prompt="Be concise.")
    with patch(
        "core.conversation.service.ollama.chat",
        return_value={"role": "assistant", "content": "Hello."},
    ):
        session.chat("Hello")
    session.reset()
    assert session.turn_count == 0
    assert session.history == [{"role": "system", "content": session.system_prompt}]
