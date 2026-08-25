"""
tests/test_agent_loop.py
========================
Unit tests for the AgentExecutionLoop orchestrator.
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings


def test_agent_loop_generate_plan():
    loop = AgentExecutionLoop()
    
    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "file_scanner",
                    "arguments": {"directory": "/sandbox"}
                }
            ]
        })
    }
    
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_plan_res) as mock_chat:
        plan = loop._generate_plan("Scan the sandbox folder", "No facts")
        assert len(plan) == 1
        assert plan[0]["tool"] == "file_scanner"
        assert plan[0]["arguments"] == {"directory": "/sandbox"}


def test_agent_loop_generate_plan_native_fallback():
    loop = AgentExecutionLoop()
    
    # Mocking native function tool_calls dictionary format
    mock_native_res = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "directory_audit",
                    "arguments": {"directory": "/sandbox/folder"}
                }
            }
        ]
    }
    
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_native_res) as mock_chat:
        plan = loop._generate_plan("Audit folder", "")
        assert len(plan) == 1
        assert plan[0]["tool"] == "directory_audit"
        assert plan[0]["arguments"] == {"directory": "/sandbox/folder"}


def test_agent_loop_reflect_and_replan():
    loop = AgentExecutionLoop()
    
    mock_reflection_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "create_directory",
                    "arguments": {"directory": "/sandbox/fixed"}
                }
            ]
        })
    }
    
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_reflection_res) as mock_chat:
        revised = loop._reflect_and_replan(
            user_goal="Create a folder",
            failed_step={"step": 1, "tool": "create_directory", "arguments": {"directory": "/bad_path"}},
            error_message="Permission Denied",
            completed_steps=[]
        )
        assert len(revised) == 1
        assert revised[0]["tool"] == "create_directory"
        assert revised[0]["arguments"] == {"directory": "/sandbox/fixed"}


def test_agent_loop_execution_success():
    loop = AgentExecutionLoop()
    
    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "file_scanner",
                    "arguments": {"directory": "/sandbox"}
                }
            ]
        })
    }
    
    mock_tool_res = {
        "success": True,
        "result": {"files": ["file1.txt"]}
    }
    
    mock_synth_res = {
        "role": "assistant",
        "content": "I successfully scanned the folder and found file1.txt."
    }
    
    # Mock calls sequentially
    mock_chat_responses = [mock_plan_res, mock_synth_res]
    
    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=mock_chat_responses):
        with patch("core.orchestrator.agent_loop.tool_registry.execute", return_value=mock_tool_res) as mock_exec:
            res = loop.run("Scan files")
            assert "file1.txt" in res
            # Since /sandbox is auto-fixed to the workspace directory by the sanitizer,
            # we must expect the fixed path, not the raw /sandbox path.
            from core.config import settings
            expected_path = str(settings.default_workspace_dir).replace("\\", "/").rstrip("/") + "/"
            mock_exec.assert_called_once_with("file_scanner", {"directory": expected_path}, mode="text")


def test_agent_loop_execution_with_reflection():
    loop = AgentExecutionLoop()
    
    # Step 1: initial plan
    mock_plan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "write_file",
                    "arguments": {"filepath": "/bad/file.txt", "content": "hello"}
                }
            ]
        })
    }
    
    # Step 2: tool execution failure (returns success=False)
    mock_failed_exec = {
        "success": False,
        "error": "PermissionError"
    }
    
    # Step 3: reflector replanning
    mock_replan_res = {
        "role": "assistant",
        "content": json.dumps({
            "plan": [
                {
                    "step": 1,
                    "tool": "write_file",
                    "arguments": {"filepath": "/workspace/file.txt", "content": "hello"}
                }
            ]
        })
    }
    
    # Step 4: tool execution success (returns success=True)
    mock_success_exec = {
        "success": True,
        "result": {"message": "success"}
    }
    
    # Step 5: final synthesis
    mock_synth_res = {
        "role": "assistant",
        "content": "Fixed and written successfully."
    }
    
    mock_chat_responses = [mock_plan_res, mock_replan_res, mock_synth_res]
    mock_tool_responses = [mock_failed_exec, mock_success_exec]
    
    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=mock_chat_responses):
        with patch("core.orchestrator.agent_loop.tool_registry.execute", side_effect=mock_tool_responses) as mock_exec:
            res = loop.run("Save hello to file")
            assert "written successfully" in res
            assert mock_exec.call_count == 2


def test_agent_loop_sanitizer_auto_remap_subagent():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "LedgerBookkeeper",
            "arguments": {"task": "Scan transactions"}
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "delegate_task"
    assert sanitized[0]["arguments"]["agent_name"] == "LedgerBookkeeper"
    assert sanitized[0]["arguments"]["task_description"] == "Scan transactions"


def test_agent_loop_sanitizer_reject_invalid_tool():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "csv_parser",
            "arguments": {}
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 0


def test_agent_loop_tool_call_leakage_recovery():
    loop = AgentExecutionLoop()
    # Mock LLM returning a raw tool call string in fallback mode
    mock_chat_res = {
        "role": "assistant",
        "content": 'Jarvis: {"name": "write_file", "parameters": {"filepath": "agents/test_leak.json", "content": "{\\"role\\": \\"CEO\\"}"}}'
    }

    mock_empty_plan = {
        "role": "assistant",
        "content": ""
    }

    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=[mock_empty_plan, mock_chat_res]):
        with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": True, "result": {}}) as mock_exec:
            res = loop.run("Create agents/test_leak.json containing role CEO")
            assert "Successfully executed 'write_file'" in res
            assert "agents/test_leak.json" in res
            mock_exec.assert_called_once_with("write_file", {"filepath": "agents/test_leak.json", "content": '{"role": "CEO"}'})


def test_agent_loop_sanitizer_toolkit_prefix_stripping():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "FileManagementToolkit.list_dir",
            "arguments": {"folder_path": "/Users/m2air/Desktop"}
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "list_dir"


def test_agent_loop_sanitizer_auto_populate_agent_builder_fields():
    loop = AgentExecutionLoop()
    raw_plan = [
        {
            "step": 1,
            "tool": "agent_builder",
            "arguments": {
                "name": "QuickBookkeeperAgent",
                "tools": ["read_file", "write_file"]
            }
        }
    ]
    sanitized = loop._sanitize_plan(raw_plan)
    assert len(sanitized) == 1
    assert sanitized[0]["tool"] == "agent_builder"
    assert "role" in sanitized[0]["arguments"]
    assert "goal" in sanitized[0]["arguments"]
    assert "backstory" in sanitized[0]["arguments"]


def test_agent_loop_exec_board_config_auto_writer():
    loop = AgentExecutionLoop()
    mock_chat_res = {
        "role": "assistant",
        "content": '''{
 "executive board_config": {
   "CEO": {"role": "Chief Executive Officer"},
   "PM": {"role": "Project Manager"}
 },
 "config files_created": [
   {"file_name": "CEO_config.json"},
   {"file_name": "PM_config.json"}
 ]
}'''
    }
    mock_empty_plan = {
        "role": "assistant",
        "content": ""
    }

    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=[mock_empty_plan, mock_chat_res]):
        with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": True, "result": {}}) as mock_exec:
            res = loop.run("Generate executive board configuration files")
            assert "Successfully generated and saved" in res
            assert "CEO_config.json" in res
            assert mock_exec.call_count == 2


def test_agent_loop_tool_call_leakage_recovery_directory():
    loop = AgentExecutionLoop()
    mock_chat_res = {
        "role": "assistant",
        "content": 'Jarvis: {"name": "create_directory", "parameters": {"directory": "/Users/m2air/Desktop/test1122"}}'
    }
    mock_empty_plan = {
        "role": "assistant",
        "content": ""
    }

    with patch("core.orchestrator.agent_loop.ollama.chat", side_effect=[mock_empty_plan, mock_chat_res]):
        with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": True, "result": {}}) as mock_exec:
            res = loop.run("Please set up directory /Users/m2air/Desktop/test1122")
            assert "Successfully executed 'create_directory'" in res
            mock_exec.assert_called_once_with("create_directory", {"directory": "/Users/m2air/Desktop/test1122"})


from unittest.mock import patch, MagicMock, PropertyMock


def test_agent_loop_windows_path_normalization(tmp_path):
    """
    Requirements 8 & 9:
    1. Input Windows workspace path is preserved in _sanitize_plan without rewriting to /home/wmjar/...
    2. create_directory executes and physically creates the folder on disk.
    """
    loop = AgentExecutionLoop()
    target_dir = tmp_path / "workspace" / "automation_demo"

    raw_plan = [
        {
            "step": 1,
            "tool": "create_directory",
            "arguments": {"directory": str(target_dir)}
        }
    ]

    with patch.object(type(settings), "desktop_dir", new_callable=PropertyMock, return_value=tmp_path):
        with patch.object(type(settings), "default_workspace_dir", new_callable=PropertyMock, return_value=tmp_path / "workspace"):
            sanitized = loop._sanitize_plan(raw_plan, "create a local project folder named automation_demo")
            assert len(sanitized) == 1
            assert "home/wmjar" not in sanitized[0]["arguments"]["directory"].replace("\\", "/")
            assert "automation_demo" in sanitized[0]["arguments"]["directory"]

            # Verify create_directory tool execution physically creates directory
            from core.tools.create_directory import CreateDirectory
            from schemas.create_directory_schema import CreateDirectoryInput
            tool = CreateDirectory()
            res = tool.run(CreateDirectoryInput(directory=str(target_dir)))
            assert res.success is True
            assert target_dir.exists()


def test_agent_loop_wsl_path_conversion_on_windows(tmp_path):
    """
    Requirement 9:
    WSL-style /mnt/c/... input path is converted to Windows drive path C:/... on Windows,
    and NOT converted to /home/wmjar/...
    """
    loop = AgentExecutionLoop()
    wsl_input_path = "/mnt/c/Users/wmjar/OneDrive/Desktop/automation_demo"

    raw_plan = [
        {
            "step": 1,
            "tool": "create_directory",
            "arguments": {"directory": wsl_input_path}
        }
    ]

    with patch.object(type(settings), "is_windows", new_callable=PropertyMock, return_value=True):
        with patch.object(type(settings), "desktop_dir", new_callable=PropertyMock, return_value=tmp_path):
            with patch.object(type(settings), "default_workspace_dir", new_callable=PropertyMock, return_value=tmp_path / "workspace"):
                sanitized = loop._sanitize_plan(raw_plan, "create folder /mnt/c/Users/wmjar/OneDrive/Desktop/automation_demo")
                assert len(sanitized) == 1
                sanitized_dir = sanitized[0]["arguments"]["directory"].replace("\\", "/")
                assert not sanitized_dir.startswith("/home/wmjar")
                assert sanitized_dir.startswith("C:")
                assert "automation_demo" in sanitized_dir


def test_agent_loop_folder_name_parsing():
    """
    Regression Test for Bug 1:
    Ensure folder extraction extracts 'automation_demo' and NEVER the literal word 'named' or 'called'.
    """
    loop = AgentExecutionLoop()
    inputs = [
        "create a local project folder named automation_demo",
        "create folder called automation_demo",
        "create automation_demo folder",
        "create project folder automation_demo"
    ]
    for inp in inputs:
        route = loop._direct_route(inp)
        assert route is not None, f"Direct route failed for: {inp}"
        target_dir = route[0]["arguments"]["directory"]
        assert "automation_demo" in target_dir
        assert "named" not in target_dir.lower()
        assert "called" not in target_dir.lower()


def test_agent_loop_synthesis_no_unexecuted_file_claims():
    """
    Regression Test for Bug 2:
    When user requests creation of a directory + 3 files, but execution ONLY completes directory creation,
    _synthesize_final_response MUST NOT claim any requested files were created.
    """
    loop = AgentExecutionLoop()
    user_req = "Create automation_demo and inside it business_script.txt, workflow_background.png, and automation_summary.md"
    completed_steps = [
        {"step": 1, "tool": "create_directory", "arguments": {"directory": "/workspace/automation_demo"}}
    ]

    mock_llm_synth = {
        "role": "assistant",
        "content": "I created the directory /workspace/automation_demo."
    }

    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_llm_synth):
        res = loop._synthesize_final_response(user_req, completed_steps, "")
        res_lower = res.lower()
        assert "business_script" not in res_lower
        assert "workflow_background" not in res_lower
        assert "automation_summary" not in res_lower
        assert "automation_demo" in res_lower


def test_agent_loop_desktop_as_universal_default(tmp_path):
    """
    Requirements 1-8:
    Verify Desktop is the universal default destination for user-created local files and folders.
    1. Input: 'Create a folder named automation_demo' -> <settings.desktop_dir>/automation_demo
    2. Input: 'Create automation_demo and write report.md inside it' -> <settings.desktop_dir>/automation_demo/report.md
    3. Input: 'Create test.txt' -> <settings.desktop_dir>/test.txt
    4. Replanning keeps the exact same canonical Desktop path.
    """
    loop = AgentExecutionLoop()
    desktop_dir = tmp_path / "Desktop"
    desktop_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(type(settings), "desktop_dir", new_callable=PropertyMock, return_value=desktop_dir):
        # Case 1: Folder creation
        route1 = loop._direct_route("Create a folder named automation_demo")
        assert route1 is not None
        expected_dir = str(desktop_dir / "automation_demo")
        assert route1[0]["arguments"]["directory"] == expected_dir

        # Case 2: Multi-step plan with file inside folder
        raw_plan = [
            {"step": 1, "tool": "create_directory", "arguments": {"directory": "automation_demo"}},
            {"step": 2, "tool": "write_file", "arguments": {"filepath": "automation_demo/report.md", "content": "Hello"}}
        ]
        sanitized2 = loop._sanitize_plan(raw_plan, "Create automation_demo and write report.md inside it")
        assert len(sanitized2) == 2
        assert sanitized2[0]["arguments"]["directory"] == str(desktop_dir / "automation_demo")
        assert sanitized2[1]["arguments"]["filepath"] == str(desktop_dir / "automation_demo" / "report.md")

        # Case 3: Simple file creation
        route3 = loop._direct_route("Create test.txt")
        assert route3 is not None
        assert route3[0]["arguments"]["filepath"] == str(desktop_dir / "test.txt")

        # Case 4: Replanning / reflection preserves Desktop root
        failed_step = {"step": 2, "tool": "write_file", "arguments": {"filepath": "automation_demo/report.md"}}
        replan_raw = [
            {"step": 1, "tool": "write_file", "arguments": {"filepath": "automation_demo/report.md", "content": "Retry content"}}
        ]
        mock_replan_res = {"role": "assistant", "content": json.dumps({"plan": replan_raw})}
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_replan_res):
            revised_plan = loop._reflect_and_replan(
                "Create automation_demo and write report.md inside it",
                failed_step,
                "Permission denied",
                [sanitized2[0]]
            )
            sanitized_replan = loop._sanitize_plan(revised_plan, "Create automation_demo and write report.md inside it")
            assert len(sanitized_replan) == 1
            assert sanitized_replan[0]["arguments"]["filepath"] == str(desktop_dir / "automation_demo" / "report.md")


def test_agent_loop_session_isolation():
    """
    Regression Test for Session Isolation:
    Turn 1: 'Create yeah.txt with Hello Jsss' executes write_file.
    Turn 2: 'Start a new interview and ask me one question about my current professional role.'
    Expected Turn 2:
    - plan is empty / conversational fallback
    - response contains NO mention of 'yeah.txt', 'Hello Jsss', file paths, or execution summaries
    - response contains interview question about professional role.
    """
    from core.state.session_manager import SessionManager
    session = SessionManager(use_tools=True)

    # Turn 1: Tool execution
    with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": True, "result": {"message": "Created"}}):
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value={"role": "assistant", "content": "I created yeah.txt with Hello Jsss."}):
            res1 = session.chat("Create yeah.txt with Hello Jsss")
            assert "yeah.txt" in res1

    # Turn 2: Isolated interview prompt
    mock_interview_response = {
        "role": "assistant",
        "content": "What is your current professional role and what are your main responsibilities?"
    }
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_interview_response):
        res2 = session.chat("Start a new interview and ask me one question about my current professional role.")
        res2_lower = res2.lower()
        assert "yeah.txt" not in res2_lower
        assert "hello jsss" not in res2_lower
        assert "completed" not in res2_lower
        assert "executed" not in res2_lower
        assert "role" in res2_lower or "question" in res2_lower or "professional" in res2_lower


def test_conversational_plan_empty_immediately_after_tool_execution():
    """
    Verify a conversational plan=[] turn immediately after a tool execution turn
    does not synthesize previous completed steps.
    """
    from core.orchestrator.agent_loop import AgentExecutionLoop
    history = []
    loop = AgentExecutionLoop(use_tools=True, history=history)

    # Turn 1: tool execution
    with patch("core.tools.tool_registry.tool_registry.execute", return_value={"success": True, "result": {}}):
        with patch("core.orchestrator.agent_loop.ollama.chat", return_value={"role": "assistant", "content": "File created."}):
            res1 = loop.run("Create test12.txt with Hello World")
            assert "test12.txt" in res1 or "created" in res1.lower()

    # Turn 2: conversational inquiry
    mock_conv_reply = {"role": "assistant", "content": "I am online and ready to assist you."}
    with patch("core.orchestrator.agent_loop.ollama.chat", return_value=mock_conv_reply):
        res2 = loop.run("Are you online?")
        assert "test12.txt" not in res2
        assert "created" not in res2.lower()
        assert "online" in res2.lower()

