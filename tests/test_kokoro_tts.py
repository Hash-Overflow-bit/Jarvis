"""
tests/test_kokoro_tts.py
========================
Unit tests for the KokoroTTS engine.
"""

import pytest
import sys
from pathlib import Path
from types import ModuleType
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
        mock_settings.kokoro_lang_code = "en-us"

        tts = KokoroTTS()

        import numpy as np
        mock_kokoro_inst = MagicMock()
        mock_kokoro_inst.create.return_value = (np.zeros(24000), 24000)

        sounddevice = ModuleType("sounddevice")
        sounddevice.play = MagicMock()
        sounddevice.wait = MagicMock()
        with patch("kokoro_onnx.Kokoro", return_value=mock_kokoro_inst):
            with patch.dict(sys.modules, {"sounddevice": sounddevice}):
                tts.speak("Hello British Emma")

                # Check that Kokoro was loaded and called with create()
                mock_kokoro_inst.create.assert_called_once_with(
                    "Hello British Emma",
                    voice="bf_emma",
                    speed=1.0,
                    lang="en-us"
                )
                # Check sd.play and sd.wait were called once (single create call)
                assert sounddevice.play.call_count == 1
                assert sounddevice.wait.call_count == 1


def test_kokoro_tts_synthesize(tmp_path):
    model_file = tmp_path / "model.onnx"
    voices_file = tmp_path / "voices.bin"
    model_file.touch()
    voices_file.touch()

    with patch("core.audio.tts.settings") as mock_settings:
        mock_settings.kokoro_voice_model = model_file
        mock_settings.kokoro_voices_file = voices_file
        mock_settings.kokoro_voice_id = "bf_emma"
        mock_settings.kokoro_lang_code = "en-us"

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
                lang="en-us"
            )
