"""
tests/smoke_test.py
===================
M1 Smoke Test — 5-turn context retention test.

Tests the conversational state machine WITHOUT audio (text-only mode).
This means it can run on any machine, including CI, without a microphone.

What it validates:
1. SessionManager holds context across 5 turns
2. LLM remembers what was said in earlier turns
3. History trimming doesn't break context
4. Session reset works correctly
5. Ollama client handles a real multi-turn conversation

Requirements to run:
- Ollama must be running: ollama serve
- Target model must be pulled: ollama pull llama3.1

Usage:
    poetry run pytest tests/smoke_test.py -v
    # OR run directly:
    poetry run python tests/smoke_test.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.config import settings
from core.llm.ollama_client import ollama, OllamaError
from core.state.session_manager import SessionManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ollama_available():
    """Skip all tests if Ollama is not running."""
    if not ollama.is_running():
        pytest.skip(
            f"Ollama is not running at {settings.ollama_base_url}. "
            "Start it with: ollama serve"
        )


@pytest.fixture
def session():
    """Fresh SessionManager for each test."""
    return SessionManager(
        system_prompt=(
            "You are Jarvis, a concise AI assistant. "
            "Answer in 1-2 sentences only. "
            "Remember everything said in this conversation."
        )
    )


# ---------------------------------------------------------------------------
# Test 1: Basic connectivity
# ---------------------------------------------------------------------------

def test_ollama_connection(ollama_available):
    """Verify Ollama server is reachable and returns a response."""
    assert ollama.is_running(), "Ollama must be running"
    models = ollama.list_models()
    print(f"\n  Available models: {models}")
    assert isinstance(models, list)


# ---------------------------------------------------------------------------
# Test 2: Single turn response
# ---------------------------------------------------------------------------

def test_single_turn(ollama_available, session):
    """Verify a single-turn response is non-empty."""
    response = session.chat("Say the word 'hello' and nothing else.")
    print(f"\n  Response: {response!r}")
    assert isinstance(response, str)
    assert len(response.strip()) > 0
    assert session.turn_count == 1


# ---------------------------------------------------------------------------
# Test 3: Context retention — 5-turn conversation
# ---------------------------------------------------------------------------

def test_five_turn_context_retention(ollama_available, session):
    """
    Core M1 test: verify the LLM remembers context over 5 turns.

    Turn sequence:
    1. Tell Jarvis a unique code word
    2. Ask an unrelated question (distraction)
    3. Another distraction
    4. Ask Jarvis to repeat the code word → must be correct
    5. Ask what was discussed first → must mention the code word
    """
    unique_code = "ALPHA-TANGO-7"

    # Turn 1: Plant the code word
    r1 = session.chat(f"Remember this code word for the rest of our conversation: {unique_code}")
    print(f"\n  Turn 1: {r1!r}")
    assert session.turn_count == 1

    # Turn 2: Distraction
    r2 = session.chat("What is the capital of France?")
    print(f"  Turn 2: {r2!r}")
    assert "paris" in r2.lower() or "france" in r2.lower()
    assert session.turn_count == 2

    # Turn 3: Distraction
    r3 = session.chat("How many days are in a leap year?")
    print(f"  Turn 3: {r3!r}")
    assert session.turn_count == 3

    # Turn 4: Ask for the code word — context must be retained
    r4 = session.chat("What was the code word I asked you to remember?")
    print(f"  Turn 4: {r4!r}")
    assert unique_code in r4, (
        f"Context LOST: Expected '{unique_code}' in response, got: {r4!r}"
    )
    assert session.turn_count == 4

    # Turn 5: Verify first topic recall
    r5 = session.chat("What was the first thing we talked about in this conversation?")
    print(f"  Turn 5: {r5!r}")
    # Should mention code word or remembering something
    assert any(kw in r5.lower() for kw in ["code", "alpha", "tango", "remember", "word"]), (
        f"Turn 5 context failure: {r5!r}"
    )
    assert session.turn_count == 5

    print(f"\n  ✅ All 5 turns passed with context intact.")


# ---------------------------------------------------------------------------
# Test 4: History structure is correct
# ---------------------------------------------------------------------------

def test_history_structure(ollama_available, session):
    """Verify the history list has the correct format."""
    session.chat("My name is TestUser.")

    assert len(session.history) == 3  # system + user + assistant
    assert session.history[0]["role"] == "system"
    assert session.history[1]["role"] == "user"
    assert session.history[2]["role"] == "assistant"
    assert "TestUser" in session.history[1]["content"]


# ---------------------------------------------------------------------------
# Test 5: Session reset clears history
# ---------------------------------------------------------------------------

def test_session_reset(ollama_available, session):
    """Verify that reset() clears conversation history."""
    code = "RESET-TEST-999"
    session.chat(f"Remember: {code}")
    assert session.turn_count == 1

    session.reset()
    assert session.turn_count == 0
    assert len(session.history) == 1  # Only system prompt remains
    assert session.history[0]["role"] == "system"

    # After reset, code word should NOT be remembered
    r = session.chat("What code word did I ask you to remember?")
    print(f"\n  Post-reset response: {r!r}")
    assert code not in r, f"Reset FAILED: Code word still in memory: {r!r}"


# ---------------------------------------------------------------------------
# Test 6: History trimming keeps system prompt
# ---------------------------------------------------------------------------

def test_history_trimming():
    """Verify history trimming never removes the system prompt."""
    small_session = SessionManager(max_turns=3)
    system_prompt_content = small_session.history[0]["content"]

    # Add more turns than max_turns allows
    for i in range(10):
        small_session.history.append({"role": "user", "content": f"Message {i}"})
        small_session.history.append({"role": "assistant", "content": f"Response {i}"})
        small_session._trim_history()

    # System prompt must always be first
    assert small_session.history[0]["role"] == "system"
    assert small_session.history[0]["content"] == system_prompt_content

    # Total history should not exceed max_turns * 2 + 1
    max_expected = (small_session.max_turns * 2) + 1
    assert len(small_session.history) <= max_expected, (
        f"History too long: {len(small_session.history)} > {max_expected}"
    )
    print(f"\n  History size after trim: {len(small_session.history)} (max: {max_expected})")


# ---------------------------------------------------------------------------
# Run directly (without pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "═" * 50)
    print("  Jarvis M1 Smoke Test — Text Mode")
    print("═" * 50)

    if not ollama.is_running():
        print(f"❌ Ollama is not running at {settings.ollama_base_url}")
        print("   Start with: ollama serve")
        sys.exit(1)

    test_session = SessionManager(
        system_prompt=(
            "You are Jarvis, a concise AI assistant. "
            "Answer in 1-2 sentences only. "
            "Remember everything said in this conversation."
        )
    )

    print("\n📋 Running 5-turn context retention test...")
    try:
        test_five_turn_context_retention(None, test_session)
        print("\n✅ SMOKE TEST PASSED — M1 context retention verified!")
    except AssertionError as e:
        print(f"\n❌ SMOKE TEST FAILED: {e}")
        sys.exit(1)
    except OllamaError as e:
        print(f"\n❌ Ollama error: {e}")
        sys.exit(1)
