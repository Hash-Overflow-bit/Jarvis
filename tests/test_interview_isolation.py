import pytest
from unittest.mock import patch, MagicMock
from core.orchestrator.agent_loop import AgentExecutionLoop

def test_interview_isolation_mode_activation():
    """
    Test: 'start fresh' or 'new isolated interview' activates interview_mode.
    """
    loop = AgentExecutionLoop(use_tools=True)
    assert not loop.interview_mode
    
    prompt = "Start a new isolated professional interview with me about my current bookkeeping workflow."
    
    # Run a mock traced loop execution (intercepting before LLM)
    with patch("core.orchestrator.agent_loop.recall") as mock_recall:
        mock_recall.return_value = MagicMock(facts=[], entities=[], as_text=lambda: "")
        
        # We patch generate_plan to return a string so it short-circuits
        with patch.object(loop, '_generate_plan', return_value="Here is your first question."):
            loop.run(prompt)
            
    assert loop.interview_mode is True

def test_interview_isolation_goal_description_no_tools():
    """
    Test: Describing a goal during interview mode results in an empty plan.
    """
    loop = AgentExecutionLoop(use_tools=True)
    loop.interview_mode = True # Already activated
    
    prompt = "My primary goal is to save time, reduce manual bookkeeping work, and keep everything organized and accurate across multiple businesses."
    
    # Mock the LLM to return a conversational response due to the strict system prompt
    with patch("core.llm.ollama_client.ollama.chat") as mock_chat:
        mock_chat.return_value = {"message": {"content": '{"reasoning": "User is describing goals", "plan": []}'}}
        
        plan = loop._generate_plan(prompt, recalled_facts="")
        
        assert isinstance(plan, list)
        assert len(plan) == 0

def test_interview_isolation_positive_control():
    """
    Test: Explicit tool request still executes even in interview mode.
    """
    loop = AgentExecutionLoop(use_tools=True)
    loop.interview_mode = True
    
    prompt = "Create a bookkeeping folder on my Desktop"
    
    with patch("core.orchestrator.agent_loop.ollama.chat") as mock_chat:
        # Mock a successful plan generation
        mock_chat.return_value = {"content": '{"reasoning": "User wants to create a folder", "plan": [{"step": 1, "tool": "create_directory", "arguments": {"path": "/Users/m2air/Desktop/bookkeeping"}}]}'}
        plan = loop._generate_plan(prompt, recalled_facts="")
        
    # In this case it should hit the direct route for 'create folder' or fallback to planner which works
    assert isinstance(plan, list)
    assert len(plan) == 1
    assert plan[0]["tool"] == "create_directory"

def test_interview_memory_relevance_gate():
    """
    Test: Irrelevant memories are suppressed in interview mode.
    """
    loop = AgentExecutionLoop(use_tools=True)
    loop.interview_mode = True
    
    prompt = "My goal is to automate bookkeeping"
    
    with patch("core.orchestrator.agent_loop.recall") as mock_recall:
        mock_res = MagicMock()
        mock_res.facts = [
            "The user previously requested automation_demo.", 
            "The user likes bookkeeping.",
            "ALPHA-TANGO-7 is active."
        ]
        mock_res.entities = []
        mock_res.as_text = lambda: "\\n".join(mock_res.facts)
        mock_recall.return_value = mock_res
        
        with patch.object(loop, '_generate_plan', return_value="Response"):
            loop.run(prompt)
            
            # The only fact retained should be the one containing "bookkeeping"
            assert len(mock_res.facts) == 1
            assert "bookkeeping" in mock_res.facts[0].lower()

def test_interview_isolation_quickbooks_hallucination_prevention():
    """
    Test: Conversational answer like 'I currently use QuickBooks...' must yield empty plan, zero tools.
    """
    loop = AgentExecutionLoop(use_tools=True)
    loop.interview_mode = True
    
    prompt = "I currently use QuickBooks for bookkeeping, along with spreadsheets for tracking and organizing some financial data."
    
    # 1. Verify pre-planner guard forces plan = []
    plan = loop._generate_plan(prompt, recalled_facts="")
    assert isinstance(plan, list)
    assert len(plan) == 0
    
    # 2. Verify hard execution sanitizer strips mutating tools if somehow bypassed
    mutating_plan = [{"step": 1, "tool": "write_file", "arguments": {"filepath": "/Users/m2air/Desktop/hello.txt"}}]
    # We patch _generate_plan to return a malicious plan, and check if sanitizer catches it
    with patch.object(loop, '_generate_plan', return_value=mutating_plan):
        # Prevent actual synthesis LLM calls
        with patch.object(loop, '_synthesize_fallback', return_value="Next question"):
            # run_traced is normally called by run(), but we can call it directly
            res = loop._run_traced(prompt, mode="text", span=MagicMock())
            # Sanitizer should reject write_file and fall back
            assert res == "Next question"
