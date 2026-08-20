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

        print(f"\n[📋 Plan] Decomposed into {len(plan)} steps:")
        for step in plan:
            print(f"  - Step {step.get('step')}: {step.get('tool')} with args: {step.get('arguments')}")

        # 3. Execution Loop
        completed_steps = []
        step_idx = 0

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
            else:
                error_msg = result.get("error") or result.get("result", {}).get("message") or "Unknown error"
                print(f"[❌ Failure] Step {step.get('step')} failed: {error_msg}")

                
                # Reflection & Self-Correction
                revised_plan = self._reflect_and_replan(
                    user_goal=user_input,
                    failed_step=step,
                    error_message=error_msg,
                    completed_steps=completed_steps
                )
                
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
        Determines if the user input is purely conversational, a greeting, 
        a memory check, or a statement of fact/preference (which does not 
        require any tools to be executed).
        """
        import re
        cleaned = user_input.lower().strip().rstrip(".!?")
        
        # 1. Simple greetings
        greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "yo", "jarvis", "hello jarvis", "hi jarvis", "are you online", "are you there", "goodbye", "exit"}
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
                
        # 3. Statements of personal facts or preferences (introductions, name declarations, preferred framework/tools)
        statements = [
            r"^(now\s*,\s*)?my name is\s+\w+",
            r"^i (prefer|like|use)\s+\w+",
            r"^my favorite\s+\w+\s+is\s+\w+",
            r"^i want to test your\s+\w+"
        ]
        for pattern in statements:
            if re.search(pattern, cleaned):
                return True
                
        return False

    def _generate_plan(self, user_input: str, recalled_facts: str) -> List[Dict[str, Any]]:
        """Asks Qwen/LLM to generate a serialized list of tool calls."""
        if not self.use_tools:
            return []

        if self._is_conversational_or_informative(user_input):
            return []

        prompt = f"""User Goal: {user_input}

Recalled Facts from Memory:
{recalled_facts if recalled_facts else 'None'}
"""
        
        desktop_path = str(settings.desktop_dir)
        home_path = str(Path.home())
        workspace_path = str(settings.default_workspace_dir)

        system_prompt = f"""You are the Planner Agent for Jarvis.
Your task is to break down a user's request into a series of serialized steps using the available tools.
You must output a JSON object containing a "plan" key, which is a list of steps.
If the user's request is purely conversational or doesn't require tools, return an empty plan: {{"plan": []}}

System Environment Context:
- Operating System: {platform.system()}
- Current OS User: {getpass.getuser()}
- User Home Directory: '{home_path}'
- User Desktop Directory: '{desktop_path}'
- Default Workspace Directory: '{workspace_path}'

CRITICAL PATH & TOOL INSTRUCTIONS:
- Always use real, fully qualified absolute paths matching the system environment context above.
- When the user asks for 'desktop', map it to '{desktop_path}'.
- NEVER use placeholder strings like 'your_username', '/path/to/...', or '<username>', or invent fake user home directories like '/home/username/'.
- CRITICAL CONVERSATIONAL RULE: When the user is stating personal facts, introductions, or preferences (e.g., "My name is Hashir", "I use ReactJS"), or asking general questions, DO NOT generate any tool calls! Return an empty plan: {{"plan": []}}. ONLY generate tool steps when the user gives an explicit command to execute an action (e.g., "Create a file", "Scan folder", "Write a document").
- DO NOT invoke 'rebuild_knowledge_graph' when answering questions. Memory facts are provided automatically.
- For 'poetry_add', 'package_name' is REQUIRED and MUST be a non-empty package name (e.g. 'requests', 'fastapi'). NEVER pass an empty package_name string or omit it.
- DO NOT run 'poetry_add' or 'poetry_install' on a directory unless 'pyproject.toml' or 'requirements.txt' exists in that folder.

Each step in the plan must have:
- "step": integer index (starting from 1)
- "tool": name of the tool to execute
- "arguments": parameter dictionary for the tool

Available tools and their schemas:
{self._get_tool_schemas_str()}

Format requirement:
Output ONLY a raw JSON object. Do not wrap in markdown code blocks. Do not add any introductory text or explanation. Start your response directly with the open curly brace '{{'.
"""

        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                format="json"
            )
            
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

            data = json.loads(content)
            if "plan" in data:
                return data.get("plan", [])
            elif "name" in data and "parameters" in data:
                return [{
                    "step": 1,
                    "tool": data["name"],
                    "arguments": data["parameters"]
                }]
            return []
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return []

    def _reflect_and_replan(
        self,
        user_goal: str,
        failed_step: Dict[str, Any],
        error_message: str,
        completed_steps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Asks Qwen/LLM to inspect the failure and generate a revised sub-plan."""
        desktop_path = str(settings.desktop_dir)
        home_path = str(Path.home())
        workspace_path = str(settings.default_workspace_dir)

        system_prompt = f"""You are the Reflector Agent for Jarvis.
An error occurred during execution of the plan.
Your task is to inspect the error, reflect on what went wrong, and generate a revised list of steps to correct it and complete the user's goal.
You must output a JSON object containing a "plan" key with the new list of steps.
If the error is unrecoverable, return an empty plan: {{"plan": []}}

System Environment Context:
- Operating System: {platform.system()}
- Current OS User: {getpass.getuser()}
- User Home Directory: '{home_path}'
- User Desktop Directory: '{desktop_path}'
- Default Workspace Directory: '{workspace_path}'

CRITICAL PATH INSTRUCTIONS:
- Always use real, fully qualified absolute paths matching the system environment context above.
- When the user asks for 'desktop', map it to '{desktop_path}'.
- NEVER use placeholder strings like 'your_username', '/path/to/...', or '<username>'.
- For 'poetry_add', 'package_name' is REQUIRED and MUST be a non-empty package name (e.g. 'requests', 'fastapi'). NEVER pass an empty package_name string or omit it.
- DO NOT run 'poetry_add' or 'poetry_install' on a directory unless 'pyproject.toml' or 'requirements.txt' exists in that folder.

Available tools and their schemas:
{self._get_tool_schemas_str()}

Format requirement:
Output ONLY a raw JSON object. Do not wrap in markdown code blocks. Do not add any introductory text or explanation. Start your response directly with the open curly brace '{{'.

Context of failure:
- User Goal: {user_goal}
- Failed Step: {json.dumps(failed_step)}
- Error Message: {error_message}
- Completed Steps: {json.dumps(completed_steps)}
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
            data = json.loads(content)
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
        """Asks Qwen/LLM to synthesize a natural answer based on execution results."""
        prompt = f"""User Goal: {user_input}

Recalled Facts from Memory:
{recalled_facts if recalled_facts else 'None'}

Executed Steps & Results:
{json.dumps(completed_steps, indent=2)}
"""
        system_prompt = (
            "You are Jarvis. Synthesize a concise, friendly final response summarizing what was completed and answering any questions. "
            "Note that you are equipped with a persistent long-term memory system (Knowledge Graph) that persists user facts across sessions. "
            "If you recall the user's name or other details from the Recalled Facts from Memory, confirm you remember them across sessions."
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
                return f"Completed tasks: {json.dumps(completed_steps)}"
            return resp.get("content", "").strip()
        except Exception as e:
            return f"Completed tasks: {json.dumps(completed_steps)}"

    def _synthesize_fallback(self, user_input: str, recalled_facts: str) -> str:
        """Asks Qwen/LLM to reply directly when no tool plan is needed."""
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
            return resp.get("content", "").strip()
        except Exception as e:
            raise OllamaError(f"Ollama chat failed: {e}")
