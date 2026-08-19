"""
tests/test_kokoro_tts.py
========================
Unit tests for the KokoroTTS engine.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.audio.tts import KokoroTTS, get_tts, ConsoleTTS


def test_kokoro_tts_availability(tmp_path):
    # Mock settings paths
    with patch("core.audio.tts.settings") as mock_settings:
        mock_settings.kokoro_voice_model = tmp_path / "model.onnx"
        mock_settings.kokoro_voices_file = tmp_path / "voices.bin"
        
        tts = KokoroTTS()
        assert tts.is_available is False
        
        # Create dummy files
        mock_settings.kokoro_voice_model.touch()
        mock_settings.kokoro_voices_file.touch()
        
        tts_ok = KokoroTTS()
        assert tts_ok.is_available is True


def test_kokoro_tts_speak(tmp_path):
    model_file = tmp_path / "model.onnx"
    voices_file = tmp_path / "voices.bin"
    model_file.touch()
    voices_file.touch()

    with patch("core.audio.tts.settings") as mock_settings:
        mock_settings.kokoro_voice_model = model_file
        mock_settings.kokoro_voices_file = voices_file
        mock_settings.kokoro_voice_id = "bf_emma"
        mock_settings.kokoro_lang_code = "b"

        tts = KokoroTTS()
        
        # Mock Kokoro create_stream generator
        mock_stream = [
            (MagicMock(), 24000),
            (MagicMock(), 24000)
        ]
        
        mock_kokoro_inst = MagicMock()
        mock_kokoro_inst.create_stream.return_value = mock_stream

        with patch("kokoro_onnx.Kokoro", return_value=mock_kokoro_inst):
            with patch("sounddevice.play") as mock_play, patch("sounddevice.wait") as mock_wait:
                tts.speak("Hello British Emma")
                
                # Check that Kokoro was loaded and called
                mock_kokoro_inst.create_stream.assert_called_once_with(
                    "Hello British Emma",
                    voice="bf_emma",
                    speed=1.0,
                    lang="b"
                )
                # Check sd.play and sd.wait were called twice
                assert mock_play.call_count == 2
                assert mock_wait.call_count == 2


def test_kokoro_tts_synthesize(tmp_path):
    model_file = tmp_path / "model.onnx"
    voices_file = tmp_path / "voices.bin"
    model_file.touch()
    voices_file.touch()

    with patch("core.audio.tts.settings") as mock_settings:
        mock_settings.kokoro_voice_model = model_file
        mock_settings.kokoro_voices_file = voices_file
        mock_settings.kokoro_voice_id = "bf_emma"
        mock_settings.kokoro_lang_code = "b"

        tts = KokoroTTS()
        
        mock_kokoro_inst = MagicMock()
        import numpy as np
        # Yield single-channel silence
        mock_kokoro_inst.create.return_value = (np.zeros(24000), 24000)

        with patch("kokoro_onnx.Kokoro", return_value=mock_kokoro_inst):
            res = tts.synthesize("Test synthesize")
            assert isinstance(res, bytes)
            assert len(res) > 0
            mock_kokoro_inst.create.assert_called_once_with(
                "Test synthesize",
                voice="bf_emma",
                speed=1.0,
                lang="b"
            )
