import pytest
from unittest.mock import patch, MagicMock
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.tools.tool_registry import tool_registry

@pytest.fixture
def mock_search_fail():
    with patch.object(tool_registry, 'execute') as mock_exec:
        def side_effect(tool_name, args, **kwargs):
            if tool_name == "web_search":
                return {"success": False, "error": "Network timeout"}
            return {"success": True, "result": {}}
        mock_exec.side_effect = side_effect
        yield mock_exec

@pytest.fixture
def mock_search_success():
    with patch.object(tool_registry, 'execute') as mock_exec:
        def side_effect(tool_name, args, **kwargs):
            if tool_name == "web_search":
                return {"success": True, "result": {"results": [{"title": "Test", "url": "http://test.com", "snippet": "Info"}]}}
            elif tool_name == "write_file":
                return {"success": True, "result": "Saved"}
            return {"success": True, "result": {}}
        mock_exec.side_effect = side_effect
        yield mock_exec

def test_research_source_failure_halts_workflow(mock_search_fail):
    prompt = "Research current uses of AI in supply-chain forecasting using real sources, write at least 1200 words, and save it on Desktop."
    loop = AgentExecutionLoop()
    
    # Needs a mock plan generator so we don't hit Ollama planner
    with patch.object(loop, '_generate_plan') as mock_gen:
        mock_gen.return_value = [
            {"step": 1, "tool": "web_search", "arguments": {"query": "AI supply chain"}},
            {"step": 2, "tool": "generate_document", "arguments": {"intent": {"task_type": "research_write", "minimum_words": 1200}}},
            {"step": 3, "tool": "write_file", "arguments": {"filepath": "report.md", "content": "<USE_GENERATED_ARTIFACT>"}}
        ]
        
        result = loop.run(prompt)
        
        assert "couldn't retrieve enough current sources" in result
        
        # Verify generate_document and write_file were NOT executed
        executed_tools = [call[0][0] for call in mock_search_fail.call_args_list]
        assert "generate_document" not in executed_tools
        assert "write_file" not in executed_tools

def test_research_success_executes_workflow(mock_search_success):
    prompt = "Research AI in supply chain, write 1200 words, save to desktop."
    loop = AgentExecutionLoop()
    
    with patch.object(loop, '_generate_plan') as mock_gen:
        mock_gen.return_value = [
            {"step": 1, "tool": "web_search", "arguments": {"query": "AI supply chain"}},
            {"step": 2, "tool": "generate_document", "arguments": {"intent": {"task_type": "research_write", "topic": "AI supply chain", "minimum_words": 1200}}},
            {"step": 3, "tool": "write_file", "arguments": {"filepath": "report.md", "content": "<USE_GENERATED_ARTIFACT>"}}
        ]
        
        # We need to bypass the actual LLM generation for this test so it doesn't take forever or fail
        with patch('core.writing.pipeline.WritingPipeline.run_research_workflow') as mock_write:
            mock_write.return_value = "Word " * 1300  # Generate 1300 words to pass word count check
            
            result = loop.run(prompt)
            
            executed_tools = [call[0][0] for call in mock_search_success.call_args_list]
            assert "web_search" in executed_tools
            # write_file should be called
            assert "write_file" in executed_tools
            
            mock_write.assert_called()

def test_simple_generation_bypasses_evidence():
    prompt = "Write a 1200-word fictional project report."
    loop = AgentExecutionLoop()
    
    with patch.object(loop, '_generate_plan') as mock_gen:
        # A simple generation shouldn't have web_search in its plan
        mock_gen.return_value = [
            {"step": 1, "tool": "generate_document", "arguments": {"intent": {"task_type": "simple", "topic": "fictional report", "minimum_words": 1200}}},
            {"step": 2, "tool": "write_file", "arguments": {"filepath": "report.md", "content": "<USE_GENERATED_ARTIFACT>"}}
        ]
        
        with patch.object(tool_registry, 'execute') as mock_exec, \
             patch('core.writing.pipeline.WritingPipeline.run_research_workflow') as mock_write, \
             patch('core.writing.pipeline.WritingPipeline.run_simple_workflow') as mock_write_simple:
            
            mock_write.return_value = "Word " * 1300
            mock_write_simple.return_value = "Word " * 1300
            mock_exec.return_value = {"success": True, "result": "Saved"}
            
            loop.run(prompt)
            
            # Should reach write_file without web_search
            executed_tools = [call[0][0] for call in mock_exec.call_args_list]
            assert "write_file" in executed_tools
