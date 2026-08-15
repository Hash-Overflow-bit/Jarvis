"""
core/audio/tts.py
=================
Text-to-Speech wrapper using Piper TTS (local, offline).

How Piper works:
- Piper is a standalone binary (not a Python library).
- We call it via subprocess: `piper --model <voice.onnx> < text | audio output`
- Piper reads text from stdin and writes WAV audio to stdout.
- We capture stdout as bytes and play it directly through the speaker.

Cross-platform:
- The binary path differs between macOS and Windows (set in .env).
- The voice model file (.onnx) is the same on both platforms.
- Download piper binary: https://github.com/rhasspy/piper/releases
- Download voice models: https://huggingface.co/rhasspy/piper-voices

Fallback:
- If Piper is not installed, falls back to printing text to console (dev mode).
- On Windows, can also fall back to edge-tts (cloud) if configured.
"""

import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from core.config import settings
from core.audio.audio_device import audio_device, AudioDeviceError


class TTSError(Exception):
    """Raised when text-to-speech fails."""
    pass


class PiperTTS:
    """
    Wrapper around the Piper TTS binary for local, offline speech synthesis.

    Usage:
        tts = PiperTTS()
        tts.speak("Hello, I am Jarvis.")
    """

    def __init__(
        self,
        binary_path: Optional[Path] = None,
        voice_model: Optional[Path] = None,
    ):
        self.binary_path = binary_path or settings.piper_binary_path
        self.voice_model = voice_model or settings.piper_voice_model
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        """Check if Piper binary and voice model exist."""
        if self.binary_path is None:
            return False
        if not Path(self.binary_path).exists():
            # Try finding piper in PATH
            found = shutil.which("piper")
            if found:
                self.binary_path = Path(found)
                return True
            return False
        if self.voice_model and not Path(self.voice_model).exists():
            print(f"[TTS] Warning: Voice model not found at {self.voice_model}")
            print(f"[TTS] Download from: https://huggingface.co/rhasspy/piper-voices")
            return False
        return True

    # ------------------------------------------------------------------
    # Core speak method
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """
        Convert text to speech and play it through the speaker.

        Args:
            text: The text to speak. Long texts are handled fine by Piper.

        If Piper is not available, prints to console as fallback.
        """
        if not text or not text.strip():
            return

        if not self._available:
            # Graceful fallback: print to console
            if settings.log_level == "DEBUG":
                print(f"[JARVIS]: {text}")
            return

        try:
            wav_bytes = self.synthesize(text)
            audio_device.play_wav_bytes(wav_bytes)
        except (TTSError, AudioDeviceError) as e:
            # Log but don't crash — fallback to print
            if settings.log_level == "DEBUG":
                print(f"[TTS] Error during speech: {e}")
                print(f"[JARVIS]: {text}")

    def synthesize(self, text: str) -> bytes:
        """
        Run Piper and return WAV bytes without playing them.
        Useful for saving audio to file or streaming.

        Args:
            text: Text to synthesize.

        Returns:
            WAV audio as bytes.

        Raises:
            TTSError: If Piper fails or is not installed.
        """
        if not self._available:
            raise TTSError(
                f"Piper TTS binary not found at '{self.binary_path}'. "
                "Download from: https://github.com/rhasspy/piper/releases"
            )

        cmd = [
            str(self.binary_path),
            "--model", str(self.voice_model),
            "--output-raw",    # Output raw PCM (no WAV header) → we wrap it
        ]

        # Use --output-file - to get WAV to stdout instead
        cmd = [
            str(self.binary_path),
            "--model", str(self.voice_model),
            "--output_file", "-",  # Write WAV to stdout
        ]

        try:
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")
                raise TTSError(f"Piper failed (exit {result.returncode}): {stderr}")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise TTSError("Piper TTS timed out after 30 seconds.")
        except FileNotFoundError:
            raise TTSError(
                f"Piper binary not executable at '{self.binary_path}'. "
                "Check file permissions and download the correct binary for your OS."
            )

    def synthesize_to_file(self, text: str, output_path: Path) -> Path:
        """Synthesize text and save as WAV file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wav_bytes = self.synthesize(text)
        output_path.write_bytes(wav_bytes)
        return output_path

    @property
    def is_available(self) -> bool:
        return self._available


class ConsoleTTS:
    """
    Fallback TTS that just prints to console.
    Used in text-only mode or when Piper is not installed.
    Always available.
    """

    def speak(self, text: str) -> None:
        if text and text.strip():
            print(f"\n🤖 JARVIS: {text}\n")

    def synthesize(self, text: str) -> bytes:
        raise TTSError("ConsoleTTS cannot synthesize audio.")

    @property
    def is_available(self) -> bool:
        return True


def get_tts() -> PiperTTS | ConsoleTTS:
    """
    Returns the best available TTS:
    - PiperTTS if the binary and model are configured and found.
    - ConsoleTTS as fallback (text-only mode).
    """
    piper = PiperTTS()
    if piper.is_available:
        return piper
    print("[TTS] Piper not available — using console fallback (text-only mode).")
    return ConsoleTTS()


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------
_tts_instance = None

def get_tts_singleton():
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = get_tts()
    return _tts_instance
