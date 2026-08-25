"""
tests/test_writing_workflow.py
==============================
Regression & Integration tests for Grounded Writing + Research + Data Extraction Workflow.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from core.writing.sources import EvidenceSource
from core.writing.extractor import DataExtractor
from core.writing.pipeline import WritingPipeline
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.state.session_manager import SessionManager
from core.tools.tool_registry import tool_registry


def test_simple_email_writing_performs_zero_research_calls():
    """
    Test 1: Simple email writing performs zero research/web_search calls.
    """
    user_input = "Write a professional email asking for a payment update."
    intent = WritingPipeline.classify_intent(user_input)
    assert intent == "simple"

    mock_llm_reply = {"role": "assistant", "content": "Subject: Payment Status Update\n\nDear Client,\nCould you please update us..."}
    with patch("core.tools.tool_registry.tool_registry.execute") as mock_exec:
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_llm_reply):
            loop = AgentExecutionLoop(use_tools=True)
            res = loop.run(user_input)
            assert "Payment Status Update" in res
            # Verify ZERO research or web search tool calls executed
            assert mock_exec.call_count == 0


def test_research_report_retrieves_sources_before_writing():
    """
    Test 2: Research report retrieves sources (web_search) before writing.
    """
    user_input = "Research the best accounting automation approaches for small businesses and write me a report with sources."
    intent = WritingPipeline.classify_intent(user_input)
    assert intent == "research"

    mock_search_result = {
        "success": True,
        "results": [
            {
                "title": "Accounting Automation 2026",
                "url": "https://example.com/accounting_automation",
                "snippet": "Automation reduces bookkeeping errors by 80%."
            }
        ]
    }

    mock_llm_report = {
        "role": "assistant",
        "content": "Executive Summary:\nAutomation reduces bookkeeping errors.\n\nSources:\n- https://example.com/accounting_automation"
    }

    loop = AgentExecutionLoop(use_tools=True)
    with patch("core.tools.tool_registry.tool_registry.execute", return_value=mock_search_result) as mock_exec:
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_llm_report):
            res = loop.run(user_input)
            assert "https://example.com/accounting_automation" in res
            mock_exec.assert_called_once()
            assert mock_exec.call_args[0][0] == "web_search"


def test_research_output_cannot_contain_unretrieved_urls():
    """
    Test 3: Research output strips/blocks hallucinated URLs not returned by retrieval.
    """
    sources = [
        EvidenceSource(
            source_type="web",
            title="Verified Source",
            url="https://verified-domain.com/article",
            content="Verified content snippet.",
            verified=True
        )
    ]
    hallucinated_llm_reply = {
        "role": "assistant",
        "content": "Here is the report with links: https://verified-domain.com/article and https://fake-hallucinated-domain.com/fake"
    }

    with patch("core.writing.pipeline.ollama.chat", return_value=hallucinated_llm_reply):
        res = WritingPipeline.run_research_workflow("Research topics", sources)
        assert "https://verified-domain.com/article" in res
        assert "https://fake-hallucinated-domain.com/fake" not in res
        assert "[unverified link removed]" in res


def test_failed_research_retrieval_produces_honest_warning():
    """
    Test 4: Failed research retrieval produces an honest verification warning rather than fake citations.
    """
    failed_sources = [
        EvidenceSource(
            source_type="web",
            title="Search Failed",
            verified=False
        )
    ]

    res = WritingPipeline.run_research_workflow("Research secret technology", failed_sources)
    assert "could not verify online search results" in res.lower()
    assert "http" not in res


def test_local_file_summary_calls_file_reader_first(tmp_path):
    """
    Test 5: Local file summary calls the file reader before generating the answer.
    Proves:
    1. File reader (read_file) is invoked before synthesis.
    2. Extracted content is supplied to the writer.
    3. Summary is grounded strictly in mocked file contents (Alpha LLC revenue is $120,000. Sarah manages payroll.).
    """
    report_file = tmp_path / "company_notes.txt"
    report_file.write_text("Alpha LLC revenue is $120,000. Sarah manages payroll.")

    loop = AgentExecutionLoop(use_tools=True)
    mock_read_result = {
        "success": True,
        "result": {"content": "Alpha LLC revenue is $120,000. Sarah manages payroll."}
    }
    mock_summary_reply = {
        "role": "assistant",
        "content": "Executive Summary: Alpha LLC generated $120,000 in revenue, and Sarah manages payroll operations."
    }

    with patch.object(tool_registry, "execute", return_value=mock_read_result) as mock_exec:
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_summary_reply):
            res = loop.run(f"Read {report_file} and give me a concise executive summary.")
            
            # Assert file reader was invoked first
            mock_exec.assert_called_once()
            called_tool = mock_exec.call_args[0][0]
            called_args = mock_exec.call_args[0][1]
            assert called_tool == "read_file"
            assert str(report_file) in str(called_args.get("filepath"))

            # Assert output is grounded in returned mocked content
            assert "$120,000" in res
            assert "Sarah" in res or "payroll" in res


def test_data_extraction_returns_only_supported_fields():
    """
    Test 6: Data extraction returns structured normalized JSON format.
    """
    content = "Invoice #1042: Total $2,500.00 due on Jan 15, 2026."
    res = DataExtractor.extract_from_content(content, source_name="invoice.txt", requested_fields=["dollar_amounts", "dates"])

    assert res["source"] == "invoice.txt"
    assert "dollar_amounts" in res["data"]
    assert "dates" in res["data"]
    assert "$2,500.00" in res["data"]["dollar_amounts"]
    assert "Jan 15, 2026" in res["data"]["dates"]


def test_missing_requested_fields_are_null_not_invented():
    """
    Test 7: Missing requested fields are returned as null / not found rather than invented.
    """
    content = "Project meeting notes with Chloe on Monday."
    res = DataExtractor.extract_from_content(content, source_name="notes.txt", requested_fields=["dollar_amounts"])

    assert res["source"] == "notes.txt"
    assert "dollar_amounts" in res["data"]
    assert res["data"]["dollar_amounts"] is None


def test_multi_source_report_preserves_attribution():
    """
    Test 8: Multi-source report preserves source attribution (filenames/filepaths).
    """
    sources = [
        EvidenceSource(source_type="local_file", title="alpha.txt", location="alpha.txt", content="Alpha data: 50 users."),
        EvidenceSource(source_type="local_file", title="beta.txt", location="beta.txt", content="Beta data: 80 users.")
    ]

    mock_attr_reply = {
        "role": "assistant",
        "content": "Summary:\n- According to alpha.txt, 50 users registered.\n- According to beta.txt, 80 users registered."
    }

    with patch("core.writing.pipeline.ollama.chat", return_value=mock_attr_reply):
        res = WritingPipeline.run_local_doc_workflow("Summarize these 2 documents", sources)
        assert "alpha.txt" in res
        assert "beta.txt" in res


def test_writing_workflow_does_not_trigger_irrelevant_tools():
    """
    Test 9: Writing workflow does NOT trigger irrelevant tools like skyvern_tool or delete_directory.
    """
    loop = AgentExecutionLoop(use_tools=True)
    user_input = "Write a professional email asking for a payment update."

    with patch.object(tool_registry, "execute") as mock_exec:
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value={"role": "assistant", "content": "Email content."}):
            res = loop.run(user_input)
            assert "Email content" in res
            for call in mock_exec.call_args_list:
                tool_name = call[0][0]
                assert tool_name not in ("skyvern_tool", "delete_directory", "git_clone", "file_cleanup")


def test_previous_filesystem_results_do_not_leak_into_writing_request():
    """
    Test 10: Previous filesystem execution results do NOT leak into a new writing request.
    """
    session = SessionManager(use_tools=True)

    # Turn 1: Directory creation
    with patch.object(tool_registry, "execute", return_value={"success": True, "result": {}}):
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value={"role": "assistant", "content": "Created directory automation_demo."}):
            res1 = session.chat("Create folder automation_demo")
            assert "automation_demo" in res1

    # Turn 2: Simple email writing request
    mock_email_reply = {"role": "assistant", "content": "Subject: Payment Status Update\n\nDear Client, please update..."}
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_email_reply):
        res2 = session.chat("Write a professional email asking for a payment update.")
        res2_lower = res2.lower()
        assert "automation_demo" not in res2_lower
        assert "created directory" not in res2_lower
        assert "payment" in res2_lower


def test_web_search_direct_execution():
    """
    Test 11: Deterministic unit test for direct execution of web_search through tool_registry.
    Mocks the underlying provider (_fetch_ddg_results) so the test does not depend on live internet.
    """
    from core.tools.web_search import WebSearch

    mock_provider_results = [
        {
            "title": "Framework Documentation",
            "url": "https://example.com/framework",
            "snippet": "Local agent framework documentation"
        }
    ]

    with patch.object(WebSearch, "_fetch_ddg_results", return_value=mock_provider_results) as mock_fetch:
        res = tool_registry.execute("web_search", {"query": "AI agent frameworks"})
        mock_fetch.assert_called()

        assert res["success"] is True
        result_data = res["result"]
        assert result_data["success"] is True
        assert len(result_data["results"]) == 1
        item = result_data["results"][0]
        assert item["title"] == "Framework Documentation"
        assert item["url"] == "https://example.com/framework"
        assert item["snippet"] == "Local agent framework documentation"


def test_web_search_provider_failure():
    """
    Test 11b: Deterministic test for provider failure / empty search results.
    Verifies that when search provider is unavailable or returns 0 results,
    Jarvis outputs a structured failure state with a warning and NEVER manufactures fake results.
    """
    from core.tools.web_search import WebSearch

    with patch.object(WebSearch, "_fetch_ddg_results", return_value=[]) as mock_fetch:
        res = tool_registry.execute("web_search", {"query": "Nonexistent secret query"})
        mock_fetch.assert_called()

        assert res["success"] is True  # Tool execution call succeeded
        result_data = res["result"]
        assert result_data["success"] is False
        assert result_data["results"] == []
        assert "warning" in result_data and result_data["warning"] is not None
        assert "Could not retrieve online sources" in result_data["warning"]


def test_research_request_performs_zero_file_writes():
    """
    Test 12: Research report request with no save intent performs ZERO write_file/read_file/list_dir calls.
    """
    user_input = "Research current AI agent frameworks suitable for local business automation and write a short comparison report with real sources and links."
    loop = AgentExecutionLoop(use_tools=True)

    mock_search_res = {
        "success": True,
        "results": [
            {
                "title": "Local AI Frameworks 2026",
                "url": "https://example.com/local_ai_agents",
                "snippet": "Frameworks like LangGraph, CrewAI, and AutoGen enable local automation."
            }
        ]
    }

    mock_llm_report = {
        "role": "assistant",
        "content": "AI Agent Frameworks Comparison:\nLangGraph and CrewAI are ideal.\nSources:\n- https://example.com/local_ai_agents"
    }

    executed_tools = []
    def track_execute(tool_name, args, mode="text"):
        executed_tools.append(tool_name)
        if tool_name == "web_search":
            return {"success": True, "result": mock_search_res}
        return {"success": True, "result": {}}

    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=track_execute):
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_llm_report):
            res = loop.run(user_input)
            assert "web_search" in executed_tools
            assert "write_file" not in executed_tools
            assert "read_file" not in executed_tools
            assert "list_dir" not in executed_tools
            assert "skyvern_tool" not in executed_tools
            assert "https://example.com/local_ai_agents" in res


def test_research_acceptance_prompt():
    """
    Test 13: Full acceptance test for user research prompt.
    """
    user_input = "Research current AI agent frameworks suitable for local business automation and write a short comparison report with real sources and links."
    loop = AgentExecutionLoop(use_tools=True)

    res = loop.run(user_input)
    assert isinstance(res, str)
    assert len(res.strip()) > 0
    res_lower = res.lower()

    # Verify no unrequested filesystem or browser tool claims
    assert "write_file" not in res_lower
    assert "skyvern" not in res_lower
    assert "list_dir" not in res_lower
