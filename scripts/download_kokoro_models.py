"""
scripts/download_kokoro_models.py
==================================
Downloads the necessary ONNX model and voice asset files for Kokoro TTS.
"""

import sys
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MODELS_DIR = PROJECT_ROOT / "models"

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"


def download_file(url: str, dest_path: Path):
    """Downloads a file with a simple progress bar printed to stdout."""
    print(f"Downloading {url} ...")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024 * 1024  # 1 MB
    downloaded = 0
    
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=block_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    sys.stdout.write(f"\rProgress: {percent:.1f}% ({downloaded / block_size:.1f}MB / {total_size / block_size:.1f}MB)")
                    sys.stdout.flush()
    print("\nDownload complete.")


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    model_dest = MODELS_DIR / "kokoro-v1.0.onnx"
    voices_dest = MODELS_DIR / "voices-v1.0.bin"
    
    if not model_dest.exists():
        download_file(MODEL_URL, model_dest)
    else:
        print(f"Kokoro ONNX model already exists at: {model_dest}")
        
    if not voices_dest.exists():
        download_file(VOICES_URL, voices_dest)
    else:
        print(f"Kokoro voices database already exists at: {voices_dest}")


if __name__ == "__main__":
    main()
