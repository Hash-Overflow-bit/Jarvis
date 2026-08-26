import os
import shutil
from pathlib import Path
from core.writing.pipeline import WritingPipeline, ContentWorkflowIntent
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings

def test_intent_classification_paraphrases():
    prompts = [
        "Create a campaign folder, write a short tagline, make a placeholder banner, and assemble a README with both.",
        "Make a local demo directory containing a 4-line product description, a simple SVG cover, and a markdown overview.",
        "Build a content package with copy, a placeholder visual, and a summary document inside a new folder.",
        "Create a project folder with a short script and visual asset, then produce a Markdown page referencing both.",
        "Jarvis, create a local project folder named content_test. Inside it, write a short 3-sentence script about an automated multi-agent business system, generate a simple background graphic or placeholder visual asset, and create a final Markdown report that includes the script and references the visual."
    ]
    
    for prompt in prompts:
        intent = WritingPipeline.parse_intent(prompt)
        assert isinstance(intent, ContentWorkflowIntent), f"Failed to classify '{prompt}' as ContentWorkflowIntent"
        assert intent.project_folder is not None
        assert intent.script_required is True
        assert intent.visual_required is True
        assert intent.report_required is True

def test_no_research_misclassification():
    prompt = "Jarvis, create a local project folder named content_test. Inside it, write a short 3-sentence script about an automated multi-agent business system, generate a simple background graphic or placeholder visual asset, and create a final Markdown report that includes the script and references the visual."
    task_type = WritingPipeline.classify_intent(prompt)
    assert task_type == "content_workflow", f"Misclassified as {task_type}"
    
    # Check that research is not triggered
    intent = WritingPipeline.parse_intent(prompt)
    assert type(intent).__name__ == "ContentWorkflowIntent"

def test_deterministic_routing_plan():
    loop = AgentExecutionLoop()
    prompt = "Create a project folder with a short script and visual asset, then produce a Markdown page referencing both."
    
    plan = loop._direct_route(prompt)
    assert plan is not None, "Direct route returned None"
    assert isinstance(plan, list), "Direct route did not return a list plan"
    
    tools_in_plan = [step.get("tool") for step in plan]
    
    assert "web_search" not in tools_in_plan, "Plan must not include web_search"
    assert "create_directory" in tools_in_plan, "Plan must include create_directory"
    assert "verify_content_workflow" in tools_in_plan, "Plan must include verify_content_workflow"
    
    # Check dependency sequence roughly
    idx_dir = tools_in_plan.index("create_directory")
    idx_script = tools_in_plan.index("generate_document")
    idx_verify = tools_in_plan.index("verify_content_workflow")
    
    assert idx_dir < idx_script, "Folder creation must precede script generation"
    assert idx_script < idx_verify, "Script generation must precede verification"
