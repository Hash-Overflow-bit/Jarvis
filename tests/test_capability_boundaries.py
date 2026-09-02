import pytest
from unittest.mock import patch
from core.config import settings
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.writing.pipeline import WritingPipeline

def test_filesystem_verification_is_not_compliance(tmp_path):
    """Test A: filesystem verification is not compliance"""
    prompt = "Create folder_A in my workspace. Inside it create folder_B. Inside folder_B create test.txt containing hello. Read it back and verify its exact path and content."
    with patch.object(settings.__class__, "default_workspace_dir", new=property(lambda _: tmp_path)):
        loop = AgentExecutionLoop()
        plan = loop._direct_route(prompt)
        assert plan is not None
        assert len(plan) == 4
        assert plan[0]["tool"] == "create_directory"
        assert plan[1]["tool"] == "create_directory"
        assert plan[2]["tool"] == "write_file"
        assert plan[3]["tool"] == "read_file"
        loop_live = AgentExecutionLoop(use_tools=True)
        res = loop_live.run(prompt)
    assert "I cannot verify that from the approved local compliance knowledge." not in res
    assert "hello" in res.lower() or "test.txt" in res.lower() or "a/b" in res.lower()

def test_simple_report_requires_no_research():
    """Test B: simple report requires no research"""
    prompt = "Generate a short project status report with Summary, Progress, Risks, and Next Steps."
    intent = WritingPipeline.parse_intent(prompt)
    
    assert intent.task_type == "simple"
    assert intent.research_required is False
    assert intent.sources_required is False
    
    loop = AgentExecutionLoop()
    plan = loop._direct_route(prompt)
    
    if plan is not None:
        tools = [s["tool"] for s in plan]
        assert "web_search" not in tools
        assert "generate_document" in tools

def test_mixed_nested_plus_simple_report():
    """Test C: mixed nested + simple report"""
    loop = AgentExecutionLoop()
    prompt = "Create project_test in my workspace. Inside it create reports. Generate a short project status report and save it inside reports as status.md. Then read it back and verify its path and contents."
    plan = loop._direct_route(prompt)
    assert plan is not None
    
    tools = [s["tool"] for s in plan]
    assert tools == ["create_directory", "create_directory", "generate_document", "write_file", "read_file"]
    
    write_step = next(s for s in plan if s["tool"] == "write_file")
    assert write_step["arguments"]["content"] == "<USE_GENERATED_ARTIFACT>"

def test_research_still_works():
    """Test D: research still works"""
    prompt = "Research current AI use in project management, write a sourced report, and save it."
    intent = WritingPipeline.parse_intent(prompt)
    
    assert intent.task_type == "research_write"
    assert intent.research_required is True
    
    loop = AgentExecutionLoop()
    plan = loop._direct_route(prompt)
    assert plan is not None
    
    tools = [s["tool"] for s in plan]
    assert "web_search" in tools
    assert "generate_document" in tools
    assert "write_file" in tools
