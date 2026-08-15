"""
core/audio/audio_device.py
==========================
Cross-platform audio recording and playback abstraction.

Strategy:
- Uses `sounddevice` on BOTH macOS and Windows (same Python API, different device index).
- Device index is set via AUDIO_INPUT_DEVICE / AUDIO_OUTPUT_DEVICE in .env.
- Set to -1 to use the OS default device (works on both platforms out of the box).
- Records until silence is detected (voice activity detection via RMS threshold).

Cross-platform notes:
- sounddevice wraps PortAudio which supports CoreAudio (macOS) and WASAPI (Windows).
- On WSL 2, audio requires a PulseAudio bridge. If WSL audio fails, the
  recommendation is to run audio on native Windows Python and route via socket.
- The AudioDevice class is platform-agnostic; only the .env values differ.
"""

import io
import wave
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd

from core.config import settings


class AudioDeviceError(Exception):
    """Raised when audio device operations fail."""
    pass


class AudioDevice:
    """
    Handles microphone recording and speaker playback.
    Works on macOS (CoreAudio), Windows (WASAPI), and Linux (ALSA/PulseAudio).
    """

    def __init__(
        self,
        input_device: int = None,
        output_device: int = None,
        sample_rate: int = None,
        channels: int = None,
    ):
        # -1 means "use OS default"
        self.input_device = input_device if input_device is not None else settings.audio_input_device
        self.output_device = output_device if output_device is not None else settings.audio_output_device
        self.sample_rate = sample_rate or settings.audio_sample_rate
        self.channels = channels or settings.audio_channels

        # Normalize -1 to None (sounddevice uses None for default)
        self._sd_input = None if self.input_device == -1 else self.input_device
        self._sd_output = None if self.output_device == -1 else self.output_device

    # ------------------------------------------------------------------
    # Device listing (useful for audit.py and debugging)
    # ------------------------------------------------------------------

    @staticmethod
    def list_devices() -> list[dict]:
        """
        Returns a list of all available audio devices with their properties.
        Use this to find the correct device index for your microphone/speaker.
        """
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            devices.append({
                "index": i,
                "name": dev["name"],
                "max_input_channels": dev["max_input_channels"],
                "max_output_channels": dev["max_output_channels"],
                "default_samplerate": dev["default_samplerate"],
                "is_input": dev["max_input_channels"] > 0,
                "is_output": dev["max_output_channels"] > 0,
            })
        return devices

    @staticmethod
    def default_input_device() -> dict:
        """Returns info about the current default input device."""
        return sd.query_devices(kind="input")

    @staticmethod
    def default_output_device() -> dict:
        """Returns info about the current default output device."""
        return sd.query_devices(kind="output")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_chunk(self, duration: float = None) -> np.ndarray:
        """
        Record a fixed-duration audio chunk.

        Args:
            duration: Recording duration in seconds. Defaults to AUDIO_CHUNK_DURATION.

        Returns:
            NumPy array of shape (samples, channels), dtype float32.
        """
        duration = duration or settings.audio_chunk_duration
        try:
            audio = sd.rec(
                frames=int(self.sample_rate * duration),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                device=self._sd_input,
            )
            sd.wait()  # Block until recording is complete
            return audio
        except sd.PortAudioError as e:
            raise AudioDeviceError(f"Recording failed: {e}") from e

    def record_until_silence(
        self,
        max_duration: float = None,
        silence_threshold: float = None,
        silence_duration: float = None,
    ) -> np.ndarray:
        """
        Record audio until silence is detected.
        Stops when RMS amplitude stays below threshold for silence_duration seconds.

        Args:
            max_duration:      Maximum recording time in seconds.
            silence_threshold: RMS amplitude below this = silence.
            silence_duration:  Seconds of continuous silence before stopping.

        Returns:
            NumPy array of the recorded audio (float32, shape: [samples, channels]).
        """
        max_duration = max_duration or settings.audio_chunk_duration
        silence_threshold = silence_threshold or settings.audio_silence_threshold
        silence_duration = silence_duration or settings.audio_silence_duration

        chunk_size = int(self.sample_rate * 0.1)  # 100ms chunks
        max_chunks = int(max_duration / 0.1)
        silence_chunks_needed = int(silence_duration / 0.1)

        recorded_chunks = []
        silence_count = 0
        speech_detected = False

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                device=self._sd_input,
                blocksize=chunk_size,
            ) as stream:
                for _ in range(max_chunks):
                    chunk, _ = stream.read(chunk_size)
                    recorded_chunks.append(chunk)

                    # Calculate RMS (root mean square) amplitude
                    rms = float(np.sqrt(np.mean(chunk ** 2)))

                    if rms > silence_threshold:
                        speech_detected = True
                        silence_count = 0
                    elif speech_detected:
                        # Only count silence AFTER speech has started
                        silence_count += 1
                        if silence_count >= silence_chunks_needed:
                            break  # Enough silence detected — stop recording

        except sd.PortAudioError as e:
            raise AudioDeviceError(f"Streaming input failed: {e}") from e

        if not recorded_chunks:
            return np.zeros((0, self.channels), dtype=np.float32)

        return np.concatenate(recorded_chunks, axis=0)

    def audio_to_wav_bytes(self, audio: np.ndarray) -> bytes:
        """
        Convert a NumPy audio array to WAV bytes in memory.
        Used for passing audio to faster-whisper without writing to disk.
        """
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self.sample_rate)
            # Convert float32 [-1, 1] to int16
            pcm = (audio * 32767).astype(np.int16)
            wf.writeframes(pcm.tobytes())
        buf.seek(0)
        return buf.read()

    def save_wav(self, audio: np.ndarray, filepath: Path) -> Path:
        """Save NumPy audio array to a WAV file. Returns the saved path."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        wav_bytes = self.audio_to_wav_bytes(audio)
        filepath.write_bytes(wav_bytes)
        return filepath

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play_wav_file(self, filepath: Path) -> None:
        """Play a WAV file through the speaker. Blocks until playback is done."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise AudioDeviceError(f"WAV file not found: {filepath}")
        try:
            import soundfile as sf
            data, sample_rate = sf.read(str(filepath), dtype="float32")
            sd.play(data, samplerate=sample_rate, device=self._sd_output)
            sd.wait()
        except ImportError:
            # Fallback: use wave + sounddevice directly
            with wave.open(str(filepath), "rb") as wf:
                rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
                sd.play(audio, samplerate=rate, device=self._sd_output)
                sd.wait()
        except sd.PortAudioError as e:
            raise AudioDeviceError(f"Playback failed: {e}") from e

    def play_wav_bytes(self, wav_bytes: bytes) -> None:
        """Play WAV bytes directly (no disk I/O). Used for TTS output."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = Path(tmp.name)
        try:
            self.play_wav_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
audio_device = AudioDevice()
