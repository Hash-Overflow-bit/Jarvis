"""
core/config.py
==============
Central configuration loader for Jarvis.
Detects the OS, loads .env, and exposes a single `settings` object
used everywhere in the codebase.

Cross-platform notes:
- Uses platform.system() to detect OS (Darwin=macOS, Windows=Windows, Linux=WSL/Linux)
- All paths are returned as pathlib.Path objects — never raw strings
- Never hardcode any path or device index here; everything comes from .env
"""

import platform
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os

# ---------------------------------------------------------------------------
# Load .env from the project root (parent of this file's directory)
# ---------------------------------------------------------------------------
_ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)


class _Settings:
    """
    Single settings object. Import and use `settings` from this module.
    All values come from environment variables (loaded from .env).
    """

    # --- OS Detection ---
    @property
    def os_name(self) -> str:
        """Returns 'macos', 'windows', or 'linux'."""
        system = platform.system()
        if system == "Darwin":
            return "macos"
        elif system == "Windows":
            return "windows"
        else:
            return "linux"  # Covers WSL 2 as well

    @property
    def is_macos(self) -> bool:
        return self.os_name == "macos"

    @property
    def is_windows(self) -> bool:
        return self.os_name == "windows"

    @property
    def is_linux(self) -> bool:
        return self.os_name == "linux"

    @property
    def is_wsl(self) -> bool:
        """Detect if running inside WSL 2."""
        if not self.is_linux:
            return False
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except FileNotFoundError:
            return False

    # --- General ---
    @property
    def environment(self) -> str:
        return os.getenv("ENVIRONMENT", "development")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "DEBUG").upper()

    # --- Ollama ---
    @property
    def ollama_base_url(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def ollama_generate_url(self) -> str:
        """Full URL for /api/generate — matches client's OLLAMA_URL."""
        return f"{self.ollama_base_url}/api/generate"

    @property
    def ollama_chat_url(self) -> str:
        """Full URL for /api/chat — used by session_manager for multi-turn."""
        return f"{self.ollama_base_url}/api/chat"

    @property
    def ollama_model(self) -> str:
        return os.getenv("OLLAMA_MODEL", "llama3.1")

    @property
    def ollama_keep_alive(self) -> int:
        return int(os.getenv("OLLAMA_KEEP_ALIVE", "3600"))

    # --- Whisper STT ---
    @property
    def whisper_model(self) -> str:
        # Client uses "base" (multilingual). Default changed from "base.en" to match.
        return os.getenv("WHISPER_MODEL", "base")

    @property
    def whisper_device(self) -> str:
        """Auto-detect if not set: cuda on Windows with GPU, cpu on macOS."""
        env_val = os.getenv("WHISPER_DEVICE")
        if env_val:
            return env_val
        # Auto-detect
        if self.is_macos:
            return "cpu"
        # On Linux/Windows, try cuda, fall back to cpu
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    @property
    def whisper_compute_type(self) -> str:
        env_val = os.getenv("WHISPER_COMPUTE_TYPE")
        if env_val:
            return env_val
        return "int8" if self.whisper_device == "cpu" else "float16"

    # --- Piper TTS ---
    @property
    def _project_root(self) -> Path:
        """Absolute path to project root (parent of core/)."""
        return Path(__file__).parent.parent

    @property
    def piper_binary_path(self) -> Optional[Path]:
        val = os.getenv("PIPER_BINARY_PATH")
        return Path(val) if val else None

    @property
    def piper_voice_model(self) -> Optional[Path]:
        """
        Resolves Piper voice model path.
        Matches client's style: PIPER_MODEL_PATH = "en_US-lessac-medium.onnx"
        - If the value is just a filename (no separators), resolves to PROJECT_ROOT/models/<filename>
        - If it's a full absolute path, uses it directly
        """
        val = os.getenv("PIPER_VOICE_MODEL")
        if not val:
            return None
        p = Path(val)
        # If it's just a filename with no directory component, resolve to models/ dir
        if p.parent == Path("."):
            return self._project_root / "models" / p
        return p

    # --- Audio ---
    @property
    def audio_input_device(self) -> int:
        return int(os.getenv("AUDIO_INPUT_DEVICE", "-1"))

    @property
    def audio_output_device(self) -> int:
        return int(os.getenv("AUDIO_OUTPUT_DEVICE", "-1"))

    @property
    def audio_sample_rate(self) -> int:
        return int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))

    @property
    def audio_channels(self) -> int:
        return int(os.getenv("AUDIO_CHANNELS", "1"))

    @property
    def audio_chunk_duration(self) -> int:
        return int(os.getenv("AUDIO_CHUNK_DURATION", "30"))

    @property
    def audio_silence_threshold(self) -> float:
        return float(os.getenv("AUDIO_SILENCE_THRESHOLD", "0.01"))

    @property
    def audio_silence_duration(self) -> float:
        return float(os.getenv("AUDIO_SILENCE_DURATION", "1.5"))

    # --- Session ---
    @property
    def session_max_turns(self) -> int:
        return int(os.getenv("SESSION_MAX_TURNS", "20"))

    @property
    def jarvis_system_prompt(self) -> str:
        return os.getenv(
            "JARVIS_SYSTEM_PROMPT",
            "You are Jarvis, a helpful local AI assistant. Be concise and precise."
        )

    # --- Sandbox (used in M2+) ---
    @property
    def sandbox_roots(self) -> list[Path]:
        raw = os.getenv("SANDBOX_ROOTS", "")
        if not raw:
            return []
        # Split by comma, support both Windows and Unix paths
        return [Path(p.strip()) for p in raw.split(",") if p.strip()]

    # --- GitHub & Poetry (used in M3+) ---
    @property
    def git_token(self) -> str:
        return os.getenv("GIT_TOKEN", "")

    @property
    def default_workspace_dir(self) -> Path:
        val = os.getenv("DEFAULT_WORKSPACE_DIR")
        if val:
            return Path(val).resolve()
        return (self._project_root / "workspace").resolve()

    @property
    def poetry_venv_path(self) -> Path:
        val = os.getenv("POETRY_VENV_PATH")
        if val:
            return Path(val).resolve()
        return (self._project_root / ".venvs").resolve()

    @property
    def git_user_email(self) -> str:
        return os.getenv("GIT_USER_EMAIL", "jarvis@local.ai")

    @property
    def git_user_name(self) -> str:
        return os.getenv("GIT_USER_NAME", "Jarvis")

    # --- Safety & Auditing (used in M4+) ---
    @property
    def safe_mode(self) -> str:
        # strict | permissive | off
        mode = os.getenv("SAFE_MODE", "strict").lower().strip()
        if mode not in ["strict", "permissive", "off"]:
            return "strict"
        return mode

    @property
    def emergency_stop_keyword(self) -> str:
        return os.getenv("EMERGENCY_STOP_KEYWORD", "JARVIS STOP").upper().strip()

    @property
    def dry_run(self) -> bool:
        return os.getenv("DRY_RUN", "false").lower().strip() == "true"

    @property
    def audit_log_path(self) -> Path:
        val = os.getenv("AUDIT_LOG_PATH")
        if val:
            return Path(val).resolve()
        return (self._project_root / "logs" / "audit.log").resolve()

    # --- Knowledge Graph (M4.5) ---
    @property
    def knowledge_graph_path(self) -> Path:
        val = os.getenv("KNOWLEDGE_GRAPH_PATH")
        if val:
            return Path(val).resolve()
        return (self._project_root / "core" / "memory" / "graph.db").resolve()

    @property
    def knowledge_corpus_dirs(self) -> list[str]:
        val = os.getenv("KNOWLEDGE_CORPUS_DIRS", "knowledge,workspace")
        return [d.strip() for d in val.split(",") if d.strip()]

    @property
    def graph_watch(self) -> bool:
        return os.getenv("GRAPH_WATCH", "false").lower().strip() == "true"

    @property
    def max_graph_hops(self) -> int:
        try:
            return min(int(os.getenv("MAX_GRAPH_HOPS", "3")), 4)
        except Exception:
            return 3

    @property
    def graph_top_k(self) -> int:
        try:
            return int(os.getenv("GRAPH_TOP_K", "8"))
        except Exception:
            return 8

    @property
    def graph_enabled(self) -> bool:
        return os.getenv("GRAPH_ENABLED", "true").lower().strip() == "true"

    def summary(self) -> str:
        """Human-readable settings summary for audit output."""
        lines = [
            f"  OS:               {self.os_name} (WSL: {self.is_wsl})",
            f"  Environment:      {self.environment}",
            f"  Log Level:        {self.log_level}",
            f"  Ollama URL:       {self.ollama_base_url}",
            f"  Ollama Model:     {self.ollama_model}",
            f"  Whisper Model:    {self.whisper_model}",
            f"  Whisper Device:   {self.whisper_device}",
            f"  Compute Type:     {self.whisper_compute_type}",
            f"  Piper Binary:     {self.piper_binary_path}",
            f"  Piper Voice:      {self.piper_voice_model}",
            f"  Audio Input Dev:  {self.audio_input_device}",
            f"  Audio Output Dev: {self.audio_output_device}",
            f"  Sample Rate:      {self.audio_sample_rate} Hz",
            f"  Session Max Turns:{self.session_max_turns}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Singleton — import this everywhere
# ---------------------------------------------------------------------------
settings = _Settings()
