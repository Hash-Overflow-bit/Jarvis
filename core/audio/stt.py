"""
core/audio/stt.py
=================
Speech-to-Text wrapper using faster-whisper.

Cross-platform:
- macOS:   WHISPER_DEVICE=cpu, WHISPER_COMPUTE_TYPE=int8
- Windows: WHISPER_DEVICE=cuda, WHISPER_COMPUTE_TYPE=float16
Both are configured via .env — no code changes needed between platforms.

Model sizes — matches client's WHISPER_MODEL_SIZE naming:
  Client uses: WHISPER_MODEL_SIZE = "base"
  - tiny    ~1s/turn  — fastest, lowest accuracy
  - base    ~2s/turn  — good balance (CLIENT DEFAULT)
  - small   ~4s/turn  — better accuracy
  - medium  ~8s/turn  — high accuracy, needs more VRAM

Note: "base" is multilingual. "base.en" is English-only (slightly faster for English).
The client uses "base" so we match that. Language can be pinned to "en" at call time.
"""

import io
import numpy as np
from pathlib import Path
from typing import Union

from faster_whisper import WhisperModel

from core.config import settings


class STTError(Exception):
    """Raised when transcription fails."""
    pass


class WhisperSTT:
    """
    Wrapper around faster-whisper for local speech-to-text transcription.
    Loads the model once on init and reuses it for all transcriptions.
    """

    def __init__(
        self,
        model_size: str = None,
        device: str = None,
        compute_type: str = None,
    ):
        self.model_size = model_size or settings.whisper_model
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute_type

        if settings.log_level == "DEBUG":
            print(
                f"[STT] Loading faster-whisper model: {self.model_size!r} "
                f"on {self.device!r} ({self.compute_type})"
            )
        try:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            if settings.log_level == "DEBUG":
                print("[STT] ✓ Model loaded successfully.")
        except Exception as e:
            raise STTError(f"Failed to load Whisper model '{self.model_size}': {e}") from e

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio: Union[np.ndarray, bytes, str, Path],
        language: str = "en",   # Pin to English; set None for multilingual auto-detect
        task: str = "transcribe",
    ) -> str:
        """
        Transcribe audio to text.

        Args:
            audio:    Can be:
                      - np.ndarray  (float32, shape [samples] or [samples, channels])
                      - bytes       (raw WAV bytes)
                      - str/Path    (path to a WAV file)
            language: Language code. Default "en" for English.
                      Set None to auto-detect (useful with multilingual "base" model).
                      Client uses: WHISPER_MODEL_SIZE = "base" (multilingual).
            task:     "transcribe" or "translate" (translate → always to English).

        Returns:
            Transcribed text string. Empty string if no speech detected.
        """
        audio_input = self._prepare_audio(audio)

        try:
            segments, info = self._model.transcribe(
                audio_input,
                language=language,
                task=task,
                beam_size=5,
                vad_filter=True,           # Built-in VAD to filter out silence
                vad_parameters={
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms": 300,
                },
            )
            # Collect all segments
            text = " ".join(seg.text for seg in segments).strip()
            return text
        except Exception as e:
            raise STTError(f"Transcription failed: {e}") from e

    def _prepare_audio(
        self, audio: Union[np.ndarray, bytes, str, Path]
    ) -> Union[np.ndarray, str]:
        """
        Normalize audio input to a format faster-whisper accepts:
        - np.ndarray of float32 mono audio (shape: [samples])
        - OR a file path string
        """
        if isinstance(audio, (str, Path)):
            return str(audio)  # faster-whisper accepts file paths directly

        if isinstance(audio, bytes):
            # Parse WAV bytes into numpy array
            import wave
            buf = io.BytesIO(audio)
            with wave.open(buf) as wf:
                frames = wf.readframes(wf.getnframes())
                audio_array = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                audio_array /= 32767.0  # Normalize to [-1, 1]
            return audio_array

        if isinstance(audio, np.ndarray):
            # Ensure float32
            audio = audio.astype(np.float32)
            # Flatten stereo to mono if needed
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            return audio

        raise STTError(f"Unsupported audio type: {type(audio)}")

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def transcribe_file(self, filepath: Union[str, Path]) -> str:
        """Transcribe a WAV file. Convenience wrapper for transcribe()."""
        return self.transcribe(Path(filepath))

    def is_speech(self, audio: np.ndarray, threshold: float = 0.005) -> bool:
        """
        Quick check if audio array contains detectable speech.
        Uses RMS amplitude as a fast pre-filter before sending to Whisper.
        """
        rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        return rms > threshold


# ---------------------------------------------------------------------------
# Lazy singleton — loaded on first access to avoid startup delay
# ---------------------------------------------------------------------------
_stt_instance = None

def get_stt() -> WhisperSTT:
    """Returns the shared WhisperSTT instance (lazy-loaded)."""
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = WhisperSTT()
    return _stt_instance
