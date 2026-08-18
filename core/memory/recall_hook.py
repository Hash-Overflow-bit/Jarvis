"""
core/memory/recall_hook.py
==========================
Standalone UserPromptSubmit hook interface for JSON-based pipeline injection.
"""

import json
import sys
from pathlib import Path

# Add project root and core/ to python path to resolve imports when executed standalone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.memory.recall import recall


def main():
    try:
        # Load user prompt from stdin
        input_data = json.load(sys.stdin)
        prompt = input_data.get("prompt", "").strip()
        
        if not prompt:
            # Fallback for empty prompts
            print(json.dumps({
                "systemMessage": "[🧠 Memory] No search query provided.",
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": ""
                }
            }))
            return

        # Run the recursive traversal
        result = recall(prompt, hops=3, top_k=8)
        text = result.as_text()
        
        # Output standard JSON structure for hooks
        print(json.dumps({
            "systemMessage": text.split("\n")[0],
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": text
            }
        }))

    except Exception as e:
        # Graceful fallback: return empty memory context on error
        print(json.dumps({
            "systemMessage": f"[🧠 Memory] Error in hook execution: {e}",
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": ""
            }
        }))


if __name__ == "__main__":
    main()
