"""
tests/test_skyvern_tool.py
===========================
Unit tests for the SkyvernTool browser automation bridge.
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from core.tools.skyvern_tool import SkyvernTool
from schemas.skyvern_schema import SkyvernTaskInput, SkyvernTaskOutput


def test_skyvern_schema_validation():
    input_data = SkyvernTaskInput(
        url="https://quotes.toscrape.com",
        navigation_goal="Extract top quotes and author names",
        extracted_fields=["quote", "author"]
    )
    assert input_data.url == "https://quotes.toscrape.com"
    assert input_data.extracted_fields == ["quote", "author"]


def test_skyvern_tool_offline_fallback():
    tool = SkyvernTool()
    input_data = SkyvernTaskInput(
        url="https://offline.portal.example.com",
        navigation_goal="Test offline handling"
    )
    
    with patch.dict("os.environ", {"SKYVERN_BASE_URL": "http://localhost:9999/api/v1"}):
        res = tool.run(input_data)
        assert isinstance(res, SkyvernTaskOutput)
        assert res.success is False
        assert res.status == "unreachable"
        assert "unreachable or offline" in res.message


def test_skyvern_tool_mock_success():
    tool = SkyvernTool()
    input_data = SkyvernTaskInput(
        url="https://portal.example.com",
        navigation_goal="Download August Invoice PDF",
        extracted_fields=["invoice_number", "total"]
    )

    mock_post_resp = MagicMock()
    mock_post_resp.__enter__.return_value = mock_post_resp
    mock_post_resp.read.return_value = json.dumps({"task_id": "skyvern-123", "status": "created"}).encode("utf-8")

    mock_get_resp = MagicMock()
    mock_get_resp.__enter__.return_value = mock_get_resp
    mock_get_resp.read.return_value = json.dumps({
        "status": "completed",
        "extracted_information": {"invoice_number": "INV-2026-08", "total": "$1,250.00"},
        "downloaded_files": ["/Users/m2air/Desktop/invoice_august.pdf"]
    }).encode("utf-8")

    def mock_urlopen(req, timeout=10):
        if req.get_method() == "POST":
            return mock_post_resp
        return mock_get_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = tool.run(input_data)
        assert res.success is True
        assert res.task_id == "skyvern-123"
        assert res.status == "completed"
        assert res.extracted_data == {"invoice_number": "INV-2026-08", "total": "$1,250.00"}
        assert res.downloaded_files == ["/Users/m2air/Desktop/invoice_august.pdf"]
