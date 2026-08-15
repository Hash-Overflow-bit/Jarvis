# Milestone 6: Local Model Fine-Tuning & Tool-Calling Optimization
> **Pay:** $40 | **Phase:** LLM Optimization

---

## Objective
Optimize system instructions, prompt structures, and function-calling parameters to eliminate tool-use hallucinations on the local Ollama backend. Achieve high-accuracy tool invocation rates where Jarvis reliably selects the correct tool (File Mgmt, Git, or Agent Builder) without syntax failures.

---

## Deliverables
- [ ] Optimized system prompt (v1 → vFinal) with full changelog
- [ ] Tool-calling JSON Schema definitions tuned for the target Ollama model
- [ ] Fallback handler: Detects when LLM fails to call a tool and retries with stronger prompting
- [ ] Hallucination detector: Identifies and rejects tool calls with invented/invalid arguments
- [ ] Benchmark suite: Measures tool selection accuracy across 50+ test cases
- [ ] Prompt version manager: Tracks prompt versions and their benchmark scores
- [ ] `TOOL_RETRY_LIMIT` and `HALLUCINATION_THRESHOLD` config variables
- [ ] Final benchmark report: ≥90% accuracy on all tool categories

---

## What the Client Needs on Windows 11

### Hardware
| Component | Requirement | Why |
|---|---|---|
| GPU VRAM | 12GB+ recommended | Running larger models (llama3.1:70b) improves tool-calling accuracy significantly |
| RAM | 32GB | Multiple model layers may be kept in RAM |

### Software to Install (Client PC)
```bash
# Additional Ollama models for comparison testing
ollama pull llama3.1          # Primary (8B)
ollama pull llama3.1:70b      # Best tool-calling (if VRAM allows)
ollama pull mistral-nemo      # Alternative — very good at function calling
ollama pull qwen2.5:7b        # Excellent tool-calling benchmark scores

# Python packages (inside WSL 2)
poetry add pandas matplotlib seaborn   # For benchmark reporting
```

### Client `.env` additions
```ini
OLLAMA_MODEL=llama3.1           # Primary model
FALLBACK_MODEL=mistral-nemo     # Used if primary fails tool call
TOOL_RETRY_LIMIT=3              # Max retries on tool-call failure
HALLUCINATION_THRESHOLD=0.7     # Confidence below this → reject + retry
BENCHMARK_OUTPUT_DIR=C:\Jarvis\benchmarks
```

---

## What Developer Needs on macOS

### Software
```bash
# Ollama models for benchmarking
ollama pull llama3.1
ollama pull mistral-nemo
ollama pull qwen2.5:7b

poetry add pandas matplotlib seaborn
```

### macOS `.env` additions
```ini
OLLAMA_MODEL=llama3.1
FALLBACK_MODEL=mistral-nemo
TOOL_RETRY_LIMIT=3
HALLUCINATION_THRESHOLD=0.7
BENCHMARK_OUTPUT_DIR=/Users/m2air/Desktop/Jarvis/benchmarks
```

---

## Project Structure (Changes in Milestone 6)
```
/Jarvis/
├── core/
│   ├── llm/
│   │   ├── ollama_client.py           # UPDATED: better tool-call parsing
│   │   ├── prompt_manager.py          # NEW: Versioned prompt management
│   │   ├── tool_call_validator.py     # NEW: Hallucination detection
│   │   └── fallback_handler.py        # NEW: Retry logic on tool-call failure
├── prompts/                           # NEW directory
│   ├── system_prompt_v1.md            # Original prompt
│   ├── system_prompt_v2.md            # Optimized prompt
│   └── system_prompt_current.md       # Symlink to active version
├── benchmarks/                        # NEW directory
│   ├── test_cases.json                # 50+ tool-calling test cases
│   ├── run_benchmark.py               # Benchmark runner script
│   └── results/                       # CSV + charts output
└── tests/
    ├── test_tool_call_validator.py    # NEW
    └── test_fallback_handler.py       # NEW
```

---

## Architecture: Tool-Call Validation & Fallback Pipeline

```
[LLM Response received]
        ↓
[ToolCallValidator.parse(response)]
  → Is it a valid JSON tool call? (not plain text)
  → Does the tool_name exist in registry?
  → Do all required args exist and have correct types?
  → Any hallucinated args (args not in schema)?
        ↓
   ┌────────────────┬─────────────────────┐
   │ VALID          │ INVALID/HALLUCINATED │
   ↓                ↓
[Execute tool]   [FallbackHandler]
                  → Log failure type
                  → Retry with corrective prompt
                  → Inject example of correct format
                  → Attempt up to TOOL_RETRY_LIMIT
                        ↓
                  Still failing?
                        ↓
                  [Ask user for clarification via TTS]
```

---

## Step-by-Step Build Plan

### Step 1: Audit Current Tool-Calling Failures
Before optimizing, measure baseline performance:
```bash
python benchmarks/run_benchmark.py --prompt v1 --model llama3.1
```
This generates a report showing which tool calls fail and why (wrong args, plain text response, etc.)

### Step 2: System Prompt Optimization (`prompts/system_prompt_v2.md`)

**Key prompt engineering principles for local models:**

1. **Be extremely explicit about output format:**
```
When you need to use a tool, you MUST respond ONLY with a JSON object in this exact format:
{"tool": "tool_name", "args": {"arg1": "value1", "arg2": "value2"}}
Do NOT add any text before or after the JSON. Do NOT use markdown code blocks.
```

2. **Provide a working example for every tool in the system prompt:**
```
Example - User says "List files in my workspace":
{"tool": "file_scanner", "args": {"directory": "/workspace", "extension_filter": null}}
```

3. **Explicit "When to use which tool" section:**
```
USE file_scanner WHEN: user wants to see files, list directory, find files
USE file_cleanup WHEN: user wants to delete, clean, remove, archive files
USE git_clone WHEN: user mentions cloning, downloading a repo, getting code
DO NOT use any tool if the user is just asking a question — respond in plain text.
```

4. **Force structured outputs for models that support it** (llama3.1 supports JSON mode):
```python
response = ollama_client.chat(
    model=settings.OLLAMA_MODEL,
    messages=history,
    format="json",   # Ollama JSON mode — forces JSON output
    options={"temperature": 0.1}  # Lower temp = more deterministic tool calls
)
```

### Step 3: Tool Call Validator (`core/llm/tool_call_validator.py`)
```python
import json
from pydantic import ValidationError

class ToolCallValidator:
    def parse_and_validate(self, response: str, tool_registry) -> tuple[dict | None, str]:
        """
        Returns: (validated_tool_call_dict, error_message)
        If valid: ({"tool": "...", "args": {...}}, "")
        If invalid: (None, "reason for failure")
        """
        # 1. Try to extract JSON from response
        try:
            # Handle cases where LLM wraps in ```json ... ```
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return None, "Response is not valid JSON — likely plain text response"

        # 2. Check required fields
        if "tool" not in parsed:
            return None, "Missing 'tool' field in response"
        if "args" not in parsed:
            return None, "Missing 'args' field in response"

        tool_name = parsed["tool"]

        # 3. Check tool exists
        tool = tool_registry.get(tool_name)
        if not tool:
            return None, f"Hallucinated tool name: '{tool_name}' does not exist"

        # 4. Validate args against Pydantic schema
        try:
            tool.input_schema(**parsed["args"])
        except ValidationError as e:
            return None, f"Invalid args for {tool_name}: {e}"

        # 5. Check for hallucinated extra args
        valid_fields = set(tool.input_schema.model_fields.keys())
        given_fields = set(parsed["args"].keys())
        hallucinated = given_fields - valid_fields
        if hallucinated:
            return None, f"Hallucinated args: {hallucinated}"

        return parsed, ""
```

### Step 4: Fallback Handler (`core/llm/fallback_handler.py`)
```python
class FallbackHandler:
    async def handle_failed_tool_call(
        self,
        original_response: str,
        error: str,
        user_message: str,
        history: list[dict]
    ) -> str | dict:
        """
        Retry tool call with corrective prompting.
        Returns either a valid tool call dict or a plain text response.
        """
        for attempt in range(settings.TOOL_RETRY_LIMIT):
            correction_prompt = f"""
Your previous response was invalid: {error}

The user said: "{user_message}"
Your response was: {original_response}

Please try again. If you need to use a tool, respond ONLY with valid JSON.
If no tool is needed, respond with plain text. Do not make up tool names or arguments.
"""
            retry_response = await ollama_client.chat(
                model=settings.OLLAMA_MODEL,
                messages=history + [{"role": "user", "content": correction_prompt}]
            )
            validated, err = tool_call_validator.parse_and_validate(retry_response, tool_registry)
            if validated:
                return validated
            original_response = retry_response
            error = err

        # All retries failed — ask user for clarification
        return f"I'm having trouble understanding what tool to use for that. Could you rephrase your request?"
```

### Step 5: Prompt Version Manager (`core/llm/prompt_manager.py`)
- Loads system prompt from `prompts/system_prompt_current.md`
- Injects tool schemas dynamically
- Tracks which prompt version is active via `.env` variable `PROMPT_VERSION`

### Step 6: Benchmark Suite (`benchmarks/`)
```json
// benchmarks/test_cases.json (sample)
[
  {
    "id": "tc001",
    "category": "file_management",
    "user_input": "Show me all the log files in my workspace",
    "expected_tool": "file_scanner",
    "expected_args": {"extension_filter": ".log"}
  },
  {
    "id": "tc002",
    "category": "git",
    "user_input": "Clone the FastAPI repository",
    "expected_tool": "git_clone",
    "expected_args": {"url": "https://github.com/tiangolo/fastapi"}
  },
  {
    "id": "tc003",
    "category": "no_tool",
    "user_input": "What is the capital of France?",
    "expected_tool": null,
    "expected_args": null
  },
  {
    "id": "tc004",
    "category": "agent_builder",
    "user_input": "Create a new agent that can search Wikipedia",
    "expected_tool": "agent_builder",
    "expected_args": {"name": "WikipediaSearchAgent", "framework": "crewai"}
  }
]
```

```python
# benchmarks/run_benchmark.py
def run_benchmark(prompt_version: str, model: str):
    results = []
    for case in load_test_cases():
        response = ollama_chat(model, case["user_input"], prompt_version)
        parsed, error = validator.parse_and_validate(response, registry)
        correct = (parsed and parsed["tool"] == case["expected_tool"]) or \
                  (parsed is None and case["expected_tool"] is None)
        results.append({**case, "correct": correct, "error": error})

    accuracy = sum(r["correct"] for r in results) / len(results)
    print(f"Accuracy: {accuracy:.1%}")
    save_csv(results, f"benchmarks/results/{prompt_version}_{model}.csv")
```

---

## Model Comparison for Tool Calling

| Model | VRAM | Tool-Call Accuracy | Speed | Recommendation |
|---|---|---|---|---|
| `llama3.1:8b` | 6GB | ~75% | Fast | Good starting point |
| `llama3.1:70b` | 40GB | ~92% | Slow | Best quality, needs strong GPU |
| `mistral-nemo` | 8GB | ~85% | Fast | Best balance |
| `qwen2.5:7b` | 5GB | ~88% | Fast | Excellent for tool-calling |
| `codellama:7b` | 5GB | ~70% | Fast | Not ideal for tool-calling |

**Recommended primary:** `qwen2.5:7b` (best tool-calling per VRAM GB)
**Recommended fallback:** `mistral-nemo`

---

## Cross-Platform Challenges, Solutions & Alternatives

| # | Challenge | Solution | Alternative |
|---|---|---|---|
| 1 | **LLM invents non-existent tool names** | Explicit tool list in system prompt; validator rejects unknown tools; fallback retries | Force model to choose from a numbered list |
| 2 | **LLM passes malformed JSON** | `json.loads()` with error handling; strip markdown code fences | Use Ollama's `format="json"` to force valid JSON |
| 3 | **LLM passes wrong argument types** | Pydantic validation; error fed back to LLM in fallback | Coerce types where safe (e.g., string "5" → int 5) |
| 4 | **Prompt drift** — model gradually loses tool-calling format over long conversations | Re-inject system prompt every 10 turns; or use Ollama's `keep_alive` option | Summarize old history to reduce context drift |
| 5 | **Different models behave differently** on Mac vs Windows | Test benchmark suite on both machines; target model must work on both | Use `OLLAMA_MODEL` in `.env` to easily switch models |
| 6 | **Low VRAM on client** prevents running larger models | `qwen2.5:7b` runs well on 6GB VRAM with good accuracy | Use `llama3.1:8b` with quantization (Q4_K_M) |
| 7 | **Temperature too high** causes format drift | Set `temperature=0.1` for tool-calling responses | Use `temperature=0` for maximum determinism |

---

## Testing Strategy

### Benchmark Testing (Both macOS and Windows)
```bash
# Run baseline benchmark
python benchmarks/run_benchmark.py --prompt v1 --model llama3.1

# Run optimized prompt benchmark
python benchmarks/run_benchmark.py --prompt v2 --model llama3.1

# Compare models
python benchmarks/run_benchmark.py --prompt v2 --model qwen2.5:7b

# Generate comparison chart
python benchmarks/generate_report.py
```

### Unit Tests
```bash
poetry run pytest tests/test_tool_call_validator.py -v
poetry run pytest tests/test_fallback_handler.py -v
```

---

## Definition of Done
- [ ] Benchmark suite has ≥50 test cases across all tool categories
- [ ] Tool selection accuracy ≥90% on optimized prompt + best model
- [ ] Fallback handler successfully recovers ≥80% of initially-failed tool calls
- [ ] Hallucination detector blocks 100% of invented tool names/args
- [ ] Benchmark report generated (CSV + charts) for both macOS and Windows results
- [ ] Final `OLLAMA_MODEL` recommendation documented with rationale
- [ ] No tool call ever crashes the system — all failures are gracefully handled

---

## Estimated Time
| Task | Hours |
|---|---|
| Baseline benchmark + failure audit | 3h |
| System prompt optimization (iterative) | 6h |
| Tool call validator | 3h |
| Fallback handler | 3h |
| Benchmark suite (50 cases) | 4h |
| Benchmark runner + report generation | 3h |
| Model comparison testing | 4h |
| Windows testing | 2h |
| **Total** | **~28h** |
