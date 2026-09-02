"""Audio subsystem.

Backends are intentionally not imported here: Whisper, CUDA, PortAudio and TTS
assets are optional runtime dependencies and must be loaded only when selected.
"""

__all__ = ["audio_device", "stt", "tts", "voice_io"]
