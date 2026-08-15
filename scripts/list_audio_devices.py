"""
scripts/list_audio_devices.py
==============================
Helper script to list all audio devices with their indices.
Run this to find the correct AUDIO_INPUT_DEVICE and AUDIO_OUTPUT_DEVICE
values to set in your .env file.

Usage:
    poetry run python scripts/list_audio_devices.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich import box
from core.audio.audio_device import AudioDevice

console = Console()

def main():
    console.print("\n[bold cyan]Audio Devices[/bold cyan]")
    console.print("[dim]Set AUDIO_INPUT_DEVICE and AUDIO_OUTPUT_DEVICE in .env[/dim]\n")

    devices = AudioDevice.list_devices()

    table = Table(box=box.ROUNDED)
    table.add_column("Index", style="bold cyan", width=6)
    table.add_column("Name", min_width=40)
    table.add_column("Input", justify="center", width=7)
    table.add_column("Output", justify="center", width=7)
    table.add_column("Sample Rate", justify="right", width=12)

    for d in devices:
        table.add_row(
            str(d["index"]),
            d["name"],
            "[green]✓[/green]" if d["is_input"] else "",
            "[green]✓[/green]" if d["is_output"] else "",
            f"{int(d['default_samplerate'])} Hz",
        )

    console.print(table)

    try:
        default_in = AudioDevice.default_input_device()
        default_out = AudioDevice.default_output_device()
        console.print(f"\n[bold]Default Input:[/bold]  {default_in['name']}")
        console.print(f"[bold]Default Output:[/bold] {default_out['name']}")
    except Exception:
        pass

    console.print(
        "\n[dim]Set -1 in .env to use the system default device.[/dim]\n"
    )

if __name__ == "__main__":
    main()
