import pytest
from unittest.mock import patch, MagicMock
from core.tools.web_search import DuckDuckGoLiteProvider, DuckDuckGoHTMLProvider

class MockResponse:
    def __init__(self, text, status_code):
        self.text = text
        self.status_code = status_code
        self.content = text.encode("utf-8")

def test_ddg_lite_provider_success():
    provider = DuckDuckGoLiteProvider()
    mock_html = """
    <html><body>
    <table>
        <tr>
            <td><a class="result-link" href="https://example.com/ai">AI Overview</a></td>
        </tr>
        <tr>
            <td class="result-snippet">This is an AI summary snippet.</td>
        </tr>
    </table>
    </body></html>
    """
    with patch("requests.post", return_value=MockResponse(mock_html, 200)) as mock_post:
        results = provider.search("AI uses")
        assert len(results) == 1
        assert results[0]["title"] == "AI Overview"
        assert results[0]["url"] == "https://example.com/ai"
        assert results[0]["snippet"] == "This is an AI summary snippet."
        mock_post.assert_called_once()

def test_ddg_lite_provider_bot_challenge():
    provider = DuckDuckGoLiteProvider()
    with patch("requests.post", return_value=MockResponse("Bot Challenge", 202)):
        results = provider.search("AI uses")
        assert len(results) == 0

def test_ddg_html_provider_success():
    provider = DuckDuckGoHTMLProvider()
    mock_html = """
    <html><body>
    <div class="result__body">
        <a class="result__a">HTML Search Result Title</a>
        <a class="result__snippet">HTML snippet content here.</a>
        <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fhtml&rut=...">URL</a>
    </div>
    </body></html>
    """
    with patch("requests.get", return_value=MockResponse(mock_html, 200)) as mock_get:
        results = provider.search("HTML search")
        assert len(results) == 1
        assert results[0]["title"] == "HTML Search Result Title"
        assert results[0]["url"] == "https://example.com/html"
        assert results[0]["snippet"] == "HTML snippet content here."
        mock_get.assert_called_once()

def test_ddg_html_provider_bot_challenge():
    provider = DuckDuckGoHTMLProvider()
    with patch("requests.get", return_value=MockResponse("Bot Challenge", 202)):
        results = provider.search("HTML search")
        assert len(results) == 0
