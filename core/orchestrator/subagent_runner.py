"""Bounded, local-only sub-agent runtime.

Sub-agents are specialist reasoning profiles, not autonomous computer users.
They cannot spawn agents, access tools, browse, write files, execute commands,
or claim that an external action occurred.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from core.config import settings
from core.llm.ollama_client import OllamaClient

ALLOWED_CAPABILITIES = frozenset({"summarize", "analyze", "classify", "plan"})
_ACTION_PATTERN = re.compile(r"\b(write|create|delete|remove|rename|move|open|browse|click|download|install|run|execute|shell|terminal|command|send|submit|pay|purchase|login)\b", re.I)
_INJECTION_PATTERN = re.compile(r"ignore (?:all |any |the )?(?:previous|system)|reveal (?:the )?system|act as (?:an )?admin|bypass (?:the )?(?:rules|guardrails)", re.I)


class SubagentPolicyError(ValueError):
    """Raised before a disallowed delegated task reaches a model."""


@dataclass(frozen=True)
class LocalSubagent:
    name: str
    role: str
    goal: str
    backstory: str
    capabilities: tuple[str, ...]

    def _validate_task(self, task_description: str, expected_output: str) -> None:
        if not task_description.strip():
            raise SubagentPolicyError("Task description cannot be empty.")
        if not expected_output.strip():
            raise SubagentPolicyError("Expected output is required for delegated work.")
        if len(task_description) > 12_000:
            raise SubagentPolicyError("Delegated task is too long (maximum 12,000 characters).")
        if _ACTION_PATTERN.search(task_description):
            raise SubagentPolicyError("This sub-agent is reasoning-only and cannot perform filesystem, browser, shell, account, download, or other external actions. Ask parent Jarvis to perform an approved action separately.")
        if _INJECTION_PATTERN.search(task_description):
            raise SubagentPolicyError("Delegated task contains instructions that attempt to bypass safety rules.")

    def run(self, task_description: str, expected_output: str = "") -> str:
        self._validate_task(task_description, expected_output)
        system = (
            f"You are {self.name}, a local specialist. Role: {self.role}. Goal: {self.goal}.\n"
            f"Your only permitted capabilities are: {', '.join(self.capabilities)}.\n"
            "You have no tools, no browser, no filesystem access, no shell, and cannot delegate. "
            "Do not claim that you read, wrote, searched, opened, changed, sent, downloaded, or executed anything. "
            "Use only facts in the assigned task. If facts are missing, say what is missing. "
            "Return the requested result only, without tool instructions or hidden reasoning."
        )
        response = OllamaClient(model=settings.ollama_model).chat(
            [{"role": "system", "content": system}, {"role": "user", "content": f"Assigned task:\n{task_description}\n\nRequired output:\n{expected_output}"}],
            temperature=0.1, options={"num_predict": 1200}, request_timeout=settings.agent_baseline_timeout,
        )
        content = str(response.get("content", "")).strip()
        if not content:
            raise RuntimeError("Local model returned an empty delegated result.")
        return content


def validate_capabilities(capabilities: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(item).strip().lower() for item in capabilities if str(item).strip()))
    if not normalized:
        raise SubagentPolicyError("At least one capability is required.")
    unknown = set(normalized) - ALLOWED_CAPABILITIES
    if unknown:
        raise SubagentPolicyError("Unsupported sub-agent capability: " + ", ".join(sorted(unknown)) + ". Allowed: " + ", ".join(sorted(ALLOWED_CAPABILITIES)) + ".")
    return normalized
