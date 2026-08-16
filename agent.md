# Jarvis Agent Session Log
> **Read this file at the start of every new session before doing anything.**
> Update this file after every step completed.

---

## Project Overview
Building a local AI assistant ("Jarvis") for a Windows 11 client, developed on macOS.
- **Dev Machine:** macOS (Apple Silicon/Intel) — `/Users/m2air/Desktop/Jarvis`
- **Client Machine:** Windows 11 + WSL 2 + NVIDIA GPU
- **Language:** Python 3.11+
- **Package Manager:** Poetry
- **LLM Backend:** Ollama (local)
- **STT:** faster-whisper
- **TTS:** Piper TTS
- **Frameworks:** CrewAI, LangGraph (Milestone 5+)

---

## Milestone Roadmap

| # | Name | Pay | Status |
|---|---|---|---|
| M1 | Stack & State Verification | $10 | ✅ DONE |
| M2 | Secure File-Management Tool Layer | $20 | ✅ DONE |
| M3 | GitHub & Poetry Repository Integration | $30 | ⬜ NOT STARTED |
| M4 | Safety, Sandboxing & Confirmation Boundaries | — | ⬜ NOT STARTED |
| M5 | Dynamic Sub-Agent Builder | $60 | ⬜ NOT STARTED |
| M6 | Local Model Fine-Tuning & Tool-Calling Optimization | $40 | ⬜ NOT STARTED |
| M7 | End-to-End System Integration & Stress Test | $20 | ⬜ NOT STARTED |

---

## Current Milestone: M3 — GitHub & Poetry Repository Integration

### M2 Steps

| Step | Description | Status |
|---|---|---|
| 1 | Create `core/tools/sandbox_enforcer.py` and implement path validation | ✅ DONE |
| 2 | Write Pydantic input/output schemas in `schemas/` folder | ✅ DONE |
| 3 | Create `core/tools/base_tool.py` abstract interface | ✅ DONE |
| 4 | Implement `FileScanner` tool with directory listing + metadata | ✅ DONE |
| 5 | Implement `FileCleanup` tool using `send2trash` | ✅ DONE |
| 6 | Implement `DirectoryAudit` tool for tree visualization | ✅ DONE |
| 7 | Create `core/tools/tool_registry.py` with Ollama schema exporter | ✅ DONE |
| 8 | Implement `core/llm/function_call_handler.py` to parse JSON calls | ✅ DONE |
| 9 | Add sandbox security unit tests in `tests/test_sandbox.py` | ✅ DONE |
| 10 | Add file tool validation unit tests in `tests/test_file_tools.py` | ✅ DONE |

---

## Completed Steps Log

### Session 1 — 2026-08-15
- ✅ Installed Poetry 2.4.1 using Python 3.11 (system Python 3.9 has venv bug)
- ✅ Created Poetry project with Python ^3.11
- ✅ Installed all M1 deps: faster-whisper, sounddevice, numpy 1.26, python-dotenv, requests, rich
- ✅ Installed dev deps: pytest, pytest-asyncio, black, ruff
- ✅ **numpy pinned to `>=1.26,<2.0`** — numpy 2.x requires Python 3.12, we're on 3.11
- ✅ Created full project skeleton (all dirs + `__init__.py` files)
- ✅ Wrote all 10 core M1 files
- ✅ Ran `scripts/audit.py` — Python, .env, faster-whisper, audio devices all PASS
- ⚠️ Audit: Ollama FAIL (not running) — needs `ollama serve` before testing
- ⚠️ Audit: Piper TTS FAIL (not configured) — console fallback is active

### Session 2 — 2026-08-15 (Client Config Alignment)
- ✅ Aligned ALL config values to match client's existing setup exactly:
  - `WHISPER_MODEL`: `base.en` → `base` (client uses multilingual `base`)
  - `OLLAMA_URL`: Added `ollama_generate_url` property = `http://localhost:11434/api/generate`
  - `PIPER_VOICE_MODEL`: Now accepts filename only (`en_US-lessac-medium.onnx`) — resolves to `models/` dir
  - `SAMPLE_RATE = 16000`, `CHANNELS = 1` — verified match
- ✅ Added `generate_compat()` to `ollama_client.py` — mirrors client's `/api/generate` call exactly
- ✅ Added `_stream_generate()` for streaming `/api/generate` responses
- ✅ Updated `chat()` to use `settings.ollama_chat_url` (not hardcoded string)
- ✅ Import verification passed — all values print correctly

### Session 3 — 2026-08-15 (Model Pull & Smoke Tests)
- ✅ Finished pulling `llama3.1` model in Ollama.
- ✅ Successfully ran `pytest tests/smoke_test.py -v` — 6 tests passed (100% success)!
- ✅ Configured Piper binary path (`/Users/m2air/Downloads/piper 2/piper`) and voice model.
- ✅ Ran `scripts/audit.py` — all checks passed (100% green)!
- ✅ Created [walkthrough.md](file:///Users/m2air/.gemini/antigravity-ide/brain/db2b2fbb-25a6-4340-a230-0daebcd64019/walkthrough.md) documenting Milestone 1 completion.

### Session 4 — 2026-08-16 (Milestone 2 Secure File Layer)
- ✅ Installed `pydantic`, `send2trash`, and `watchdog` dependencies.
- ✅ Implemented `core/tools/sandbox_enforcer.py` path verification enforcer.
- ✅ Defined Pydantic models inside `schemas/`.
- ✅ Developed `BaseTool` abstract interface, `ToolRegistry`, and `FunctionCallHandler`.
- ✅ Developed `FileScanner`, `FileCleanup` (with WSL `.jarvis_trash/` directory fallback), and `DirectoryAudit` tools.
- ✅ Registered tools globally and wired native function calling into `OllamaClient` and `SessionManager`.
- ✅ Created safety unit tests `tests/test_sandbox.py` (directory traversal, external symlinks).
- ✅ Created tool unit tests `tests/test_file_tools.py` (functional validation, mock integration).
- ✅ Successfully ran full pytest test suite (15 passed, 100% success).
- ✅ Created [walkthrough.md](file:///Users/m2air/.gemini/antigravity-ide/brain/5fd18e5a-1c62-4370-a490-1415ad58d30b/walkthrough.md) documenting Milestone 2 completion.

---

## Current File Structure
```
/Users/m2air/Desktop/Jarvis/
├── agent.md                        ← THIS FILE (update every session)
├── main.py                         ← Entry point (--mode text | --mode audio)
├── pytest.ini                      ← pytest config
├── pyproject.toml                  ← Poetry dependencies
├── poetry.lock
├── .env                            ← Active config (gitignored)
├── .env.example                    ← Template (committed to git)
├── .gitignore
├── core/
│   ├── __init__.py
│   ├── config.py                   ← OS detection + settings singleton
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── audio_device.py         ← Cross-platform mic/speaker (sounddevice)
│   │   ├── stt.py                  ← faster-whisper STT wrapper
│   │   └── tts.py                  ← Piper TTS + ConsoleTTS fallback
│   ├── llm/
│   │   ├── __init__.py
│   │   └── ollama_client.py        ← Ollama REST API wrapper
│   └── state/
│       ├── __init__.py
│       └── session_manager.py      ← Conversational state machine
├── tests/
│   ├── __init__.py
│   └── smoke_test.py               ← M1: 6 tests (5-turn context + extras)
├── scripts/
│   ├── __init__.py
│   ├── audit.py                    ← Full system health check
│   └── list_audio_devices.py       ← Helper: find audio device indices
├── sandbox/
│   └── test_files/
│       └── .gitkeep
├── logs/
│   └── .gitkeep
├── models/                         ← Place Piper voice .onnx files here
├── milestone1_plan.md
├── milestone2_plan.md
├── milestone3_plan.md
├── milestone4_plan.md
├── milestone5_plan.md
├── milestone6_plan.md
└── milestone7_plan.md
```

---

## Key Decisions & Notes
- **Audio strategy:** Use `sounddevice` on both Mac and Windows (same API, different device index per `.env`)
- **STT device:** Use `cpu` on macOS, `cuda` on Windows (configurable via `.env`)
- **TTS:** Piper TTS binary called via subprocess (binary path in `.env`)
- **Ollama API:** REST call to `http://localhost:11434` — same on both platforms
- **No hardcoded paths** — everything via `pathlib.Path` and `.env`
- **No `shell=True`** in any subprocess call

---

## Environment Variables Reference

| Variable | macOS Example | Windows Example | Used In |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `production` | config.py |
| `OLLAMA_MODEL` | `llama3.1` | `llama3.1` | ollama_client.py |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `http://localhost:11434` | ollama_client.py |
| `WHISPER_MODEL` | `base` | `base` | stt.py |
| `WHISPER_DEVICE` | `cpu` | `cuda` | stt.py |
| `PIPER_BINARY_PATH` | `/Users/m2air/Downloads/piper 2/piper` | `/home/user/.local/bin/piper` | tts.py |
| `PIPER_VOICE_MODEL` | `en_US-lessac-medium.onnx` | `en_US-lessac-medium.onnx` | tts.py |
| `AUDIO_INPUT_DEVICE` | `-1` (default) | `1` (USB mic index) | audio_device.py |
| `AUDIO_OUTPUT_DEVICE` | `-1` (default) | `-1` (default) | audio_device.py |
| `AUDIO_SAMPLE_RATE` | `16000` | `16000` | audio_device.py |
| `SESSION_MAX_TURNS` | `20` | `20` | session_manager.py |
| `SANDBOX_ROOTS` | `/Users/m2air/Desktop/Jarvis/sandbox` | `C:\Jarvis\sandbox` | (M2) |
| `LOG_LEVEL` | `DEBUG` | `INFO` | all |

---

## Blocking Issues / Open Questions
- [ ] Confirm client's GPU model (affects WHISPER_DEVICE and model choices)
- [ ] Confirm Piper TTS binary location on client's WSL 2
- [ ] Confirm if client wants wake-word (M7) or push-to-talk for initial testing

---

## How to Resume a Session
1. Read `agent.md` (this file) top to bottom
2. Check **Current Milestone** section and find the first `⬜ TODO` step
3. Read the relevant `milestone{N}_plan.md` for that step
4. Continue building from that step
5. Update this file after completing each step

---

*Last Updated: 2026-08-16 | Session 4 | Completed M2 Verification*
