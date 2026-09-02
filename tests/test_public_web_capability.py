from unittest.mock import Mock, patch

from core.orchestrator.agent_loop import AgentExecutionLoop
from core.tools.public_web import FetchURL, FetchURLInput, OpenURL, OpenURLInput


def _public_dns(*_args, **_kwargs):
    return [(None, None, None, None, ("93.184.216.34", 0))]


def test_open_url_uses_default_browser_only_for_public_https_url():
    with patch("core.tools.public_web.socket.getaddrinfo", side_effect=_public_dns), patch("core.tools.public_web.webbrowser.open", return_value=True) as open_browser:
        result = OpenURL().run(OpenURLInput(url="https://example.com/docs"))
    assert result.success
    open_browser.assert_called_once_with("https://example.com/docs", new=2)


def test_public_web_blocks_local_urls_before_fetch_or_open():
    with patch("core.tools.public_web.requests.get") as get_page, patch("core.tools.public_web.webbrowser.open") as open_browser:
        fetched = FetchURL().run(FetchURLInput(url="http://127.0.0.1:8000/admin"))
        opened = OpenURL().run(OpenURLInput(url="http://localhost:8000"))
    assert not fetched.success and "private" in fetched.warning
    assert not opened.success and "private" in opened.message
    get_page.assert_not_called()
    open_browser.assert_not_called()


def test_fetch_url_returns_real_evidence_fields_and_strips_scripts():
    response = Mock(status_code=200, url="https://example.com/article", headers={"content-type": "text/html"})
    response.text = "<html><head><title>Example Article</title></head><body><script>secret()</script><h1>Evidence</h1><p>Verified public text.</p></body></html>"
    response.raise_for_status = Mock()
    with patch("core.tools.public_web.socket.getaddrinfo", side_effect=_public_dns), patch("core.tools.public_web.requests.get", return_value=response):
        result = FetchURL().run(FetchURLInput(url="https://example.com/article"))
    assert result.success
    assert result.title == "Example Article"
    assert result.final_url == "https://example.com/article"
    assert "Verified public text." in result.excerpt and "secret" not in result.excerpt
    assert result.retrieved_at


def test_direct_route_uses_open_for_open_and_fetch_for_reading():
    loop = AgentExecutionLoop()
    assert loop._direct_route("Open https://example.com") == [{"step": 1, "tool": "open_url", "arguments": {"url": "https://example.com"}}]
    assert loop._direct_route("Read https://example.com and summarize it") == [{"step": 1, "tool": "fetch_url", "arguments": {"url": "https://example.com"}}]
