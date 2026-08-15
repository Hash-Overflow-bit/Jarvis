# Jarvis Windows 11 / WSL 2 Deployment Guide (Milestone 1)

This guide explains how to deploy the Jarvis system (Milestone 1) on the client's Windows 11 PC using WSL 2 (Ubuntu 22.04 LTS) and native Ollama.

---

## 💻 1. Prerequisites on Windows 11

### Step 1.1: Enable WSL 2 and Install Ubuntu
Open PowerShell as Administrator and run:
```powershell
wsl --install -d Ubuntu-22.04
```
*Restart the PC if prompted.*

### Step 1.2: Install NVIDIA GPU Drivers (If client has NVIDIA GPU)
Make sure the client has the latest NVIDIA drivers installed on the Windows host.
[NVIDIA Driver Downloads](https://www.nvidia.com/Download/index.aspx)

---

## 🦙 2. Setup Ollama on Windows Host

We recommend running Ollama directly on the Windows host (not inside WSL) for easiest GPU access.
1. Download and run the installer from: [ollama.com/download/windows](https://ollama.com/download/windows)
2. Open Windows command prompt or PowerShell and run:
   ```cmd
   ollama pull llama3.1
   ```
3. Verify Ollama is running by opening `http://localhost:11434` in the browser on Windows.

---

## 🐧 3. Setup Python & Poetry inside WSL 2 (Ubuntu)

Open the Ubuntu terminal in Windows and run the following setup commands:

### Step 3.1: Update System & Install PortAudio (for audio capture)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev git ffmpeg portaudio19-dev
```

### Step 3.2: Install Poetry
```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
```

### Step 3.3: Verify Installations
```bash
python3 --version
poetry --version
git --version
```

---

## 📂 4. Deploy Jarvis Code

### Step 4.1: Transfer Code to Windows
Create a folder `C:\Jarvis` on the Windows host.
WSL automatically mounts the Windows C drive. Navigate to it inside your Ubuntu terminal:
```bash
cd /mnt/c/
mkdir Jarvis
cd Jarvis
```
*(Copy the codebase files from the Mac to this directory via Git, USB, or local network share).*

### Step 4.2: Install Python Dependencies
Inside `/mnt/c/Jarvis` on the WSL terminal, run:
```bash
poetry install
```

---

## 🗣️ 5. Setup Piper TTS inside WSL 2

### Step 5.1: Download Piper Linux binary
```bash
cd /mnt/c/Jarvis
mkdir -p bin
cd bin
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_linux_x86_64.tar.gz
tar -xvf piper_linux_x86_64.tar.gz
chmod +x piper/piper
```

### Step 5.2: Create models directory & download voice
```bash
cd /mnt/c/Jarvis
mkdir -p models
cd models
# Download ONNX voice model
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
# Download ONNX config file
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

---

## ⚙️ 6. Configure `.env` on Windows/WSL 2

Create a file named `.env` in the root `/mnt/c/Jarvis/.env` and copy-paste this configuration:

```ini
# --- General ---
ENVIRONMENT=production
LOG_LEVEL=INFO

# --- Ollama LLM ---
# Since Ollama runs on Windows host, WSL accesses it via localhost/127.0.0.1
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_KEEP_ALIVE=3600

# --- Whisper STT ---
WHISPER_MODEL=base
# Use 'cuda' if client has an NVIDIA GPU, otherwise 'cpu'
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# --- Piper TTS ---
PIPER_BINARY_PATH=/mnt/c/Jarvis/bin/piper/piper
PIPER_VOICE_MODEL=en_US-lessac-medium.onnx

# --- Audio Device ---
AUDIO_INPUT_DEVICE=-1
AUDIO_OUTPUT_DEVICE=-1
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
AUDIO_CHUNK_DURATION=30
AUDIO_SILENCE_THRESHOLD=0.002
AUDIO_SILENCE_DURATION=1.0

# --- Session ---
SESSION_MAX_TURNS=20
JARVIS_SYSTEM_PROMPT=You are Jarvis, a helpful local AI assistant. Be concise and precise.

# --- Sandbox (M2+) ---
SANDBOX_ROOTS=/mnt/c/Jarvis/sandbox
```

---

## 🧪 7. Test and Run on Windows/WSL 2

### Step 7.1: Run the Audit Script
Verify that everything is configured correctly:
```bash
poetry run python scripts/audit.py
```
*All checks should show `✅ PASS`.*

### Step 7.2: Run the Smoke Test
```bash
poetry run pytest tests/smoke_test.py -v
```
*All tests should pass.*

### Step 7.3: Run Jarvis
* **Text Mode:**
  ```bash
  poetry run python main.py --mode text
  ```
* **Audio Mode:**
  ```bash
  poetry run python main.py --mode audio
  ```
