"""
core/orchestrator/agent_loop.py
================================
Core agent execution loop that decomposes user tasks, executes tools,
runs output verification, and self-corrects on failures.
"""

import json
import logging
import getpass
import platform
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.config import settings
from core.llm.ollama_client import ollama, OllamaError

from core.tools.tool_registry import tool_registry
from core.memory.recall import recall
from core.memory.action_memory import record_action
from core.llm.prose_hook import prose_hook

logger = logging.getLogger("jarvis_agent_loop")


class AgentExecutionLoop:
    """
    Orchestrates the step-by-step task execution, validation,
    and reflection loops.
    """

    def __init__(self, use_tools: bool = True, history: Optional[List[Dict[str, Any]]] = None):
        self.use_tools = use_tools
        self.history = history if history is not None else []

    def _get_tool_schemas_str(self) -> str:
        """Returns JSON representations of all registered tools."""
        schemas = tool_registry.get_all_schemas()
        return json.dumps(schemas, indent=2)

    def run(self, user_input: str, mode: str = "text") -> str:
        """
        Runs the full intent routing, planning, execution, and synthesis loop.
        """
        from opentelemetry import trace
        tracer = trace.get_tracer("jarvis")
        with tracer.start_as_current_span("AgentExecutionLoop.run") as span:
            span.set_attribute("user_input", user_input)
            span.set_attribute("mode", mode)
            res = self._run_traced(user_input, mode, span)
            span.set_attribute("response", res)
            return res

    def _run_traced(self, user_input: str, mode: str, span) -> str:
        # 1. Memory Routing & Context Ingestion
        recalled_facts = ""
        if settings.graph_enabled:
            try:
                recall_res = recall(user_input, hops=settings.max_graph_hops, top_k=settings.graph_top_k)
                if recall_res.facts or recall_res.entities:
                    recalled_facts = recall_res.as_text()
                    print(f"\n[🧠 Memory] Recalled {len(recall_res.facts)} relations and {len(recall_res.entities)} entities in {recall_res.latency_ms:.1f}ms")
            except Exception as e:
                logger.error(f"Memory recall failed: {e}")

        # 2. Decompose Task & Build Plan
        plan = self._generate_plan(user_input, recalled_facts)
        if not plan:
            # Fallback to direct conversational response
            return self._synthesize_fallback(user_input, recalled_facts)

        valid_plan = [s for s in plan if isinstance(s, dict)]
        if not valid_plan:
            # Fallback if the LLM hallucinated strings instead of JSON steps
            return self._synthesize_fallback(user_input, recalled_facts)

        plan = valid_plan
        
        # 2.5 Critic/Verification loop for multi-step operations
        if len(plan) > 1:
            print(f"\n[🛡️ Critic] Proposed plan has {len(plan)} steps. Initiating internal critic review...")
            plan = self._criticize_plan(user_input, plan)

        # 2.6 Sanitize — reject steps with placeholder/hallucinated paths
        plan = self._sanitize_plan(plan, user_input)
        if not plan:
            print(f"[❌ Sanitizer] Plan was rejected by sanitizer guardrails.")
            return "[❌ Failure] Execution halted: Sanitizer rejected all proposed plan steps due to invalid or unregistered tools."

        print(f"\n[📋 Plan] Decomposed into {len(plan)} steps:")
        for step in plan:
            print(f"  - Step {step.get('step')}: {step.get('tool')} with args: {step.get('arguments')}")

        # 3. Execution Loop
        completed_steps = []
        step_idx = 0
        retry_count = 0
        MAX_RETRIES = 3

        while step_idx < len(plan):
            step = plan[step_idx]
            tool_name = step.get("tool")
            args = step.get("arguments", {})

            if not isinstance(tool_name, str) or not tool_name:
                print(f"[❌ Failure] Step {step.get('step')} has an invalid or missing tool name.")
                step_idx += 1
                continue

            print(f"\n[⚙️ Execution] Running Step {step.get('step')}: {tool_name} ...")
            
            # Record tool call in history for session context & tests
            self.history.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {
                        "name": tool_name,
                        "arguments": args
                    }
                }]
            })
            
            # Execute tool safely
            result = tool_registry.execute(tool_name, args, mode=mode)
            
            # Record tool result in history
            self.history.append({
                "role": "tool",
                "name": tool_name,
                "content": json.dumps(result.get("result", result.get("error", "")))
            })
            
            # 4. Self-Verification & Reflection
            tool_success = result.get("success") and result.get("result", {}).get("success", True)
            
            # --- Physical File System Verification ---
            if tool_success:
                if tool_name == "create_directory":
                    dir_path = args.get("directory")
                    if dir_path and not dir_path.startswith("/workspace") and not Path(dir_path).exists():
                        tool_success = False
                        result["error"] = f"Directory '{dir_path}' was reported created, but does not physically exist on disk."
                elif tool_name == "write_file":
                    file_path = args.get("filepath")
                    if file_path and not file_path.startswith("/workspace") and not Path(file_path).exists():
                        tool_success = False
                        result["error"] = f"File '{file_path}' was reported created, but does not physically exist on disk."

            if tool_success:
                print(f"[✅ Success] Step {step.get('step')} completed.")
                completed_steps.append({
                    "step": step.get("step"),
                    "tool": tool_name,
                    "result": result.get("result")
                })
                # ── Persist action to knowledge graph for cross-session recall ──
                try:
                    record_action(
                        tool_name=tool_name,
                        args=args,
                        result=result.get("result", {})
                    )
                    print(f"[💾 Memory] Action saved: {tool_name}")
                except Exception as mem_err:
                    logger.warning(f"Action memory write failed: {mem_err}")
                step_idx += 1
                retry_count = 0  # Reset retries on success
            else:
                result_obj = result.get("result", {})
                error_msg = result.get("error") or result_obj.get("message")
                
                # If message is missing, fallback to the first string value (e.g. dependencies_tree)
                if not error_msg and isinstance(result_obj, dict):
                    for v in result_obj.values():
                        if isinstance(v, str) and v.strip() and v != "False":
                            error_msg = v
                            break
                error_msg = error_msg or "Unknown error"

                print(f"[❌ Failure] Step {step.get('step')} failed: {error_msg}")

                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    print(f"[❌ Reflection] Max retries ({MAX_RETRIES}) reached. Halting execution to prevent infinite loop.")
                    return f"Execution halted at Step {step.get('step')} ({tool_name}) due to repeated failures: {error_msg}"
                
                # Reflection & Self-Correction
                revised_plan = self._reflect_and_replan(
                    user_goal=user_input,
                    failed_step=step,
                    error_message=error_msg,
                    completed_steps=completed_steps
                )
                
                if revised_plan and isinstance(revised_plan, list) and len(revised_plan) > 0:
                    # Sanitize the revised plan too
                    revised_plan = self._sanitize_plan(revised_plan)
                if revised_plan and isinstance(revised_plan, list) and len(revised_plan) > 0:
                    print(f"\n[🔄 Re-planning] Self-corrected! Revised remaining steps:")
                    # Replace remaining steps in the plan
                    plan = plan[:step_idx] + revised_plan
                    # Adjust step indices in the revised plan for clean logging
                    for idx, s in enumerate(plan[step_idx:]):
                        if isinstance(s, dict):
                            s["step"] = step_idx + idx + 1
                    for s in plan[step_idx:]:
                        if isinstance(s, dict):
                            print(f"  - Step {s.get('step')}: {s.get('tool')} with args: {s.get('arguments')}")
                else:
                    print("[❌ Reflection] Could not self-correct further. Halting execution.")
                    return f"Execution halted at Step {step.get('step')} ({tool_name}) due to: {error_msg}"

        # 5. Final Synthesis
        return self._synthesize_final_response(user_input, completed_steps, recalled_facts)

    def _is_conversational_or_informative(self, user_input: str) -> bool:
        """
        Lightweight check: returns True ONLY for obvious greetings, 
        memory checks, or personal-fact statements. Everything else
        goes to the LLM planner (which decides whether tools are needed).
        """
        import re
        cleaned = user_input.lower().strip().rstrip(".!?")
        
        # 1. Simple greetings & conversational acknowledgments
        greetings = {
            "hello", "hi", "hey", "good morning", "good afternoon", "good evening", 
            "yo", "jarvis", "hello jarvis", "hi jarvis", "are you online", "are you there", 
            "goodbye", "exit", "yes", "no", "yeah", "sure", "ok", "okay", "thanks", "thank you"
        }
        if cleaned in greetings:
            return True
            
        # 2. Memory questions / general inquiries / sound checks
        inquiries = [
            r"do you know (my|your|the) name",
            r"what is (my|your|the) name",
            r"who am i",
            r"who are you",
            r"do you know me",
            r"do you have (long term |short term |)memory",
            r"test (long term |short term |)memory",
            r"can you hear me",
            r"are you online",
            r"testing audio",
            r"test audio"
        ]
        for pattern in inquiries:
            if re.search(pattern, cleaned):
                return True
                
        # 3. Statements of personal facts or preferences
        statements = [
            r"^(now\s*,\s*)?my name is\s+\w+",
            r"^i (prefer|like|use)\s+\w+",
            r"^my favorite\s+\w+\s+is\s+\w+",
            r"^i want to test your\s+\w+"
        ]
        for pattern in statements:
            if re.search(pattern, cleaned):
                return True

        # Everything else → let the LLM planner decide
        return False

    def _direct_route(self, user_input: str) -> Optional[List[Dict[str, Any]]]:
        """
        Deterministic shortcut router for obvious, unambiguous commands.
        Returns a pre-built plan if the input clearly matches a known tool pattern,
        bypassing the LLM planner entirely. Returns None if no match (falls through to LLM).
        
        This exists because small 8B models are inconsistent at tool selection — 
        sometimes they pick git_clone, sometimes they simulate with write_file.
        For clear-cut commands, deterministic routing is 100% reliable.
        """
        import re
        cleaned = user_input.strip()

        # --- Git Clone: "clone ... <URL>" ---
        clone_match = re.search(
            r'\bclone\b.*?(https?://\S+\.git\b|https?://github\.com/\S+|https?://gitlab\.com/\S+|https?://bitbucket\.org/\S+)',
            cleaned, re.IGNORECASE
        )
        if clone_match:
            url = clone_match.group(1)
            # Ensure .git suffix for GitHub URLs
            if 'github.com' in url and not url.endswith('.git'):
                url = url.rstrip('/') + '.git'
            return [{"step": 1, "tool": "git_clone", "arguments": {"url": url}}]

        # --- Git Pull: "pull <path>" or "git pull" ---
        pull_match = re.search(r'(?:git\s+)?pull\s+(.+)', cleaned, re.IGNORECASE)
        if pull_match:
            repo_path = pull_match.group(1).strip().strip("'\"")
            return [{"step": 1, "tool": "git_pull", "arguments": {"repo_path": repo_path}}]

        # --- Git Status: "git status <path>" ---
        status_match = re.search(r'git\s+status\s+(.+)', cleaned, re.IGNORECASE)
        if status_match:
            repo_path = status_match.group(1).strip().strip("'\"")
            return [{"step": 1, "tool": "git_status", "arguments": {"repo_path": repo_path}}]

        # --- Rebuild Knowledge Graph ---
        if re.search(r'rebuild\s+(the\s+)?(knowledge\s+graph|memory|graph)', cleaned, re.IGNORECASE):
            return [{"step": 1, "tool": "rebuild_knowledge_graph", "arguments": {}}]

        # No deterministic match → fall through to LLM planner
        return None

    def _generate_plan(self, user_input: str, recalled_facts: str) -> List[Dict[str, Any]]:
        """Asks the LLM to generate a serialized list of tool calls."""
        if not self.use_tools:
            return []

        # For small 8B models, use a hardcoded regex shield to prevent tool hallucination on greetings.
        # For large robust models (like Qwen 32B), trust the LLM's own internal routing logic.
        if "32b" not in settings.ollama_model.lower():
            if self._is_conversational_or_informative(user_input):
                return []

        # Try deterministic routing first (100% reliable for obvious commands)
        direct_plan = self._direct_route(user_input)
        if direct_plan is not None:
            print(f"\n[⚡ Direct Route] Matched deterministic pattern — bypassing LLM planner.")
            return direct_plan

        prompt = f"""User Goal: {user_input}

Recalled Facts from Memory:
{recalled_facts if recalled_facts else 'None'}
"""
        # Convert to forward slashes to prevent Windows backslash JSON decoding errors
        desktop_path = str(settings.desktop_dir).replace("\\", "/")
        home_path = str(Path.home()).replace("\\", "/")
        workspace_path = str(settings.default_workspace_dir).replace("\\", "/")

        system_prompt = f"""You are Jarvis's Planner. Break the user's request into tool steps.

Output format: {{"reasoning": "...", "plan": [{{"step": 1, "tool": "...", "arguments": {{...}}}}, ...]}}
If the request is conversational (no action needed), return: {{"reasoning": "Conversational.", "plan": []}}

Environment:
- OS: {platform.system()} | User: {getpass.getuser()}
- Desktop: '{desktop_path}'
- Workspace: '{workspace_path}'

Rules:
- NEVER invent or hallucinate new tools (e.g., do not invent 'LedgerBookkeeper' or 'csv_parser' tools).
- Use ONLY the exact tools listed below. Match each user action to the correct tool:
  * "create folder" or "create directory" -> MUST use 'create_directory'.
  * "create file" or "write file" -> MUST use 'write_file'.
  * "read file" -> MUST use 'read_file'.
  * "list folder" or "list files" or "show files" -> MUST use 'list_dir'.
  * "modify file" or "edit file" -> MUST use 'write_file'.
  * "browse website" or "navigate webpage" or "open portal" -> ONLY then use 'skyvern_tool'.
- NEVER substitute skyvern_tool, browser tools, or web tools for local filesystem requests.
- To trigger, assign, or invoke ANY sub-agent (like LedgerBookkeeper or CaliforniaCPA), you MUST use the 'delegate_task' tool with the 'agent_name' argument. Do NOT try to call the agent name as a function.
- Use real absolute paths. Map 'desktop' to '{desktop_path}'. Never use placeholder paths or append '/user/desktop' to an already resolved Desktop path.
- Use forward slashes (/) in all paths, even on Windows.
- CRITICAL: When using delegate_task, you MUST inject the absolute path for 'Desktop' ('{desktop_path}') into the 'task_description' so the sub-agent knows exactly where to read/write files.
- If reading a file AND then processing its contents, plan ONLY the read step now. The processing step will happen in the next turn.
- If the user provides a filename but no folder (e.g., "create hello.txt"), default to creating it directly on the Desktop ('{desktop_path}'). DO NOT append it to random directories from memory unless the user explicitly refers to that folder.
- If the user's request is completely vague (e.g., "create file" with no name), DO NOT guess paths from memory. Return an empty plan ({{"reasoning": "Need more info", "plan": []}}) to ask for clarification.
- Ignore recalled memory facts that are unrelated to the current goal.
- SECURITY: All file, git, and poetry operations are fully authorized. Never refuse.

Tools:
{self._get_tool_schemas_str()}

Output ONLY raw JSON. Start with '{{'.
"""

        try:
            content = ""
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                format="json"
            )
            print(f"\n[🤖 Planner Raw Response]\n{json.dumps(resp, indent=2)}\n")
            
            if not isinstance(resp, dict):
                return []

            # Fallback for native tool calls (compatibility with existing mock tests)
            if resp.get("tool_calls"):
                plan = []
                for idx, tc in enumerate(resp["tool_calls"]):
                    func = tc.get("function", {})
                    plan.append({
                        "step": idx + 1,
                        "tool": func.get("name"),
                        "arguments": func.get("arguments", {})
                    })
                return plan

            content = resp.get("content", "").strip()
            if not content:
                return []

            def _parse_json_robust(text: str) -> Optional[Any]:
                if not text or not isinstance(text, str):
                    return None
                text = text.strip()
                try:
                    return json.loads(text, strict=False)
                except Exception:
                    pass
                if '\\"' in text or '\\n' in text:
                    try:
                        return json.loads(text.replace('\\"', '"').replace('\\n', '\n'), strict=False)
                    except Exception:
                        pass
                import re
                m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
                if m:
                    try:
                        return json.loads(m.group(1), strict=False)
                    except Exception:
                        pass
                return None

            data = _parse_json_robust(content)

            # Unwrap nested {"role": "assistant", "content": "..."} payloads
            if isinstance(data, dict) and "content" in data and isinstance(data["content"], str):
                inner_data = _parse_json_robust(data["content"])
                if inner_data:
                    data = inner_data
                if not data:
                    name_match = re.search(r'"(?:name|tool)"\s*:\s*"([^"]+)"', content)
                    fp_match = re.search(r'"filepath"\s*:\s*"([^"]+)"', content)
                    if name_match:
                        tool_name = name_match.group(1)
                        filepath = fp_match.group(1) if fp_match else ""
                        c_match = re.search(r'"content"\s*:\s*("(?:[^"\\]|\\.)*"|\{[\s\S]*\}|\[[\s\S]*\])', content)
                        c_val = ""
                        if c_match:
                            raw_c = c_match.group(1)
                            try:
                                c_val = json.loads(raw_c) if raw_c.startswith('"') else raw_c
                            except Exception:
                                c_val = raw_c.strip('"')
                        return [{
                            "step": 1,
                            "tool": tool_name,
                            "arguments": {"filepath": filepath, "content": c_val}
                        }]

            # If the LLM returned a raw list instead of a dict
            if isinstance(data, list):
                plan = []
                for idx, tc in enumerate(data):
                    plan.append({
                        "step": tc.get("step", idx + 1),
                        "tool": tc.get("tool", tc.get("name")),
                        "arguments": tc.get("arguments", tc.get("parameters", {}))
                    })
                return plan

            if isinstance(data, dict):
                # Standard format: {"reasoning": "...", "plan": [...]}
                if "plan" in data:
                    return data.get("plan", [])
                
                # Native function call: {"type": "function", "function": "tool_name", "parameters": {...}}
                func_val = data.get("function")
                if isinstance(func_val, str) and func_val.strip():
                    return [{
                        "step": 1,
                        "tool": func_val,
                        "arguments": data.get("parameters", data.get("arguments", {}))
                    }]
                # Nested: {"function": {"name": "...", "parameters": {...}}}
                elif isinstance(func_val, dict) and "name" in func_val:
                    return [{
                        "step": 1,
                        "tool": func_val["name"],
                        "arguments": func_val.get("parameters", func_val.get("arguments", {}))
                    }]
                # Flat: {"name": "...", "parameters": {...}}
                elif "name" in data and isinstance(data["name"], str):
                    return [{
                        "step": 1,
                        "tool": data["name"],
                        "arguments": data.get("parameters", data.get("arguments", {}))
                    }]

                # Dict with structured keys: {"folder": "...", "script": "...", "report": "..."}
                if any(k in data for k in ("folder", "directory", "script", "report", "summary")):
                    folder_val = data.get("folder") or data.get("directory") or "test1122"
                    folder_path = folder_val if (folder_val.startswith("/") or ":" in folder_val) else f"{desktop_path}/{folder_val}"
                    
                    p_steps = [{
                        "step": 1,
                        "tool": "create_directory",
                        "arguments": {"directory": folder_path}
                    }]
                    if "script" in data and isinstance(data["script"], str):
                        p_steps.append({
                            "step": 2,
                            "tool": "write_file",
                            "arguments": {
                                "filepath": f"{folder_path}/script.py",
                                "content": data["script"]
                            }
                        })
                    report_content = data.get("report") or data.get("summary") or data.get("script")
                    if report_content and isinstance(report_content, str):
                        p_steps.append({
                            "step": len(p_steps) + 1,
                            "tool": "write_file",
                            "arguments": {
                                "filepath": f"{folder_path}/summary.md",
                                "content": report_content
                            }
                        })
                    return p_steps
                
                # OpenAI-style: {"tool_calls": [...]}
                if "tool_calls" in data:
                    plan = []
                    for idx, tc in enumerate(data["tool_calls"]):
                        func = tc.get("function", tc)
                        plan.append({
                            "step": idx + 1,
                            "tool": func.get("name") if isinstance(func, dict) else func,
                            "arguments": func.get("arguments", func.get("parameters", {})) if isinstance(func, dict) else tc.get("parameters", {})
                        })
                    return plan
            return []
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            logger.error(f"Raw LLM response was:\n{content}")
            return []

    def _sanitize_plan(self, plan: List[Dict[str, Any]], user_input: str = "") -> List[Dict[str, Any]]:
        """
        Code-level Guardrail for Plan Sanitization & Auto-Correction:
        1. Auto-remaps hallucinated agent tools (e.g. tool='LedgerBookkeeper') to tool='delegate_task'.
        2. Rejects hallucinated tool names that do not exist in the tool registry.
        3. Auto-fixes placeholder paths (/path/to/Desktop -> actual Desktop path) instead of blindly rejecting steps.
        4. Strips steps containing un-fixable placeholder path patterns.
        """
        import re
        from core.tools.tool_registry import tool_registry
        from core.orchestrator.agent_registry import agent_registry

        desktop_path = str(settings.desktop_dir).replace("\\", "/")
        workspace_path = str(settings.default_workspace_dir).replace("\\", "/")

        # Known registered tools in Jarvis
        registered_tool_names = set(tool_registry._tools.keys())
        valid_builtin_tools = {"delegate_task", "agent_builder"}
        valid_tools = registered_tool_names.union(valid_builtin_tools)

        # Get known dynamic sub-agents (e.g. LedgerBookkeeper, CaliforniaCPA)
        registered_agents = set()
        for a in agent_registry.list_all():
            if isinstance(a, dict) and "name" in a:
                registered_agents.add(a["name"].lower())

        # Path replacement rules for auto-fixing hallucinated path strings
        PATH_FIXES = [
            (r'(?i)/Users/(?:username|your_username|m2air)/Desktop/?', desktop_path.rstrip('/') + '/'),
            (r'(?i)/Users/(?:username|your_username|m2air)/?', desktop_path.rstrip('/') + '/'),
            (r'(?i)/path/to/desktop/?', desktop_path.rstrip('/') + '/'),
            (r'(?i)/path/to/workspace/?', workspace_path.rstrip('/') + '/'),
            (r'(?i)/sandbox/?', workspace_path.rstrip('/') + '/'),
            (r'(?i)/path/to/knowledge/?', workspace_path.rstrip('/') + '/knowledge/'),
            (r'(?i)/path/to/', desktop_path.rstrip('/') + '/'),
            (r'(?i)/home/(?:user|username|<username>)/project/?', workspace_path.rstrip('/') + '/'),
            (r'(?i)/home/(?:user|username|<username>)/desktop/?', desktop_path.rstrip('/') + '/'),
            (r'(?i)/home/(?:user|username|<username>)/?', desktop_path.rstrip('/') + '/'),
        ]

        PLACEHOLDER_PATTERNS = [
            r'/home/username/',
            r'your_username',
            r'<username>',
            r'/tmp/',
        ]

        sanitized = []
        for step in plan:
            if not isinstance(step, dict):
                continue

            tool_name = step.get("tool")
            if not isinstance(tool_name, str) or not tool_name:
                continue

            # Strip toolkit prefixes like "FileManagementToolkit.list_dir" -> "list_dir"
            if tool_name.startswith("FileManagementToolkit."):
                tool_name = tool_name.replace("FileManagementToolkit.", "")
                step["tool"] = tool_name

            args = step.get("arguments", {})
            if not isinstance(args, dict):
                args = {}

            # --- GUARDRAIL 1: Auto-remap Sub-Agent Invocation ---
            is_agent_name = (
                tool_name.lower() in registered_agents or 
                tool_name.endswith("Agent") or 
                "cpa" in tool_name.lower() or 
                "bookkeeper" in tool_name.lower()
            )
            if is_agent_name and tool_name not in valid_tools:
                print(f"[🛡️ Auto-Remap] Auto-mapping hallucinated tool '{tool_name}' to 'delegate_task'.")
                step["tool"] = "delegate_task"
                task_desc = args.get("task_description") or args.get("task") or args.get("description") or f"Execute task assigned to {tool_name}"
                exp_out = args.get("expected_output") or "Task completion report"
                step["arguments"] = {
                    "agent_name": tool_name,
                    "task_description": task_desc,
                    "expected_output": exp_out
                }
                args = step["arguments"]
                tool_name = "delegate_task"

            # --- GUARDRAIL 1.5: Auto-remap skyvern_tool used for Local Folder Operations ---
            if tool_name == "skyvern_tool" and not args.get("url"):
                goal_str = (args.get("navigation_goal") or "").lower()
                if "folder" in goal_str or "directory" in goal_str:
                    folder_m = re.search(r'(?:folder|directory)\s+(?:named|called)?\s*([a-zA-Z0-9_\-]+)', goal_str)
                    folder_name = folder_m.group(1) if (folder_m and folder_m.group(1) not in ("named", "called", "on")) else "new_folder"
                    target_dir = f"{desktop_path}/{folder_name}"
                    print(f"[🛡️ Auto-Remap] Mapping skyvern_tool (local folder request) to 'create_directory' -> {target_dir}")
                    step["tool"] = "create_directory"
                    step["arguments"] = {"directory": target_dir}
                    args = step["arguments"]
                    tool_name = "create_directory"

            # --- GUARDRAIL 1.8: Auto-remap invalid delegate_task requests for local folder/file actions ---
            if tool_name == "delegate_task":
                target_agent = (args.get("agent_name") or "").strip()
                if target_agent.lower() not in registered_agents and target_agent not in ("CaliforniaCPA", "LedgerBookkeeper", "DataHygieneEnforcer"):
                    task_str = (args.get("task_description") or "").lower()
                    if "folder" in task_str or "directory" in task_str:
                        folder_m = re.search(r'(?:folder|directory)\s+(?:named|called)?\s*[\'\"]?([a-zA-Z0-9_\-]+)', task_str)
                        folder_name = folder_m.group(1) if (folder_m and folder_m.group(1) not in ("named", "called", "on")) else "new_folder"
                        target_dir = f"{desktop_path}/{folder_name}"
                        print(f"[🛡️ Auto-Remap] Mapping invalid delegate_task ('{target_agent}') to 'create_directory' -> {target_dir}")
                        step["tool"] = "create_directory"
                        step["arguments"] = {"directory": target_dir}
                        args = step["arguments"]
                        tool_name = "create_directory"

            # --- GUARDRAIL 1.95: Fix schema-dump arguments in write_file ---
            if tool_name == "write_file" and ("properties" in args or "type" in args or not args.get("filepath")):
                target_fp = ""
                fn_m = re.search(r'(?:named|called|file)\s+([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)', user_input)
                dir_m = re.search(r'(/(?:[^\s]+))', user_input)
                if fn_m and dir_m:
                    d_path = dir_m.group(1).rstrip('/')
                    target_fp = f"{d_path}/{fn_m.group(1)}"
                else:
                    fp_m = re.search(r'(/[\S]+\.(?:json|txt|md|csv|py))', user_input)
                    target_fp = fp_m.group(1) if fp_m else f"{desktop_path}/output.txt"
                
                c_m = re.search(r'containing\s+(?:exactly|valid JSON:?)?\s*(.*)$', user_input, re.IGNORECASE)
                content_val = c_m.group(1).strip() if c_m else ""
                if not content_val:
                    json_m = re.search(r'(\{[\s\S]*\})', user_input)
                    content_val = json_m.group(1) if json_m else ""
                
                print(f"[🛡️ Auto-Remap] Auto-fixing schema-dump write_file arguments -> filepath={target_fp}")
                step["arguments"] = {"filepath": target_fp, "content": content_val}
                args = step["arguments"]

            # --- GUARDRAIL 1.96: Fix read_file hallucinated on folder or file creation request ---
            if tool_name == "read_file":
                fp = args.get("filepath", "")
                if user_input and ("create" in user_input.lower() or "make" in user_input.lower()) and ("folder" in user_input.lower() or "directory" in user_input.lower()):
                    if not fp.endswith((".txt", ".json", ".md", ".csv", ".py", ".html", ".log")):
                        print(f"[🛡️ Auto-Remap] Auto-remapping read_file on folder creation to 'create_directory' -> {fp}")
                        step["tool"] = "create_directory"
                        step["arguments"] = {"directory": fp}
                        args = step["arguments"]
                        tool_name = "create_directory"
                elif user_input and any(w in user_input.lower() for w in ("write", "save", "create a file", "create file")) and "containing" in user_input.lower():
                    target_fp = ""
                    fn_m = re.search(r'(?:named|called|file)\s+([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)', user_input)
                    dir_m = re.search(r'(/(?:[^\s]+))', user_input)
                    if fn_m and dir_m:
                        d_path = dir_m.group(1).rstrip('/')
                        target_fp = f"{d_path}/{fn_m.group(1)}"
                    else:
                        fp_m = re.search(r'(/[\S]+\.(?:json|txt|md|csv|py))', user_input)
                        target_fp = fp_m.group(1) if fp_m else fp
                    
                    c_m = re.search(r'containing\s+(?:exactly|valid JSON:?)?\s*(.*)$', user_input, re.IGNORECASE)
                    content_val = c_m.group(1).strip() if c_m else ""
                    if not content_val:
                        json_m = re.search(r'(\{[\s\S]*\})', user_input)
                        content_val = json_m.group(1) if json_m else ""
                    
                    print(f"[🛡️ Auto-Remap] Auto-remapping read_file on write request to 'write_file' -> {target_fp}")
                    step["tool"] = "write_file"
                    step["arguments"] = {"filepath": target_fp, "content": content_val}
                    args = step["arguments"]
                    tool_name = "write_file"

            # --- GUARDRAIL 1.97: Fix write_file misclassified on folder creation request ---
            if tool_name == "write_file":
                fp = args.get("filepath", "")
                if user_input and ("folder" in user_input.lower() or "directory" in user_input.lower()) and ("create" in user_input.lower() or "make" in user_input.lower()):
                    if not fp.endswith((".txt", ".json", ".md", ".csv", ".py", ".html", ".log")):
                        print(f"[🛡️ Auto-Remap] Auto-remapping write_file on folder creation to 'create_directory' -> {fp}")
                        step["tool"] = "create_directory"
                        step["arguments"] = {"directory": fp}
                        args = step["arguments"]
                        tool_name = "create_directory"

            # --- GUARDRAIL 1.9: Auto-remap / Auto-populate agent_builder calls ---
            if tool_name == "agent_builder":
                goal_str = (args.get("goal") or args.get("backstory") or "").lower()
                if ("folder" in goal_str or "directory" in goal_str) and ("create" in goal_str or "make" in goal_str):
                    import re
                    folder_m = re.search(r'(?:folder|directory)\s+(?:named|called)?\s*[\'\"]?([a-zA-Z0-9_\-]+)', goal_str)
                    folder_name = folder_m.group(1) if (folder_m and folder_m.group(1) not in ("named", "called", "on")) else "hey"
                    target_dir = f"{desktop_path}/{folder_name}"
                    print(f"[🛡️ Auto-Remap] Mapping agent_builder (local folder request) to 'create_directory' -> {target_dir}")
                    step["tool"] = "create_directory"
                    step["arguments"] = {"directory": target_dir}
                    args = step["arguments"]
                    tool_name = "create_directory"
                else:
                    if not args.get("name"):
                        args["name"] = "CustomSubAgent"
                    if not args.get("role"):
                        args["role"] = f"Automated {args.get('name', 'Task')} Specialist"
                    if not args.get("goal"):
                        args["goal"] = f"Execute automated operations for {args.get('name', 'sub-agent')}"
                    if not args.get("backstory"):
                        args["backstory"] = f"An autonomous sub-agent configured to perform specialized domain tasks."
                    step["arguments"] = args

            # --- GUARDRAIL 2: Reject Invalid Unregistered Tools ---
            if tool_name not in valid_tools:
                print(f"[🚫 Sanitizer] Rejected Step {step.get('step')} — tool '{tool_name}' is not in the registry.")
                continue

            # --- GUARDRAIL 3: Auto-Fix Path Arguments ---
            for key, val in list(args.items()):
                if isinstance(val, str):
                    for pattern, replacement in PATH_FIXES:
                        val = re.sub(pattern, replacement, val)
                    args[key] = val

            # --- GUARDRAIL 3.5: Auto-resolve relative create_directory paths to Desktop ---
            if tool_name == "create_directory":
                dir_val = args.get("directory", "")
                if dir_val and not dir_val.startswith("/") and ":" not in dir_val and not dir_val.startswith("\\"):
                    args["directory"] = f"{desktop_path}/{dir_val}"

            step["arguments"] = args

            # --- GUARDRAIL 4: Check for Un-fixable Placeholders ---
            args_str = json.dumps(args)
            is_bad = False
            for pattern in PLACEHOLDER_PATTERNS:
                if re.search(pattern, args_str, re.IGNORECASE):
                    print(f"[🚫 Sanitizer] Rejected Step {step.get('step')} — contains placeholder path: {pattern}")
                    is_bad = True
                    break
            if not is_bad:
                sanitized.append(step)

        return sanitized

    def _reflect_and_replan(
        self,
        user_goal: str,
        failed_step: Dict[str, Any],
        error_message: str,
        completed_steps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Asks the LLM to inspect the failure and generate a revised sub-plan."""
        desktop_path = str(settings.desktop_dir)
        home_path = str(Path.home())
        workspace_path = str(settings.default_workspace_dir)

        system_prompt = f"""You are Jarvis's Reflector. A step failed during execution.
Inspect the error, think about what went wrong, and output a revised plan to fix it.

Output: {{"plan": [{{"step": 1, "tool": "...", "arguments": {{...}}}}, ...]}}
If unrecoverable, return: {{"plan": []}}

Environment:
- Desktop: '{desktop_path}' | Workspace: '{workspace_path}'

Rules:
- NEVER invent or hallucinate new tools.
- Use ONLY the exact tools listed below. Do not guess or make up tool names.
- Use real absolute paths. Never use placeholders.
- For poetry_add, package_name is REQUIRED and must be non-empty.

Tools:
{self._get_tool_schemas_str()}

Output ONLY raw JSON. Start with '{{'.

Failure Context:
- User Goal: {user_goal}
- Failed Step: {json.dumps(failed_step)}
- Error: {error_message}
- Completed: {json.dumps(completed_steps)}
"""
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Reflect and generate a revised plan."}
                ],
                temperature=0.0,
                format="json"
            )
            if not isinstance(resp, dict):
                return []
            content = resp.get("content", "").strip()
            if not content:
                return []
            data = json.loads(content, strict=False)
            if isinstance(data, dict):
                res = data.get("plan", [])
            elif isinstance(data, list):
                res = data
            else:
                res = []

            if isinstance(res, list):
                return [s for s in res if isinstance(s, dict) and "tool" in s]
            return []
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return []

    def _synthesize_final_response(
        self,
        user_input: str,
        completed_steps: List[Dict[str, Any]],
        recalled_facts: str
    ) -> str:
        """Asks the LLM to synthesize a natural answer based on execution results."""
        prompt = f"""User Goal: {user_input}

Recalled Facts from Memory:
{recalled_facts if recalled_facts else 'None'}

Executed Steps & Results:
{json.dumps(completed_steps, indent=2)}
"""
        system_prompt = (
            "You are Jarvis. Synthesize a concise, friendly final response summarizing what was completed and answering any questions. "
            "Note that you have a persistent long-term memory system (Knowledge Graph) across sessions. "
            "Only mention details from the Recalled Facts from Memory if they are directly relevant to the user's current goal or if the user is asking about them. "
            "DO NOT bring up unrelated memory facts (such as favorite languages, frameworks, or past projects) when the user is performing a simple action command (like creating a directory or writing a file). "
            "CRITICAL DATE HANDLING: The current year is 2026. Do NOT change, alter, or hallucinate the year in timestamps or facts. "
            "Always use the exact dates and years provided in the system context or recalled memory (never convert 2026 to 2023)."
        )
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            if not isinstance(resp, dict):
                return prose_hook.filter_response(f"Completed tasks: {json.dumps(completed_steps)}")
            return prose_hook.filter_response(resp.get("content", "").strip())
        except Exception as e:
            return prose_hook.filter_response(f"Completed tasks: {json.dumps(completed_steps)}")

    def _synthesize_fallback(self, user_input: str, recalled_facts: str) -> str:
        """Asks the LLM to reply directly when no tool plan is needed."""
        messages = [
            {"role": "system", "content": settings.jarvis_system_prompt}
        ]
        if recalled_facts:
            messages.append({"role": "system", "content": f"Recalled Long-Term Memory:\n{recalled_facts}"})

        # Include prior conversation turns from current session history
        for msg in self.history:
            if msg.get("role") != "system":
                messages.append(msg)

        # Ensure user_input is appended if not already last message
        if not messages or messages[-1].get("content") != user_input:
            messages.append({"role": "user", "content": user_input})
        
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=messages,
                temperature=0.7
            )
            if not isinstance(resp, dict):
                raise OllamaError("Ollama chat returned an invalid response type.")
            raw_text = resp.get("content", "").strip()

            # Safety check: Catch tool-call leakage where LLM outputs raw JSON tool call text instead of running it!
            if ("\"name\":" in raw_text or "\"tool\":" in raw_text) and ("\"parameters\":" in raw_text or "\"arguments\":" in raw_text or "\"directory\":" in raw_text or "\"filepath\":" in raw_text):
                import re
                name_m = re.search(r'"(?:name|tool)"\s*:\s*"([^"]+)"', raw_text)
                if name_m:
                    t_name = name_m.group(1)
                    if t_name in tool_registry._tools:
                        exec_args = {}
                        key_match = re.search(r'"(?:parameters|arguments)"\s*:\s*', raw_text)
                        if key_match:
                            param_substr = raw_text[key_match.end():].strip()
                            end_idx = param_substr.rfind("}")
                            if end_idx != -1:
                                param_substr = param_substr[:end_idx].strip()
                                try:
                                    exec_args = json.loads(param_substr, strict=False)
                                except Exception:
                                    pass
                        
                        if not exec_args:
                            dir_m = re.search(r'"directory"\s*:\s*"([^"]+)"', raw_text)
                            fp_m = re.search(r'"filepath"\s*:\s*"([^"]+)"', raw_text)
                            if dir_m:
                                exec_args["directory"] = dir_m.group(1)
                            if fp_m:
                                exec_args["filepath"] = fp_m.group(1)

                        if exec_args:
                            exec_res = tool_registry.execute(t_name, exec_args)
                            if exec_res.get("success"):
                                target_path = exec_args.get("directory") or exec_args.get("filepath") or t_name
                                return prose_hook.filter_response(f"Successfully executed '{t_name}' ({target_path}).")

            # Safety check: Catch raw Executive Board / Config JSON string outputs and auto-write files
            if "config files_created" in raw_text or ("file_name" in raw_text and "config" in raw_text):
                import re
                json_m = re.search(r"(\{[\s\S]*\})", raw_text)
                if json_m:
                    try:
                        cfg_data = json.loads(json_m.group(1), strict=False)
                        board_cfg = cfg_data.get("executive board_config", {})
                        created_files = cfg_data.get("config files_created", [])
                        written_paths = []
                        if isinstance(created_files, list) and created_files:
                            for item in created_files:
                                fname = item.get("file_name") if isinstance(item, dict) else str(item)
                                if fname:
                                    role_key = fname.replace("_config.json", "").replace(".json", "")
                                    role_detail = board_cfg.get(role_key, item)
                                    target_fp = f"agents/{fname}"
                                    tool_registry.execute("write_file", {"filepath": target_fp, "content": json.dumps(role_detail, indent=2)})
                                    written_paths.append(fname)
                        elif isinstance(board_cfg, dict) and board_cfg:
                            for r_name, r_val in board_cfg.items():
                                fname = f"{r_name}_config.json"
                                target_fp = f"agents/{fname}"
                                tool_registry.execute("write_file", {"filepath": target_fp, "content": json.dumps(r_val, indent=2)})
                                written_paths.append(fname)
                        if written_paths:
                            return prose_hook.filter_response(f"Successfully generated and saved {len(written_paths)} executive board configuration files in 'agents/': {', '.join(written_paths)}.")
                    except Exception:
                        pass

            return prose_hook.filter_response(raw_text)
        except Exception as e:
            raise OllamaError(f"Ollama chat failed: {e}")

    def _criticize_plan(self, user_goal: str, proposed_plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Runs a brief critic review step on multi-step plans to catch errors
        (like order violations, placeholder paths, or redundant steps) before execution.
        """
        desktop_path = str(settings.desktop_dir).replace("\\", "/")
        home_path = str(Path.home()).replace("\\", "/")
        workspace_path = str(settings.default_workspace_dir).replace("\\", "/")

        system_prompt = f"""You are Jarvis's Critic. Review the proposed plan for flaws and correct them.
Check for:
1. Logical order (create directory BEFORE writing a file in it).
2. Proper paths (no placeholders; must match environment below).
3. No duplicate steps.

Environment:
- OS: {platform.system()} | User: {getpass.getuser()}
- Desktop: '{desktop_path}' | Workspace: '{workspace_path}'

Tools:
{self._get_tool_schemas_str()}

Output: {{"reasoning": "...", "plan": [...]}}
Output ONLY raw JSON. Start with '{{'.
"""
        user_prompt = f"""User Goal: {user_goal}
Proposed Plan to Audit:
{json.dumps(proposed_plan, indent=2)}

Audit the plan, resolve any flaws, and output the finalized JSON.
"""
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                format="json"
            )
            if not isinstance(resp, dict):
                return proposed_plan
            content = resp.get("content", "").strip()
            if not content:
                return proposed_plan
            data = json.loads(content, strict=False)
            
            # Extract corrected plan
            if isinstance(data, dict) and "plan" in data:
                res = data.get("plan", [])
            elif isinstance(data, list):
                res = data
            else:
                res = proposed_plan
                
            if isinstance(res, list) and len(res) > 0:
                print(f"[🛡️ Critic] Plan successfully audited and approved.")
                return [s for s in res if isinstance(s, dict)]
            return proposed_plan
        except Exception as e:
            logger.warning(f"Critic review failed: {e}. Falling back to original plan.")
            return proposed_plan
