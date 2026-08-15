"""
scripts/audit.py
================
System health check for Jarvis.
Run this before any session to verify all dependencies are working.

Usage:
    poetry run python scripts/audit.py

Checks:
1. Python version (must be 3.11+)
2. Ollama server running + model available
3. faster-whisper importable
4. Audio devices listed
5. Piper TTS binary found
6. .env file present + required keys set
7. Sandbox directories exist (M2+)
"""

import sys
import platform
import subprocess
from pathlib import Path

# Add project root to path so core/* imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def check(label: str, ok: bool, detail: str = "", fix: str = "") -> bool:
    icon = "✅" if ok else "❌"
    status = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
    console.print(f"  {icon} {status}  {label}")
    if detail:
        console.print(f"         [dim]{detail}[/dim]")
    if not ok and fix:
        console.print(f"         [yellow]Fix: {fix}[/yellow]")
    return ok


def run_audit() -> bool:
    console.print("\n[bold cyan]═══════════════════════════════════════[/]")
    console.print("[bold cyan]   Jarvis System Audit[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════[/]\n")

    all_pass = True

    # ------------------------------------------------------------------
    # 1. Python version
    # ------------------------------------------------------------------
    console.print("[bold]1. Python Environment[/bold]")
    ver = sys.version_info
    py_ok = ver.major == 3 and ver.minor >= 11
    all_pass &= check(
        f"Python version: {ver.major}.{ver.minor}.{ver.micro}",
        py_ok,
        fix="Install Python 3.11+ via Homebrew: brew install python@3.11"
    )
    console.print(f"     Platform: {platform.system()} {platform.machine()}")

    # WSL detection
    is_wsl = False
    try:
        with open("/proc/version") as f:
            is_wsl = "microsoft" in f.read().lower()
    except FileNotFoundError:
        pass
    console.print(f"     WSL2: {'Yes' if is_wsl else 'No'}")
    console.print()

    # ------------------------------------------------------------------
    # 2. .env file
    # ------------------------------------------------------------------
    console.print("[bold]2. Configuration (.env)[/bold]")
    env_path = Path(__file__).parent.parent / ".env"
    env_exists = env_path.exists()
    all_pass &= check(".env file exists", env_exists, str(env_path),
                      fix="cp .env.example .env")

    if env_exists:
        from dotenv import dotenv_values
        env_vals = dotenv_values(env_path)
        required_keys = [
            "OLLAMA_BASE_URL", "OLLAMA_MODEL",
            "WHISPER_MODEL", "WHISPER_DEVICE",
        ]
        for key in required_keys:
            present = key in env_vals and bool(env_vals[key])
            all_pass &= check(f".env has {key}", present,
                              fix=f"Add {key}=<value> to .env")
    console.print()

    # ------------------------------------------------------------------
    # 3. Ollama
    # ------------------------------------------------------------------
    console.print("[bold]3. Ollama LLM Server[/bold]")
    from core.config import settings
    from core.llm.ollama_client import ollama, OllamaError

    ollama_running = ollama.is_running()
    all_pass &= check(
        f"Ollama running at {settings.ollama_base_url}",
        ollama_running,
        fix="Start Ollama: ollama serve  (or open Ollama.app on macOS)"
    )

    if ollama_running:
        try:
            models = ollama.list_models()
            target = settings.ollama_model
            model_ok = any(target in m for m in models)
            all_pass &= check(
                f"Model '{target}' available",
                model_ok,
                detail=f"Available models: {', '.join(models) if models else 'none'}",
                fix=f"Pull model: ollama pull {target}"
            )
        except OllamaError as e:
            all_pass &= check("Model list", False, detail=str(e))
    console.print()

    # ------------------------------------------------------------------
    # 4. faster-whisper
    # ------------------------------------------------------------------
    console.print("[bold]4. faster-whisper (STT)[/bold]")
    try:
        from faster_whisper import WhisperModel
        all_pass &= check("faster-whisper importable", True,
                          f"Model: {settings.whisper_model}, Device: {settings.whisper_device}")
    except ImportError as e:
        all_pass &= check("faster-whisper importable", False, str(e),
                          fix="poetry add faster-whisper")

    # CUDA check (only relevant on Windows)
    if settings.whisper_device == "cuda":
        try:
            import torch
            cuda_ok = torch.cuda.is_available()
            all_pass &= check("CUDA available", cuda_ok,
                              detail=f"CUDA device: {torch.cuda.get_device_name(0) if cuda_ok else 'none'}",
                              fix="Install NVIDIA CUDA Toolkit 12.x")
        except ImportError:
            check("PyTorch (for CUDA check)", False, "Optional — not installed",
                  fix="pip install torch --index-url https://download.pytorch.org/whl/cu121")
    console.print()

    # ------------------------------------------------------------------
    # 5. Audio devices
    # ------------------------------------------------------------------
    console.print("[bold]5. Audio Devices[/bold]")
    try:
        from core.audio.audio_device import AudioDevice
        devices = AudioDevice.list_devices()
        input_devices = [d for d in devices if d["is_input"]]
        output_devices = [d for d in devices if d["is_output"]]

        all_pass &= check(
            f"Audio input devices found: {len(input_devices)}",
            len(input_devices) > 0,
            fix="Check microphone connection or PulseAudio bridge (WSL2)"
        )
        all_pass &= check(
            f"Audio output devices found: {len(output_devices)}",
            len(output_devices) > 0,
        )

        if input_devices:
            table = Table(box=box.SIMPLE)
            table.add_column("Index", style="cyan")
            table.add_column("Name")
            table.add_column("In")
            table.add_column("Out")
            for d in devices[:8]:  # Show first 8
                table.add_row(
                    str(d["index"]),
                    d["name"][:50],
                    "✓" if d["is_input"] else "",
                    "✓" if d["is_output"] else "",
                )
            console.print("     ", table)
            console.print(f"     [dim]Active input device: {settings.audio_input_device} "
                          f"(-1 = default)[/dim]")
    except Exception as e:
        all_pass &= check("Audio device listing", False, str(e),
                          fix="Install PortAudio: brew install portaudio (macOS)")
    console.print()

    # ------------------------------------------------------------------
    # 6. Piper TTS
    # ------------------------------------------------------------------
    console.print("[bold]6. Piper TTS[/bold]")
    piper_path = settings.piper_binary_path
    piper_model = settings.piper_voice_model

    if piper_path:
        piper_ok = Path(piper_path).exists()
        all_pass &= check(
            f"Piper binary: {piper_path}",
            piper_ok,
            fix="Download from: https://github.com/rhasspy/piper/releases"
        )
    else:
        check("Piper binary configured", False,
              fix="Set PIPER_BINARY_PATH in .env")

    if piper_model:
        model_ok = Path(piper_model).exists()
        all_pass &= check(
            f"Piper voice model: {piper_model.name if piper_model else 'not set'}",
            model_ok,
            fix="Download voice: https://huggingface.co/rhasspy/piper-voices"
        )
    else:
        check("Piper voice model configured", False,
              fix="Set PIPER_VOICE_MODEL in .env")

    if not piper_path or not piper_model:
        console.print("     [yellow]⚠ Piper not configured — "
                      "will use console (text-only) fallback[/yellow]")
    console.print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    console.print("[bold cyan]═══════════════════════════════════════[/]")
    if all_pass:
        console.print("[bold green]  ✅  ALL CHECKS PASSED — Jarvis is ready![/bold green]")
    else:
        console.print("[bold red]  ❌  SOME CHECKS FAILED — Fix issues above.[/bold red]")
    console.print("[bold cyan]═══════════════════════════════════════[/]\n")

    console.print("[dim]Settings summary:[/dim]")
    console.print(settings.summary())
    console.print()

    return all_pass


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
