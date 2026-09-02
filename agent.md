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
- **TTS:** Piper TTS / Kokoro TTS
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
| M5.5 | Grounded Writing, Web Research & Data Extraction | — | ✅ DONE |
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
- Built dynamic YAML CrewAI agent builder, hot loader, baseline runner, and tool mapper.
- Integrated `JarvisCrewTool` wrapper adapting custom tools to CrewAI.

### Session 11 — 2026-08-25 (Session Isolation & Execution State Cleanup)
- Fixed session isolation bug where prior tool execution details (`yeah.txt`, `Hello Jsss`, `user_goal.txt`) leaked into subsequent conversational turns or interview requests.
- Filtered raw `tool_calls` payloads and `role: "tool"` execution blobs out of fallback prompt history in `_synthesize_fallback()`.
- Added strict `CRITICAL CONVERSATIONAL ISOLATION & TRUTH RULES` to the fallback prompt.
- Extended `_is_conversational_or_informative()` to recognize interview requests (e.g. `Start a new isolated interview. Ask one question about my current professional role`).
- Enforced clean per-run local execution state (`completed_steps = []`) in `AgentExecutionLoop.run()`.

### Session 12 — 2026-08-26 (Grounded Writing, Web Research & Data Extraction Workflow)
- **Goal:** Build a grounded 4-mode writing pipeline to cleanly distinguish between Simple Writing, Research-Backed Writing, Local Document Writing, and Data Extraction.
- **Implemented Components:**
  - `core/writing/sources.py`: Defined `EvidenceSource` model (`source_type`, `title`, `location`, `url`, `content`, `verified`).
  - `core/writing/extractor.py`: Built zero-hallucination `DataExtractor` for TXT, MD, CSV, JSON, and documents into normalized schema (`source`, `data`, `warnings`). Absent fields return `null` / `"not found"`.
  - `core/writing/pipeline.py`: Built `WritingPipeline` for 4 workflow modes:
    1. *Mode A (Simple Writing)*: 0 research calls, clean generation based on user prompt.
    2. *Mode B (Research Writing)*: Gathers evidence via `web_search`. Enforces strict URL verification (strips unretrieved fake links). If retrieval fails, explicitly states it could not verify online search results.
    3. *Mode C (Local Document Writing)*: Reads local files via `read_file`, preserves source attribution across multi-document summaries.
    4. *Mode D (Data Extraction)*: Extracts structured key-value data without guessing missing fields.
  - `core/tools/web_search.py`: Created real-time DuckDuckGo web search tool (`web_search`) returning normalized result dicts. Added `_clean_query()` stripping instruction filler words and multi-stage fallback search.
  - `core/orchestrator/agent_loop.py`:
    - Updated `_get_tool_schemas_str()`, `_direct_route()`, and synthesis handlers.
    - Fixed error message extraction so query strings are never extracted as tool errors.
    - Added `Guardrail 3` in `_sanitize_plan()`: strips unrequested filesystem tools (`write_file`, `read_file`, `list_dir`) for research prompts without explicit save intent.
    - Standardized Windows Desktop path rules (`PATH_FIXES`) mapping WSL/Linux path representations to native Windows `desktop_dir`.
- **Test Infrastructure & Results:**
  - Created `tests/test_writing_workflow.py` with 14 comprehensive unit, regression, and acceptance tests.
  - Full test suite status: **100 passed, 1 skipped (100% green)**.

### Session 13 — 2026-09-01 (Capability 1 — Conversation & Drafting Rebuild)
- Added a deterministic `ConversationRouter` that keeps normal conversation,
  planning, rewriting, summarization of pasted text, and drafting out of the
  tool planner.
- Added a one-call `ConversationService` with clean role filtering, no tool
  schemas, non-empty response validation, and history rollback on failure.
- Separated the clean conversational system prompt from filesystem/tool
  instructions so ordinary answers are not polluted by action guidance.
- Made the Ollama request timeout configurable with
  `OLLAMA_REQUEST_TIMEOUT` (default 300 seconds) and normalized timeout/invalid
  response errors.
- Added `tests/test_conversation_capability.py` with 14 deterministic acceptance
  tests. Local result: **14 passed**; legacy text smoke result: **1 passed,
  5 skipped** because Ollama is not available in the Codex runner.

### Session 14 — 2026-09-01 (Capability 2 — Voice I/O Rebuild)
- Added an injected, testable `VoiceIO` boundary for microphone capture, STT,
  command recognition, and verified TTS playback.
- Voice exit/emergency commands now require a complete utterance, preventing
  phrases such as "create an exit plan" from shutting down Jarvis.
- Audio mode now reports missing or failed TTS explicitly instead of silently
  treating console text as voice output.
- Made audio backends lazy so a missing PortAudio or faster-whisper runtime does
  not break unrelated imports or text mode.
- Hardened empty/non-finite speech detection, stereo WAV conversion, sample
  clipping, and Piper binary/model availability checks.
- Added `tests/test_voice_capability.py`; local result: **15 passed**.

### Session 15 — 2026-09-01 (Capability 3 — Controlled Workspace Documents)
- Added one always-on `WorkspaceDocuments` boundary shared by `read_file` and
  `write_file`; `SANDBOX_MODE=false` can no longer expand document access.
- Relative and `workspace/...` paths resolve inside the configured workspace;
  traversal, absolute outside paths, and symlink escapes are rejected.
- Added UTF-8/binary checks, configurable document extensions and 10 MB limit,
  exclusive create semantics, atomic overwrite/append, exact byte verification,
  SHA-256 receipts, and clear failure results.
- Replaced the conflicting Desktop-default tool prompt with an explicit
  workspace-only contract and changed the default sandbox setting to enabled.
- Added `tests/test_workspace_documents_capability.py`; local result: **11
  passed**. Combined Capabilities 1–3 result: **41 passed, 5 live-Ollama skips**.

### Session 16 — 2026-09-01 (Capability 4 — Deterministic Filesystem)
- Added a non-destructive `WorkspaceFilesystem` for bounded directory creation
  and file listing with symlink checks and a 500-file safety ceiling.
- Added a deterministic one-action router for daily create-folder, list, read,
  create/overwrite/append document commands. Compound or ambiguous prompts are
  not partially executed.
- Routed supported filesystem commands before the LLM planner, eliminating
  hallucinated paths and model latency for these actions.
- Reduced the default generic tool registry to four workspace tools. Deletion,
  Git/package mutation, dynamic sub-agents, weight changes, and Skyvern are not
  registered; web research is handled separately in Capability 5.
- Fixed physical verification that previously skipped all real Linux paths
  beginning with `/workspace`.
- Added `tests/test_deterministic_filesystem_capability.py`; result: **7 passed**.
  Related regressions: **8 file-tool + 10 filesystem-core + 19 agent-loop passed**.

### Session 17 — 2026-09-01 (Capability 5 — Grounded Web Research)
- Added a dedicated `ResearchService` and deterministic research router so web
  requests bypass the generic multi-step planner.
- Search evidence is normalized to unique HTTP(S) URLs with non-empty snippets;
  the model is not called if connectivity fails or no usable sources exist.
- Research generation uses a single low-temperature call with enumerated
  evidence. Hallucinated URLs and out-of-range citation numbers are removed,
  and the exact retrieved source list plus an honest verification note is added.
- Combined research-and-save requests return research in chat and explicitly do
  not create a file before user review.
- Added `tests/test_web_research_capability.py`: **13 passed**. Existing research
  pipeline/dependency/planner regressions: **15 passed**.

### Session 18 — 2026-09-01 (Capability 6 — Local Memory Recall)
- Added a separate deterministic SQLite `LocalMemoryService` for typed daily
  facts: the user's name, one current preference, one project deadline, and
  explicit `remember that ...` notes. Whole conversations are never copied into
  this store and no LLM is used to extract facts.
- Added strict storage filters for questions, secrets, local/transient paths,
  filesystem actions, and prompt-injection text. Repeated typed facts update the
  same key instead of accumulating contradictory records.
- Recall is query-scoped: normal unrelated chat receives no long-term memory,
  while name, preference, deadline, and explicit memory questions receive only
  the relevant typed facts as non-instructional data.
- Added deterministic forget-one and clear-all commands. Session reset clears
  short-term chat history while intentionally preserving opted-in local memory.
- Memory database failures are fail-open for conversation: they never prevent a
  normal response from being generated.
- Added `tests/test_local_memory_capability.py`: **9 passed**. Existing chat
  memory, memory-isolation, and knowledge-graph regressions: **14 passed**.

### Session 19 — 2026-09-02 (Cross-Capability Regression and Handoff)
- Removed the Tier-1 workflow's undeclared direct dependency on the external
  `ollama` Python SDK; it now uses the project's configured `OllamaClient`.
- Kept destructive directory deletion outside the daily tool registry and
  aligned legacy safety tests with that restricted capability contract.
- Made legacy audio confirmation and Kokoro tests independent of unavailable
  CI microphone/PortAudio/Whisper hardware while preserving behavioral checks.
- Verified all six capability suites plus affected memory, filesystem,
  research, agent, audio, and Tier-1 regressions: **192 passed, 1 live-Ollama
  skip**. `poetry check --lock`, Python compilation, and `git diff --check`
  passed.
- Added `docs/milestones/CORE_CAPABILITIES_REBUILD_REPORT.md` with Windows
  acceptance commands, safety boundaries, and honest runtime limitations.

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
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── agent_builder.py        ← Autonomous sub-agent generator tool
│   │   ├── background_runner.py    ← Subprocess exec manager
│   │   ├── base_tool.py            ← Abstract tool interface
│   │   ├── create_directory.py     ← Create folder tool
│   │   ├── delete_directory.py     ← Directory deletion tool
│   │   ├── directory_audit.py      ← Tree structure audit
│   │   ├── file_cleanup.py         ← Sandbox file deletion tool
│   │   ├── file_scanner.py         ← Sandbox scanner tool
│   │   ├── git_tool.py             ← Git client tool
│   │   ├── poetry_tool.py          ← Poetry environment manager
│   │   ├── read_file.py            ← Read file tool
│   │   ├── sandbox_enforcer.py     ← Sandbox path boundaries
│   │   ├── skyvern_tool.py         ← Skyvern browser automation tool
│   │   ├── tool_registry.py        ← Tool call interceptor
│   │   ├── web_search.py           ← Real-time DuckDuckGo web search tool
│   │   ├── weight_tool.py          ← Model weight manager tool
│   │   └── write_file.py           ← Write file content tool
│   └── writing/
│       ├── __init__.py
│       ├── extractor.py            ← Grounded DataExtractor (JSON/KV/Entities)
│       ├── pipeline.py             ← 4-Mode WritingPipeline manager
│       └── sources.py              ← EvidenceSource model & prompt formatter
├── tests/
│   ├── smoke_test.py
│   ├── test_agent_builder.py
│   ├── test_agent_loop.py
│   ├── test_chat_memory.py
│   ├── test_confirmation_gate.py
│   ├── test_critic_loop.py
│   ├── test_delete_directory.py
│   ├── test_emergency_stop.py
│   ├── test_file_tools.py
│   ├── test_git_tool.py
│   ├── test_knowledge_graph.py
│   ├── test_kokoro_tts.py
│   ├── test_live_agents.py
│   ├── test_milestone5_polish.py
│   ├── test_no_slop.py
│   ├── test_poetry_tool.py
│   ├── test_sandbox.py
│   ├── test_skyvern_tool.py
│   ├── test_weight_manager.py
│   ├── test_worktree_orchestrator.py
│   └── test_writing_workflow.py   ← 14 Grounded writing & research tests
├── scripts/
│   ├── audit.py
│   ├── download_kokoro_models.py
│   ├── list_audio_devices.py
│   ├── manual_test_subagents.py
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
- **Session Isolation:** Raw `tool_calls` payloads and `role: "tool"` execution blobs are filtered out of history when building conversational fallback prompts to prevent stale tool execution contamination across turns.
- **Grounded Research & Link Truth:** Research outputs strictly strip any URL that was not present in retrieved search engine results (`EvidenceSource`). If web search is unavailable or returns 0 results, Jarvis explicitly states it could not verify online search results instead of fabricating citations.
- **Research File-Write Protection:** `_sanitize_plan()` strips unrequested filesystem tools (`write_file`, `read_file`, `list_dir`) for research prompts unless the user explicitly requests file-saving intent (`save to file`, `export`, `report.txt`).

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

---

## Session 20 — Controlled Sub-Agent Delegation Rebuild

- Replaced the legacy CrewAI/ReAct user-facing delegation path with bounded local specialist profiles.
- Permitted sub-agent capabilities: `summarize`, `analyze`, `classify`, and `plan` only.
- Sub-agents cannot receive tools, browse, access the filesystem, execute commands, operate accounts, make purchases, or spawn further agents.
- Delegation now binds both the task and expected-output contract to the local model call, rejects action requests and common prompt-injection attempts before calling the model, and returns model errors without false success claims.
- Full regression result after the rebuild: `310 passed, 7 skipped`.
- Client-facing limitations and task scope: `docs/milestones/SUBAGENT_DELEGATION_REPORT.md`.
- Added public-web tools: `web_search`, `fetch_url` (GET-only evidence), and `open_url` (default-browser launch). Public URLs only; no website interaction or authenticated actions.
- Added `test_source_compilation.py` so malformed/truncated Python source fails before runtime or deployment.

*Last Updated: 2026-09-02 | Session 20 | Controlled Sub-Agent Delegation Rebuilt and Verified*

## Session 21 — Public URL Execution Routing

- Fixed the chat entry-point routing gap where commands such as
  `Open https://example.com` were incorrectly treated as normal conversation
  and merely answered by the local model.
- Explicit public URL commands now deterministically invoke `open_url`; URL
  read/summarize requests invoke GET-only `fetch_url`. Bare links remain text,
  so Jarvis does not open pages without an explicit user instruction.
- Added a deterministic browser-result response so Jarvis reports an open only
  after the default-browser tool succeeds; it does not rely on an LLM to claim
  that action.
- Normalized common pasted `www.` links and trailing punctuation, and rejected
  login, form, click, upload/download, payment, and booking requests rather
  than treating them as browser automation.

## Session 22 — Known Site Alias Routing

- Added deterministic aliases for explicit requests to open Google, YouTube,
  GitHub, Wikipedia, LinkedIn, and Reddit in the system default browser.
- Added support for explicit bare hostnames such as `open google.com`; DNS and
  public-address validation still occur before the browser is launched.

## Session 23 — Cross-Turn Report Save Integrity

- Moved generated-document artifacts from an individual agent-loop instance
  into `SessionManager`, so research/report text survives into the user's next
  message.
- A follow-up `save this/that report in that directory` now writes the exact
  retained report text and resolves the prior verified directory reference.
- Research save references are no longer misclassified as fresh research.
- If no verified report or referenced directory exists in the current session,
  Jarvis refuses the save and creates no empty file.
- A failed replacement research request clears the active report artifact, so a
  later save cannot accidentally write an older report.

## Session 24 — Filesystem vs. Public URL Routing Repair

- Fixed the public URL detector so bare local filenames such as `notes.txt`,
  `employees.csv`, and `report.json` cannot be misrouted to `fetch_url`.
- Explicit URLs and normal public hostnames remain supported; controlled
  workspace document flows return to the filesystem planner.
- Anchored cross-turn save detection to actual save commands, preventing status
  questions such as “Where did you save the report?” from being treated as a
  request to write a file.
- Model text that resembles a tool call is now treated as untrusted text and
  is restricted to the legacy local write/directory recovery path; file writes
  are physically verified before a success response is allowed.
- Stripped sentence punctuation before classifying a bare host token, so
  `status.md.` and `test.txt.` remain local filenames rather than URLs.
- Added regression coverage for research → later save, exact file contents,
  reset isolation, and deterministic directory references.
