"""
core/orchestrator/agent_loop.py
================================
Core agent execution loop that decomposes user tasks, executes tools,
runs output verification, and self-corrects on failures.
"""

import json
import logging
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
                if recall_res.facts:
                    recalled_facts = recall_res.as_text()
                    print(f"\n[🧠 Memory] Recalled {len(recall_res.facts)} facts in {recall_res.latency_ms:.1f}ms")
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
                
                if revised_plan:
                    print(f"\n[🔄 Re-planning] Self-corrected! Revised remaining steps:")
                    # Replace remaining steps in the plan
                    plan = plan[:step_idx] + revised_plan
                    # Adjust step indices in the revised plan for clean logging
                    for idx, s in enumerate(plan[step_idx:]):
                        s["step"] = step_idx + idx + 1
                    for s in plan[step_idx:]:
                        print(f"  - Step {s.get('step')}: {s.get('tool')} with args: {s.get('arguments')}")
                else:
                    print("[❌ Reflection] Could not self-correct further. Halting execution.")
                    return f"Execution halted at Step {step.get('step')} ({tool_name}) due to: {error_msg}"

        # 5. Final Synthesis
        return self._synthesize_final_response(user_input, completed_steps, recalled_facts)

    def _generate_plan(self, user_input: str, recalled_facts: str) -> List[Dict[str, Any]]:
        """Asks Qwen/LLM to generate a serialized list of tool calls."""
        if not self.use_tools:
            return []

        prompt = f"""User Goal: {user_input}

Recalled Facts from Memory:
{recalled_facts if recalled_facts else 'None'}
"""
        
        system_prompt = f"""You are the Planner Agent for Jarvis.
Your task is to break down a user's request into a series of serialized steps using the available tools.
You must output a JSON object containing a "plan" key, which is a list of steps.
If the user's request is purely conversational or doesn't require tools, return an empty plan: {{"plan": []}}

Each step must have:
- "step": integer index (starting from 1)
- "tool": name of the tool to execute
- "arguments": parameter dictionary for the tool

Available tools and their schemas:
{self._get_tool_schemas_str()}

Ensure simplicity, serial execution, and security. Output ONLY a valid JSON object.
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
        system_prompt = f"""You are the Reflector Agent for Jarvis.
An error occurred during execution of the plan.
Your task is to inspect the error, reflect on what went wrong, and generate a revised list of steps to correct it and complete the user's goal.
You must output a JSON object containing a "plan" key with the new list of steps.
If the error is unrecoverable, return an empty plan: {{"plan": []}}

Original Goal: {user_goal}
Failed Step: {json.dumps(failed_step)}
Error Message: {error_message}
Completed Steps so far: {json.dumps(completed_steps)}

Available tools:
{self._get_tool_schemas_str()}

Generate a revised plan of action. Output ONLY a valid JSON object.
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
            content = resp.get("content", "").strip()
            data = json.loads(content)
            return data.get("plan", [])
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
        system_prompt = "You are Jarvis. Synthesize a concise, friendly final response summarizing what was completed and answering any questions based on the executed step results."
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return resp.get("content", "").strip()
        except Exception as e:
            return f"Completed tasks: {json.dumps(completed_steps)}"

    def _synthesize_fallback(self, user_input: str, recalled_facts: str) -> str:
        """Asks Qwen/LLM to reply directly when no tool plan is needed."""
        messages = [
            {"role": "system", "content": settings.jarvis_system_prompt}
        ]
        if recalled_facts:
            messages.append({"role": "system", "content": recalled_facts})
        messages.append({"role": "user", "content": user_input})
        
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=messages,
                temperature=0.7
            )
            return resp.get("content", "").strip()
        except Exception as e:
            raise OllamaError(f"Ollama chat failed: {e}")
