# Jarvis Project Status and Developer Notes

**Authoritative branch:** `main`
**Code baseline reviewed:** `ae08a1cadb38a1ec46cc8e38b9602bd65f008653` (2026-09-03)

## Current shape of the codebase

| Area | Entry point / location | Current status |
| --- | --- | --- |
| Application | `main.py` | Text mode is the primary startup path; audio mode is separately configured. |
| Configuration | `core/config.py`, `.env.example` | Environment-driven. `.env` is local-only and must not be committed. |
| Orchestration | `core/orchestrator/agent_loop.py` and `agent_loop_legacy.py` | The small public wrapper applies current routing policy; the legacy engine is large and should not be bulk-rewritten without source-compilation tests. |
| Documents/files | `core/workspace/`, `core/tools/` | Controlled workspace read/write flows and deterministic file routing are present. |
| Local model | `core/llm/` | Ollama is the configured local model provider. Model tag must match `ollama list`. |
| Memory | `core/memory/` | Local SQLite/knowledge-graph runtime data; databases are ignored by Git. |
| Voice | `core/audio/` | Requires target-machine audio devices and TTS assets; text mode does not prove voice readiness. |
| Sub-agents | `core/orchestrator/subagent_runner.py`, `core/tools/delegate_task.py` | Local specialist delegation exists. The current public-URL instruction test allows only explicitly listed public URLs; it is not general browser automation. |
| Tests | `tests/` | Pytest suite includes source compilation, Tier 1, workspace, memory, web, voice, and sub-agent regression coverage. |

## Current supported baseline

The verified daily-use baseline is local conversation/drafting, local memory,
controlled workspace document operations, deterministic simple filesystem
workflows, voice components when configured, and public web/read-only paths
where the relevant connectivity/tool is available.

The repository contains broader/legacy integration code and planning artifacts.
Do not treat the presence of a module, a Docker service, or a config variable as
proof that an integration is production-ready. Confirm it is registered, tested
and enabled in the current runtime before promising it as a capability.

## Recent fixes on `main`

- `7298257`: repaired a corrupted `agent_loop_legacy.py` source file that
  blocked Python imports with null bytes.
- `91afc09`: fixed Tier 1 deterministic rule handling, builder rejection text,
  and strict URL-instruction parsing.
- `ae08a1c`: fixed false-success propagation so an invalid URL instruction file
  returns a failed sub-agent delegation rather than a successful result.

## Test evidence and honest status

The most recent full macOS run reported:

```text
337 passed, 6 skipped, 1 failed
```

The only failure was
`test_browser_subagent_rejects_untrusted_instruction_lines`. Its root cause was
fixed in `ae08a1c` after that run. A full-suite rerun on the target developer
machine is still required before claiming a fully green suite.

The first commands a new developer should run are:

```bash
poetry run pytest tests/test_source_compilation.py -q
poetry run pytest tests/test_subagent_instruction_urls.py -q
poetry run pytest tests -q
```

Tier 1's acceptance case is intentionally strict: it must read local approved
prompt files, create `test_summary.md` inside the configured workspace, contain
exactly three grounded bullets, and verify the physical file. It must not fall
back to a Desktop path or claim success without a file.

## Known operational constraints

- Local-model quality and latency vary by hardware and model. Model promotion
  should follow a real benchmark, not a name change in `.env`.
- A local 32B model can be unsuitable on 16 GB unified memory and may time out
  or use heavy swap. Test candidate models on their actual target GPU/RAM.
- Voice mode depends on microphone/speaker drivers, Whisper configuration, and
  local Piper/Kokoro assets.
- Public URL opening is limited to reviewed lines in a workspace instruction
  file. It is not login, search, click, form submission, download, upload, or
  account automation.
- Runtime data is intentionally ignored by Git: `.env`, workspace contents,
  agent blueprints, logs, model assets and SQLite databases.

## Safe pickup procedure for the next developer

1. Read `docs/DEPLOYMENT.md` and this file before changing the planner.
2. Make a clean branch from the latest `main` and run source compilation first.
3. Reproduce a failure with one focused test before changing routing logic.
4. Keep generated/runtime data out of source control.
5. Make one behavior change at a time, add or update its regression test, then
   run the focused test and the full suite.
6. Do not silently promote an Ollama candidate model or enable an optional
   integration as part of a bug fix.
