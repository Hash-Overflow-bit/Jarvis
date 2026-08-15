# Milestone 7: End-to-End System Integration & Stress Test
> **Pay:** $20 | **Phase:** Final Integration & Deployment

---

## Objective
Execute a complete, uninterrupted pipeline cycle: **Voice Wake-Word → Multi-Turn Conversation → Tool Intent Recognition → Autonomous Action (File cleanup, Git clone, or Agent build) → Spoken Audio Response**. Deliver a fully operational, hands-free local Jarvis assistant ready for everyday deployment on the client's Windows 11 machine.

---

## Deliverables
- [ ] Wake-word detection system (e.g., "Hey Jarvis") using `openwakeword` or `pvporcupine`
- [ ] End-to-end pipeline orchestrator tying all milestones together
- [ ] WebSocket/event-loop architecture eliminating race conditions
- [ ] Memory leak detection and fix (long-running session stress test)
- [ ] Audio-to-action latency measurement and optimization (target: <3s STT→Response)
- [ ] Production deployment package for Windows 11 (installer/setup script)
- [ ] System startup script (auto-start Jarvis on Windows boot via Task Scheduler)
- [ ] Final stress test report: 30-minute uninterrupted session with 20+ commands
- [ ] User manual (README) for the client

---

## What the Client Needs on Windows 11

### Hardware
| Component | Minimum | Why It Matters |
|---|---|---|
| GPU (NVIDIA) | GTX 1660 6GB | CUDA for Whisper + Ollama in parallel |
| RAM | 32GB | Long-running sessions + concurrent tasks |
| USB Mic | Any cardioid USB | Clean wake-word detection |
| Speaker | Any | TTS playback |
| SSD | 50GB free | Model storage + workspace |

### Final Software Stack (Client - Full List)
```
WINDOWS HOST LAYER:
├── Windows 11 (22H2+)
├── NVIDIA GPU Driver 535+
├── WSL 2 (Ubuntu 22.04 LTS)
├── Ollama for Windows (native) OR Ollama inside WSL 2
├── Windows Task Scheduler entry (auto-start Jarvis)
└── PulseAudio for Windows (if audio routed through WSL)

WSL 2 / UBUNTU LAYER:
├── Python 3.11
├── Poetry
├── CUDA 12.x + cuDNN 8.x
├── faster-whisper
├── Piper TTS binary + voice model
├── openwakeword / pvporcupine (wake-word)
├── CrewAI + LangGraph
├── All Jarvis Python dependencies (from pyproject.toml)
└── Git 2.40+

OLLAMA MODELS:
├── qwen2.5:7b (primary — best tool-calling)
└── llama3.1 (fallback conversational)
```

### Windows Auto-Start Setup (Client)
```powershell
# Run in PowerShell as Administrator
# Creates a Task Scheduler entry to start Jarvis on login
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-e bash -c 'cd /mnt/c/Jarvis && python main.py'"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "JarvisAutoStart" -Action $action -Trigger $trigger -RunLevel Highest
```

---

## What Developer Needs on macOS

### Additional Software
```bash
# Wake-word detection
poetry add openwakeword   # Free, runs locally

# Memory profiling for stress test
poetry add memray tracemalloc

# WebSocket support
poetry add websockets

# Process management
poetry add psutil
```

---

## Final Project Structure (Complete — All Milestones)
```
/Jarvis/
├── .env                              # Active config (gitignored)
├── .env.example                      # Template with all required vars
├── pyproject.toml
├── poetry.lock
├── README.md                         # User manual for client
├── main.py                           # ENTRY POINT: Full pipeline
├── main_text.py                      # Text-only mode (dev/testing)
│
├── core/
│   ├── config.py                     # M1: OS detection + settings
│   ├── audio/
│   │   ├── audio_device.py           # M1: Cross-platform audio
│   │   ├── stt.py                    # M1: faster-whisper STT
│   │   ├── tts.py                    # M1: Piper TTS
│   │   └── wake_word.py              # M7: Wake-word detector (NEW)
│   ├── llm/
│   │   ├── ollama_client.py          # M1: Ollama API wrapper
│   │   ├── prompt_manager.py         # M6: Versioned prompts
│   │   ├── tool_call_validator.py    # M6: Hallucination detection
│   │   └── fallback_handler.py      # M6: Retry logic
│   ├── state/
│   │   ├── session_manager.py        # M1: Conversation history
│   │   └── pipeline_orchestrator.py  # M7: Main event loop (NEW)
│   ├── tools/
│   │   ├── base_tool.py              # M2: Abstract tool
│   │   ├── tool_registry.py          # M2: Tool registration
│   │   ├── sandbox_enforcer.py       # M2: Path security
│   │   ├── file_scanner.py           # M2: File scanning
│   │   ├── file_cleanup.py           # M2: File cleanup
│   │   ├── directory_audit.py        # M2: Directory audit
│   │   ├── git_tool.py               # M3: Git operations
│   │   ├── poetry_tool.py            # M3: Poetry operations
│   │   ├── background_runner.py      # M3: Async subprocess
│   │   └── agent_builder.py          # M5: Dynamic agent builder
│   ├── safety/
│   │   ├── confirmation_gate.py      # M4: User confirmation
│   │   ├── risk_classifier.py        # M4: Tool risk levels
│   │   ├── emergency_stop.py         # M4: Kill switch
│   │   ├── exception_handler.py      # M4: Global error catcher
│   │   └── dry_run_wrapper.py        # M4: Simulation mode
│   ├── orchestrator/
│   │   ├── agent_registry.py         # M5: Agent tracking
│   │   ├── hot_loader.py             # M5: Dynamic imports
│   │   ├── code_validator.py         # M5: AST security
│   │   ├── baseline_runner.py        # M5: Agent smoke tests
│   │   └── rollback_manager.py       # M5: Revert bad agents
│   └── logging/
│       └── audit_logger.py           # M4: Structured logs
│
├── prompts/
│   ├── system_prompt_v1.md
│   └── system_prompt_current.md
├── schemas/                          # Pydantic models
├── templates/                        # Jinja2 agent templates
├── agents/                           # Generated agents
├── workspace/                        # Cloned repos
├── sandbox/                          # Safe file operations zone
├── benchmarks/                       # M6 benchmark suite
├── logs/                             # Audit logs
└── tests/                            # All tests
    ├── smoke_test.py                  # M1
    ├── test_sandbox.py                # M2
    ├── test_file_tools.py             # M2
    ├── test_git_tool.py               # M3
    ├── test_poetry_tool.py            # M3
    ├── test_confirmation_gate.py      # M4
    ├── test_emergency_stop.py         # M4
    ├── test_agent_builder.py          # M5
    ├── test_hot_loader.py             # M5
    ├── test_tool_call_validator.py    # M6
    ├── test_fallback_handler.py       # M6
    └── stress_test.py                 # M7 (NEW)
```

---

## Architecture: Complete End-to-End Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPELINE ORCHESTRATOR                     │
│                  (pipeline_orchestrator.py)                  │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ↓                    ↓                    ↓
  [Audio Thread]      [LLM Thread]         [Tool Thread]
         │                    │                    │
         ↓                    ↓                    ↓
[WakeWordDetector]  [SessionManager]    [BackgroundRunner]
         │            (Ollama API)       (async subprocess)
         ↓                    │                    │
[AudioDevice.record()]        ↓                    ↓
         │            [FallbackHandler]  [ToolRegistry.execute()]
         ↓                    │                    │
  [STT.transcribe()]  [ToolCallValidator]           │
         │                    │                    │
         └──────────→ [SafetyGate] ←───────────────┘
                             │
                    [ConfirmationGate]
                    [EmergencyStop listener]
                             │
                             ↓
                     [TTS.speak()]
                             │
                     [AuditLogger.log()]
```

---

## Step-by-Step Build Plan

### Step 1: Wake-Word Detection (`core/audio/wake_word.py`)
```python
import openwakeword
from openwakeword.model import Model

class WakeWordDetector:
    def __init__(self, wake_word: str = "hey_jarvis"):
        self.model = Model(wakeword_models=[wake_word])
        self.wake_word = wake_word

    async def listen_for_wake_word(self, audio_stream) -> bool:
        """Continuously listens and returns True when wake-word detected"""
        chunk = await audio_stream.read_chunk()
        prediction = self.model.predict(chunk)
        return prediction.get(self.wake_word, 0) > 0.5
```

**Cross-platform note:** `openwakeword` is pure Python and works on both macOS and Windows. Uses CPU only — no GPU dependency.

### Step 2: Pipeline Orchestrator (`core/state/pipeline_orchestrator.py`)
The main event loop using `asyncio` to prevent race conditions:

```python
import asyncio

class PipelineOrchestrator:
    def __init__(self):
        self.running = True
        self.audio_queue = asyncio.Queue()     # STT → LLM
        self.response_queue = asyncio.Queue()  # LLM → TTS
        self.tool_queue = asyncio.Queue()      # Tool calls pending

    async def run(self):
        await asyncio.gather(
            self.audio_capture_loop(),
            self.llm_processing_loop(),
            self.tts_output_loop(),
            self.tool_execution_loop(),
            self.emergency_stop_listener(),
        )

    async def audio_capture_loop(self):
        """Runs continuously. Detects wake-word, then records utterance."""
        while self.running:
            # 1. Wait for wake word
            await wake_word_detector.listen_for_wake_word(audio_stream)
            tts.speak("Yes?")  # Acknowledgement chirp

            # 2. Record utterance until silence
            audio_data = await audio_device.record_until_silence()

            # 3. Transcribe
            text = stt.transcribe(audio_data)
            if text.strip():
                await self.audio_queue.put(text)

    async def llm_processing_loop(self):
        """Processes transcribed text through LLM, detects tool calls."""
        while self.running:
            user_input = await self.audio_queue.get()

            # Check for emergency stop
            if emergency_stop.is_triggered(user_input):
                emergency_stop.trigger()
                tts.speak("Stopping all tasks.")
                continue

            # Get LLM response
            response = await session_manager.chat(user_input)

            # Validate tool call
            tool_call, error = tool_call_validator.parse_and_validate(response, tool_registry)

            if tool_call:
                await self.tool_queue.put(tool_call)
            else:
                await self.response_queue.put(response)

    async def tool_execution_loop(self):
        """Executes tool calls with safety gates."""
        while self.running:
            tool_call = await self.tool_queue.get()

            # Safety gate check
            risk = risk_classifier.classify(tool_call["tool"])
            if risk in [HIGH, CRITICAL]:
                confirmed = await confirmation_gate.request_confirmation(
                    tool_call["tool"], tool_call["args"]
                )
                if not confirmed:
                    await self.response_queue.put("Understood. Action cancelled.")
                    continue

            # Execute
            result = await safe_execute(tool_registry.get(tool_call["tool"]), tool_call["args"])

            # Feed result back to LLM for natural language summary
            summary = await session_manager.summarize_tool_result(result)
            await self.response_queue.put(summary)

    async def tts_output_loop(self):
        """Speaks responses."""
        while self.running:
            text = await self.response_queue.get()
            tts.speak(text)
```

### Step 3: Memory Leak Prevention
```python
# In session_manager.py
MAX_HISTORY_TURNS = 20  # Keep last 20 turns to prevent memory growth

def _trim_history(self):
    if len(self.history) > (MAX_HISTORY_TURNS * 2) + 1:  # +1 for system prompt
        # Keep system prompt + last MAX_HISTORY_TURNS turns
        self.history = [self.history[0]] + self.history[-(MAX_HISTORY_TURNS * 2):]
```

### Step 4: Latency Optimization
Target: **<3 seconds from speech end to first audio output word**

```
Component breakdown (target):
├── STT (faster-whisper base.en, CUDA): 0.3-0.8s
├── Ollama LLM (qwen2.5:7b, first token): 0.5-1.5s
├── TTS (Piper, streaming): 0.2-0.5s
└── Total target: ~1-3s
```

Optimization techniques:
- **Streaming TTS**: Start speaking as soon as first sentence is generated (don't wait for full response)
- **Whisper model size**: Use `base.en` for speed, `small.en` for accuracy
- **Ollama keep_alive**: Set `keep_alive=3600` to keep model loaded in VRAM
- **Async pipeline**: Audio processing and TTS run in parallel with LLM generation

### Step 5: Stress Test (`tests/stress_test.py`)
```python
async def test_30_minute_session():
    """30-minute uninterrupted session with 20+ diverse commands"""
    commands = [
        "List all files in the workspace",
        "What did I just ask you?",      # Context test
        "Clone the requests library",
        "How many files did you find?",   # Context test
        "Build a simple calculator agent",
        # ... 15+ more commands
    ]

    start_time = time.time()
    memory_start = psutil.Process().memory_info().rss

    for cmd in commands:
        result = await pipeline.process_text_command(cmd)
        latency = result["latency_ms"]
        assert latency < 5000, f"Latency spike: {latency}ms"

    duration = time.time() - start_time
    memory_end = psutil.Process().memory_info().rss
    memory_growth_mb = (memory_end - memory_start) / (1024 * 1024)

    assert memory_growth_mb < 100, f"Memory leak detected: +{memory_growth_mb:.1f}MB"
    print(f"Stress test PASSED: {duration:.1f}s, +{memory_growth_mb:.1f}MB RAM")
```

### Step 6: Windows Deployment Package
```
/Jarvis/
└── deploy/
    ├── windows_setup.ps1      # PowerShell: installs WSL, CUDA, pulls models
    ├── wsl_setup.sh           # Bash: installs Python, Poetry, all dependencies
    ├── start_jarvis.bat       # Double-click to start Jarvis on Windows
    └── install_autostart.ps1  # Registers Task Scheduler entry
```

---

## Cross-Platform Challenges, Solutions & Alternatives

| # | Challenge | Solution | Alternative |
|---|---|---|---|
| 1 | **Audio-to-action latency spikes** — network, disk I/O, or model loading | Keep Ollama model loaded with `keep_alive`; stream TTS; profile with `cProfile` | Use smaller/faster model for latency-sensitive sessions |
| 2 | **Race condition** — TTS speaking while STT picks up its own voice | Mute microphone input while TTS is playing (gate the audio input queue) | Use speaker-isolated directional mic; add post-TTS silence buffer |
| 3 | **Wake-word false positives** — triggers on background speech/TV | Raise confidence threshold; use far-field `hey_jarvis` model | Use push-to-talk (keyboard shortcut) as alternative mode |
| 4 | **Memory leaks** from long-running sessions | Sliding history window; explicit garbage collection after tool runs | Periodic pipeline restart (e.g., every 2 hours via scheduler) |
| 5 | **openwakeword on WSL 2** — limited audio hardware access | Use Windows-native Python process for audio; communicate via local socket to WSL | Use pvporcupine (commercial, but has native Windows support) |
| 6 | **asyncio event loop conflicts** — multiple audio streams + tool processes | Single `asyncio.get_event_loop()` with separate `Queue` objects per pipeline stage | Use `multiprocessing` for CPU-bound tasks to avoid GIL |
| 7 | **Windows Task Scheduler fails** to start WSL process | Use `wsl.exe --exec` command syntax; run script as SYSTEM user | Create a Windows Service wrapper with `nssm` |
| 8 | **Piper TTS audio output** on WSL 2 — no native speaker access | Write TTS audio to a temp WAV file, play via `powershell.exe -c (New-Object Media.SoundPlayer)` | Run TTS on Windows-native Python process (same audio split as wake-word) |

---

## Testing Strategy

### macOS (Developer — Full Integration)
```bash
# Text-mode integration (no mic needed)
python main_text.py

# Audio mode integration (requires mic)
python main.py

# Stress test
poetry run pytest tests/stress_test.py -v -s

# Latency profiling
python scripts/latency_benchmark.py
```

### Windows 11 (Client — Acceptance Testing)
```bash
# Run from WSL 2
cd /mnt/c/Jarvis
python scripts/audit.py            # Full system health check

# Full pipeline test
python main.py

# Stress test
pytest tests/stress_test.py -v -s
```

### Final Acceptance Test Checklist (Run with Client)
- [ ] Say "Hey Jarvis" → Jarvis responds within 2 seconds
- [ ] 5-turn conversation with context maintained
- [ ] Say "List files in my workspace" → correct files spoken back
- [ ] Say "Clean up old log files" → confirmation requested → confirmed → files cleaned
- [ ] Say "Clone the requests repo" → cloned successfully + spoken confirmation
- [ ] Say "Build a summarizer agent" → code written, loaded, tested, confirmed
- [ ] Say "JARVIS STOP" mid-task → all tasks cancelled immediately
- [ ] 30-minute stress test → no crashes, no memory leaks
- [ ] Windows auto-start → Jarvis starts automatically on next login

---

## Deployment Checklist for Client

### Pre-Deployment (Developer)
- [ ] All tests pass: `pytest tests/ -v` (100% pass rate)
- [ ] Benchmark report shows ≥90% tool accuracy
- [ ] `.env.example` fully documented
- [ ] `README.md` written for client (step-by-step setup)
- [ ] Stress test report attached to final deliverable

### Client Setup Steps (Windows 11)
1. Install WSL 2 + Ubuntu 22.04 (`wsl --install`)
2. Install NVIDIA CUDA drivers
3. Run `deploy/windows_setup.ps1` (installs all dependencies)
4. Run `deploy/wsl_setup.sh` (Python env + models)
5. Edit `.env` with personal settings (sandbox paths, GitHub token)
6. Run `scripts/audit.py` — all checks must pass
7. Run `python main.py` — first boot test
8. Run `deploy/install_autostart.ps1` — enable on boot

---

## Definition of Done
- [ ] Full pipeline runs end-to-end on Windows 11: voice → action → voice
- [ ] Wake-word "Hey Jarvis" reliably triggers within 1 second
- [ ] Latency from speech-end to first TTS word ≤ 3 seconds
- [ ] 30-minute stress test completes with 0 crashes and <100MB memory growth
- [ ] No audio race conditions (mic doesn't pick up TTS output)
- [ ] Emergency stop works instantly during any operation
- [ ] Jarvis auto-starts on Windows login via Task Scheduler
- [ ] Client can set up from scratch using `README.md` alone
- [ ] All 7 milestone deliverables demonstrated in a single recorded demo session

---

## Complete Project Timeline

| Milestone | Description | Pay | Est. Hours |
|---|---|---|---|
| M1 | Stack & State Verification | $10 | 14h |
| M2 | Secure File-Management Layer | $20 | 18h |
| M3 | GitHub & Poetry Integration | $30 | 20h |
| M4 | Safety & Sandboxing | — | 18h |
| M5 | Dynamic Sub-Agent Builder | $60 | 30h |
| M6 | LLM Fine-Tuning & Optimization | $40 | 28h |
| M7 | End-to-End Integration & Stress Test | $20 | 20h |
| **TOTAL** | | **$180** | **~148h** |

---

## Estimated Time
| Task | Hours |
|---|---|
| Wake-word integration | 4h |
| Pipeline orchestrator (asyncio event loop) | 6h |
| Memory leak detection + fixes | 3h |
| Latency optimization | 4h |
| Stress test suite | 3h |
| Windows deployment package | 4h |
| Task Scheduler auto-start | 1h |
| Client README + documentation | 2h |
| Final acceptance testing with client | 3h |
| **Total** | **~30h** |
