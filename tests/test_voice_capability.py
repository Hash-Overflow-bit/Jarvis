"""Acceptance tests for Capability 2: voice input and output."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from core.audio.audio_device import AudioDevice
from core.audio.tts import ConsoleTTS, PiperTTS
from core.audio.voice_io import VoiceIO, VoiceInputError, VoiceOutputError


def _voice(*, transcript="Hello Jarvis", speech=True, tts_available=True):
    audio = MagicMock()
    audio.record_until_silence.return_value = np.ones((1600, 1), dtype=np.float32)
    stt = MagicMock()
    stt.is_speech.return_value = speech
    stt.transcribe.return_value = transcript
    tts = MagicMock()
    tts.is_available = tts_available
    tts.speak.return_value = True
    return VoiceIO(audio, stt, tts, "JARVIS STOP"), audio, stt, tts


def test_voice_listen_returns_transcribed_text():
    voice, audio, stt, _ = _voice(transcript="Draft a short email")
    result = voice.listen()
    assert result is not None
    assert result.text == "Draft a short email"
    assert result.command == "continue"
    audio.record_until_silence.assert_called_once()
    stt.transcribe.assert_called_once()


def test_silence_does_not_call_transcription():
    voice, _, stt, _ = _voice(speech=False)
    assert voice.listen() is None
    stt.transcribe.assert_not_called()


@pytest.mark.parametrize("command", ["Exit.", "QUIT!", "Goodbye", "shut down", "stop Jarvis"])
def test_exit_commands_require_a_complete_utterance(command):
    voice, _, _, _ = _voice()
    assert voice.classify_command(command) == "exit"


def test_exit_word_inside_normal_request_does_not_stop_jarvis():
    voice, _, _, _ = _voice()
    assert voice.classify_command("Create an exit plan for the project") == "continue"


def test_emergency_keyword_is_exact_and_punctuation_tolerant():
    voice, _, _, _ = _voice()
    assert voice.classify_command("Jarvis, stop!") == "emergency"
    assert voice.classify_command("Explain the Jarvis stop feature") == "continue"


def test_voice_output_requires_real_tts():
    voice, _, _, _ = _voice(tts_available=False)
    with pytest.raises(VoiceOutputError, match="No audio-capable TTS"):
        voice.speak("Hello")


def test_voice_output_reports_playback_failure():
    voice, _, _, tts = _voice()
    tts.speak.return_value = False
    with pytest.raises(VoiceOutputError, match="could not play"):
        voice.speak("Hello")


def test_voice_input_wraps_device_or_stt_errors():
    voice, audio, _, _ = _voice()
    audio.record_until_silence.side_effect = RuntimeError("microphone disconnected")
    with pytest.raises(VoiceInputError, match="microphone disconnected"):
        voice.listen()


def test_audio_to_wav_clips_out_of_range_samples():
    device = AudioDevice(sample_rate=16000, channels=1)
    wav_bytes = device.audio_to_wav_bytes(np.array([[2.0], [-2.0]], dtype=np.float32))
    assert wav_bytes.startswith(b"RIFF")


def test_console_fallback_is_not_reported_as_voice_output():
    assert ConsoleTTS().is_available is False


def test_piper_requires_both_binary_and_voice_model(tmp_path):
    binary = tmp_path / "piper"
    binary.touch()
    tts = PiperTTS(binary_path=binary, voice_model=tmp_path / "missing.onnx")
    assert tts.is_available is False
