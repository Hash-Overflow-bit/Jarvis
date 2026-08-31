# Legacy Acceptance Mapping

This document maps the legacy acceptance tests (Tier 1 and M5 Test 1) to the current architecture and tracks their evidence status.

## Legacy Tier 1 (File Operations & Generation)
**Exact wording:**
> “Read the local system prompt files in the configured workspace, summarize the core instructions in exactly three bullet points, and create test_summary.md in that workspace.”

**Dependencies:**
- Configured Workspace (`settings.default_workspace_dir`)
- File Reader (`core/tools/read_file.py`)
- File Writer (`core/tools/write_file.py`)
- LLM Planner (Bypassed if `_direct_route` intercepts)
- Sandbox Enforcer (`core/tools/sandbox_enforcer.py`)

**Current Evidence Status:**
- **FAILED**. The `_direct_route` deterministic parser incorrectly intercepts this prompt. It drops the read/summarize clause due to regex mismatches (no file extension, unhandled verb "summarize") and executes the write clause with an empty payload to the default `Desktop` directory instead of the workspace.

---

## Legacy M5 Test 1 (Audio Streaming & Action Memory)
**Exact wording:**
> *"Explain the water cycle in a full paragraph."* (Low-latency TTS test)
> *"Create a folder named M5_memory_test on my desktop"* (Action Memory cross-session recall)

**Dependencies:**
- Audio TTS Engine (`core/audio/` or Kokoro TTS)
- Action Memory Graph (`core/memory/action_memory.py`, Neo4j/Local Graph)
- `create_directory` tool

**Current Evidence Status:**
- **UNTESTED** in Milestone 1 Phase A.
