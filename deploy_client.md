# Jarvis Client Deployment Guide

This guide explains how to deploy and configure Jarvis on a client's machine (supporting both **macOS** and **Windows 11 / WSL 2**).

---

## 📋 1. Prerequisites

### For macOS:
1. **Homebrew**: Install Homebrew if not already installed:
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
2. **System Dependencies** (for PyAudio and Kokoro TTS):
   ```bash
   brew install portaudio espeak-ng python@3.11 git
   ```

### For Windows 11 / WSL 2 (Ubuntu):
1. **WSL 2**: Open PowerShell as Administrator and run:
   ```powershell
   wsl --install -d Ubuntu-22.04
   ```
   *Restart the PC if prompted.*
2. **WSL System Dependencies**: Open the Ubuntu terminal and run:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3-pip python3-venv python3-dev git ffmpeg portaudio19-dev espeak-ng
   ```

---

## 🦙 2. Setup Ollama (Local LLM)

We recommend running Ollama directly on the host machine for best GPU acceleration.
1. Download Ollama from: [ollama.com](https://ollama.com)
2. Install it and run the model pull command:
   ```bash
   ollama pull llama3.1
   ```
3. Verify Ollama is running by navigating to `http://localhost:11434` in your browser.

---

## 🗣️ 3. Download TTS Model Assets

Create a `models/` directory in the root of the project folder and download the Kokoro TTS files:

```bash
mkdir -p models
cd models

# Download Kokoro ONNX model
curl -L -o kokoro-v1.0.onnx https://huggingface.co/fastrtc/kokoro-onnx/resolve/main/kokoro-v1.0.onnx

# Download voices binary file
curl -L -o voices-v1.0.bin https://huggingface.co/fastrtc/kokoro-onnx/resolve/main/voices-v1.0.bin
```

---

## 📂 4. Install Jarvis

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Hash-Overflow-bit/Jarvis.git
   cd Jarvis
   ```
2. **Install Poetry**:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   # Add poetry to your PATH (on macOS/Linux/WSL)
   export PATH="$HOME/.local/bin:$PATH"
   ```
3. **Install Dependencies**:
   ```bash
   poetry install
   ```
4. **Create Data Directories**:
   ```bash
   mkdir -p sandbox workspace logs knowledge
   ```

---

## ⚙️ 5. Configure `.env` File

Create a `.env` file in the root directory:

```ini
# --- General ---
ENVIRONMENT=production
LOG_LEVEL=INFO

# --- Ollama LLM ---
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_KEEP_ALIVE=3600

# --- Whisper STT ---
WHISPER_MODEL=base
WHISPER_DEVICE=cpu               # Change to 'cuda' on Windows/Linux if NVIDIA GPU is present
WHISPER_COMPUTE_TYPE=int8        # Change to 'float16' on GPU

# --- Kokoro TTS ---
TTS_ENGINE=kokoro
KOKORO_VOICE_MODEL=kokoro-v1.0.onnx
KOKORO_VOICES_FILE=voices-v1.0.bin
KOKORO_VOICE_ID=bf_emma
KOKORO_LANG_CODE=en-us

# --- Audio Device ---
AUDIO_INPUT_DEVICE=-1            # -1 uses system default microphone
AUDIO_OUTPUT_DEVICE=-1           # -1 uses system default speaker
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
AUDIO_SILENCE_THRESHOLD=0.002
AUDIO_SILENCE_DURATION=1.5

# --- Session ---
SESSION_MAX_TURNS=20
JARVIS_SYSTEM_PROMPT=You are Jarvis, a helpful local AI assistant. Be concise and precise.

# --- Sandbox ---
SANDBOX_MODE=false               # Set to true to enforce strict sandbox roots
SANDBOX_ROOTS=/absolute/path/to/Jarvis/sandbox

# --- Workspace & Safety ---
DEFAULT_WORKSPACE_DIR=/absolute/path/to/Jarvis/workspace
SAFE_MODE=strict
EMERGENCY_STOP_KEYWORD=JARVIS STOP
AUDIT_LOG_PATH=/absolute/path/to/Jarvis/logs/audit.log

# --- Knowledge Graph ---
KNOWLEDGE_GRAPH_PATH=/absolute/path/to/Jarvis/core/memory/graph.db
KNOWLEDGE_CORPUS_DIRS=knowledge,workspace
GRAPH_WATCH=false
MAX_GRAPH_HOPS=3
GRAPH_TOP_K=8
GRAPH_ENABLED=true
```
*(Make sure to replace `/absolute/path/to/Jarvis` with the actual path of the project on the client's PC.)*

---

## 🧪 6. Testing & Running

1. **Verify Configuration**:
   ```bash
   poetry run python -c "from core.audio.tts import get_tts; tts = get_tts(); tts.speak('Hello! Jarvis audio is fully functional.')"
   ```
2. **Run All Unit Tests**:
   ```bash
   poetry run pytest -v
   ```
3. **Launch Jarvis (Text Mode)**:
   ```bash
   poetry run python main.py --mode text
   ```
4. **Launch Jarvis (Audio Mode)**:
   ```bash
   poetry run python main.py --mode audio
   ```

5. **Build/Refresh Knowledge Graph**:
   Once Jarvis is started, type or speak:
   > *"Jarvis, rebuild your knowledge graph"*
   *(Enter `yes` when prompted to authorize the action).*
