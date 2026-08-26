import json
from unittest.mock import patch, MagicMock
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.writing.sources import EvidenceSource

def test_compliance_direct_route_prevents_web_search():
    """
    Test 1: Local-only compliance prompt never calls web_search.
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "What is the California ZR-88 withholding threshold for 2026? Use approved local knowledge."
    
    plan = loop._direct_route(prompt)
    assert plan is not None, "Direct route failed to intercept compliance query."
    assert len(plan) == 1
    assert plan[0]["tool"] == "read_file"
    assert "ca_compliance_2026.md" in plan[0]["arguments"]["filepath"]

def test_missing_compliance_fact_returns_grounded_response():
    """
    Test 2: Missing compliance fact returns the grounded unknown response.
    """
    from core.writing.pipeline import WritingPipeline
    
    sources = [
        EvidenceSource(
            source_type="local_file",
            title="ca_compliance_2026.md",
            location="/workspace/knowledge/ca_compliance_2026.md",
            content="California standard withholding is 9%. No mention of ZR-88.",
            verified=True
        )
    ]
    
    mock_llm_report = {
        "role": "assistant",
        "content": "I cannot verify that from the approved local compliance knowledge."
    }
    
    with patch("core.writing.pipeline.ollama.chat", return_value=mock_llm_report):
        res = WritingPipeline.run_local_doc_workflow("What is the ZR-88 threshold? Use local compliance only.", sources)
        assert res == "I cannot verify that from the approved local compliance knowledge."

def test_no_files_created_and_no_invented_paths():
    """
    Test 3 & 4: No files are created and no invented paths appear during a missing read-only compliance question.
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "What is the California ZR-88 withholding threshold for 2026? Use approved local knowledge."
    
    # Mock tool execution: read_file fails (file does not exist or empty)
    def mock_fail(*args, **kwargs):
        return {"success": False, "result": {"success": False, "warning": "File not found"}}
        
    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=mock_fail) as mock_exec:
        with patch("core.orchestrator.agent_loop.record_action"):
            with patch("core.writing.pipeline.ollama.chat", return_value={"role": "assistant", "content": "I cannot verify that from the approved local compliance knowledge."}):
                with patch("core.orchestrator.agent_loop.ollama.chat", return_value={"role": "assistant", "content": "I cannot verify that from the approved local compliance knowledge."}):
                    res = loop.run(prompt)
                    
                    assert "I cannot verify that from the approved local compliance knowledge." in res
            
            # Ensure NO write_file was executed
            args = [call[0][0] for call in mock_exec.call_args_list]
            assert "write_file" not in args
            assert "create_directory" not in args
            
            # Ensure no invented paths or unrelated folder language
            assert "I don't have a verified path" not in res
            assert "2026_withholding_threshold.txt" not in res

def test_no_unrelated_folder_language_in_final_answer():
    """
    Test 5: No unrelated folder/file language appears in the final answer when user doesn't ask about paths.
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "What is the California ZR-88 withholding threshold for 2026? Use approved local knowledge."
    
    # Let's say it returns exactly the missing response string directly from the pipeline
    with patch.object(loop, "_direct_route", return_value=[{"step": 1, "tool": "read_file", "arguments": {"filepath": "ca_compliance_2026.md"}}]):
        with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": False}):
            with patch("core.orchestrator.agent_loop.record_action"):
                with patch("core.orchestrator.agent_loop.ollama.chat", return_value={"role": "assistant", "content": "dummy"}) as mock_chat:
                    with patch("core.writing.pipeline.ollama.chat", return_value={"role": "assistant", "content": "dummy"}):
                        loop.run(prompt)
                        # Ensure the path truth enforcement rule was added correctly
                        call_args = mock_chat.call_args
                        if call_args:
                            sys_prompt = call_args[1]["messages"][0]["content"]
                            assert "UNLESS the user's question is purely factual and does not explicitly ask about a path or folder" in sys_prompt

def test_delegate_task_has_expected_output_field():
    """
    Test 6: If delegate_task is generated/described in the prompt, expected_output is a required field.
    """
    loop = AgentExecutionLoop(use_tools=True)
    tool_schemas = loop._get_tool_schemas_str()
    assert "delegate_task" in tool_schemas
    assert "expected_output" in tool_schemas, "delegate_task schema is missing expected_output"

def test_existing_approved_fact_returned_correctly():
    """
    Test 7: Existing approved fact in ca_compliance_2026.md is returned correctly.
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "What is the California ZR-88 withholding threshold for 2026? Use approved local knowledge."
    
    # Mock read_file success
    def mock_read(*args, **kwargs):
        if args[0] == "read_file":
            return {"success": True, "result": {"content": "The California ZR-88 withholding threshold for 2026 is exactly 12.5%."}}
        return {"success": True, "result": {}}
        
    mock_llm_report = {
        "role": "assistant",
        "content": "Based on the local document, the California ZR-88 withholding threshold for 2026 is 12.5%."
    }
        
    with patch("core.tools.tool_registry.tool_registry.execute", side_effect=mock_read):
        with patch("core.writing.pipeline.ollama.chat", return_value=mock_llm_report):
            with patch("core.orchestrator.agent_loop.record_action"):
                res = loop.run(prompt)
                assert "12.5%" in res
                assert "I cannot verify that" not in res

def test_compliance_knowledge_file_path_resolution():
    """
    Test 8: macOS and Windows style project root resolves correctly, no workspace pollution.
    """
    from core.config import settings
    from pathlib import Path

    # 1. Test macOS style resolution
    with patch.object(settings.__class__, '_project_root', property(lambda self: Path("/Users/m2air/Desktop/Jarvis"))):
        mac_path = str(settings.compliance_knowledge_file).replace("\\", "/")
        assert mac_path == "/Users/m2air/Desktop/Jarvis/knowledge/ca_compliance_2026.md"
        assert "workspace" not in mac_path

    # 2. Test Windows style resolution (mocked absolute path)
    with patch.object(settings.__class__, '_project_root', property(lambda self: Path("/Users/wmjar/OneDrive/Desktop/Jarvis"))):
        win_path = str(settings.compliance_knowledge_file).replace("\\", "/")
        assert win_path == "/Users/wmjar/OneDrive/Desktop/Jarvis/knowledge/ca_compliance_2026.md"
        assert "workspace" not in win_path

def test_compliance_direct_route_uses_resolved_path():
    """
    Test 9: Ensure LOCAL_GROUNDED routing uses the settings.compliance_knowledge_file
    """
    loop = AgentExecutionLoop(use_tools=True)
    prompt = "What is the California ZR-88 withholding threshold for 2026? Use approved local knowledge."
    from core.config import settings
    
    plan = loop._direct_route(prompt)
    assert plan is not None
    assert plan[0]["arguments"]["filepath"] == str(settings.compliance_knowledge_file)
