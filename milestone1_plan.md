# Milestone 1: Stack & State Verification
> **Pay:** $10 | **Phase:** 1 & 2 Audit

---

## Objective
Audit the existing Windows 11 / WSL 2 / Ollama setup and verify that the conversational state machine and audio streaming (faster-whisper + Piper TTS) are properly wired and stable. Deliver a successful multi-turn conversational smoke test where audio inputs maintain context over several turns without breaking session memory.

---

## Deliverables
- [ ] Working audio pipeline: Microphone → faster-whisper (STT) → Ollama LLM → Piper TTS → Speaker
- [ ] Conversational state machine holding context for at least 5+ turns
- [ ] Session memory persistence (context does NOT reset between turns)
- [ ] Smoke test script that validates the full loop automatically
- [ ] Audit report documenting all installed component versions and health checks
- [ ] Configuration file (`.env`) with OS-specific paths and device indices

---

## What the Client Needs on Windows 11

### Hardware
| Component | Minimum Requirement | Recommended |
|---|---|---|
| CPU | Intel i5 / AMD Ryzen 5 | Intel i7 / Ryzen 7+ |
| RAM | 16 GB | 32 GB |
| GPU | NVIDIA GTX 1660 (6GB VRAM) | NVIDIA RTX 3060+ (12GB VRAM) |
| Microphone | Any USB mic | Dedicated USB cardioid mic |
| Speaker/Headset | Any | Low-latency audio output |
| Storage | 20 GB free | 50 GB SSD free |

### Software to Install (Client PC - Windows 11)
```
1. Windows 11 (22H2 or later)
2. WSL 2 with Ubuntu 22.04 LTS
3. NVIDIA GPU Driver (latest stable, 535+)
4. CUDA Toolkit 12.x (inside WSL 2)
5. cuDNN 8.x (inside WSL 2)
6. Ollama (native Windows OR inside WSL 2)
7. Python 3.11+ (inside WSL 2)
8. Poetry (inside WSL 2)
9. Piper TTS binary (inside WSL 2)
10. faster-whisper (pip install inside WSL 2)
11. Git (inside WSL 2)
12. PulseAudio (for audio bridge between Windows and WSL 2)
```

### Ollama Models to Pull (Client PC)
```bash
ollama pull llama3.1        # Primary conversational model
ollama pull mistral         # Fallback option
```

---

## What Developer Needs on macOS

### Hardware
| Component | Minimum | Recommended |
|---|---|---|
| Mac | Intel Mac 16GB RAM | Apple Silicon M1/M2/M3 |
| RAM | 16 GB | 32 GB |
| Microphone | Built-in | USB mic for accurate testing |
| Speaker | Built-in | Headphones for isolated testing |

### Software to Install (macOS Dev Machine)
```bash
# Core
brew install python@3.11
brew install git
brew install portaudio       # Required by PyAudio/sounddevice
brew install ffmpeg          # Required by faster-whisper
curl -fsSL https://ollama.com/install.sh | sh   # Ollama for Mac

# Python package manager
curl -sSL https://install.python-poetry.org | python3 -

# Piper TTS (macOS binary)
# Download from: https://github.com/rhasspy/piper/releases
```

### macOS Ollama Models
```bash
ollama pull llama3.1
```

---

## Project Structure (After Milestone 1)
```
/Jarvis/
├── .env                          # OS-specific config (NOT committed to git)
├── .env.example                  # Template for config
├── pyproject.toml                # Poetry dependency file
├── poetry.lock
├── README.md
├── core/
│   ├── __init__.py
│   ├── config.py                 # Loads .env, detects OS
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── stt.py                # faster-whisper STT wrapper
│   │   ├── tts.py                # Piper TTS wrapper
│   │   └── audio_device.py      # Abstract audio device handler (cross-platform)
│   ├── llm/
│   │   ├── __init__.py
│   │   └── ollama_client.py     # Ollama REST API wrapper
│   └── state/
│       ├── __init__.py
│       └── session_manager.py   # Conversational state machine
├── tests/
│   ├── test_audio.py
│   ├── test_llm.py
│   └── smoke_test.py            # End-to-end smoke test for M1
└── scripts/
    └── audit.py                 # System audit script
```

---

## Architecture: Conversational State Machine

```
[Microphone Input]
        ↓
[faster-whisper STT]  ←─── CUDA (Windows) / Metal/CPU (Mac)
        ↓
[Transcript Text]
        ↓
[Session Manager]  ←──────  Holds conversation history (list of dicts)
        ↓
[Ollama LLM API]   ←──────  POST http://localhost:11434/api/chat
        ↓
[LLM Response Text]
        ↓
[Piper TTS]
        ↓
[Speaker Output]
        ↓
[Loop back to Microphone]
```

---

## Step-by-Step Build Plan

### Step 1: Project Initialization
```bash
cd /Users/m2air/Desktop/Jarvis
poetry init --name jarvis --python "^3.11" --no-interaction
poetry add faster-whisper sounddevice numpy python-dotenv requests rich
poetry add --group dev pytest black ruff
```

### Step 2: Config Manager (`core/config.py`)
- Detect OS using `platform.system()`
- Load `.env` for device indices, model names, sandbox paths
- Expose a single `settings` object used everywhere

### Step 3: Audio Device Handler (`core/audio/audio_device.py`)
- Abstract class `BaseAudioDevice` with `record()` and `play()` methods
- `MacOSAudioDevice` implementation using `sounddevice`
- `WindowsAudioDevice` implementation using `sounddevice` (same lib, different device index from `.env`)
- Factory function `get_audio_device()` returns correct implementation based on OS

### Step 4: STT Wrapper (`core/audio/stt.py`)
- Load `faster-whisper` model (default: `base.en` for speed)
- `transcribe(audio_chunk) -> str`
- Handle `CUDA` device on Windows, `cpu` or `mps` on Mac

### Step 5: TTS Wrapper (`core/audio/tts.py`)
- Wrap `piper` binary via subprocess call
- `speak(text: str) -> None`
- Find piper binary path from `.env`

### Step 6: Ollama Client (`core/llm/ollama_client.py`)
- Simple `requests` wrapper for `/api/chat`
- Streaming support via `stream=True`

### Step 7: Session Manager (`core/state/session_manager.py`)
```python
class SessionManager:
    def __init__(self, model: str, system_prompt: str):
        self.history = [{"role": "system", "content": system_prompt}]
        self.model = model

    def chat(self, user_input: str) -> str:
        self.history.append({"role": "user", "content": user_input})
        response = ollama_client.chat(self.model, self.history)
        self.history.append({"role": "assistant", "content": response})
        return response
```

### Step 8: Smoke Test (`tests/smoke_test.py`)
- Programmatically injects 5 text turns (bypasses audio for CI testing)
- Verifies context is maintained (e.g., asks "What did I just say?" and checks answer)
- Reports PASS/FAIL

### Step 9: System Audit Script (`scripts/audit.py`)
- Checks: Python version, Ollama running, CUDA available, audio devices listed, Piper binary found
- Outputs a clean report to console

---

## Cross-Platform Challenges, Solutions & Alternatives

| # | Challenge | Solution | Alternative |
|---|---|---|---|
| 1 | **Audio device index differs** between Mac and Windows | Store device index in `.env` per machine | Auto-detect default input/output device |
| 2 | **Sample rate mismatch** — wireless mic may output 48kHz but faster-whisper expects 16kHz | Resample in `audio_device.py` using `scipy.signal.resample` | Use `ffmpeg` subprocess to convert on-the-fly |
| 3 | **CUDA memory clash** — Ollama and faster-whisper both allocate GPU VRAM | Run faster-whisper on CPU (base model is fast enough) OR set `CUDA_VISIBLE_DEVICES` | Use NVIDIA MIG if client has capable GPU |
| 4 | **WSL 2 has no audio hardware access** by default | Route audio via PulseAudio bridge on Windows host | Run entire stack natively on Windows (no WSL) |
| 5 | **Piper TTS binary path** differs between Mac and Windows | Load from `.env` variable `PIPER_BINARY_PATH` | Use `edge-tts` (cloud) or `coqui-tts` as fallback |
| 6 | **Ollama not running** when script starts | `audit.py` checks and auto-starts Ollama | Provide user-facing error with fix instructions |
| 7 | **Session memory grows too large** for LLM context window | Implement sliding window: keep last N turns + system prompt | Summarize old turns using a fast model call |

---

## Testing Strategy

### On macOS (Developer)
```bash
python scripts/audit.py          # System health check
poetry run pytest tests/ -v      # All unit tests
python main.py --mode text       # Text-only loop (no mic needed)
python main.py --mode audio      # Full audio loop
```

### On Windows 11 (Client - inside WSL 2)
```bash
cd /mnt/c/Jarvis
python scripts/audit.py
pytest tests/smoke_test.py -v
python main.py --mode audio
```

---

## Definition of Done
- [ ] `scripts/audit.py` runs cleanly on BOTH Mac and Windows with no errors
- [ ] `pytest tests/smoke_test.py` passes all 5 context-retention assertions
- [ ] 5-turn audio conversation demo is recorded (screen capture)
- [ ] `.env.example` committed to repo with all required keys documented
- [ ] Zero hardcoded paths in the codebase

---

## Estimated Time
| Task | Hours |
|---|---|
| Project setup + Poetry init | 1h |
| Config manager + OS detection | 1h |
| Audio device abstraction layer | 3h |
| STT + TTS wrappers | 2h |
| Ollama client + Session manager | 2h |
| Smoke test + Audit script | 2h |
| Windows testing + debugging | 3h |
| **Total** | **~14h** |
