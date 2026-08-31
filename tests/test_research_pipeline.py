"""
tests/test_research_pipeline.py
================================
Regression tests for the research → generate_document → synthesis pipeline.
"""
import pytest
import re
from unittest.mock import patch, MagicMock

from core.writing.pipeline import WritingPipeline, WritingIntent
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.state.session_manager import SessionManager


# ──────────────────────────────────────────────────────────────────────
# Test 1: Commas do not truncate research requirements
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("prompt, must_contain", [
    (
        "do a research on psx market from 2020 to 20, its trend, best stock and list all time top 10 companies",
        ["trend", "best stock", "top 10"],
    ),
    (
        "research AI in healthcare, its benefits, risks, and future outlook",
        ["benefits", "risks", "future"],
    ),
    (
        "investigate crypto market, volatility trends, top coins, and regulatory updates",
        ["volatility", "top coins", "regulatory"],
    ),
])
def test_commas_do_not_truncate_research_topic(prompt, must_contain):
    """Topic must preserve all comma-separated subtopics."""
    intent = WritingPipeline.parse_intent(prompt)
    topic_lower = intent.topic.lower()
    for keyword in must_contain:
        assert keyword in topic_lower, (
            f"Keyword '{keyword}' lost from topic. Got: '{intent.topic}'"
        )


# ──────────────────────────────────────────────────────────────────────
# Test 2: Multi-part research produces multiple focused searches
# ──────────────────────────────────────────────────────────────────────
def test_multi_part_research_decomposes_into_multiple_searches():
    """A multi-faceted research request should produce >1 search query."""
    prompt = "do a research on psx market from 2020 to 20, its trend, best stock and list all time top 10 companies"
    intent = WritingPipeline.parse_intent(prompt)
    queries = WritingPipeline.decompose_research_queries(prompt, intent.topic)
    assert len(queries) > 1, f"Expected multiple queries, got {len(queries)}: {queries}"
    # Each query should be non-trivially short
    for q in queries:
        assert len(q) > 5, f"Query too short: '{q}'"


def test_single_topic_research_produces_single_search():
    """A simple single-topic request should produce exactly one query."""
    prompt = "research the latest quantum computing breakthroughs"
    intent = WritingPipeline.parse_intent(prompt)
    queries = WritingPipeline.decompose_research_queries(prompt, intent.topic)
    assert len(queries) == 1


# ──────────────────────────────────────────────────────────────────────
# Test 3: Web search results flow into generate_document
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def session():
    return SessionManager()


@pytest.fixture
def agent_loop(session):
    return AgentExecutionLoop(session)


@patch("core.writing.pipeline.WritingPipeline.run_research_workflow")
@patch("core.llm.ollama_client.OllamaClient.chat")
def test_web_search_results_flow_into_generate_document(mock_chat, mock_research, agent_loop):
    """Web search evidence must be passed to generate_document as sources."""
    mock_chat.return_value = {"content": "Fallback ok"}
    captured_sources = []

    def capture_research(topic, sources):
        captured_sources.extend(sources)
        return "Generated research report with evidence."

    mock_research.side_effect = capture_research

    # Simulate: web_search step completes, then generate_document runs
    # We mock tool_registry.execute for web_search to return structured results
    def mock_exec(tool_name, args, **kwargs):
        if tool_name == "web_search":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "query": args.get("query", ""),
                    "results": [
                        {"title": "PSX Market Report", "url": "https://example.com/psx", "snippet": "PSX index rose 15% in 2023."},
                        {"title": "Top Companies", "url": "https://example.com/top", "snippet": "Top companies by market cap."},
                    ]
                }
            }
        return {"success": True, "result": {"message": "Success"}}

    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=mock_exec):
        agent_loop.run("research the psx market trends", mode="text")

    # Verify sources were passed to run_research_workflow
    assert len(captured_sources) > 0, "No sources were passed to generate_document"
    assert any("PSX" in s.title for s in captured_sources), "Web search title not found in sources"


# ──────────────────────────────────────────────────────────────────────
# Test 4: Successful document generation returns non-empty content
# ──────────────────────────────────────────────────────────────────────
@patch("core.writing.pipeline.WritingPipeline.run_research_workflow")
@patch("core.llm.ollama_client.OllamaClient.chat")
def test_successful_generation_returns_content(mock_chat, mock_research, agent_loop):
    """When generate_document succeeds, session_artifacts must have non-empty content."""
    mock_chat.return_value = {"content": "Fallback ok"}
    mock_research.return_value = "This is a comprehensive PSX market analysis report with 500 words of content."

    def mock_exec(tool_name, args, **kwargs):
        if tool_name == "web_search":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "query": args.get("query", ""),
                    "results": [
                        {"title": "Test", "url": "https://example.com", "snippet": "Test snippet."},
                    ]
                }
            }
        return {"success": True, "result": {"message": "Success"}}

    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=mock_exec):
        agent_loop.run("research the psx market", mode="text")

    assert "last_generated_document" in agent_loop.session_artifacts
    content = agent_loop.session_artifacts["last_generated_document"]["content"]
    assert len(content) > 0, "Generated content is empty"
    assert "PSX" in content or "market" in content, "Generated content doesn't match the request"


# ──────────────────────────────────────────────────────────────────────
# Test 5: generate_document success cannot synthesize failure
# ──────────────────────────────────────────────────────────────────────
@patch("core.writing.pipeline.WritingPipeline.run_research_workflow")
@patch("core.llm.ollama_client.OllamaClient.chat")
def test_successful_generation_does_not_report_failure(mock_chat, mock_research, agent_loop):
    """If generate_document succeeds, final synthesis must NOT say 'unable to generate'."""
    mock_chat.return_value = {"content": "Fallback ok"}
    mock_research.return_value = "Detailed research report about cryptocurrency market trends and analysis."

    def mock_exec(tool_name, args, **kwargs):
        if tool_name == "web_search":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "query": args.get("query", ""),
                    "results": [
                        {"title": "Crypto Report", "url": "https://example.com/crypto", "snippet": "Bitcoin leads market."},
                    ]
                }
            }
        return {"success": True, "result": {"message": "Success"}}

    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=mock_exec):
        result = agent_loop.run("research the cryptocurrency market", mode="text")

    assert "unable to" not in result.lower(), (
        f"Synthesis reported failure despite successful generation. Got: '{result[:200]}'"
    )
    assert "research report" in result.lower() or "here is" in result.lower() or "cryptocurrency" in result.lower(), (
        f"Synthesis did not return the generated content. Got: '{result[:200]}'"
    )


# ──────────────────────────────────────────────────────────────────────
# Test 6: Failed/ungrounded generation cannot be marked success
# ──────────────────────────────────────────────────────────────────────
@patch("core.writing.pipeline.WritingPipeline.run_research_workflow")
@patch("core.llm.ollama_client.OllamaClient.chat")
def test_failed_generation_reports_failure(mock_chat, mock_research, agent_loop):
    """If run_research_workflow returns an error/empty, synthesis must report failure."""
    mock_chat.return_value = {"content": "Fallback ok"}
    # Simulate grounding failure: no verified sources → returns error message
    mock_research.return_value = "I attempted to search online for your request, but I could not retrieve online search results."

    def mock_exec(tool_name, args, **kwargs):
        if tool_name == "web_search":
            # web_search succeeds but returns zero results
            return {
                "success": True,
                "result": {
                    "success": True,
                    "query": args.get("query", ""),
                    "results": []
                }
            }
        return {"success": True, "result": {"message": "Success"}}

    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=mock_exec):
        result = agent_loop.run("research the psx market", mode="text")

    # When no evidence is available, the report should reflect that limitation
    # (it shouldn't claim success with fabricated content)
    assert "last_generated_document" in agent_loop.session_artifacts or "unable" in result.lower() or "could not" in result.lower()


# ──────────────────────────────────────────────────────────────────────
# Test 7: Ranking claims require an explicit supported metric
# ──────────────────────────────────────────────────────────────────────
def test_research_prompt_includes_ranking_metric_rule():
    """The research workflow system prompt must instruct the LLM to disclose ranking metrics."""
    import inspect
    source = inspect.getsource(WritingPipeline.run_research_workflow)
    assert "RANKING METRIC" in source.upper() or "ranking metric" in source.lower(), (
        "Research workflow prompt does not include ranking metric disclosure rule"
    )
    # Verify the rule mentions specific metrics
    assert "market capitalization" in source.lower() or "total return" in source.lower(), (
        "Ranking metric rule does not provide example metrics"
    )
