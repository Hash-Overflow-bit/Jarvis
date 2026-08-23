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
import re

# ---------------------------------------------------------------------------
# Load .env from the project root (parent of this file's directory)
# ---------------------------------------------------------------------------
_ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)


def normalize_path(path_str: str) -> Path:
    """
    Translates and normalizes paths between Windows (C:\\path) and WSL/Linux (/mnt/c/path) styles
    depending on the current host OS.
    """
    if not path_str:
        return Path()

    path_str = path_str.strip()
    # Check if running under Linux (e.g. WSL 2) or macOS vs native Windows
    is_windows = (platform.system() == "Windows")

    if not is_windows:
        # We are on Linux/WSL/macOS
        # Convert all backslashes to forward slashes
        path_str = path_str.replace("\\", "/")
        # Convert drive letter prefixes like "C:/" to "/mnt/c/"
        match = re.match(r"^([a-zA-Z]):/(.*)", path_str)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2)
            path_str = f"/mnt/{drive}/{rest}"
        elif re.match(r"^([a-zA-Z]):", path_str):
            drive = path_str[0].lower()
            path_str = f"/mnt/{drive}/{path_str[2:]}"
    else:
        # We are on native Windows
        # Convert forward slashes to backslashes
        path_str = path_str.replace("/", "\\")
        # Convert /mnt/c/ style paths to C:\\ style
        match = re.match(r"^/mnt/([a-zA-Z])/(.*)", path_str.replace("\\", "/"))
        if match:
            drive = match.group(1).upper()
            rest = match.group(2).replace("/", "\\")
            path_str = f"{drive}:\\{rest}"

    return Path(path_str).resolve()


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

    def _get_wsl_host_ip(self) -> str:
        """Helper to dynamically resolve Windows host IP address from inside WSL 2."""
        # 1. Try Default Gateway first (most accurate for Windows host on WSL bridge)
        try:
            import subprocess
            result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True, timeout=2.0)
            for line in result.stdout.splitlines():
                if line.startswith("default via"):
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2]
        except Exception:
            pass

        # 2. Fall back to nameserver in resolv.conf
        try:
            resolv_path = Path("/etc/resolv.conf")
            if resolv_path.exists():
                content = resolv_path.read_text()
                for line in content.splitlines():
                    if "nameserver" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            return parts[1]
        except Exception:
            pass
        return "127.0.0.1"

    def _check_onedrive_and_redirect(self, path: Path, subfolder: str) -> Path:
        """
        Detects if a path is located inside OneDrive and redirects it
        to a local directory to avoid synchronization issues and file locks.
        """
        path_str = str(path.resolve())
        if "onedrive" in path_str.lower():
            if self.is_windows:
                safe_base = Path.home() / "Jarvis"
            else:
                safe_base = Path.home() / ".jarvis"
            
            # Preserve filename if path is a file
            if path.suffix:
                redirected = (safe_base / subfolder / path.name).resolve()
            else:
                redirected = (safe_base / subfolder).resolve()
                
            redirected.parent.mkdir(parents=True, exist_ok=True)
            
            return redirected
        return path

    @property
    def nopus_prose_filter(self) -> bool:
        return os.getenv("NOPUS_PROSE_FILTER", "true").lower().strip() == "true"

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
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        if self.is_wsl and ("localhost" in url or "127.0.0.1" in url):
            host_ip = self._get_wsl_host_ip()
            url = url.replace("localhost", host_ip).replace("127.0.0.1", host_ip)
        return url

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
            import torch  # type: ignore[import-not-found] # pyright: ignore[reportMissingImports]
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
        return normalize_path(val) if val else None

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
        # If it's just a filename with no directory component, resolve to models/ dir
        if "/" not in val and "\\" not in val:
            return self._project_root / "models" / Path(val)
        return normalize_path(val)

    # --- Kokoro TTS ---
    @property
    def tts_engine(self) -> str:
        return os.getenv("TTS_ENGINE", "piper").lower().strip()

    @property
    def kokoro_voice_model(self) -> Optional[Path]:
        val = os.getenv("KOKORO_VOICE_MODEL", "kokoro-v1.0.onnx")
        if not val:
            return None
        if "/" not in val and "\\" not in val:
            return self._project_root / "models" / Path(val)
        return normalize_path(val)

    @property
    def kokoro_voices_file(self) -> Optional[Path]:
        val = os.getenv("KOKORO_VOICES_FILE", "voices-v1.0.bin")
        if not val:
            return None
        if "/" not in val and "\\" not in val:
            return self._project_root / "models" / Path(val)
        return normalize_path(val)

    @property
    def kokoro_voice_id(self) -> str:
        return os.getenv("KOKORO_VOICE_ID", "bf_emma").strip()

    @property
    def kokoro_lang_code(self) -> str:
        return os.getenv("KOKORO_LANG_CODE", "en-us").strip()

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
        base = os.getenv(
            "JARVIS_SYSTEM_PROMPT",
            "You are Jarvis, a versatile local AI assistant. You are friendly, helpful, and capable of discussing any topic (including programming, food, recommendations, general knowledge, and general conversation) naturally without rigid disclaimers."
        )
        return (
            f"{base.strip()} You are equipped with a persistent long-term memory system (a local Knowledge Graph) "
            "that remembers the user and their preferences across sessions. Only mention details from the recalled facts "
            "if they are directly relevant to the user's current query or if the user explicitly asks about them. "
            "CRITICAL DATE HANDLING: The current year is 2026. Do NOT change, alter, or hallucinate the year in timestamps or facts. "
            "Always use the exact dates and years provided in the system context or recalled memory (never convert 2026 to 2023). "
            "You have access to tools, but you should ONLY call a tool if you need to perform a write action or run code. "
            "If the user's question can be answered using the conversation history or the provided system/recalled facts, "
            "you MUST answer the user directly and you MUST NOT call any tools.\n\n"
            "CRITICAL BEHAVIOR RULES:\n"
            "1. Reply to ALL questions very precisely and concisely. Do NOT write long paragraphs.\n"
            "2. Answer general questions using your intrinsic real-world knowledge. Do NOT reference local dummy files or test data unless the user explicitly asks you to read a specific file."
        )

    # --- Sandbox (used in M2+) ---
    @property
    def sandbox_roots(self) -> list[Path]:
        raw = os.getenv("SANDBOX_ROOTS", "")
        if not raw:
            return []
        # Split by comma, support both Windows and Unix paths
        paths = [normalize_path(p) for p in raw.split(",") if p.strip()]
        return [self._check_onedrive_and_redirect(p, "sandbox") for p in paths]

    @property
    def sandbox_mode(self) -> bool:
        """
        Controls path restriction enforcement.
        SANDBOX_MODE=true  → Jarvis can only operate inside SANDBOX_ROOTS (locked down).
        SANDBOX_MODE=false → Jarvis can read/write/delete anywhere on the filesystem
                             that the OS user has permission to access (unrestricted).
        Defaults to false (unrestricted) for maximum usefulness.
        """
        return os.getenv("SANDBOX_MODE", "false").lower().strip() == "true"

    # --- GitHub & Poetry (used in M3+) ---
    @property
    def git_token(self) -> str:
        return os.getenv("GIT_TOKEN", "")

    @property
    def default_workspace_dir(self) -> Path:
        val = os.getenv("DEFAULT_WORKSPACE_DIR")
        path = normalize_path(val) if val else (self._project_root / "workspace").resolve()
        return self._check_onedrive_and_redirect(path, "workspace")

    @property
    def poetry_venv_path(self) -> Path:
        val = os.getenv("POETRY_VENV_PATH")
        path = normalize_path(val) if val else (self._project_root / ".venvs").resolve()
        return self._check_onedrive_and_redirect(path, "venvs")

    @property
    def git_user_email(self) -> str:
        return os.getenv("GIT_USER_EMAIL", "veoviewing@gmail.com")

    @property
    def git_user_name(self) -> str:
        return os.getenv("GIT_USER_NAME", "veoviewing")

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

    # --- Dynamic Sub-Agents (used in M5+) ---
    @property
    def agents_blueprint_path(self) -> Path:
        val = os.getenv("AGENTS_BLUEPRINT_PATH")
        path = normalize_path(val) if val else (self._project_root / "agents" / "agents_blueprint.yaml").resolve()
        return self._check_onedrive_and_redirect(path, "agents")

    @property
    def agent_baseline_timeout(self) -> float:
        try:
            return float(os.getenv("AGENT_BASELINE_TIMEOUT", "60.0").strip())
        except ValueError:
            return 60.0

    @property
    def audit_log_path(self) -> Path:
        val = os.getenv("AUDIT_LOG_PATH")
        path = normalize_path(val) if val else (self._project_root / "logs" / "audit.log").resolve()
        return self._check_onedrive_and_redirect(path, "logs")

    # --- Knowledge Graph (M4.5) ---
    @property
    def knowledge_graph_path(self) -> Path:
        val = os.getenv("KNOWLEDGE_GRAPH_PATH")
        path = normalize_path(val) if val else (self._project_root / "core" / "memory" / "graph.db").resolve()
        return self._check_onedrive_and_redirect(path, "memory")

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

    @property
    def telemetry_enabled(self) -> bool:
        return os.getenv("TELEMETRY_ENABLED", "false").lower().strip() == "true"

    @property
    def otel_exporter_otlp_endpoint(self) -> str:
        return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006/v1/traces").strip()

    @property
    def desktop_dir(self) -> Path:
        """Dynamically detects the user's real Desktop directory path."""
        override = os.getenv("DESKTOP_DIR")
        if override:
            return normalize_path(override)

        home = Path.home()
        paths_to_check = [
            home / "OneDrive" / "Desktop",
            home / "onedrive" / "Desktop",
            home / "Desktop",
        ]
        
        # WSL detection helper
        if self.is_wsl or self.os_name.lower() == "linux":
            import getpass
            try:
                # Try to map Windows users
                mnt_c_users = Path("/mnt/c/Users")
                if mnt_c_users.exists():
                    for user_dir in mnt_c_users.iterdir():
                        if user_dir.is_dir() and user_dir.name.lower() not in ("public", "all users", "default", "defaultuser0"):
                            paths_to_check.append(user_dir / "Desktop")
                            paths_to_check.append(user_dir / "OneDrive" / "Desktop")
            except Exception:
                pass

        for p in paths_to_check:
            # Check existence
            try:
                if p.exists() and p.is_dir():
                    return p.resolve()
            except Exception:
                pass
                
        return (home / "Desktop").resolve()

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
