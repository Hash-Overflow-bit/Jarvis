import pytest
import sys
import io
from pathlib import Path
from unittest.mock import patch

from core.orchestrator.agent_loop import AgentExecutionLoop
from core.state.session_manager import SessionManager
from core.config import settings

class BadEncoderStream(io.StringIO):
    """A mock stdout stream that crashes if anything outside ASCII/CP1252 is printed."""
    def write(self, s):
        # Simulate a CP1252 encode failure for emojis or special unicode
        try:
            s.encode('cp1252') 
        except UnicodeEncodeError as e:
            sys.stderr.write(f"FAILED TO ENCODE: {repr(s)}\n")
            raise e
        return super().write(s)

def test_encoding_failure_does_not_abort_execution(tmp_path):
    """
    Test that even if print() fails with a UnicodeEncodeError (simulating a 
    Windows console encoding failure), the execution workflow continues safely.
    """
    loop = AgentExecutionLoop(use_tools=True)
    
    # We patch settings to use our tmp_path workspace
    with patch.object(settings.__class__, 'default_workspace_dir', property(lambda self: tmp_path)):
        
        # We patch sys.stdout with our BadEncoderStream which crashes on emojis.
        # But wait, we just added sys.stdout.reconfigure(errors='replace') to config.py.
        # However, that only works if stdout *can* be reconfigured and hasn't been replaced.
        # Here we simulate the *actual* print function throwing an error, or we verify that 
        # the system doesn't produce emojis that would crash CP1252 anyway.
        # Wait, the user requirement says: "Add regression tests simulating a CP1252/non-UTF-8 output stream"
        
        bad_stream = BadEncoderStream()
        
        with patch('sys.stdout', bad_stream):
            prompt = "Read the local system prompt files in the configured workspace, summarize the core instructions in exactly three bullet points, and create test_summary.md in that workspace."
            
            # We mock ollama.chat to return a JSON plan with 3 steps
            mock_plan = f'''```json
[
    {{"step": 1, "tool": "read_file", "arguments": {{"filepath": "{(tmp_path / 'system_prompt.txt').as_posix()}"}}}},
    {{"step": 2, "tool": "generate_document", "arguments": {{"intent": {{"task_type": "research_write", "topic": "summarize system prompt in exactly three bullet points", "sources_required": true, "source_files": ["system_prompt.txt"]}}}}}},
    {{"step": 3, "tool": "write_file", "arguments": {{"filepath": "{(tmp_path / 'test_summary.md').as_posix()}", "content": "<USE_GENERATED_ARTIFACT>"}}}}
]
```'''

            def mock_chat(*args, **kwargs):
                if kwargs.get('format') == 'json' or 'format' in kwargs and kwargs['format'] == 'json':
                    return {'content': mock_plan}
                return {'content': "- Always be helpful\n- Keep it concise\n- Use bullet points"}

            sys_prompt = tmp_path / "system_prompt.txt"
            sys_prompt.write_text("Rule 1: Always be helpful.\\nRule 2: Keep it concise.\\nRule 3: Use bullet points.\\n")

            with patch('core.orchestrator.agent_loop.ollama.chat', side_effect=mock_chat):
                loop.run(prompt, mode="text")
                
            expected_file = tmp_path / "test_summary.md"
            assert expected_file.exists(), "test_summary.md was not created! Execution aborted."
            
            content = expected_file.read_text().strip()
            assert content != "", "Created file is empty!"
