"""
tests/test_confirmation_gate.py
===============================
Unit tests for the risk classification, confirmation gate, and dry run modes.
"""

import pytest
import os
import sys
from types import ModuleType
from unittest.mock import patch, MagicMock, AsyncMock
from core.safety.risk_classifier import risk_classifier, RiskLevel
from core.safety.confirmation_gate import confirmation_gate
from core.safety.dry_run_wrapper import dry_run_wrapper
from core.tools.tool_registry import tool_registry


def test_risk_classification():
    """Verify tool risk mapping matches the design specifications."""
    assert risk_classifier.get_risk_level("file_scanner") == RiskLevel.LOW
    assert risk_classifier.get_risk_level("directory_audit") == RiskLevel.LOW
    assert risk_classifier.get_risk_level("file_cleanup") == RiskLevel.HIGH
    assert risk_classifier.get_risk_level("git_clone") == RiskLevel.MEDIUM
    assert risk_classifier.get_risk_level("git_push") == RiskLevel.CRITICAL
    assert risk_classifier.get_risk_level("poetry_install") == RiskLevel.MEDIUM
    # Unknown tools default to MEDIUM risk
    assert risk_classifier.get_risk_level("unknown_action") == RiskLevel.MEDIUM


def test_should_confirm_by_safe_mode():
    """Verify decision rules for confirmation requests across safe modes."""
    # Test safe_mode = off
    with patch.dict(os.environ, {"SAFE_MODE": "off"}):
        assert not risk_classifier.should_confirm("file_cleanup")
        assert not risk_classifier.should_confirm("git_push")

    # Test safe_mode = strict/permissive (only confirm deletion tools)
    with patch.dict(os.environ, {"SAFE_MODE": "strict"}):
        assert not risk_classifier.should_confirm("file_scanner")  # LOW
        assert not risk_classifier.should_confirm("git_clone")     # MEDIUM
        assert not risk_classifier.should_confirm("git_push")      # CRITICAL
        assert risk_classifier.should_confirm("file_cleanup")      # HIGH (Deletion)


@pytest.mark.asyncio
async def test_text_confirmation_approval():
    """Verify that action succeeds when user approves via console text."""
    with patch("builtins.input", return_value="yes"):
        result = await confirmation_gate.confirm_action("file_cleanup", {}, mode="text")
        assert result is True

    with patch("builtins.input", return_value="no"):
        result = await confirmation_gate.confirm_action("file_cleanup", {}, mode="text")
        assert result is False


@pytest.mark.asyncio
async def test_audio_confirmation_approval():
    """Verify voice confirmation gate handles matching keywords correctly."""
    # Mock audio device & STT dependencies
    mock_audio = MagicMock()
    mock_audio.record_until_silence.return_value = MagicMock()
    
    mock_stt = MagicMock()
    mock_stt.is_speech.return_value = True
    mock_stt.transcribe.return_value = "yes proceed please"

    stt_module = ModuleType("core.audio.stt")
    stt_module.get_stt = MagicMock(return_value=mock_stt)
    tts_module = ModuleType("core.audio.tts")
    tts_module.get_tts_singleton = MagicMock(return_value=MagicMock())
    device_module = ModuleType("core.audio.audio_device")
    device_module.audio_device = mock_audio

    with patch.dict(
        sys.modules,
        {
            "core.audio.stt": stt_module,
            "core.audio.tts": tts_module,
            "core.audio.audio_device": device_module,
        },
    ):
        
        result = await confirmation_gate.confirm_action("git_push", {}, mode="audio")
        assert result is True
        
        # Test denial
        mock_stt.transcribe.return_value = "no cancel it"
        result = await confirmation_gate.confirm_action("git_push", {}, mode="audio")
        assert result is False


def test_deletion_request_requires_confirmation():
    """Verify that destructive file/directory actions and delegated deletion tasks require confirmation."""
    with patch.dict(os.environ, {"SAFE_MODE": "strict"}):
        assert risk_classifier.should_confirm("file_cleanup")
        assert risk_classifier.should_confirm("delete_directory")
        assert risk_classifier.should_confirm("delete_file")
        assert risk_classifier.should_confirm("delegate_task", {"task_description": "Delete the smoke_test folder from Desktop"})
        assert risk_classifier.should_confirm("delegate_task", {"task_description": "Remove temp files"})


def test_confirmation_denial_halts_agent_execution(tmp_path):
    """Verify disabled destructive tools cannot delete a workspace folder."""
    from core.orchestrator.agent_loop import AgentExecutionLoop
    from core.config import settings

    test_folder = tmp_path / "smoke_test_safety_verify"
    test_folder.mkdir(exist_ok=True)
    assert test_folder.exists()

    with patch.object(
        settings.__class__, "default_workspace_dir", property(lambda self: tmp_path)
    ):
        loop = AgentExecutionLoop()
        with patch("builtins.input") as confirm:
            res = loop.run(f"Delete the folder {test_folder}")

    confirm.assert_not_called()
    assert "rejected" in res.lower() or "unregistered" in res.lower()
    assert test_folder.exists(), "An unregistered deletion tool must not delete anything."
