# Legacy Tier 1 - Root Cause Analysis

## Executive Summary
The failure of the Legacy Tier 1 prompt is **not** a path resolution bug in the underlying `write_file` tool or `sandbox_enforcer`. Instead, it is an over-eager deterministic routing issue caused by the `_direct_route` method in `core/orchestrator/agent_loop.py`.

## Prompt Analyzed
“Read the local system prompt files in the configured workspace, summarize the core instructions in exactly three bullet points, and create test_summary.md in that workspace.”

## Root Cause Breakdown
When this prompt is processed by `AgentExecutionLoop._direct_route`:
1. **Clause Splitting**: The regex splits the prompt at `, and create`, resulting in two clauses.
2. **Clause 1 Ignored**: The first clause (`Read the local system prompt files... summarize...`) fails to match any deterministic intent because:
   - The `read` regex requires a file extension (e.g. `.txt`, `.md`), but "system prompt files" has none.
   - The `generation` regex looks for verbs like `generate`, `produce`, or `draft`, but not `summarize`.
   - Consequently, this clause is completely dropped. No read or summarize steps are planned.
3. **Clause 2 Mismatched Path**: The second clause (`create test_summary.md in that workspace.`) matches the `write_file` pattern. However, the path resolution in `_resolve_parent_dir` fails to match the phrase "in that workspace" because its regex (`(?:inside|under|within|in)\s+(?:it|that folder|that directory|([a-zA-Z0-9_\-\.]+))|there`) matches "that workspace" as an unrecognized location. It falls back to the default `last_created_dir`, which is `settings.desktop_dir`.
4. **Empty Content**: Because the summarization generation was dropped, the `write_file` step is created with empty content (`""`).
5. **LLM Bypassed**: Since `_direct_route` successfully returns a (flawed) 1-step plan, the actual LLM planner is completely bypassed.

## Captured Telemetry
- **Original requested path**: Implicitly "that workspace" -> `test_summary.md`
- **Resolved absolute path**: `/Users/m2air/Desktop/test_summary.md`
- **Current working directory**: `/Users/m2air/Desktop/Jarvis`
- **Tool call arguments**: `{'filepath': '/Users/m2air/Desktop/test_summary.md', 'content': ''}`
- **Tool result**: `{"success": true, "message": "Successfully wrote content to: /Users/m2air/Desktop/test_summary.md"}`
- **Model response**: Bypassed by `[⚡ Direct Route]`
- **Whether test_summary.md was actually created**: Yes, but at the wrong path (`Desktop/` instead of `workspace/`) and with empty content.

## Resolution (Phase B)
The issue was fixed by:
1. Modifying `_direct_route` to return `None` (falling back to the LLM planner) if a multi-clause prompt fails to fully validate deterministically. This prevents dropping earlier clauses and executing only the parsed fragments.
2. Enhancing `_resolve_parent_dir` and the `ref_match` regex to accurately parse multi-word locations (like "that workspace") and paths with slashes.
3. Adding strict boundary enforcement in `write_file` relative to the configured workspace, completely blocking unauthorized fallback writes to the Desktop.
4. Correcting the intent path resolution in `WritingPipeline` to correctly respect `workspace` as an allowed target destination alongside `desktop`.
