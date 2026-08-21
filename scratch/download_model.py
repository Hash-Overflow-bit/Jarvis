import os
import requests
from kokoro_onnx import Kokoro

os.makedirs("models", exist_ok=True)

model_url = "https://huggingface.co/fastrtc/kokoro-onnx/resolve/main/kokoro-v1.0.onnx"
model_path = "models/kokoro-v1.0.onnx"

voices_url = "https://huggingface.co/fastrtc/kokoro-onnx/resolve/main/voices-v1.0.bin"
voices_path = "models/voices-v1.0.bin"

def download_file(url, path):
    print(f"Downloading {url} to {path}...")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    print(f"Finished downloading {path}. Size: {os.path.getsize(path)} bytes")

try:
    download_file(model_url, model_path)
    download_file(voices_url, voices_path)
    print("Testing Kokoro loading...")
    k = Kokoro(model_path, voices_path)
    print("SUCCESS: Kokoro loaded ONNX model and voices file from fastrtc successfully!")
except Exception as e:
    print("ERROR:", e)
