import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from core.orchestrator.agent_loop import AgentExecutionLoop

@pytest.fixture
def mock_agent():
    return AgentExecutionLoop(use_tools=True)

def test_deterministic_3_step_generation(mock_agent):
    """
    Test that the exact acceptance prompt generates exactly 3 ordered steps 
    via the deterministic router.
    """
    prompt = "Create a folder named jarvis_execution_test on my Desktop. Inside it, create notes.txt containing exactly Jarvis execution verified. Then read the file back and confirm the exact path and content. Do not claim success unless you physically verify both the folder and file."
    
    plan = mock_agent._direct_route(prompt)
    assert plan is not None
    assert len(plan) == 3
    
    # 1. create_directory
    assert plan[0]["tool"] == "create_directory"
    assert "jarvis_execution_test" in plan[0]["arguments"]["directory"]
    
    # 2. write_file
    assert plan[1]["tool"] == "write_file"
    assert "notes.txt" in plan[1]["arguments"]["filepath"]
    assert plan[1]["arguments"]["content"] == "Jarvis execution verified"
    
    # 3. read_file
    assert plan[2]["tool"] == "read_file"
    assert "notes.txt" in plan[2]["arguments"]["filepath"]

def test_physical_verification_partial_failure(mock_agent):
    """
    Test that if write_file fails physical verification, the final response correctly
    states partial completion and excludes hallucinated success for remaining steps.
    """
    prompt = "Create a folder named jarvis_execution_test on my Desktop. Inside it, create notes.txt containing exactly Jarvis execution verified. Then read the file back and confirm the exact path and content."
    
    # Only step 1 (create_directory) succeeds
    completed_steps = [
        {"step": 1, "tool": "create_directory", "result": {"success": True}}
    ]
    
    mock_synth_response = {
        "message": {"role": "assistant"},
        "content": "The folder jarvis_execution_test was created, but notes.txt was not created."
    }
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_synth_response):
        response = mock_agent._synthesize_final_response(
            user_input=prompt,
            completed_steps=completed_steps,
            recalled_facts="/workspace/file.txt"
        )
    
    response_lower = response.lower()
    assert "notes.txt" in response_lower
    assert "not" in response_lower
    assert "folder" in response_lower
    assert "created" in response_lower
    assert "/workspace/file.txt" not in response_lower  # Memory exclusion
    assert "step 2" not in response_lower
    assert "step 3" not in response_lower

def test_physical_verification_success(mock_agent):
    """
    Test that if all steps physically verify, the correct success message is returned
    and recalled memory is still excluded.
    """
    prompt = "Create a folder named jarvis_execution_test on my Desktop. Inside it, create notes.txt containing exactly Jarvis execution verified. Then read the file back and confirm the exact path and content."
    
    completed_steps = [
        {"step": 1, "tool": "create_directory", "result": {"success": True}},
        {"step": 2, "tool": "write_file", "result": {"success": True}},
        {"step": 3, "tool": "read_file", "result": {"success": True}}
    ]
    
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value={"message": {"role": "assistant"}, "content": "Step 1 create_directory ✅\nStep 2 write_file ✅\nStep 3 read_file ✅\nThe folder jarvis_execution_test and notes.txt were successfully created."}):
        response = mock_agent._synthesize_final_response(
            user_input=prompt,
            completed_steps=completed_steps,
            recalled_facts="/workspace/file.txt"
        )
    
    response_lower = response.lower()
    assert "notes.txt" in response_lower
    assert "jarvis_execution_test" in response_lower
    assert "/workspace/file.txt" not in response_lower  # Memory exclusion
