"""End-to-end tests for the bounded sub-agent public-URL instruction flow."""

from unittest.mock import patch

from core.config import settings
from core.orchestrator.agent_registry import agent_registry
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.orchestrator.subagent_runner import LocalSubagent
from core.tools.delegate_task import DelegateTask, DelegateTaskInput


def _public_dns(*_args, **_kwargs):
    return [(None, None, None, None, ("93.184.216.34", 0))]


def _browser_agent():
    return LocalSubagent(
        "BrowserReviewAgent",
        "Reviewed URL launcher",
        "Open only user-reviewed public URLs from a workspace file",
        "",
        ("open_public_urls",),
    )


def test_browser_subagent_opens_only_explicit_workspace_urls(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instruction_file = workspace / "browser_urls.txt"
    instruction_file.write_text(
        "# Reviewed links\nOPEN https://example.com/docs\nOPEN https://www.python.org\n",
        encoding="utf-8",
    )
    agent_registry._agents.clear()
    agent_registry.register("BrowserReviewAgent", _browser_agent(), ["open_public_urls"])

    with patch.object(
        settings.__class__, "default_workspace_dir", property(lambda _self: workspace)
    ), patch(
        "core.tools.public_web.socket.getaddrinfo", side_effect=_public_dns
    ), patch(
        "core.tools.public_web.webbrowser.open", return_value=True
    ) as open_browser:
        result = DelegateTask().run(
            DelegateTaskInput(
                agent_name="BrowserReviewAgent",
                task_description="Open public URLs listed in browser_urls.txt",
                expected_output="confirmation",
            )
        )

    assert result.success
    assert "Opened 2 reviewed public URL(s)" in result.result
    assert [call.args[0] for call in open_browser.call_args_list] == [
        "https://example.com/docs", "https://www.python.org",
    ]


def test_browser_subagent_rejects_untrusted_instruction_lines(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "browser_urls.txt").write_text(
        "OPEN https://example.com\nOPEN https://example.com/login and submit\n",
        encoding="utf-8",
    )
    agent_registry._agents.clear()
    agent_registry.register("BrowserReviewAgent", _browser_agent(), ["open_public_urls"])

    with patch.object(
        settings.__class__, "default_workspace_dir", property(lambda _self: workspace)
    ), patch(
        "core.tools.public_web.socket.getaddrinfo", side_effect=_public_dns
    ), patch("core.tools.public_web.webbrowser.open") as open_browser:
        result = DelegateTask().run(
            DelegateTaskInput(
                agent_name="BrowserReviewAgent",
                task_description="Open public URLs listed in browser_urls.txt",
                expected_output="confirmation",
            )
        )

    assert not result.success
    assert "Invalid instruction" in result.error
    open_browser.assert_not_called()


def test_browser_subagent_requires_explicit_instruction_file_task():
    agent_registry._agents.clear()
    agent_registry.register("BrowserReviewAgent", _browser_agent(), ["open_public_urls"])
    with patch("core.orchestrator.subagent_runner.OllamaClient.chat") as model:
        result = DelegateTask().run(
            DelegateTaskInput(
                agent_name="BrowserReviewAgent",
                task_description="Open Google and find the best price.",
                expected_output="result",
            )
        )

    assert not result.success
    assert "reasoning-only" in result.error
    model.assert_not_called()


def test_browser_subagent_routes_from_user_instruction_to_mediated_opener(tmp_path):
    """The main loop delegates the explicit file instruction without an LLM plan."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "browser_urls.txt").write_text("OPEN https://example.com\n", encoding="utf-8")
    agent_registry._agents.clear()
    agent_registry.register("BrowserReviewAgent", _browser_agent(), ["open_public_urls"])

    with patch.object(
        settings.__class__, "default_workspace_dir", property(lambda _self: workspace)
    ), patch(
        "core.tools.public_web.socket.getaddrinfo", side_effect=_public_dns
    ), patch("core.tools.public_web.webbrowser.open", return_value=True) as open_browser:
        response = AgentExecutionLoop(use_tools=True).run(
            "Have BrowserReviewAgent open public URLs listed in browser_urls.txt",
            mode="text",
        )

    assert "Opened 1 reviewed public URL" in response
    open_browser.assert_called_once_with("https://example.com", new=2)
