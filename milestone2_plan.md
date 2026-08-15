# Milestone 2: Secure Local File-Management Tool Layer
> **Pay:** $20 | **Phase:** Tool Layer

---

## Objective
Implement Python subprocess utility tools mapped to local LLM function-calling that allow Jarvis to safely scan, clean, and manage authorized workspace directories. All file operations must be strictly sandboxed with Pydantic validation.

---

## Deliverables
- [ ] `FileScanner` tool: List files in a directory with metadata (size, modified date, type)
- [ ] `FileCleanup` tool: Delete or archive files matching criteria (age, extension, size)
- [ ] `DirectoryAudit` tool: Generate a tree-view report of a directory
- [ ] Pydantic schemas for every tool's input and output
- [ ] Sandbox enforcer: Rejects any path that escapes the approved directories
- [ ] LLM function-calling schema (JSON Schema) for each tool registered with Ollama
- [ ] Unit tests for sandbox escape attempts and valid operations
- [ ] `.env` variable `SANDBOX_ROOTS` listing all approved directories

---

## What the Client Needs on Windows 11

### Hardware
> Same as Milestone 1 — no additional hardware required.

### Software to Install (Client PC)
```
1. All Milestone 1 software (already installed)
2. No additional installations required for this milestone
```

### Authorized Sandbox Directories (Client configures in .env)
```ini
# .env on Windows 11
SANDBOX_ROOTS=C:\Users\Client\Documents\Jarvis_Workspace,C:\Users\Client\Downloads\Jarvis_Temp
```

---

## What Developer Needs on macOS

### Software
```bash
# Additional Python packages
poetry add pydantic watchdog send2trash

# No new system-level installs needed
```

### Authorized Sandbox Directories (Dev .env on macOS)
```ini
# .env on macOS
SANDBOX_ROOTS=/Users/m2air/Desktop/Jarvis/sandbox,/Users/m2air/Downloads/jarvis_temp
```

---

## Project Structure (Changes in Milestone 2)
```
/Jarvis/
├── core/
│   ├── tools/                        # NEW directory
│   │   ├── __init__.py
│   │   ├── base_tool.py              # Abstract BaseTool class
│   │   ├── sandbox_enforcer.py       # Path validation & sandbox logic
│   │   ├── file_scanner.py           # FileScanner tool
│   │   ├── file_cleanup.py           # FileCleanup tool
│   │   ├── directory_audit.py        # DirectoryAudit tool
│   │   └── tool_registry.py          # Registers tools + generates LLM schemas
│   └── llm/
│       └── function_call_handler.py  # NEW: Parses LLM tool-call responses
├── schemas/                          # NEW directory
│   ├── file_scanner_schema.py        # Pydantic input/output models
│   ├── file_cleanup_schema.py
│   └── directory_audit_schema.py
├── tests/
│   ├── test_sandbox.py               # NEW: Sandbox escape tests
│   ├── test_file_tools.py            # NEW: Tool operation tests
└── sandbox/                          # NEW: Safe test area (gitignored contents)
    ├── .gitkeep
    └── test_files/                   # Dummy files for testing
```

---

## Architecture: Tool-Calling Flow

```
[User Voice Input]
        ↓
[STT → Text]
        ↓
[Session Manager → Ollama LLM]
   (with tool schemas in system prompt)
        ↓
[LLM Response: either text OR tool_call JSON]
        ↓
[function_call_handler.py]
   Parses tool name + arguments
        ↓
[Tool Registry looks up tool]
        ↓
[Sandbox Enforcer validates path]
   ↓ FAIL → Return error to LLM
   ↓ PASS → Execute tool
        ↓
[Tool Result → Back to LLM for natural language response]
        ↓
[TTS speaks the result]
```

---

## Step-by-Step Build Plan

### Step 1: Sandbox Enforcer (`core/tools/sandbox_enforcer.py`)
This is the most critical piece. It must be bulletproof.
```python
from pathlib import Path
import os

class SandboxEnforcer:
    def __init__(self, allowed_roots: list[str]):
        self.allowed_roots = [Path(r).resolve() for r in allowed_roots]

    def validate(self, target_path: str) -> Path:
        resolved = Path(target_path).resolve()
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root)  # Raises ValueError if not inside
                return resolved
            except ValueError:
                continue
        raise PermissionError(
            f"Path '{resolved}' is outside all allowed sandbox roots."
        )
```

### Step 2: Pydantic Schemas (`schemas/`)
```python
# file_scanner_schema.py
from pydantic import BaseModel, Field
from typing import Optional

class FileScannerInput(BaseModel):
    directory: str = Field(..., description="Absolute path to directory to scan")
    extension_filter: Optional[str] = Field(None, description="e.g., '.log', '.tmp'")
    min_size_mb: Optional[float] = Field(None, description="Minimum file size in MB")

class FileScannerOutput(BaseModel):
    files: list[dict]   # [{name, path, size_mb, modified_date}]
    total_count: int
    total_size_mb: float
```

### Step 3: Base Tool (`core/tools/base_tool.py`)
```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class BaseTool(ABC):
    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    @abstractmethod
    def run(self, input_data: BaseModel) -> BaseModel:
        pass

    def to_ollama_schema(self) -> dict:
        """Generate JSON Schema for LLM function calling"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema()
            }
        }
```

### Step 4: Implement Tools
- **FileScanner**: Uses `os.walk()` + `pathlib` to scan, applies filters, returns file list
- **FileCleanup**: Validates each file path, moves to trash using `send2trash` (NOT `os.remove` by default — safer)
- **DirectoryAudit**: Recursive tree walk, outputs formatted string report

### Step 5: Tool Registry (`core/tools/tool_registry.py`)
- Holds a dict of `{tool_name: tool_instance}`
- `get_all_schemas()` returns list of JSON Schemas for the LLM system prompt
- `execute(tool_name, raw_args_dict)` runs the tool with Pydantic validation

### Step 6: Function Call Handler (`core/llm/function_call_handler.py`)
- Parses Ollama's response to detect if it's a `tool_call` or plain text
- Extracts `tool_name` and `arguments`
- Calls `tool_registry.execute()` and formats result for LLM follow-up

### Step 7: Wire into Session Manager
- Pass tool schemas into the Ollama system prompt
- Detect tool calls in responses and route through handler

---

## Cross-Platform Challenges, Solutions & Alternatives

| # | Challenge | Solution | Alternative |
|---|---|---|---|
| 1 | **Path separator differences** — Windows uses `\`, Linux/Mac use `/` | Always use `pathlib.Path` and `.resolve()`. Never string-join paths | N/A — pathlib is mandatory |
| 2 | **Directory traversal attack** — LLM generates `../../etc/passwd` style paths | `SandboxEnforcer.validate()` uses `.relative_to()` which detects traversal | Regex whitelist on paths as secondary defense |
| 3 | **File permission errors** — Jarvis tries to touch locked Windows system files | Wrap all file ops in `try/except PermissionError` and return descriptive error | Skip locked files, report them in audit |
| 4 | **WSL path vs Windows path** — `/mnt/c/Users/` vs `C:\Users\` | Config stores paths in the format native to where Python runs | Provide a path normalization utility |
| 5 | **`send2trash` on WSL** — May not work correctly for Windows trash | Detect WSL environment, use `subprocess` to call Windows `recycle.exe` | Move files to a `.jarvis_trash/` folder instead |
| 6 | **LLM generates invalid tool arguments** — malformed JSON or wrong field names | Pydantic validation catches and returns error; LLM retries | Hard-coded fallback values for optional fields |
| 7 | **Symlink escape** — symlink inside sandbox points outside | Resolve symlinks with `Path.resolve()` before sandbox check | Disable symlink following entirely |

---

## Testing Strategy

### On macOS (Developer)
```bash
# Create test sandbox files
mkdir -p /Users/m2air/Desktop/Jarvis/sandbox/test_files
touch /Users/m2air/Desktop/Jarvis/sandbox/test_files/old.log
touch /Users/m2air/Desktop/Jarvis/sandbox/test_files/data.tmp

# Run sandbox security tests
poetry run pytest tests/test_sandbox.py -v

# Run tool tests
poetry run pytest tests/test_file_tools.py -v
```

### Critical Security Tests to Write
```python
# test_sandbox.py
def test_path_traversal_blocked():
    enforcer = SandboxEnforcer(["/Jarvis/sandbox"])
    with pytest.raises(PermissionError):
        enforcer.validate("/Jarvis/sandbox/../../../etc/passwd")

def test_symlink_escape_blocked():
    # Create symlink inside sandbox pointing outside
    ...

def test_valid_path_passes():
    enforcer = SandboxEnforcer(["/Jarvis/sandbox"])
    result = enforcer.validate("/Jarvis/sandbox/test_files/old.log")
    assert result is not None
```

### On Windows 11 (Client)
```bash
# Update SANDBOX_ROOTS in .env to Windows paths
# Run same pytest suite
pytest tests/test_sandbox.py tests/test_file_tools.py -v
```

---

## Definition of Done
- [ ] `SandboxEnforcer` blocks 100% of path traversal test cases
- [ ] All 3 tools run correctly inside sandbox on both Mac and Windows
- [ ] Pydantic validation rejects malformed LLM inputs gracefully
- [ ] LLM can invoke a file scan via voice and receive a spoken summary
- [ ] Zero use of `os.remove()` — all deletes go through `send2trash` or `.jarvis_trash/`

---

## Estimated Time
| Task | Hours |
|---|---|
| Sandbox enforcer + security tests | 3h |
| Pydantic schemas (3 tools) | 2h |
| Tool implementations | 4h |
| Tool registry + function call handler | 3h |
| LLM integration + voice test | 3h |
| Windows path testing + debugging | 3h |
| **Total** | **~18h** |
