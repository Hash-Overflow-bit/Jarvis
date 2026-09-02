# Jarvis Core Capabilities Rebuild Report

**Date:** 2026-09-02  
**Branch:** `codex/rebuild-core-capabilities`  
**Base:** `0fc8cb809da89b62da139bea52988d3ed613c61a`

## Outcome

The six requested daily-use capabilities were rebuilt in sequence. Each has a
dedicated execution boundary and deterministic acceptance tests. Normal chat,
voice, workspace documents, simple filesystem commands, web research, and
local memory no longer depend on the same generic multi-step LLM planner.

## Implemented Capabilities

| # | Capability | New execution contract | Focused result |
|---|---|---|---|
| 1 | Conversation and drafting | One clean Ollama call; no tools or planner for ordinary chat/drafts | 14 passed |
| 2 | Voice input/output | Testable mic → STT → chat → verified TTS boundary; exact voice commands | 15 passed |
| 3 | Workspace documents | Always workspace-only, UTF-8, atomic writes, hashes, traversal/symlink blocking | 11 passed |
| 4 | Deterministic filesystem | Safe single-action create/list/read/write/append routing before the LLM | 7 passed |
| 5 | Web research | Search first, synthesize only retrieved evidence, preserve exact source URLs | 13 passed |
| 6 | Local memory | Typed SQLite facts, selective recall, explicit forget, injection/path/secret filters | 9 passed |

## Important Safety Decisions

- Destructive deletion, Git/package mutation, dynamic agent creation, model
  weight changes, and browser automation are not exposed in the default daily
  tool registry.
- Document and filesystem operations cannot escape the configured workspace,
  even if `SANDBOX_MODE=false` is supplied.
- Compound or ambiguous filesystem commands are not partially executed.
- Research produces no model-written answer when no usable online evidence was
  retrieved. Unverified URLs are removed from generated prose.
- Local memory never stores whole conversations, questions, credentials,
  transient paths, action commands, or prompt-injection instructions.
- A memory database failure does not stop normal conversation.

## Verification Evidence

- Six capability suites plus affected legacy/regression suites:
  **192 passed, 1 skipped**.
- The skipped case requires a live local Ollama model and is intentionally an
  environment test rather than a mocked unit test.
- Python compilation: passed for `core/`.
- `poetry check --lock`: passed; only Poetry metadata deprecation warnings.
- `git diff --check`: passed.
- An earlier monolithic collection completed with **322 passed** before the
  remaining compatibility failures were repaired. The final monolithic rerun
  was not allowed in the hosted verifier because a legacy CrewAI dependency
  attempted unspecified external telemetry. Telemetry was not authorized.
  Every changed capability and every previously failing module was then run in
  an offline-safe explicit suite, producing the 192/1 result above.

## Required Windows Acceptance

Run these checks on the client's Windows 11 machine after pulling the branch.
They validate real hardware/services that mocked tests cannot prove.

```powershell
git switch codex/rebuild-core-capabilities
git pull --ff-only origin codex/rebuild-core-capabilities
poetry install
poetry run pytest tests/test_conversation_capability.py tests/test_voice_capability.py tests/test_workspace_documents_capability.py tests/test_deterministic_filesystem_capability.py tests/test_web_research_capability.py tests/test_local_memory_capability.py -q
```

Then manually verify:

1. Start Ollama and confirm the configured model tag exists with `ollama list`.
2. Text: ask a normal question, draft an email, and continue for three turns.
3. Voice: speak one request and confirm both accurate transcription and audible
   Piper/Kokoro output on the selected Windows devices.
4. Workspace: create, read, overwrite, and append a test document; verify an
   outside-workspace path is rejected.
5. Filesystem: create one folder and list it; confirm a compound ambiguous
   command asks for clarification or falls through without partial execution.
6. Research: request a current topic while online, inspect every returned URL,
   then repeat while disconnected and confirm Jarvis reports unavailability.
7. Memory: state a name and deadline, restart the session, recall both, then use
   `Forget my name` and verify it is removed.

## Honest Limitations

- Drafting and evidence synthesis still use a probabilistic local model, so
  wording quality is not guaranteed and factual claims should be reviewed.
- Web research depends on search connectivity and the quality of retrieved
  snippets; sources remain the authority.
- Voice quality depends on the Windows microphone, audio drivers, STT model,
  TTS model files, and selected playback device.
- These changes deliberately cover bounded daily tasks. They do not claim safe
  autonomous purchasing, payments, form submission, unrestricted PC control,
  or reliable multi-browser automation.

