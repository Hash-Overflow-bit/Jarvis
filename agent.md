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
| M3 | GitHub & Poetry Repository Integration | $30 | ✅ DONE |
| M4 | Safety, Sandboxing & Confirmation Boundaries | — | ✅ DONE |
| M4.5 | Local Knowledge Graph Memory | — | ✅ DONE |
| M5 | Core Agent Execution Loop & Kokoro TTS | $60 | ✅ DONE |
| M6 | Local Model Fine-Tuning & Tool-Calling Optimization | $40 | ⬜ NOT STARTED |
| M7 | End-to-End System Integration & Stress Test | $20 | ⬜ NOT STARTED |

---

## Completed Milestones Log

### Session 1 — 2026-08-15
- Installed Poetry 2.4.1 using Python 3.11
- Installed all M1 deps: faster-whisper, sounddevice, numpy 1.26, python-dotenv, requests, rich
- Created full project skeleton
- Ran audit.log checks

### Session 2 — 2026-08-15 (Client Config Alignment)
- Aligned configuration variables with client machine
- Implemented Ollama generate backward compatibility wrapper

### Session 3 — 2026-08-15 (Model Pull & Smoke Tests)
- Finished pulling `llama3.1` model in Ollama.
- Verified all M1 smoke tests (100% green).

### Session 4 — 2026-08-16 (Milestone 2 Secure File Layer)
- Developed `SandboxEnforcer`, `BaseTool`, and `ToolRegistry`.
- Implemented `FileScanner`, `FileCleanup`, and `DirectoryAudit` tools.
- Wrote safety and file tool unit tests (15 passed).

### Session 5 — 2026-08-16 (Milestone 3 Git & Poetry Integration)
- Implemented Git and Poetry execution commands inside isolated subprocesses.
- Added Pip fallback mechanisms for standard non-Poetry requirements.
- Wrote git and package execution tests (22 passed).

### Session 6 — 2026-08-17 (Milestone 4 Safety & Confirmation Boundaries)
- Built `RiskClassifier` mapping tools to LOW/MEDIUM/HIGH/CRITICAL risk profiles.
- Built `ConfirmationGate` for text (console) and voice (TTS/STT confirmation) approval checks.
- Hooked `EmergencyStop` process registry to terminate active subprocesses instantly.
- Built JSON rotating `AuditLogger` at `logs/audit.log` and `DryRunWrapper`.
- Integrated safety checks dynamically in `tool_registry.py` and `main.py` (28 passed).

### Session 7 — 2026-08-17 (Milestone 4.5 Knowledge Graph Memory)
- Created SQLite memory schema and indexes in `schema.sql`.
- Developed `build_graph.py` parser using Ollama fact extraction and UUID5 hashing.
- Developed `recall.py` walk engine utilizing recursive SQL queries (max 3 hops limit).
- Built CLI hook script `recall_hook.py`.
- Integrated recall context injection cleanly inside `session_manager.py`.
- Wrote automated test suite verifying recall boundaries (33 passed, 100% success).

### Session 8 — 2026-08-18 (M4.5 Polish, Fallback Tool Call, and Manipulations)
- Implemented stopword token-based matching to prevent keyword mismatch.
- Developed database-driven name resolution in `build_graph.py` to merge entities across documents regardless of type classification.
- Added self-healing fallback parser for text-based JSON tool calls.
- Built and registered `CreateDirectory` and `WriteFile` tools (34 unit tests green).
- Updated client deployment guide and pushed M4.5 codebase.

### Session 9 — 2026-08-19 (Milestone 5 - Agent Loop & Kokoro TTS Upgrade)
- Created `AgentExecutionLoop` class in `core/orchestrator/agent_loop.py` for task decomposition, verification, and reflection replanning on failure.
- Hooked loop execution directly inside `session_manager.py` with backward compatibility support for native function `tool_calls`.
- Built `KokoroTTS` wrapper class in `core/audio/tts.py` implementing 24kHz low-latency streaming audio.
- Created models downloader script `scripts/download_kokoro_models.py` to cache Kokoro ONNX assets.
- Added new Kokoro parameters to `config.py`, `.env.example`, and `.env`.
- Wrote test suites in `tests/test_agent_loop.py` and `tests/test_kokoro_tts.py` (42/42 tests passing).

### Session 10 — 2026-08-20 (Milestone 5 Update - Dynamic YAML CrewAI Blueprint)
- Built `KokoroTTS` wrapper class in `core/audio/tts.py` implementing 24kHz low-latency streaming audio.
- Created models downloader script `scripts/download_kokoro_models.py` to cache Kokoro ONNX assets.
- Added new Kokoro parameters to `config.py`, `.env.example`, and `.env`.
- Wrote test suites in `tests/test_agent_loop.py` and `tests/test_kokoro_tts.py` (42/42 tests passing).

### Milestone 5: Dynamic YAML CrewAI Blueprint (Completed)
- **Goal:** Allow the LLM to output a structured YAML configuration representing a custom sub-agent, which Jarvis dynamically parses and loads as a `crewai.Agent`.
- **Status:** **COMPLETED**
- **Implementation Details:**
  - `agents/agents_blueprint.yaml`: The single source of truth template.
  - `core/orchestrator/hot_loader.py`: Reads the YAML and instantiates native CrewAI `LLM` and `Agent` objects.
  - `core/orchestrator/agent_registry.py`: In-memory tracking of dynamically loaded agents.
  - `core/orchestrator/baseline_runner.py`: Executes a quick diagnostic smoke-test (with timeout) to ensure the newly loaded agent is functional.
  - `core/orchestrator/tool_mapper.py`: Dynamically maps string-based tool names from the YAML to safe `FileManagementToolkit` and custom Jarvis tools. Updated to respect `SANDBOX_MODE` from `.env`.
- **Testing Infrastructure:**
  - Automated Integration Tests: `tests/test_live_agents.py` verifies the end-to-end flow using the live Ollama model.
  - Interactive CLI Tests: `scripts/manual_test_subagents.py` allows the user to manually trigger the hot-loading and assign arbitrary real-world tasks to the agent.
- **Errors Encountered & Resolved:**
  1. *Pydantic Model Validation Errors*: Occurred when attempting to pass raw `langchain_community` LLM objects into CrewAI. Resolved by instantiating CrewAI's native `crewai.LLM` class.
  2. *OpenAI Connection Fallback Error*: CrewAI's default LiteLLM wrapper defaulted to OpenAI endpoints when local Ollama wasn't running or configured properly. Resolved by explicitly passing `base_url` to the native LLM wrapper.
  3. *Registry KeyError*: Test scripts attempted to retrieve the agent from the registry using `agent_info["module"]` instead of `agent_info["agent"]`.
  4. *LangChain Sandbox Permissions*: The integration test attempted to write to a random pytest `tmp_path` deep in `/private/var/`, which was actively blocked by `FileManagementToolkit`'s `root_dir` security. Resolved by dynamically checking `SANDBOX_MODE`.
  5. *LLM JSON Short-Circuiting*: The LLaMA 3.1 model occasionally output raw JSON tool-calling syntax as its "Final Answer" instead of physically executing the tool through CrewAI's ReAct loop. Resolved by adding explicit enforcement rules to the test prompts.
- **Errors Faced & Resolved (General):**
  - *Dependency conflicts*: Resolved `rich` version constraints during `poetry add`.
  - *Circular Imports*: Resolved circular import loop between `agent_builder`, `hot_loader`, `tool_mapper`, and `tool_registry` by deferring the `tool_registry` import locally inside the `load_approved_tools` function.
  - *CrewAI Tool Pydantic Validation*: CrewAI's `Agent` expects tools to strictly inherit from `crewai.tools.BaseTool` (a Pydantic BaseModel). LangChain toolkit tools failed this type check. Fixed by building a `JarvisCrewTool` wrapper class that adapts both standard and custom tools.
  - *Test LLM Type Validation*: Mocking `OllamaLLM` with `MagicMock` in unit tests failed Pydantic's `BaseLLM` strict instance type checking in CrewAI. Fixed by creating a concrete `MockLLM` subclass inheriting directly from LangChain's `BaseLLM` to satisfy Pydantic.

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
├── agents/
│   └── agents_blueprint.yaml       ← CrewAI dynamic configuration
├── templates/
├── core/
│   ├── __init__.py
│   ├── config.py                   ← Settings singleton
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── audio_device.py         ← Mic/speaker interface
│   │   ├── stt.py                  ← faster-whisper STT + DLL paths
│   │   └── tts.py                  ← Piper + Kokoro TTS streaming
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── function_call_handler.py← LLM tool calling dispatcher
│   │   └── ollama_client.py        ← Ollama REST API wrapper
│   ├── logging/
│   │   └── audit_logger.py         ← Rotating JSON audit trail logger
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── schema.sql              ← 3-table SQLite schema
│   │   ├── extract_prompt.md       ← Ingestion prompt template
│   │   ├── build_graph.py          ← Ingestion pipeline
│   │   ├── recall.py               ← Recursive walking engine
│   │   ├── recall_hook.py          ← JSON prompt interceptor hook
│   │   └── graph_manager.py        ← Management tools
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── agent_loop.py           ← Serialized steps planning, execution & reflection loop
│   │   ├── agent_registry.py       ← Sub-agent runtime state tracking
│   │   ├── baseline_runner.py      ← Verification sandbox runner
│   │   ├── hot_loader.py           ← Dynamic CrewAI agent builder
│   │   ├── rollback_manager.py     ← Failsafe config restoration
│   │   └── tool_mapper.py          ← YAML-to-sandbox tool bindings
│   ├── safety/
│   │   ├── confirmation_gate.py    ← Voice/text approval loop
│   │   ├── dry_run_wrapper.py      ← Mock simulator wrapper
│   │   ├── emergency_stop.py       ← Subprocess halt coordinator
│   │   ├── exception_handler.py    ← Safe execute wrapper
│   │   └── risk_classifier.py      ← Tool risk profiles mapping
│   ├── state/
│   │   ├── __init__.py
│   │   └── session_manager.py      ← Conversational state machine
│   └── tools/
│       ├── __init__.py
│       ├── agent_builder.py        ← Autonomous sub-agent generator tool
│       ├── background_runner.py    ← Subprocess exec manager
│       ├── base_tool.py            ← Abstract tool interface
│       ├── create_directory.py     ← Create folder tool
│       ├── write_file.py           ← Write file content tool
│       ├── directory_audit.py      ← Tree structure audit
│       ├── file_cleanup.py         ← Sandbox file deletion tool
│       ├── file_scanner.py         ← Sandbox scanner tool
│       ├── git_tool.py             ← Git client tool
│       ├── poetry_tool.py          ← Poetry environment manager
│       ├── sandbox_enforcer.py     ← Sandbox path boundaries
│       └── tool_registry.py        ← Tool call interceptor
├── tests/
│   ├── smoke_test.py
│   ├── test_agent_builder.py
│   ├── test_agent_loop.py
│   ├── test_confirmation_gate.py
│   ├── test_emergency_stop.py
│   ├── test_file_tools.py
│   ├── test_git_tool.py
│   ├── test_knowledge_graph.py
│   ├── test_kokoro_tts.py
│   ├── test_poetry_tool.py
│   └── test_sandbox.py
├── scripts/
│   ├── audit.py
│   ├── list_audio_devices.py
│   └── test_whisper.py
├── sandbox/
├── workspace/
├── logs/
└── models/
```

---

## Key Decisions & Notes
- **Windows DLL loading:** ctranslate2 native C++ loader ignores `os.add_dll_directory()`. We dynamically resolve `nvidia.cublas` and `nvidia.cudnn` absolute paths and prepend them directly to `os.environ["PATH"]` on Windows startup.
- **Nested Event Loops:** Used `nest-asyncio` dependency to execute async prompt hooks and voice confirmation gates synchronously inside the conversational LLM loop.
- **Safe Execution Format:** Standardised `safe_execute` to return `{"success": True, "result": ...}` to prevent attribute errors on pydantic model returns.

---

## Environment Variables Reference (M4.5 Additions)

| Variable | macOS Example | Windows Example | Used In |
|---|---|---|---|
| `SAFE_MODE` | `strict` | `strict` | risk_classifier.py |
| `EMERGENCY_STOP_KEYWORD` | `JARVIS STOP` | `JARVIS STOP` | main.py |
| `DRY_RUN` | `false` | `false` | tool_registry.py |
| `KNOWLEDGE_GRAPH_PATH` | `/Users/m2air/Desktop/Jarvis/core/memory/graph.db` | `C:\Users\wmjar\OneDrive\Desktop\Jarvis\core\memory\graph.db` | config.py |
| `KNOWLEDGE_CORPUS_DIRS` | `knowledge,workspace` | `knowledge,workspace` | config.py |
| `GRAPH_ENABLED` | `true` | `true` | session_manager.py |

---

## How to Resume a Session
1. Read `agent.md` (this file) top to bottom
2. Check **Milestone Roadmap** table and find the first `⬜ NOT STARTED` milestone
3. Read the relevant `milestone{N}_plan.md` plan
4. Continue building from that milestone

---

*Last Updated: 2026-08-20 | Session 10 | Milestone 5 Completed (Dynamic YAML Blueprint)*
