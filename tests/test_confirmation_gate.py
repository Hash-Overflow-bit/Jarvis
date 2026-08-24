"""
tests/test_confirmation_gate.py
===============================
Unit tests for the risk classification, confirmation gate, and dry run modes.
"""

import pytest
import os
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

    with patch("core.audio.audio_device.audio_device", mock_audio), \
         patch("core.audio.stt.get_stt", return_value=mock_stt), \
         patch("core.audio.tts.get_tts_singleton") as mock_tts:
        
        result = await confirmation_gate.confirm_action("git_push", {}, mode="audio")
        assert result is True
        
        # Test denial
        mock_stt.transcribe.return_value = "no cancel it"
        result = await confirmation_gate.confirm_action("git_push", {}, mode="audio")
        assert result is False
