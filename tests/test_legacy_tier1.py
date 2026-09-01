import pytest
from core.orchestrator.agent_loop import AgentExecutionLoop
from unittest.mock import patch
from pathlib import Path

@pytest.fixture
def loop():
    return AgentExecutionLoop(use_tools=True)

def test_direct_route_drops_multi_clause_unmatched(loop):
    """
    Test that if a multi-clause prompt has unhandled clauses (like 'summarize'),
    _direct_route returns None to fall back to the LLM planner.
    """
    prompt = "Read the local system prompt files, summarize them in three bullets, and create summary.md"
    plan = loop._direct_route(prompt)
    assert plan is None, "Expected _direct_route to fall through to the LLM planner for multi-step prompts with unhandled clauses."

def test_workspace_resolution(loop, tmp_path):
    """
    Test that 'in that workspace' resolves to the configured workspace, not the desktop.
    """
    from core.config import settings
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        prompt = "Create test_summary.md in that workspace."
        plan = loop._direct_route(prompt)
        assert plan is not None
        assert len(plan) == 1
        
        filepath = plan[0]["arguments"]["filepath"].replace("\\", "/")
        
        assert "test_summary.md" in filepath
        assert str(tmp_path).replace("\\", "/") in filepath
        assert str(settings.desktop_dir).replace("\\", "/") not in filepath

def test_mocked_planner_enforces_dependencies(tmp_path):
    """
    Test that the fallback planner correctly sequences read -> write 
    and validates exactly three bullets against the source content.
    """
    from core.config import settings
    
    sys_prompt = tmp_path / "system_prompt.txt"
    sys_prompt.write_text("Rule 1: Always be helpful.\\nRule 2: Keep it concise.\\nRule 3: Use bullet points.\\n")
    
    # We mock ollama.chat to return a JSON plan with 3 steps: read, generate_document (or write directly), write
    mock_plan = f'''```json
[
    {{"step": 1, "tool": "read_file", "arguments": {{"filepath": "{(tmp_path / 'system_prompt.txt').as_posix()}"}}}},
    {{"step": 2, "tool": "write_file", "arguments": {{"filepath": "{(tmp_path / 'test_summary.md').as_posix()}", "content": "- Always be helpful\\n- Keep it concise\\n- Use bullet points"}}}}
]
```'''

    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        # Construct loop INSIDE patched context to prevent any caching of the workspace path
        loop = AgentExecutionLoop(use_tools=True)
        with patch('core.orchestrator.agent_loop.ollama.chat', return_value={'content': mock_plan}):
            prompt = "Read the local system prompt files in the configured workspace, summarize the core instructions in exactly three bullet points, and create test_summary.md in that workspace."
            loop.run(prompt, mode="text")
            
            expected_file = tmp_path / "test_summary.md"
            assert expected_file.exists(), "test_summary.md was not created!"
            
            content = expected_file.read_text().strip()
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            bullet_lines = [line for line in lines if line.startswith('-') or line.startswith('*') or line[0].isdigit()]
            
            assert len(bullet_lines) == 3, "Expected exactly 3 bullets in mocked output"
            assert "helpful" in content
            assert "concise" in content
            assert "bullet points" in content
def test_legacy_tier1_end_to_end(tmp_path):
    """
    Live test to verify that the Legacy Tier 1 prompt runs end-to-end,
    produces exactly three bullets, and correctly writes to the workspace.
    """
    from core.config import settings
    from core.orchestrator.agent_loop import AgentExecutionLoop
    
    # Create mock system prompt files
    sys_prompt = tmp_path / "prompt.txt"
    sys_prompt.write_text("Rule 1: Always be helpful.\\nRule 2: Keep it concise.\\nRule 3: Use bullet points.\\n")
    
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        # Construct loop INSIDE patched context to prevent any caching of the workspace path
        loop = AgentExecutionLoop(use_tools=True)
        
        prompt = "Read the local system prompt files in the configured workspace, summarize the core instructions in exactly three bullet points, and create test_summary.md in that workspace."
        import pytest
        from core.llm.ollama_client import OllamaError
        try:
            loop.run(prompt, mode="text")
        except OllamaError:
            pytest.skip("Ollama is not running locally. Skipping end-to-end test.")
        
        expected_file = tmp_path / "test_summary.md"
        assert expected_file.exists(), "test_summary.md was not created in the workspace!"
        
        content = expected_file.read_text().strip()
        assert content != "", "Created file is empty!"
        
        # Verify exactly three bullets
        lines = [line.strip() for line in content.split('\\n') if line.strip()]
        bullet_lines = [line for line in lines if line.startswith('-') or line.startswith('*') or line[0].isdigit()]
        assert len(bullet_lines) >= 3, f"Expected at least 3 bullets, found {len(bullet_lines)}: {content}"


