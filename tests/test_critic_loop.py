import unittest
from unittest.mock import patch, MagicMock
from core.orchestrator.agent_loop import AgentExecutionLoop


class TestCriticLoop(unittest.TestCase):
    """
    Unit tests to verify the pre-execution Critic loop (Gauntlet) in Jarvis.
    """

    @patch("core.orchestrator.agent_loop.ollama.chat")
    def test_criticize_plan_success(self, mock_chat):
        # Mock LLM to return a revised plan where steps are logically sorted or corrected
        mock_response = {
            "content": '{"reasoning": "Plan needs correction", "plan": [{"step": 1, "tool": "create_directory", "arguments": {"directory": "/workspace/test"}}, {"step": 2, "tool": "write_file", "arguments": {"file_path": "/workspace/test/file.txt", "content": "hello"}}]}'
        }
        mock_chat.return_value = mock_response

        loop = AgentExecutionLoop()
        proposed_plan = [
            {"step": 1, "tool": "write_file", "arguments": {"file_path": "/workspace/test/file.txt", "content": "hello"}},
            {"step": 2, "tool": "create_directory", "arguments": {"directory": "/workspace/test"}}
        ]
        
        # Run Critic review
        criticized_plan = loop._criticize_plan("Create folder and write file", proposed_plan)
        
        # Verify the plan was corrected and returned in order
        self.assertEqual(len(criticized_plan), 2)
        self.assertEqual(criticized_plan[0]["tool"], "create_directory")
        self.assertEqual(criticized_plan[1]["tool"], "write_file")

    @patch("core.orchestrator.agent_loop.ollama.chat")
    def test_criticize_plan_fallback(self, mock_chat):
        # Mock LLM failing or returning invalid output
        mock_chat.side_effect = Exception("Ollama error")

        loop = AgentExecutionLoop()
        proposed_plan = [
            {"step": 1, "tool": "write_file", "arguments": {"file_path": "/workspace/test/file.txt", "content": "hello"}}
        ]
        
        # Run Critic review
        criticized_plan = loop._criticize_plan("Write file", proposed_plan)
        
        # Verify that it gracefully falls back to the original plan on failure
        self.assertEqual(criticized_plan, proposed_plan)
