# Jarvis Deployment and Developer Handoff

This is the authoritative setup guide for the current `main` branch. It is
written for a new developer or a clean client machine. Start in **text mode**;
configure voice only after text mode and tests work.

## 1. What this repository needs

Required for the text baseline:

- Git
- Python `>=3.11,<3.14`
- Poetry
- Ollama running locally or at the configured `OLLAMA_BASE_URL`
- One Ollama model whose tag exactly matches `OLLAMA_PRIMARY_MODEL`

Optional for voice mode:

- A working microphone and speakers
- Faster-Whisper dependencies and a supported compute configuration
- Either Piper plus its executable/voice model, or Kokoro model assets

Windows with a local NVIDIA GPU is the preferred target for larger local
models. macOS is suitable for text-mode development with a model that fits its
available unified memory. Do not assume a 32B candidate model fits or is faster
until it is tested on the actual machine.

## 2. Clean checkout

```bash
git clone https://github.com/Hash-Overflow-bit/Jarvis.git
cd Jarvis
git switch main
git pull --ff-only origin main
poetry install
```

On Windows PowerShell, use `Copy-Item .env.example .env`. On macOS/Linux/WSL,
use `cp .env.example .env`.

Do not copy a previous developer's `.env`, `workspace/`, `agents/`, `logs/`,
`models/`, or `core/memory/*.db` into a clean checkout unless their contents
have been deliberately reviewed. They are machine/runtime data, not source.

## 3. Configure the local environment

Edit `.env` from `.env.example`.

Minimum values for a safe text-mode baseline:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_PRIMARY_MODEL=llama3.1:8b
DEFAULT_WORKSPACE_DIR=./workspace
SANDBOX_MODE=true
SANDBOX_ROOTS=./sandbox,./workspace
SAFE_MODE=strict
AUDIT_LOG_PATH=./logs/audit.log
KNOWLEDGE_GRAPH_PATH=./core/memory/graph.db
AGENTS_BLUEPRINT_PATH=./agents/agents_blueprint.yaml
```

`OLLAMA_PRIMARY_MODEL` must be the exact installed tag. Check it before
launching:

```bash
ollama list
```

If the required tag is missing, pull the tag you choose and make the `.env`
value match it:

```bash
ollama pull llama3.1:8b
```

If Ollama is not already running as a host service, start it in a separate
terminal:

```bash
ollama serve
```

### Environment-variable reference

| Group | Variables | Required? | Notes |
| --- | --- | --- | --- |
| Local model | `OLLAMA_BASE_URL`, `OLLAMA_PRIMARY_MODEL` | Yes | No API key is required for a local Ollama server. |
| Workspace safety | `DEFAULT_WORKSPACE_DIR`, `SANDBOX_MODE`, `SANDBOX_ROOTS` | Yes | Keep sandbox mode enabled. Workspace document operations are constrained to `DEFAULT_WORKSPACE_DIR`. |
| Audit/safety | `SAFE_MODE`, `DRY_RUN`, `AUDIT_LOG_PATH`, `EMERGENCY_STOP_KEYWORD` | Yes | Use `SAFE_MODE=strict` and `DRY_RUN=false` for normal verified operation. |
| Memory | `KNOWLEDGE_GRAPH_PATH`, `LOCAL_MEMORY_ENABLED`, `GRAPH_*` | Recommended | Use a local writable path; do not share the database by default. |
| Voice | `WHISPER_*`, `AUDIO_*`, `TTS_ENGINE`, `PIPER_*` or `KOKORO_*` | Only for audio mode | First use device index `-1`; change only after listing/testing local devices. |
| Sub-agents | `AGENTS_BLUEPRINT_PATH`, `AGENT_BASELINE_TIMEOUT` | Recommended | The blueprint is local runtime state and Git-ignored. |
| Benchmark | `OLLAMA_CANDIDATE_MODEL` | No | Set only when intentionally comparing installed local models. It does not promote a model. |
| Optional services | `GIT_TOKEN`, `SKYVERN_API_KEY`, `SKYVERN_BASE_URL`, `TELEMETRY_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT` | No | Enable only when the relevant integration is configured and reviewed. |

## 4. Credentials and secret handling

The baseline text/filesystem/memory setup needs **no cloud credential**. The
following values are optional and must be created by the machine owner when an
integration actually needs them:

- `GIT_TOKEN`: a least-privilege GitHub token, only for an approved private
  repository workflow.
- `SKYVERN_API_KEY`: only for a separately configured Skyvern service.
- Remote telemetry credentials, if an OTLP endpoint requires authentication.

Never commit `.env`, API tokens, passwords, browser cookies, model caches,
workspace documents, memory databases, agent blueprints, or audit logs. Share
secrets through the team's approved secret manager or a direct secure channel,
not through source control or issue comments.

## 5. Verify before use

Run these from the repository root after `poetry install`:

```bash
poetry run pytest tests/test_source_compilation.py -q
poetry run pytest tests/test_agent_builder.py tests/test_legacy_tier1.py tests/test_subagent_instruction_urls.py -q
poetry run pytest tests -q
```

Then start the lowest-risk manual smoke test:

```bash
poetry run python main.py --mode text
```

Confirm Jarvis reports an Ollama connection, then test one short conversation.
Only after this succeeds should you configure `--mode audio`.

## 6. Voice-mode setup

Audio mode needs an installed TTS engine and its local assets. For Piper,
provide `PIPER_BINARY_PATH` and `PIPER_VOICE_MODEL`. For Kokoro, place the
configured model and voices file in the local `models/` directory or set
absolute paths in `.env`.

Validate audio devices on the target machine and retain the default (`-1`) if
it works. Audio is hardware-dependent; a passing text-mode test does not prove
microphone or speaker functionality.

Launch only after the assets and devices are configured:

```bash
poetry run python main.py --mode audio
```

## 7. Docker and telemetry

`docker-compose.yml` provides an optional local app/Ollama/Phoenix stack. It is
not required for the verified text-mode developer baseline and should be used
only after host-model and path configuration have been reviewed. Do not run a
second Ollama stack solely to solve a model or test failure.

## 8. Useful troubleshooting checks

| Symptom | Check |
| --- | --- |
| Ollama 404/model not found | Compare `OLLAMA_PRIMARY_MODEL` with `ollama list`; tags must match exactly. |
| Timeout | Test a smaller local prompt; then review model size, GPU/RAM and `OLLAMA_REQUEST_TIMEOUT`. |
| File action rejected | Confirm the requested path is inside `DEFAULT_WORKSPACE_DIR`. |
| Empty/incorrect report saved | Stop, inspect the prior generated content and session context; do not treat an empty file as success. |
| Voice unavailable | Validate microphone/speaker selection and TTS model/binary paths before changing code. |
| Tests fail at import | Run `tests/test_source_compilation.py` first and inspect the exact error before editing generated/runtime files. |

## 9. Handoff checklist

- [ ] `git status --short` is clean after setup changes are intentionally excluded.
- [ ] `.env` exists locally and contains no copied secrets from another machine.
- [ ] `ollama list` contains the configured primary model tag.
- [ ] Source-compilation and focused regression tests pass.
- [ ] Text mode launches and returns one normal response.
- [ ] The workspace, logs, graph database, and agent blueprint paths are local and writable.
- [ ] Audio is configured and tested separately, if required.
