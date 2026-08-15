# Milestone 4: Safety, Sandboxing, and Confirmation Boundaries
> **Pay:** Not specified (Safety Infrastructure) | **Phase:** Guardrails

---

## Objective
Establish hard safety gates — mandatory confirmation prompts and explicit environment flags — for all system-level execution tools before they run. Prevent any unconfirmed file deletion, code execution, or network operations. The system must remain safe even if the LLM misbehaves.

---

## Deliverables
- [ ] `ConfirmationGate`: Middleware that intercepts high-risk tool calls and requires explicit user approval (voice or text)
- [ ] Risk classification system: Tools tagged as `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` risk
- [ ] `SafetyFlags` environment config: `SAFE_MODE=strict|permissive|off`
- [ ] `EmergencyStop`: Keyboard/voice trigger that immediately halts all background tasks
- [ ] Uncaught exception handler: Catches all subprocess errors without freezing the loop
- [ ] Audit log: Every tool execution (approved or denied) is logged to file
- [ ] Dry-run mode: Tools simulate execution and report what they WOULD do without doing it
- [ ] Unit tests: Every high-risk tool must have a test that verifies the gate blocks it without confirmation

---

## What the Client Needs on Windows 11

### Hardware
> Same as Milestone 1 — no additional hardware required.

### Software to Install (Client PC)
```
1. All Milestone 1-3 software (already installed)
2. No additional installations required
```

### Client Configuration (`.env` additions)
```ini
# Safety settings
SAFE_MODE=strict                    # strict | permissive | off
REQUIRE_CONFIRMATION_FOR=DELETE,EXECUTE,CLONE,GIT_PUSH
AUDIT_LOG_PATH=C:\Jarvis\logs\audit.log
EMERGENCY_STOP_KEYWORD=JARVIS STOP
DRY_RUN=false                       # Set true for testing without real actions
```

---

## What Developer Needs on macOS

### Software
```bash
# Additional Python packages
poetry add structlog   # Structured logging
# No new system installs needed
```

### macOS `.env` additions
```ini
SAFE_MODE=strict
REQUIRE_CONFIRMATION_FOR=DELETE,EXECUTE,CLONE,GIT_PUSH
AUDIT_LOG_PATH=/Users/m2air/Desktop/Jarvis/logs/audit.log
EMERGENCY_STOP_KEYWORD=JARVIS STOP
DRY_RUN=true    # Always dry-run on dev machine first
```

---

## Project Structure (Changes in Milestone 4)
```
/Jarvis/
├── core/
│   ├── safety/                         # NEW directory
│   │   ├── __init__.py
│   │   ├── confirmation_gate.py        # Intercepts high-risk calls
│   │   ├── risk_classifier.py          # Tags tools with risk levels
│   │   ├── emergency_stop.py           # Immediate halt mechanism
│   │   ├── exception_handler.py        # Global uncaught exception catcher
│   │   └── dry_run_wrapper.py          # Simulates tool execution
│   ├── logging/                        # NEW directory
│   │   ├── __init__.py
│   │   └── audit_logger.py             # Structured audit logging
│   └── tools/
│       └── base_tool.py               # UPDATED: adds risk_level, dry_run support
├── logs/                               # NEW directory (gitignored contents)
│   └── .gitkeep
└── tests/
    ├── test_confirmation_gate.py       # NEW
    ├── test_emergency_stop.py          # NEW
    └── test_audit_logger.py            # NEW
```

---

## Architecture: Safety Gate Pipeline

```
[LLM emits tool_call]
        ↓
[RiskClassifier.classify(tool_name, args)]
        ↓
   ┌────────────┬──────────────┬────────────────┐
   │   LOW      │   MEDIUM     │  HIGH/CRITICAL  │
   │            │              │                 │
   ↓            ↓              ↓                 │
[Execute    [Log + Execute] [ConfirmationGate]   │
 directly]                     ↓                 │
                        [TTS asks user:           │
                    "Are you sure you want        │
                     to delete 47 files?"]        │
                               ↓                  │
                    [STT listens for              │
                     "yes" / "confirm"            │
                     OR "no" / "cancel"]          │
                               ↓                  │
                        ┌──────┴──────┐           │
                        ↓            ↓            │
                    [Execute]    [Abort]          │
                        ↓            ↓            │
                [AuditLogger logs decision + args + result]
```

---

## Risk Classification System

```python
# core/safety/risk_classifier.py

class RiskLevel:
    LOW = "low"         # Read-only, no side effects
    MEDIUM = "medium"   # Writes to files, reversible
    HIGH = "high"       # Deletes files, installs packages
    CRITICAL = "critical"  # System-level changes, network push

TOOL_RISK_MAP = {
    "file_scanner":      RiskLevel.LOW,
    "directory_audit":   RiskLevel.LOW,
    "file_cleanup":      RiskLevel.HIGH,      # Deletes files!
    "git_clone":         RiskLevel.MEDIUM,    # Downloads code
    "git_pull":          RiskLevel.MEDIUM,
    "git_push":          RiskLevel.CRITICAL,  # Modifies remote
    "poetry_install":    RiskLevel.MEDIUM,
    "poetry_add":        RiskLevel.MEDIUM,
    "agent_builder":     RiskLevel.CRITICAL,  # Executes dynamic code
    "execute_script":    RiskLevel.CRITICAL,
}
```

---

## Step-by-Step Build Plan

### Step 1: Risk Classifier (`core/safety/risk_classifier.py`)
- Map each tool to a risk level
- `classify(tool_name, args) -> RiskLevel`
- Check `REQUIRE_CONFIRMATION_FOR` from `.env` to override defaults

### Step 2: Confirmation Gate (`core/safety/confirmation_gate.py`)
```python
class ConfirmationGate:
    def __init__(self, tts, stt, settings):
        self.tts = tts
        self.stt = stt
        self.settings = settings

    async def request_confirmation(self, tool_name: str, args: dict) -> bool:
        if self.settings.SAFE_MODE == "off":
            return True  # Skip gate entirely (dangerous mode)

        # Describe what will happen in plain English
        description = self._describe_action(tool_name, args)
        self.tts.speak(f"I need your confirmation. I am about to {description}. Say YES to proceed or NO to cancel.")

        # Listen for response with 10-second timeout
        response = await self.stt.listen_for_confirmation(timeout=10)

        confirmed = response.lower() in ["yes", "confirm", "proceed", "do it"]
        audit_logger.log(tool_name, args, confirmed=confirmed)
        return confirmed

    def _describe_action(self, tool_name: str, args: dict) -> str:
        descriptions = {
            "file_cleanup": f"delete {args.get('file_count', 'some')} files from {args.get('directory')}",
            "git_push": f"push changes to {args.get('remote', 'origin')}",
            "agent_builder": f"create and run a new agent called {args.get('name', 'unknown')}",
        }
        return descriptions.get(tool_name, f"run {tool_name} with args {args}")
```

### Step 3: Emergency Stop (`core/safety/emergency_stop.py`)
```python
import asyncio

class EmergencyStop:
    def __init__(self):
        self._stop_event = asyncio.Event()
        self._active_tasks: list[asyncio.Task] = []

    def register_task(self, task: asyncio.Task):
        self._active_tasks.append(task)

    def trigger(self):
        """Call this when emergency stop keyword is heard"""
        self._stop_event.set()
        for task in self._active_tasks:
            task.cancel()
        self._active_tasks.clear()
        audit_logger.log("EMERGENCY_STOP", {}, confirmed=True)

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def reset(self):
        self._stop_event.clear()
```

### Step 4: Exception Handler (`core/safety/exception_handler.py`)
```python
import asyncio

def handle_tool_exception(tool_name: str, exc: Exception) -> dict:
    """
    Catches any exception from tool execution.
    Returns a structured error dict instead of crashing.
    """
    audit_logger.log_error(tool_name, str(exc))
    return {
        "success": False,
        "error": str(exc),
        "tool": tool_name,
        "recoverable": isinstance(exc, (FileNotFoundError, PermissionError))
    }

# Wrap all tool executions:
async def safe_execute(tool, input_data) -> dict:
    try:
        return await tool.run(input_data)
    except Exception as e:
        return handle_tool_exception(tool.name, e)
```

### Step 5: Audit Logger (`core/logging/audit_logger.py`)
```python
import structlog
import datetime

logger = structlog.get_logger()

def log(tool_name: str, args: dict, confirmed: bool, result: dict = None):
    logger.info(
        "tool_execution",
        timestamp=datetime.datetime.utcnow().isoformat(),
        tool=tool_name,
        args=args,
        confirmed=confirmed,
        result=result
    )
```

### Step 6: Dry-Run Wrapper (`core/safety/dry_run_wrapper.py`)
- Intercepts tool execution when `DRY_RUN=true`
- Returns a description of what WOULD happen
- Useful for testing on macOS without risk of affecting real files

### Step 7: Update `main.py`
- Register emergency stop keyword in STT stream
- Wrap all tool calls in `safe_execute()`
- Check risk level before every tool dispatch

---

## Cross-Platform Challenges, Solutions & Alternatives

| # | Challenge | Solution | Alternative |
|---|---|---|---|
| 1 | **Overly restrictive gate** blocks legitimate maintenance | Configurable `SAFE_MODE=permissive` lowers confirmation threshold | Per-tool override in `.env` (`AUTO_APPROVE_GIT_PULL=true`) |
| 2 | **Uncaught subprocess exception** freezes the loop | `safe_execute()` wrapper catches ALL exceptions, returns structured error | Restart the background runner on crash |
| 3 | **Emergency stop during async I/O** doesn't cancel cleanly | Use `asyncio.CancelledError` handling in all background tasks | Maintain a global task registry and `kill()` each |
| 4 | **Audit log fills disk** over time | Rotate logs: max 10MB, keep 5 files using `logging.handlers.RotatingFileHandler` | Store logs in SQLite for querying |
| 5 | **Confirmation voice response** misheard ("yes" → "no") | Use high-confidence threshold (>0.85) for confirmation words | Fall back to text input if audio confidence is low |
| 6 | **DRY_RUN flag forgotten** on client deployment | `audit.py` (from M1) checks and warns if `DRY_RUN=true` in non-dev environment | Auto-disable DRY_RUN if `ENVIRONMENT=production` |
| 7 | **`SAFE_MODE=off`** accidentally left in config | Add prominent warning in `audit.py` output when safe mode is off | Require explicit `--allow-unsafe` CLI flag to disable |

---

## Testing Strategy

### Safety Unit Tests (Critical)
```python
# test_confirmation_gate.py

async def test_high_risk_tool_blocked_without_confirmation():
    gate = ConfirmationGate(mock_tts, mock_stt_no_response, settings)
    result = await gate.request_confirmation("file_cleanup", {"directory": "/sandbox"})
    assert result is False  # No response = denied

async def test_emergency_stop_cancels_all_tasks():
    stop = EmergencyStop()
    task = asyncio.create_task(long_running_operation())
    stop.register_task(task)
    stop.trigger()
    assert task.cancelled()

async def test_exception_does_not_crash_loop():
    # Tool that always raises
    result = await safe_execute(BrokenTool(), {})
    assert result["success"] is False
    assert "error" in result
```

### On macOS (Developer)
```bash
poetry run pytest tests/test_confirmation_gate.py -v
poetry run pytest tests/test_emergency_stop.py -v
poetry run pytest tests/test_audit_logger.py -v

# Test DRY_RUN mode
DRY_RUN=true python main.py
# Try voice: "Delete all log files" → should describe action without deleting
```

### On Windows 11 (Client)
```bash
pytest tests/ -v   # All tests should pass identically
# Verify audit.log is being written to correct Windows path
```

---

## Definition of Done
- [ ] No HIGH/CRITICAL tool executes without explicit confirmation
- [ ] Emergency stop ("JARVIS STOP") kills all background tasks within 1 second
- [ ] Any subprocess exception returns a structured error (never crashes the loop)
- [ ] Audit log records every tool attempt with timestamp, args, and decision
- [ ] Dry-run mode works for all tools
- [ ] `SAFE_MODE=strict` is the default in `.env.example`
- [ ] All safety tests pass on both macOS and Windows 11

---

## Estimated Time
| Task | Hours |
|---|---|
| Risk classifier | 1h |
| Confirmation gate | 4h |
| Emergency stop mechanism | 2h |
| Global exception handler | 2h |
| Audit logger | 2h |
| Dry-run wrapper | 2h |
| Wiring into main loop | 2h |
| Tests | 3h |
| **Total** | **~18h** |
