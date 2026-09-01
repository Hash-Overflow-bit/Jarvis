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
    and validates <USE_GENERATED_ARTIFACT> against the source content.
    We use a prompt that DOES NOT match the Tier 1 direct route regex.
    """
    from core.config import settings
    
    sys_prompt = tmp_path / "system_prompt.txt"
    sys_prompt.write_text("Rule 1: Always be helpful.\\nRule 2: Keep it concise.\\nRule 3: Use bullet points.\\n")
    
    mock_plan = f'''```json
[
    {{"step": 1, "tool": "read_file", "arguments": {{"filepath": "{(tmp_path / 'system_prompt.txt').as_posix()}"}}}},
    {{"step": 2, "tool": "generate_document", "arguments": {{"intent": {{"task_type": "research_write", "topic": "summarize", "sources_required": true, "source_files": ["system_prompt.txt"]}}}}}},
    {{"step": 3, "tool": "write_file", "arguments": {{"filepath": "{(tmp_path / 'some_other_file.md').as_posix()}", "content": "<USE_GENERATED_ARTIFACT>"}}}}
]
```'''

    def mock_chat(*args, **kwargs):
        # If it's a JSON request for the planner
        if kwargs.get('format') == 'json' or 'format' in kwargs and kwargs['format'] == 'json':
            return {'content': mock_plan}
        # Otherwise it's the document generator
        return {'content': "- Always be helpful\n- Keep it concise\n- Use bullet points"}

    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        # Construct loop INSIDE patched context to prevent any caching of the workspace path
        loop = AgentExecutionLoop(use_tools=True)
        with patch('core.orchestrator.agent_loop.ollama.chat', side_effect=mock_chat):
            prompt = "Read system_prompt.txt and save a summary to some_other_file.md"
            loop.run(prompt, mode="text")
            
            expected_file = tmp_path / "some_other_file.md"
            assert expected_file.exists(), "some_other_file.md was not created!"
            
            content = expected_file.read_text().strip()
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            bullet_lines = [line for line in lines if line.startswith('-') or line.startswith('*') or line[0].isdigit()]
            
            assert len(bullet_lines) == 3, "Expected exactly 3 bullets in mocked output"
            assert "helpful" in content
            assert "concise" in content
            assert "bullet points" in content

def test_legacy_tier1_end_to_end(tmp_path):
    """
    Live test to verify that the Legacy Tier 1 prompt runs end-to-end (via direct route),
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
        
        result = loop.run(prompt, mode="text")
        if isinstance(result, str) and ("LLM generation failed" in result or "ConnectionRefused" in result or "Max retries exceeded" in result):
            pytest.skip("Ollama is not running locally. Skipping end-to-end test.")
            
        expected_file = tmp_path / "test_summary.md"
        assert expected_file.exists(), "test_summary.md was not created in the workspace!"
        
        content = expected_file.read_text().strip()
        assert content != "", "Created file is empty!"
        
        # Verify exactly three bullets
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        bullet_lines = [line for line in lines if line.startswith('-') or line.startswith('*') or line[0].isdigit()]
        assert len(bullet_lines) == 3, f"Expected exactly 3 bullets, found {len(bullet_lines)}: {content}"



