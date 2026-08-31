import pytest
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.state.session_manager import SessionManager
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.writing.pipeline import WritingPipeline

@pytest.fixture
def session():
    sm = SessionManager()
    return sm

@pytest.fixture
def agent_loop(session):
    return AgentExecutionLoop(session)

@patch("core.writing.pipeline.WritingPipeline.run_research_workflow")
@patch("core.llm.ollama_client.OllamaClient.chat")
def test_cross_turn_save_report(mock_chat, mock_generate, agent_loop):
    mock_chat.return_value = {"content": "Fallback ok"}
    # 1. User asks for report -> exact content saved
    # First turn: generate report
    mock_generate.return_value = "This is the exact generated report on e-commerce."
    agent_loop.run("Make a research report about e-commerce", mode="text")
    
    assert "last_generated_document" in agent_loop.session_artifacts
    assert agent_loop.session_artifacts["last_generated_document"]["content"] == "This is the exact generated report on e-commerce."
    
    # Second turn: save this report
    with patch("core.tools.tool_registry.tool_registry.execute") as mock_exec:
        mock_exec.return_value = {"success": True, "result": {"message": "Success"}}
        agent_loop.run("save this report on my workspace", mode="text")
        
        # 6. save report -> no unnecessary list_dir
        executed_tools = [call.args[0] for call in mock_exec.call_args_list]
        assert "list_dir" not in executed_tools
        assert "write_file" in executed_tools
        
        # 2. previous assistant/report content is non-empty in write_file
        # 7. saved file content exactly matches generated report
        write_call = next(call for call in mock_exec.call_args_list if call.args[0] == "write_file")
        assert write_call.args[1]["content"] == "This is the exact generated report on e-commerce."


@patch("core.writing.pipeline.WritingPipeline.run_research_workflow")
@patch("core.llm.ollama_client.OllamaClient.chat")
def test_single_turn_generate_and_save(mock_chat, mock_generate, agent_loop):
    mock_chat.return_value = {"content": "Fallback ok"}
    # 3. "make report and save it" -> generation result flows into write_file
    mock_generate.return_value = "This is the simple e-commerce report."
    
    with patch("core.tools.tool_registry.tool_registry.execute") as mock_exec:
        mock_exec.return_value = {"success": True, "result": {"message": "Success"}}
        agent_loop.run("make a research report on e-commerce and save it to workspace", mode="text")
        
        write_call = next((call for call in mock_exec.call_args_list if call.args[0] == "write_file"), None)
        assert write_call is not None
        assert write_call.args[1]["content"] == "This is the simple e-commerce report."


@patch("core.writing.pipeline.WritingPipeline.run_research_workflow")
@patch("core.llm.ollama_client.OllamaClient.chat")
def test_generation_failure_stops_save(mock_chat, mock_generate, agent_loop):
    mock_chat.return_value = {"content": "Fallback ok"}
    # 4. generation failure -> write_file not executed
    # Simulate a failure (e.g. minimum words not met)
    mock_generate.return_value = "short report"
    
    def mock_exec_side_effect(tool_name, args, **kwargs):
        return {"success": True, "result": {"message": "Success"}}

    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=mock_exec_side_effect) as mock_exec:
        # Prompt explicitly demands 1000 words, which will trigger failure
        res = agent_loop.run("make a 1000 word research report on e-commerce and save it to workspace", mode="text")
        
        executed_tools = [call.args[0] for call in mock_exec.call_args_list]
        assert "write_file" not in executed_tools
        
        # 5. generation failure -> error text not saved as report
        assert "Execution halted" in res or "Failure" in res
