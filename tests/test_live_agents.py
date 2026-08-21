"""
tests/test_live_agents.py
=========================
Integration tests for the Dynamic Sub-Agent Builder.
These tests use the LIVE Ollama LLM to verify that generated agents
can correctly perform reasoning and use tools.

Run this specifically using: pytest tests/test_live_agents.py -m integration -v
"""

import pytest
import os
from pathlib import Path
from core.tools.agent_builder import AgentBuilder, AgentBuilderInput
from core.orchestrator.agent_registry import agent_registry


@pytest.mark.integration
def test_live_file_organizer_agent(tmp_path):
    """
    Dynamically builds a Workspace Organizer agent and asks it to create a file.
    Tests the full loop: YAML generation -> Hot Load -> Live Reasoning -> Tool Execution.
    """
    builder = AgentBuilder()
    
    # 1. Define the Agent
    input_data = AgentBuilderInput(
        name="WorkspaceOrganizerAgent",
        role="Senior File System Manager",
        goal="Manage the workspace, create directories and write files accurately.",
        backstory="An AI system trained to organize files efficiently.",
        tools=["write_file", "create_directory"]
    )

    # 2. Build and Hot-Load the Agent (this updates YAML and loads it into memory)
    print("\n--- Building Agent ---")
    output = builder.run(input_data)
    assert output.success is True
    assert output.agent == "WorkspaceOrganizerAgent"

    # 3. Fetch the hot-loaded agent from registry
    agent_info = agent_registry.get("WorkspaceOrganizerAgent")
    assert agent_info is not None
    crewai_agent = agent_info["agent"]
    
    # 4. Create a real task for the agent
    from crewai import Task, Crew
    
    # Use the designated sandbox directory instead of tmp_path since the tool restricts access
    sandbox_dir = Path("./workspace_sandbox")
    sandbox_dir.mkdir(exist_ok=True)
    test_file_path = sandbox_dir / "integration_hello_world.txt"
    if test_file_path.exists():
        test_file_path.unlink()
        
    task_description = (
        f"You must use your `write_file` tool to create a new file at the EXACT path: '{test_file_path.resolve().as_posix()}'. "
        "The file content must be exactly: 'Integration test passed!'. "
        "CRITICAL: Do NOT just output JSON as your final answer. You MUST physically execute the `write_file` tool. "
        "After the tool returns success, your final answer should be 'File created'."
    )
    
    task = Task(
        description=task_description,
        agent=crewai_agent,
        expected_output="The exact phrase 'File created'."
    )

    # 5. Execute the task using the Live LLM
    print(f"\n--- Executing Task on Live Agent ---\nTask: {task_description}")
    crew = Crew(agents=[crewai_agent], tasks=[task])
    result = crew.kickoff()
    
    print("\n--- Agent Execution Complete ---")
    print(f"Result: {result}")

    # 6. Verify real-world outcome
    assert test_file_path.exists(), f"Agent failed to create the file at {test_file_path}"
    content = test_file_path.read_text().strip()
    assert "Integration test passed!" in content, f"Agent wrote incorrect content: {content}"
    
    # Cleanup
    test_file_path.unlink()
