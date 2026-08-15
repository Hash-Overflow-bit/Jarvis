# Milestone 3: Automated GitHub & Poetry Repository Integration
> **Pay:** $30 | **Phase:** Autonomous Package Management

---

## Objective
Build the script wrapper utilizing `git` and `poetry` to allow Jarvis to autonomously clone external repositories, resolve dependency trees, and integrate new packages locally — all triggered by voice commands and executed safely in the background.

---

## Deliverables
- [ ] `GitTool`: Clone, pull, status, and branch operations via subprocess
- [ ] `PoetryTool`: Install, add, remove, lock, and show dependencies
- [ ] Background job runner: Non-blocking subprocess execution with stdout/stderr streaming
- [ ] Git credential manager: Handles HTTPS token auth without interactive prompts
- [ ] Conflict detection: Detects merge conflicts and dependency lock-file breaks
- [ ] LLM function-calling schemas for all Git/Poetry tools
- [ ] Integration test: Clone a real public repo + run `poetry install` end-to-end
- [ ] `.env` variables for `GIT_TOKEN`, `DEFAULT_WORKSPACE_DIR`, `POETRY_VENV_PATH`

---

## What the Client Needs on Windows 11

### Hardware
> Same as Milestone 1 — no additional hardware required.

### Software to Install (Client PC - inside WSL 2)
```bash
# Git (usually pre-installed in Ubuntu)
sudo apt install git -y
git --version   # Should be 2.40+

# Poetry
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
poetry --version   # Should be 1.8+

# GitHub Personal Access Token (PAT)
# Client must generate at: https://github.com/settings/tokens
# Scopes needed: repo, read:packages
```

### Git Credential Configuration (Client)
```bash
# Store GitHub PAT so git never prompts
git config --global credential.helper store
echo "https://USERNAME:TOKEN@github.com" > ~/.git-credentials
# OR use gh CLI:
gh auth login
```

---

## What Developer Needs on macOS

### Software
```bash
# Git (usually pre-installed on macOS with Xcode tools)
xcode-select --install
git --version

# Poetry (if not already from M1)
curl -sSL https://install.python-poetry.org | python3 -

# GitHub CLI (optional but recommended for testing)
brew install gh
gh auth login

# Additional Python packages
poetry add gitpython asyncio aiofiles
```

### macOS `.env` additions
```ini
GIT_TOKEN=ghp_yourPersonalAccessTokenHere
DEFAULT_WORKSPACE_DIR=/Users/m2air/Desktop/Jarvis/workspace
POETRY_VENV_PATH=/Users/m2air/Desktop/Jarvis/.venvs
GIT_USER_EMAIL=your@email.com
GIT_USER_NAME=YourName
```

---

## Project Structure (Changes in Milestone 3)
```
/Jarvis/
├── core/
│   ├── tools/
│   │   ├── git_tool.py               # NEW: Git operations wrapper
│   │   ├── poetry_tool.py            # NEW: Poetry operations wrapper
│   │   └── background_runner.py      # NEW: Async subprocess manager
│   └── llm/
│       └── function_call_handler.py  # UPDATED: handles git/poetry tool calls
├── schemas/
│   ├── git_tool_schema.py            # NEW: Pydantic schemas for git
│   └── poetry_tool_schema.py         # NEW: Pydantic schemas for poetry
├── workspace/                        # NEW: Where repos get cloned (sandboxed)
│   └── .gitkeep
├── .venvs/                           # NEW: Isolated Poetry envs per cloned repo
│   └── .gitkeep
└── tests/
    ├── test_git_tool.py              # NEW
    └── test_poetry_tool.py           # NEW
```

---

## Architecture: Git + Poetry Workflow

```
[User: "Clone the repo X and install its dependencies"]
        ↓
[STT → Text → LLM]
        ↓
[LLM emits tool_call: git_clone(url="...", target_dir="workspace/X")]
        ↓
[Sandbox Enforcer validates target_dir]
        ↓
[BackgroundRunner: subprocess git clone (non-blocking)]
        ↓
[Stream stdout → Session Manager (shows progress)]
        ↓
[On success → LLM emits tool_call: poetry_install(project_dir="workspace/X")]
        ↓
[BackgroundRunner: subprocess poetry install]
        ↓
[Stream output → LLM summarizes result → TTS speaks summary]
```

---

## Step-by-Step Build Plan

### Step 1: Background Runner (`core/tools/background_runner.py`)
This is the backbone — runs subprocesses asynchronously without blocking the audio loop.
```python
import asyncio
import subprocess

class BackgroundRunner:
    async def run(
        self,
        cmd: list[str],
        cwd: str = None,
        env: dict = None,
        timeout: int = 300
    ) -> dict:
        """
        Run a subprocess asynchronously.
        Returns: {stdout, stderr, returncode, success}
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode,
                "success": proc.returncode == 0
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": "Process timed out"}
```

**Key rule:** NEVER use `shell=True`. Always pass commands as `list[str]`.
This avoids shell injection and works identically on macOS and Windows.

### Step 2: Git Tool (`core/tools/git_tool.py`)
```python
class GitTool(BaseTool):
    name = "git"

    async def clone(self, url: str, target_dir: str, token: str = None) -> dict:
        # Inject token into URL for HTTPS auth (avoids interactive prompt)
        if token:
            url = url.replace("https://", f"https://oauth2:{token}@")
        cmd = ["git", "clone", url, target_dir, "--depth=1"]
        return await runner.run(cmd, cwd=settings.DEFAULT_WORKSPACE_DIR)

    async def pull(self, repo_dir: str) -> dict:
        cmd = ["git", "pull", "--ff-only"]
        return await runner.run(cmd, cwd=repo_dir)

    async def status(self, repo_dir: str) -> dict:
        cmd = ["git", "status", "--short"]
        return await runner.run(cmd, cwd=repo_dir)
```

### Step 3: Poetry Tool (`core/tools/poetry_tool.py`)
```python
class PoetryTool(BaseTool):
    name = "poetry"

    async def install(self, project_dir: str) -> dict:
        cmd = ["poetry", "install", "--no-interaction"]
        return await runner.run(cmd, cwd=project_dir, timeout=600)

    async def add(self, project_dir: str, package: str) -> dict:
        cmd = ["poetry", "add", package, "--no-interaction"]
        return await runner.run(cmd, cwd=project_dir)

    async def show(self, project_dir: str) -> dict:
        cmd = ["poetry", "show", "--tree"]
        return await runner.run(cmd, cwd=project_dir)
```

### Step 4: Git Credential Manager
- Store PAT in `.env` as `GIT_TOKEN`
- Inject into HTTPS URLs at clone time (token embedded in URL)
- NEVER write credentials to disk in plaintext outside of `.env` (which is .gitignored)
- Alternative: Use SSH keys configured once on the client machine

### Step 5: Conflict & Error Detection
```python
def detect_conflicts(git_output: str) -> bool:
    conflict_keywords = ["CONFLICT", "merge conflict", "Automatic merge failed"]
    return any(kw in git_output for kw in conflict_keywords)

def detect_poetry_failure(output: str) -> bool:
    failure_keywords = ["SolverProblemError", "VersionConflictError", "No matching distribution"]
    return any(kw in output for kw in failure_keywords)
```

### Step 6: Integration Test
```python
# tests/test_git_tool.py
async def test_clone_public_repo():
    result = await git_tool.clone(
        url="https://github.com/tiangolo/fastapi",
        target_dir="workspace/fastapi_test"
    )
    assert result["success"] is True
    assert Path("workspace/fastapi_test/pyproject.toml").exists()

async def test_poetry_install():
    result = await poetry_tool.install("workspace/fastapi_test")
    assert result["success"] is True
```

---

## Cross-Platform Challenges, Solutions & Alternatives

| # | Challenge | Solution | Alternative |
|---|---|---|---|
| 1 | **Git credential prompt hangs** the background loop | Embed PAT in clone URL (`https://token@github.com/...`), set `GIT_TERMINAL_PROMPT=0` env var | Use SSH keys with agent forwarding |
| 2 | **Poetry PATH not found** in subprocess environment | Explicitly pass `PATH` including `~/.local/bin` in `env=` parameter to subprocess | Use full absolute path to poetry binary |
| 3 | **`poetry install` hangs** on large dependency trees | Set `timeout=600` in background runner; stream progress output | Use `pip install -r requirements.txt` as fallback |
| 4 | **Merge conflicts during `git pull`** | Detect conflict strings in output, abort merge, report to user | Always use `--ff-only` flag on pull to refuse merges |
| 5 | **Windows/WSL path for cloned repos** | All repos cloned inside `workspace/` which is under `SANDBOX_ROOTS` | Use a separate `REPO_WORKSPACE` env var pointing inside WSL home |
| 6 | **`pyproject.toml` missing** in cloned repo | Check before running `poetry install`, fall back to `pip install -r requirements.txt` | Offer to `poetry init` the repo |
| 7 | **Dependency lock-file conflicts** after update | Run `poetry lock --no-update` first to check, then full install | Present conflict details to user for manual resolution |
| 8 | **GitHub rate limiting** on large clones | Use `--depth=1` (shallow clone) by default | Cache repos locally, only pull updates |

---

## Testing Strategy

### On macOS (Developer)
```bash
# Test git clone (public repo, no auth needed)
poetry run pytest tests/test_git_tool.py::test_clone_public_repo -v

# Test with private repo (uses GIT_TOKEN from .env)
poetry run pytest tests/test_git_tool.py::test_clone_private_repo -v

# Test poetry install
poetry run pytest tests/test_poetry_tool.py -v

# Full integration via voice
python main.py  # Say: "Clone the fastapi repo and install its dependencies"
```

### On Windows 11 (Client)
```bash
# Inside WSL 2
cd /mnt/c/Jarvis
pytest tests/test_git_tool.py tests/test_poetry_tool.py -v

# Verify git credential flow works
python -c "from core.tools.git_tool import GitTool; print('OK')"
```

---

## Definition of Done
- [ ] Jarvis can clone `https://github.com/tiangolo/fastapi` via voice command
- [ ] `poetry install` runs successfully in the cloned repo directory
- [ ] No interactive prompts ever appear (fully non-interactive)
- [ ] Git credential prompt is never triggered (PAT injected silently)
- [ ] Conflict detection catches and reports errors gracefully
- [ ] All operations stay inside `SANDBOX_ROOTS`
- [ ] Tests pass on both macOS and Windows 11 / WSL 2

---

## Estimated Time
| Task | Hours |
|---|---|
| Background runner (async subprocess) | 3h |
| Git tool + credential manager | 4h |
| Poetry tool + error detection | 3h |
| LLM schema registration | 2h |
| Integration tests | 3h |
| Windows/WSL 2 PATH debugging | 3h |
| Voice integration test | 2h |
| **Total** | **~20h** |
