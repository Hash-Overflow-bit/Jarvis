import inspect
import json

from core.orchestrator.agent_loop import AgentExecutionLoop

# ──────────────────────────────────────────────────────────────────────
# Test 8: Planner Completion Rule for Multi-Part Research
# ──────────────────────────────────────────────────────────────────────
def test_planner_prompt_includes_completion_rule():
    """The planner system prompt must instruct the LLM to use generate_document for research synthesis."""
    loop = AgentExecutionLoop()
    # The schemas string must now contain generate_document
    schemas = loop._get_tool_schemas_str()
    assert "generate_document" in schemas, "generate_document tool schema is missing from planner prompt"
    
    # We can't directly check the internal system_prompt local variable without invoking, 
    # but we can verify our fix was added to the _generate_plan logic.
    source = inspect.getsource(AgentExecutionLoop._generate_plan)
    assert "COMPLETION RULE" in source, "Planner completion rule missing"
    assert "generate_document" in source, "generate_document not mentioned in planner rules"


# ──────────────────────────────────────────────────────────────────────
# Test 9: Incomplete Rankings Disclosure Rule
# ──────────────────────────────────────────────────────────────────────
def test_research_prompt_includes_incomplete_rankings_rule():
    """The research workflow system prompt must instruct the LLM not to invent missing rankings."""
    from core.writing.pipeline import WritingPipeline
    source = inspect.getsource(WritingPipeline.run_research_workflow)
    assert "INCOMPLETE RANKINGS" in source.upper() or "incomplete rankings" in source.lower(), (
        "Research workflow prompt does not include incomplete rankings disclosure rule"
    )
    assert "invent" in source.lower() or "hallucinate" in source.lower(), (
        "Rule does not explicitly ban inventing missing items"
    )

