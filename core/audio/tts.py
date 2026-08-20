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

        # Use a temporary file to avoid subprocess pipe buffer deadlocks on Windows
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        cmd = [
            str(self.binary_path),
            "--model", str(self.voice_model),
            "--output_file", str(temp_path),
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
                if temp_path.exists():
                    temp_path.unlink()
                raise TTSError(f"Piper failed (exit {result.returncode}): {stderr}")
            
            if temp_path.exists():
                wav_bytes = temp_path.read_bytes()
                temp_path.unlink()
                return wav_bytes
            else:
                raise TTSError("Piper finished but output file was not created.")
        except subprocess.TimeoutExpired:
            if temp_path.exists():
                temp_path.unlink()
            raise TTSError("Piper TTS timed out after 30 seconds.")
        except FileNotFoundError:
            if temp_path.exists():
                temp_path.unlink()
            raise TTSError(
                f"Piper binary not executable at '{self.binary_path}'. "
                "Check file permissions and download the correct binary for your OS."
            )
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise TTSError(f"TTS synthesis failed: {e}")

    def synthesize_to_file(self, text: str, output_path: Path) -> Path:
        """Synthesize text and save as WAV file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wav_bytes = self.synthesize(text)
        output_path.write_bytes(wav_bytes)
        return output_path

class KokoroTTS:
    """
    Wrapper around kokoro-onnx for local, high-quality, streaming TTS.
    """

    def __init__(self):
        self.model_path = settings.kokoro_voice_model
        self.voices_path = settings.kokoro_voices_file
        self.voice_id = settings.kokoro_voice_id
        self.lang_code = settings.kokoro_lang_code
        self._available = self._check_availability()
        self.kokoro = None

    def _check_availability(self) -> bool:
        if self.model_path is None or self.voices_path is None:
            return False
        return Path(self.model_path).exists() and Path(self.voices_path).exists()

    def _ensure_loaded(self):
        if self.kokoro is None:
            import os
            if "PHONEMIZER_ESPEAK_LIBRARY" not in os.environ:
                for candidate in [
                    "/opt/homebrew/lib/libespeak-ng.dylib",
                    "/opt/homebrew/lib/libespeak.dylib",
                    "/usr/local/lib/libespeak-ng.dylib",
                    "/usr/local/lib/libespeak.dylib",
                ]:
                    if Path(candidate).exists():
                        os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = candidate
                        break

            from kokoro_onnx import Kokoro
            self.kokoro = Kokoro(str(self.model_path), str(self.voices_path))

    def speak(self, text: str) -> None:
        if not text or not text.strip():
            return

        if not self._available:
            if settings.log_level == "DEBUG":
                print(f"[JARVIS]: {text}")
            return

        try:
            self._ensure_loaded()
            import sounddevice as sd

            # Use synchronous create() — simpler and avoids all async/nest_asyncio issues
            samples, sr = self.kokoro.create(
                text,
                voice=self.voice_id,
                speed=1.0,
                lang=self.lang_code
            )
            sd.play(samples, sr)
            sd.wait()
        except Exception as e:
            print(f"[TTS] Kokoro speak failed: {e}")
            print(f"[JARVIS]: {text}")

    def synthesize(self, text: str) -> bytes:
        """Synthesizes text and returns WAV bytes (required for API compatibility)."""
        self._ensure_loaded()
        import io
        import soundfile as sf
        
        samples, sr = self.kokoro.create(
            text,
            voice=self.voice_id,
            speed=1.0,
            lang=self.lang_code
        )
        
        buffer = io.BytesIO()
        sf.write(buffer, samples, sr, format="WAV")
        return buffer.getvalue()

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


def get_tts():
    """
    Returns the best available TTS:
    - KokoroTTS if configured and voice model files exist.
    - PiperTTS if configured and binary/voice model files exist.
    - ConsoleTTS as fallback.
    """
    if settings.tts_engine == "kokoro":
        kokoro = KokoroTTS()
        if kokoro.is_available:
            return kokoro
        print("[TTS] Kokoro configuration requested, but voice assets are missing. Falling back...")

    piper = PiperTTS()
    if piper.is_available:
        return piper
    print("[TTS] Piper and Kokoro not available — using console fallback (text-only mode).")
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
