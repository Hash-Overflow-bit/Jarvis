"""Acceptance tests for Capability 5: grounded web research."""

from unittest.mock import patch

import pytest

from core.research.service import (
    ResearchResult,
    ResearchRouter,
    ResearchService,
    ResearchSource,
    ResearchUnavailable,
)
from core.state.session_manager import SessionManager


class FakeBackend:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.results


RESULTS = [
    {
        "title": "Primary source",
        "url": "https://example.com/primary",
        "snippet": "The project reported a 12 percent improvement in 2026.",
    },
    {
        "title": "Second source",
        "url": "https://example.org/second",
        "snippet": "The documented limitation was a small sample size.",
    },
]


@pytest.mark.parametrize(
    "prompt",
    [
        "Research AI in project management",
        "Investigate current warehouse automation",
        "Search the web for local LLM benchmarks",
        "Look up online current Python releases",
    ],
)
def test_research_router_matches_explicit_online_requests(prompt):
    assert ResearchRouter().matches(prompt)


def test_query_removes_action_and_save_directives():
    query = ResearchRouter().query(
        "Research AI in project management and save the report to report.md"
    )
    assert query == "AI in project management"


def test_research_uses_retrieved_evidence_and_exact_source_list():
    backend = FakeBackend(RESULTS)
    service = ResearchService(backend=backend)
    model_output = {
        "role": "assistant",
        "content": (
            "The retrieved project reported a 12 percent improvement [1]. "
            "The sample was limited [2]."
        ),
    }
    with patch("core.research.service.ollama.chat", return_value=model_output) as chat:
        result = service.research("Research the project outcome")

    assert backend.queries == ["the project outcome"]
    assert "[1] Primary source — https://example.com/primary" in result.report
    assert "[2] Second source — https://example.org/second" in result.report
    prompt = chat.call_args.kwargs["messages"][1]["content"]
    assert RESULTS[0]["snippet"] in prompt
    assert chat.call_args.kwargs["tools"] is None


def test_hallucinated_urls_and_citation_numbers_are_removed():
    service = ResearchService(backend=FakeBackend(RESULTS))
    output = {
        "role": "assistant",
        "content": "Claim [9]. More at https://fake.example/hallucinated.",
    }
    with patch("core.research.service.ollama.chat", return_value=output):
        result = service.research("Research the project")
    assert "https://fake.example" not in result.report
    assert "[invalid citation removed]" in result.report
    assert "[unverified link removed]" in result.report


def test_invalid_duplicate_and_empty_search_results_are_filtered():
    results = RESULTS + [
        dict(RESULTS[0]),
        {"title": "Bad", "url": "javascript:alert(1)", "snippet": "bad"},
        {"title": "Empty", "url": "https://example.net", "snippet": ""},
    ]
    service = ResearchService(backend=FakeBackend(results))
    with patch(
        "core.research.service.ollama.chat",
        return_value={"role": "assistant", "content": "Supported [1]."},
    ):
        result = service.research("Research it")
    assert len(result.sources) == 2


def test_no_sources_fails_without_calling_model():
    service = ResearchService(backend=FakeBackend([]))
    with patch("core.research.service.ollama.chat") as chat:
        with pytest.raises(ResearchUnavailable, match="No usable online sources"):
            service.research("Research unavailable topic")
    chat.assert_not_called()


def test_connectivity_error_is_explicit():
    service = ResearchService(backend=FakeBackend(error=TimeoutError("offline")))
    with pytest.raises(ResearchUnavailable, match="Search connectivity failed"):
        service.research("Research current news")


def test_save_request_does_not_silently_create_a_file(tmp_path):
    service = ResearchService(backend=FakeBackend(RESULTS))
    with patch(
        "core.research.service.ollama.chat",
        return_value={"role": "assistant", "content": "Evidence [1]."},
    ):
        result = service.research("Research the project and save it to report.md")
    assert "was not automatically saved" in result.report
    assert not (tmp_path / "report.md").exists()


def test_session_routes_research_without_generic_agent_planner():
    session = SessionManager(use_tools=True, system_prompt="Be concise.")
    research_result = ResearchResult(
        query="AI planning",
        report="Grounded report\n\nSources\n[1] Source — https://example.com",
        sources=(ResearchSource("Source", "https://example.com", "Evidence"),),
    )
    with patch("core.research.service.ResearchService.research", return_value=research_result) as research, patch(
        "core.orchestrator.agent_loop.AgentExecutionLoop.run"
    ) as agent:
        response = session.chat("Research AI planning")
    research.assert_called_once()
    agent.assert_not_called()
    assert response == research_result.report


def test_session_returns_honest_message_when_search_is_offline():
    session = SessionManager(use_tools=True, system_prompt="Be concise.")
    with patch(
        "core.research.service.ResearchService.research",
        side_effect=ResearchUnavailable("network offline"),
    ):
        response = session.chat("Research current AI news")
    assert "could not complete grounded web research" in response.lower()
    assert "network offline" in response
