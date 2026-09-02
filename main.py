"""
main.py
=======
Jarvis entry point.

Modes:
  --mode text   → Text input from keyboard, text output to console (no mic/speaker needed)
  --mode audio  → Voice input (mic) and voice output (Piper TTS)

Usage:
    poetry run python main.py --mode text
    poetry run python main.py --mode audio

Cross-platform:
- Text mode works identically on macOS and Windows.
- Audio mode requires a microphone and either Piper TTS or console fallback.
"""

import sys
import argparse
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from core.config import settings
from core.llm.ollama_client import ollama, OllamaError
from core.state.session_manager import SessionManager

console = Console()


def print_banner():
    console.print(Panel.fit(
        "[bold cyan] W I L S O N ' S J A R V I S[/bold cyan]\n"
        "[dim]Local AI Assistant[/dim]\n"
        f"[dim]Model: {settings.ollama_model} | OS: {settings.os_name}[/dim]",
        border_style="cyan"
    ))


def run_text_mode():
    """
    Interactive text loop — no microphone or speaker required.
    Perfect for development and testing on macOS.
    """
    console.print("\n[bold green]Text mode active.[/bold green] "
                  "Type your message and press Enter. Type [bold]'quit'[/bold] to exit.\n")

    session = SessionManager()

    while True:
        try:
            user_input = Prompt.ask("[bold blue]You[/bold blue]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting...[/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "bye"):
            console.print("[cyan]Jarvis:[/cyan] Goodbye!")
            break

        if user_input.lower() in ("reset", "/reset"):
            session.reset()
            console.print("[dim]Session reset. Starting fresh conversation.[/dim]\n")
            continue

        if user_input.upper().strip() == settings.emergency_stop_keyword:
            from core.safety.emergency_stop import emergency_stop
            killed_count = emergency_stop.halt_all()
            console.print(f"[bold red]🛑 EMERGENCY STOP TRIGGERED! Terminated {killed_count} active background tasks.[/bold red]\n")
            continue

        if user_input.lower() in ("/turns", "/status"):
            console.print(
                f"[dim]Session turns: {session.turn_count} | "
                f"History length: {len(session.history)} messages[/dim]"
            )
            continue

        try:
            response = session.chat(user_input, mode="text")
            console.print(f"\n[cyan]Jarvis:[/cyan] {response}\n")
        except OllamaError as e:
            console.print(f"\n[red]Error:[/red] {e}\n")
            console.print("[dim]Is Ollama running? Try: ollama serve[/dim]\n")


def run_audio_mode():
    """
    Full voice loop: mic → STT → LLM → TTS → speaker.
    Requires microphone, Ollama, and optionally Piper TTS.
    """
    from core.audio.audio_device import audio_device, AudioDeviceError
    from core.audio.stt import get_stt, STTError
    from core.audio.tts import get_tts_singleton
    from core.audio.voice_io import VoiceIO, VoiceInputError, VoiceOutputError

    # Load STT model
    if settings.log_level == "DEBUG":
        console.print("[dim]Loading Whisper STT model...[/dim]")
    try:
        stt = get_stt()
    except STTError as e:
        console.print(f"[red]STT Error:[/red] {e}")
        sys.exit(1)

    # Load TTS
    tts = get_tts_singleton()
    if not getattr(tts, "is_available", False):
        console.print(
            "[red]Voice output is unavailable.[/red] Configure valid Kokoro assets "
            "or a Piper binary and voice model before using audio mode."
        )
        return
    if settings.log_level == "DEBUG":
        console.print(f"[dim]TTS: {'Piper' if hasattr(tts, 'binary_path') else 'Console fallback'}[/dim]")

    session = SessionManager()
    voice = VoiceIO(audio_device, stt, tts, settings.emergency_stop_keyword)
    console.print("\n[cyan]Jarvis online.[/cyan]\n")
    try:
        voice.speak("Jarvis online. How can I help you?")
    except VoiceOutputError as e:
        console.print(f"[red]Voice Error:[/red] {e}")
        return

    while True:
        try:
            # Record audio until silence
            voice_input = voice.listen()
            if voice_input is None:
                continue
            text = voice_input.text

            console.print(f"You: {text}")

            # Check emergency stop keyword
            if voice_input.command == "emergency":
                from core.safety.emergency_stop import emergency_stop
                killed_count = emergency_stop.halt_all()
                console.print(f"[bold red]🛑 EMERGENCY STOP TRIGGERED! Terminated {killed_count} active background tasks.[/bold red]\n")
                voice.speak("Emergency stop. Terminated all active tasks.")
                continue

            # Check for exit command
            if voice_input.command == "exit":
                voice.speak("Goodbye!")
                break

            # Get LLM response
            try:
                response = session.chat(text, mode="audio")
                console.print(f"Jarvis: {response}\n")
                voice.speak(response)
            except OllamaError as e:
                if settings.log_level == "DEBUG":
                    console.print(f"[red]Error:[/red] {e}")
                voice.speak("I encountered an error connecting to Ollama.")

        except KeyboardInterrupt:
            from core.safety.emergency_stop import emergency_stop
            killed_count = emergency_stop.halt_all()
            console.print(f"[bold red]🛑 EMERGENCY STOP TRIGGERED! Terminated {killed_count} active background tasks.[/bold red]\n")
            try:
                voice.speak("Shutting down.")
            except (KeyboardInterrupt, Exception):
                console.print("[JARVIS]: Shutting down.")
            break
        except AudioDeviceError as e:
            if settings.log_level == "DEBUG":
                console.print(f"[red]Audio Error:[/red] {e}")
        except (VoiceInputError, VoiceOutputError) as e:
            console.print(f"[red]Voice Error:[/red] {e}")


def main():
    # Initialize OpenTelemetry telemetry & tracing loops (M6)
    from core.logging.tracing import init_telemetry
    init_telemetry()

    parser = argparse.ArgumentParser(
        description="Jarvis — Local AI Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode text    # Text-only mode (no mic needed)
  python main.py --mode audio   # Full voice mode
        """
    )
    parser.add_argument(
        "--mode",
        choices=["text", "audio"],
        default="text",
        help="Input/output mode (default: text)"
    )
    args = parser.parse_args()

    print_banner()

    # Check Ollama before starting
    if not ollama.is_running():
        console.print(
            f"\n[red]❌ Ollama is not running at {settings.ollama_base_url}[/red]\n"
            "[yellow]Start it with: ollama serve[/yellow]\n"
            "[yellow]Or run the audit: python scripts/audit.py[/yellow]\n"
        )
        sys.exit(1)

    console.print(f"[green]✓[/green] Ollama connected | Model: [bold]{settings.ollama_model}[/bold]")

    # Check Skyvern browser automation availability (non-blocking)
    try:
        import urllib.request
        probe = urllib.request.Request(f"{settings.skyvern_base_url}/heartbeat", method="GET")
        probe.add_header("User-Agent", "Jarvis-Skyvern-Bridge/1.0")
        urllib.request.urlopen(probe, timeout=2)
        console.print("[green]✓[/green] Browser automation available (Skyvern)")
    except Exception:
        console.print("[yellow]⚠[/yellow] Browser automation unavailable (Skyvern offline)")

    if args.mode == "text":
        run_text_mode()
    else:
        run_audio_mode()


if __name__ == "__main__":
    main()
