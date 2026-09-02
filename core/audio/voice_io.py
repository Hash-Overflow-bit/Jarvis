"""Testable voice input/output boundary for Jarvis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


class VoiceInputError(Exception):
    """Raised when microphone capture or transcription fails."""


class VoiceOutputError(Exception):
    """Raised when no real speech engine is available or playback fails."""


VoiceCommand = Literal["continue", "exit", "emergency"]


@dataclass(frozen=True)
class VoiceInput:
    text: str
    command: VoiceCommand = "continue"


class VoiceIO:
    """Coordinate injected microphone, STT, and TTS implementations."""

    _EXIT_COMMANDS = {"exit", "quit", "goodbye", "shut down", "stop jarvis"}

    def __init__(self, audio_device: Any, stt: Any, tts: Any, emergency_keyword: str):
        self.audio_device = audio_device
        self.stt = stt
        self.tts = tts
        self.emergency_keyword = self._normalize_command(emergency_keyword)

    @staticmethod
    def _normalize_command(text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
        return re.sub(r"\s+", " ", normalized).strip()

    def classify_command(self, text: str) -> VoiceCommand:
        """Match only complete commands; never exit on a substring in a sentence."""
        normalized = self._normalize_command(text)
        if normalized and normalized == self.emergency_keyword:
            return "emergency"
        if normalized in self._EXIT_COMMANDS:
            return "exit"
        return "continue"

    def listen(self) -> VoiceInput | None:
        """Capture one utterance and return clean text, or None for silence."""
        try:
            audio = self.audio_device.record_until_silence()
            if audio is None or getattr(audio, "size", 0) == 0:
                return None
            if not self.stt.is_speech(audio):
                return None
            text = self.stt.transcribe(audio).strip()
        except Exception as exc:
            raise VoiceInputError(f"Voice input failed: {exc}") from exc

        if not text:
            return None
        return VoiceInput(text=text, command=self.classify_command(text))

    def speak(self, text: str) -> None:
        """Speak text and fail clearly when only a console fallback exists."""
        if not text or not text.strip():
            return
        if not bool(getattr(self.tts, "is_available", False)):
            raise VoiceOutputError("No audio-capable TTS engine is available.")
        try:
            result = self.tts.speak(text)
        except Exception as exc:
            raise VoiceOutputError(f"Voice output failed: {exc}") from exc
        if result is False:
            raise VoiceOutputError("The TTS engine could not play the response.")
