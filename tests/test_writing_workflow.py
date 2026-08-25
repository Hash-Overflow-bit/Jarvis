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
    """
    report_file = tmp_path / "report.txt"
    report_file.write_text("Q1 Revenue reached $100,000 with 15% growth.")

    loop = AgentExecutionLoop(use_tools=True)
    mock_read_result = {"success": True, "result": {"content": "Q1 Revenue reached $100,000 with 15% growth."}}
    mock_summary_reply = {"role": "assistant", "content": "Executive Summary: Q1 Revenue was $100,000."}

    with patch("core.tools.tool_registry.tool_registry.execute", return_value=mock_read_result) as mock_exec:
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_summary_reply):
            res = loop.run(f"Read {report_file} and give me an executive summary.")
            assert "Q1 Revenue" in res
            mock_exec.assert_called_once()
            assert mock_exec.call_args[0][0] == "read_file"


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

    with patch("core.tools.tool_registry.tool_registry.execute") as mock_exec:
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
    with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": True, "result": {}}):
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
