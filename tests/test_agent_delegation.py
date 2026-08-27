"""
tests/test_agent_delegation.py
==============================
Focused unit and integration tests for Jarvis to sub-agent delegation and builder routing.
"""

import pytest
import yaml
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from core.config import settings
from core.orchestrator.agent_registry import AgentRegistry, CrewAIAgentAdapter
from core.tools.delegate_task import DelegateTask, DelegateTaskInput
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.tools.agent_builder import AgentBuilder, AgentBuilderInput
from core.orchestrator.baseline_runner import baseline_runner
from crewai import Agent, LLM


@pytest.fixture
def clean_registry():
    from core.orchestrator.agent_registry import agent_registry
    old_agents = agent_registry._agents
    agent_registry._agents = {}
    yield agent_registry
    agent_registry._agents = old_agents


@pytest.fixture
def temp_blueprint(tmp_path):
    blueprint_file = tmp_path / "agents_blueprint.yaml"
    with patch("core.config._Settings.agents_blueprint_path", new_callable=PropertyMock, return_value=blueprint_file):
        yield blueprint_file


def test_registry_normalization(clean_registry):
    mock_agent = MagicMock(spec=Agent)
    clean_registry.register("CaliforniaCPAAgent", mock_agent, ["tax_review"])

    assert clean_registry.load_if_needed("CaliforniaCPAAgent") is not None
    assert clean_registry.load_if_needed("California CPA Agent") is not None
    assert clean_registry.load_if_needed("california_cpa_agent") is not None
    assert clean_registry.load_if_needed("californiacpaagent") is not None
    assert clean_registry.load_if_needed("CaliforniaCPA") is not None


def test_direct_delegation_to_loaded_fake_agent(clean_registry):
    mock_adapter = MagicMock()
    mock_adapter.run.return_value = "Mocked execution success"
    
    clean_registry.register("MockAgent", MagicMock(spec=Agent), [])
    clean_registry._agents["MockAgent"]["adapter"] = mock_adapter

    dt = DelegateTask()
    res = dt.run(DelegateTaskInput(
        agent_name="MockAgent",
        task_description="Perform audit",
        expected_output="Audit report"
    ))
    
    assert res.success is True
    assert res.result == "Mocked execution success"
    mock_adapter.run.assert_called_with("Perform audit")


def test_generated_crewai_agent_uses_ollama_not_openai(clean_registry, temp_blueprint):
    blueprint_data = {
        "custom_sub_agents": [
            {
                "name": "LocalResearchAgent",
                "role": "Local Researcher",
                "goal": "Test LLM binding",
                "backstory": "Background context",
                "verbose": True,
                "allow_delegation": False,
                "tools": []
            }
        ]
    }
    with open(temp_blueprint, "w") as f:
        yaml.safe_dump(blueprint_data, f)

    adapter = clean_registry.load_if_needed("LocalResearchAgent")
    assert adapter is not None
    
    agent_instance = clean_registry.get("LocalResearchAgent")["agent"]
    assert agent_instance.llm.provider == "ollama_chat"
    assert agent_instance.llm.model == settings.ollama_model
    assert agent_instance.llm.base_url.startswith(settings.ollama_base_url)
    assert agent_instance.llm.api_key == "NA"


def test_missing_agent_returns_failure(clean_registry):
    dt = DelegateTask()
    res = dt.run(DelegateTaskInput(
        agent_name="NonexistentAgent",
        task_description="Do nothing",
        expected_output="nothing"
    ))
    assert res.success is False
    assert "not found" in res.error.lower()


def test_persisted_agent_can_be_restored_after_clearing_registry(clean_registry, temp_blueprint):
    blueprint_data = {
        "custom_sub_agents": [
            {
                "name": "PersistedAgent",
                "role": "Analyst",
                "goal": "Analyze",
                "backstory": "Expert",
                "tools": []
            }
        ]
    }
    with open(temp_blueprint, "w") as f:
        yaml.safe_dump(blueprint_data, f)

    clean_registry._agents = {}
    adapter = clean_registry.load_if_needed("PersistedAgent")
    assert adapter is not None
    assert clean_registry.get("PersistedAgent") is not None


def test_rolled_back_agent_cannot_be_restored(clean_registry, temp_blueprint):
    builder = AgentBuilder()
    input_data = AgentBuilderInput(
        name="BrokenAgent",
        role="Broken",
        goal="Fail",
        backstory="None",
        tools=[]
    )

    with patch("core.tools.agent_builder.baseline_runner.test", return_value={"success": False, "error": "Crash"}):
        output = builder.run(input_data)
        assert output.success is False

    assert clean_registry.load_if_needed("BrokenAgent") is None


def test_ask_research_agent_routes_to_delegate_task(clean_registry, temp_blueprint):
    blueprint_data = {
        "custom_sub_agents": [
            {
                "name": "ResearchAgent",
                "role": "Researcher",
                "goal": "Research",
                "backstory": "Researcher",
                "tools": []
            }
        ]
    }
    with open(temp_blueprint, "w") as f:
        yaml.safe_dump(blueprint_data, f)

    loop = AgentExecutionLoop()
    plan = loop._direct_route("Ask ResearchAgent to summarize this webpage")
    
    assert plan is not None
    assert plan[0]["tool"] == "delegate_task"
    assert plan[0]["arguments"]["agent_name"] == "ResearchAgent"
    assert plan[0]["arguments"]["task_description"] == "summarize this webpage"


def test_let_research_agent_handle_routes_to_delegate_task(clean_registry, temp_blueprint):
    blueprint_data = {
        "custom_sub_agents": [
            {
                "name": "ResearchAgent",
                "role": "Researcher",
                "goal": "Research",
                "backstory": "Researcher",
                "tools": []
            }
        ]
    }
    with open(temp_blueprint, "w") as f:
        yaml.safe_dump(blueprint_data, f)

    loop = AgentExecutionLoop()
    plan = loop._direct_route("Let Research Agent handle this analysis")
    
    assert plan is not None
    assert plan[0]["tool"] == "delegate_task"
    assert plan[0]["arguments"]["agent_name"] == "ResearchAgent"
    assert plan[0]["arguments"]["task_description"] == "this analysis"


def test_explicit_missing_agent_does_not_cause_jarvis_to_perform_task(clean_registry, temp_blueprint):
    loop = AgentExecutionLoop()
    plan = loop._direct_route("Ask MissingAgent to review this document")
    
    assert plan is not None
    assert plan[0]["tool"] == "delegate_task"
    assert plan[0]["arguments"]["agent_name"] == "MissingAgent"
    assert plan[0]["arguments"]["task_description"] == "review this document"


def test_build_restart_delegate_integration(clean_registry, temp_blueprint):
    builder = AgentBuilder()
    input_data = AgentBuilderInput(
        name="IntegrationAgent",
        role="Integration Specialist",
        goal="Verify integration flow",
        backstory="Mock integration backstory",
        tools=[]
    )

    with patch("core.tools.agent_builder.baseline_runner.test", return_value={"success": True}):
        output = builder.run(input_data)
        assert output.success is True

    clean_registry._agents = {}
    assert clean_registry.get("IntegrationAgent") is None

    adapter = clean_registry.load_if_needed("IntegrationAgent")
    assert adapter is not None

    with patch.object(adapter, "run", return_value="Integration Success") as mock_run:
        dt = DelegateTask()
        res = dt.run(DelegateTaskInput(
            agent_name="IntegrationAgent",
            task_description="Execute test",
            expected_output="success"
        ))
        assert res.success is True
        assert res.result == "Integration Success"
        mock_run.assert_called_with("Execute test")


# --- NEW focused tests from User request ---

def test_focused_build_research_agent_routing():
    loop = AgentExecutionLoop()
    plan = loop._direct_route("Build me a ResearchAgent using CrewAI that can summarize text.")
    assert plan is not None
    assert plan[0]["tool"] == "agent_builder"
    args = plan[0]["arguments"]
    assert args["name"] == "ResearchAgent"
    assert args["framework"] == "crewai"
    assert "summarize" in args["capabilities"]
    # Ensure delegate_task is NOT in the plan
    assert not any(step.get("tool") == "delegate_task" for step in plan)


def test_focused_ask_research_agent_routing():
    loop = AgentExecutionLoop()
    plan = loop._direct_route("Ask ResearchAgent to summarize this paragraph.")
    assert plan is not None
    assert plan[0]["tool"] == "delegate_task"
    assert plan[0]["arguments"]["agent_name"] == "ResearchAgent"
    assert not any(step.get("tool") == "agent_builder" for step in plan)


def test_focused_build_accounting_agent_langgraph():
    loop = AgentExecutionLoop()
    plan = loop._direct_route("Build me an AccountingAgent using LangGraph.")
    assert plan is not None
    assert plan[0]["tool"] == "agent_builder"
    args = plan[0]["arguments"]
    assert args["name"] == "AccountingAgent"
    assert args["framework"] == "langgraph"


def test_focused_replanning_prevents_agent_renaming():
    loop = AgentExecutionLoop()
    failed_step = {
        "step": 1,
        "tool": "agent_builder",
        "arguments": {
            "name": "ResearchAgent",
            "framework": "crewai",
            "capabilities": ["summarize"]
        }
    }
    
    # Verify replanning yields the exact same arguments and prevents renaming to CrewAI
    revised = loop._reflect_and_replan(
        user_goal="Build me a ResearchAgent using CrewAI that can summarize text.",
        failed_step=failed_step,
        error_message="Baseline test timed out",
        completed_steps=[]
    )
    
    assert len(revised) == 1
    assert revised[0]["tool"] == "agent_builder"
    assert revised[0]["arguments"]["name"] == "ResearchAgent"
    assert revised[0]["arguments"]["framework"] == "crewai"


@pytest.mark.asyncio
async def test_focused_baseline_pass():
    dummy_agent = Agent(role="Tester", goal="Test", backstory="Test")
    # Mock crew.kickoff returning "success"
    with patch("core.orchestrator.baseline_runner.Crew") as MockCrew:
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = "success"
        MockCrew.return_value = mock_crew_instance
        
        res = await baseline_runner.test(dummy_agent)
        assert res["success"] is True
        assert res["result"] == "success"


@pytest.mark.asyncio
async def test_focused_baseline_fail_on_tool_error():
    dummy_agent = Agent(role="Tester", goal="Test", backstory="Test")
    # Mock crew.kickoff returning an error response
    with patch("core.orchestrator.baseline_runner.Crew") as MockCrew:
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = "Action 'Say the word success' don't exist"
        MockCrew.return_value = mock_crew_instance
        
        res = await baseline_runner.test(dummy_agent)
        assert res["success"] is False
        assert "tool/action error" in res["error"]


def test_focused_build_only_stops_after_build():
    loop = AgentExecutionLoop()
    # Mock a build-only plan containing both agent_builder and a hallucinated delegate_task
    raw_plan = [
        {"step": 1, "tool": "agent_builder", "arguments": {"name": "ResearchAgent", "framework": "crewai"}},
        {"step": 2, "tool": "delegate_task", "arguments": {"agent_name": "ResearchAgent", "task_description": "test"}}
    ]
    
    sanitized = loop._sanitize_plan(raw_plan, "Build me a ResearchAgent using CrewAI")
    
    # Should stop after build (delegate_task stripped)
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "agent_builder"


def test_synthesis_build_only_mentions_capabilities():
    loop = AgentExecutionLoop()
    completed_steps = [{
        "step": 1,
        "tool": "agent_builder",
        "arguments": {
            "name": "ResearchAgent",
            "framework": "crewai",
            "capabilities": ["summarize"]
        },
        "success": True,
        "result": "Agent successfully built"
    }]
    
    # Run synthesis directly
    res = loop._synthesize_final_response(
        user_input="Build me a ResearchAgent using CrewAI that can summarize text.",
        completed_steps=completed_steps,
        recalled_facts=""
    )

    # Must mention capability configuration but not claim successful execution
    assert "summariz" in res.lower() or "configured" in res.lower() or "capabilit" in res.lower()
    assert "successfully summarized text" not in res.lower()
    # Must not contain the info disclaimer for capabilities
    assert "i don't have any information about the agent's ability" not in res.lower()


def test_synthesis_build_and_delegate_task():
    loop = AgentExecutionLoop()
    completed_steps = [
        {
            "step": 1,
            "tool": "agent_builder",
            "arguments": {"name": "ResearchAgent", "framework": "crewai", "capabilities": ["summarize"]},
            "success": True,
            "result": "Agent successfully built"
        },
        {
            "step": 2,
            "tool": "delegate_task",
            "arguments": {"agent_name": "ResearchAgent", "task_description": "Summarize the text"},
            "success": True,
            "result": "The summarization task completed successfully."
        }
    ]
    
    res = loop._synthesize_final_response(
        user_input="Build ResearchAgent and ask it to summarize the text.",
        completed_steps=completed_steps,
        recalled_facts=""
    )
    
    assert "summarize" in res.lower() or "summarization" in res.lower()
    assert "completed successfully" in res.lower() or "success" in res.lower()


def test_quality_summarize_only_agent_zero_tools(clean_registry):
    # Mock LLM response to be tool-free direct response
    mock_llm = MagicMock()
    mock_llm.call.return_value = "This is a direct summary."
    
    agent_instance = Agent(role="Summarizer", goal="Summarize", backstory="Backstory", tools=[], llm="ollama/llama3.1")
    agent_instance.llm = mock_llm
    adapter = CrewAIAgentAdapter(agent_instance, capabilities=["summarize"])
    
    res = adapter.run("Summarize text")
    assert res == "This is a direct summary."
    # Verify no action/tool prompt was used and direct call was made
    mock_llm.call.assert_called_once()


def test_quality_semantic_preservation(clean_registry):
    mock_llm = MagicMock()
    # Output matches requested semantic constraints
    mock_llm.call.return_value = "Local AI assistants improve privacy and reduce dependence on cloud services by running models locally."
    
    agent_instance = Agent(role="Summarizer", goal="Summarize", backstory="Backstory", tools=[], llm="ollama/llama3.1")
    agent_instance.llm = mock_llm
    adapter = CrewAIAgentAdapter(agent_instance, capabilities=["summarize"])
    
    res = adapter.run("Local AI assistants run models locally, improving privacy and reducing cloud dependence.")
    assert "privacy" in res.lower()
    assert "local" in res.lower()
    assert "cloud" in res.lower()
    # Ensure it doesn't contain hallucinated pro-cloud claims
    assert "enhance efficiency" not in res.lower()


def test_quality_no_invented_actions(clean_registry):
    mock_llm = MagicMock()
    mock_llm.call.return_value = "Direct summary text."
    
    agent_instance = Agent(role="Summarizer", goal="Summarize", backstory="Backstory", tools=[], llm="ollama/llama3.1")
    agent_instance.llm = mock_llm
    adapter = CrewAIAgentAdapter(agent_instance, capabilities=["summarize"])
    
    res = adapter.run("Summarize this text.")
    # Verify no file-saving or web search keywords are present
    assert "write" not in res.lower()
    assert "save" not in res.lower()
    assert "search" not in res.lower()


@pytest.mark.asyncio
async def test_quality_invalid_tool_error_detection(clean_registry):
    # Simulate a CrewAI agent execution that returns an invalid Action error in its final output
    mock_agent = Agent(role="Summarizer", goal="Summarize", backstory="Backstory", tools=[], llm="ollama/llama3.1")
    mock_agent.tools = [MagicMock()]
    adapter = CrewAIAgentAdapter(mock_agent, capabilities=["summarize"])
    
    # We patch kickoff_async to return a tool error, and then patch llm.call to succeed on retry
    with patch("crewai.Crew") as MockCrew:
        mock_crew_instance = MagicMock()
        # Returns a tool failure output
        mock_crew_instance.kickoff_async = MagicMock(
            return_value=asyncio.Future()
        )
        mock_crew_instance.kickoff_async.return_value.set_result("Action 'Write Summary to File' don't exist")
        MockCrew.return_value = mock_crew_instance
        
        with patch.object(mock_agent.llm, "call", return_value="Direct summary after retry") as mock_call:
            res = adapter.run("Summarize text")
            # Should have detected the error, retried once via llm.call, and returned the clean result
            assert res == "Direct summary after retry"
            mock_call.assert_called_once()


def test_quality_synthesis_no_unrelated_disclaimers():
    loop = AgentExecutionLoop()
    completed_steps = [
        {
            "step": 1,
            "tool": "delegate_task",
            "arguments": {"agent_name": "ResearchAgent", "task_description": "Summarize text"},
            "success": True,
            "result": "This is the summary result."
        }
    ]
    
    res = loop._synthesize_final_response(
        user_input="Ask ResearchAgent to summarize this.",
        completed_steps=completed_steps,
        recalled_facts=""
    )
    
    assert "summariz" in res.lower() or "result" in res.lower()
    # Must not contain path disclaimers since no paths/files were asked about
    assert "i don't have any additional information" not in res.lower()
    assert "verified path" not in res.lower()


def test_synthesis_no_false_delegation_disclaimers():
    loop = AgentExecutionLoop()
    completed_steps = [
        {
            "step": 1,
            "tool": "delegate_task",
            "arguments": {
                "agent_name": "ResearchAgent",
                "task_description": "summarize: Local AI assistants run models locally",
                "expected_output": "Final result of the assigned task."
            },
            "success": True,
            "result": "Local AI assistants run models on the user's machine, improving privacy."
        }
    ]
    
    res = loop._synthesize_final_response(
        user_input="Ask ResearchAgent to summarize: Local AI assistants run models locally",
        completed_steps=completed_steps,
        recalled_facts=""
    )
    
    res_lower = res.lower()
    # Must mention delegated result
    assert "privacy" in res_lower or "local" in res_lower or "researchagent" in res_lower
    # Must NOT contain false disclaimers
    assert "request was not explicitly stated" not in res_lower
    assert "i don't have information" not in res_lower
    assert "not available in executed steps" not in res_lower


def test_generalized_capability_extraction_finance():
    loop = AgentExecutionLoop()
    prompt = "Build me a FinanceManagerAgent using CrewAI that can analyze financial data, identify budget variances, and provide financial recommendations for a technology company."
    plan = loop._direct_route(prompt)
    assert plan is not None
    args = plan[0]["arguments"]
    assert args["name"] == "FinanceManagerAgent"
    assert len(args["capabilities"]) > 0
    caps_str = " ".join(args["capabilities"]).lower()
    assert "financial" in caps_str or "analyze" in caps_str
    assert "budget" in caps_str or "variance" in caps_str
    assert "recommendations" in caps_str
    assert args["role"] != "FinanceManagerAgent Specialist"
    assert "Technology" in args["role"] or "Finance" in args["role"]


def test_generalized_capability_extraction_hr():
    loop = AgentExecutionLoop()
    prompt = "Build me an HRManagerAgent that can review resumes, identify skill gaps, and recommend interview questions."
    plan = loop._direct_route(prompt)
    assert plan is not None
    args = plan[0]["arguments"]
    assert args["name"] == "HRManagerAgent"
    assert len(args["capabilities"]) == 3
    caps_str = " ".join(args["capabilities"]).lower()
    assert "resume" in caps_str
    assert "skill" in caps_str
    assert "interview" in caps_str


def test_generalized_capability_extraction_security():
    loop = AgentExecutionLoop()
    prompt = "Build me a SecurityAgent able to inspect logs and identify suspicious activity."
    plan = loop._direct_route(prompt)
    assert plan is not None
    args = plan[0]["arguments"]
    assert args["name"] == "SecurityAgent"
    assert len(args["capabilities"]) == 2
    caps_str = " ".join(args["capabilities"]).lower()
    assert "inspect" in caps_str or "log" in caps_str
    assert "suspicious" in caps_str or "activity" in caps_str


def test_grounding_missing_support_metrics():
    from core.orchestrator.agent_registry import CrewAIAgentAdapter
    from crewai import Agent

    fake_agent = Agent(
        role="Customer Support Manager",
        goal="Manage support tickets",
        backstory="An AI support specialist",
        llm="ollama/llama3.1",
        allow_delegation=False
    )
    mock_llm = MagicMock()
    mock_llm.call.return_value = "The required metrics (unhappy customer percentage and response time) are missing from the input data and cannot be determined."
    fake_agent.llm = mock_llm

    adapter = CrewAIAgentAdapter(fake_agent, expected_output="metrics")
    res = adapter.run("What percentage of our customers are unhappy and what is our average support response time?")
    
    assert "cannot be determined" in res.lower() or "missing" in res.lower()
    assert "12%" not in res
    assert "4 hours" not in res.lower() and "4-hour" not in res.lower()


def test_grounding_missing_finance_metrics():
    from core.orchestrator.agent_registry import CrewAIAgentAdapter
    from crewai import Agent

    fake_agent = Agent(
        role="Finance Manager",
        goal="Manage finance",
        backstory="An AI finance specialist",
        llm="ollama/llama3.1",
        allow_delegation=False
    )
    mock_llm = MagicMock()
    mock_llm.call.return_value = "The Q3 gross profit margin and EBITDA data are missing from the input and cannot be determined."
    fake_agent.llm = mock_llm

    adapter = CrewAIAgentAdapter(fake_agent, expected_output="metrics")
    res = adapter.run("What is our Q3 gross profit margin percentage and EBITDA?")
    
    assert "cannot be determined" in res.lower() or "missing" in res.lower()


def test_chat_memory_question_not_persisted():
    from core.memory.chat_memory import learn_from_message
    with patch("core.memory.chat_memory.save_conversational_fact") as mock_save:
        learn_from_message("What is the average support response time?")
        mock_save.assert_not_called()


def test_build_only_agent_request():
    loop = AgentExecutionLoop()
    prompt = "Build me a RiskManagerAgent using CrewAI that can identify operational risks, assess severity, and recommend mitigations."
    plan = loop._direct_route(prompt)
    assert plan is not None
    assert len(plan) == 1
    assert plan[0]["tool"] == "agent_builder"


def test_build_and_delegate_in_one_prompt():
    loop = AgentExecutionLoop()
    prompt = "Build me a RiskManagerAgent using CrewAI that can identify operational risks, assess severity, and recommend mitigations, then ask it to analyze: Our production server has no automated backup, one engineer holds all deployment credentials, and monitoring alerts are often ignored."
    plan = loop._direct_route(prompt)
    assert plan is not None
    assert len(plan) == 2
    assert plan[0]["tool"] == "agent_builder"
    assert plan[1]["tool"] == "delegate_task"
    assert plan[1]["arguments"]["agent_name"] == "RiskManagerAgent"
    assert "analyze:" in plan[1]["arguments"]["task_description"].lower()


def test_delegated_task_not_in_capabilities():
    loop = AgentExecutionLoop()
    prompt = "Build me a RiskManagerAgent using CrewAI that can identify operational risks, assess severity, and recommend mitigations, then ask it to analyze: Our production server has no automated backup, one engineer holds all deployment credentials, and monitoring alerts are often ignored."
    plan = loop._direct_route(prompt)
    assert plan is not None
    caps = plan[0]["arguments"]["capabilities"]
    caps_str = " ".join(caps).lower()
    assert "analyze" not in caps_str
    assert "production server" not in caps_str
    assert "backup" not in caps_str
    assert caps == ["identify operational risks", "assess severity", "recommend mitigations"]


def test_no_delegate_execution_synthesis_truth():
    loop = AgentExecutionLoop()
    completed_steps = [
        {
            "step": 1,
            "tool": "agent_builder",
            "arguments": {
                "name": "RiskManagerAgent",
                "capabilities": ["identify operational risks", "assess severity", "recommend mitigations"]
            },
            "success": True,
            "result": "Agent RiskManagerAgent successfully built and registered."
        }
    ]
    res = loop._synthesize_final_response(
        user_input="Build me a RiskManagerAgent using CrewAI that can identify operational risks, assess severity, and recommend mitigations, then ask it to analyze: Our production server has no automated backup.",
        completed_steps=completed_steps,
        recalled_facts=""
    )
    res_lower = res.lower()
    assert "analyzed" not in res_lower or "delegate_task" not in res_lower
    assert "built" in res_lower or "configured" in res_lower





