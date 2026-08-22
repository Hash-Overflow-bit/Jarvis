import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.state.session_manager import SessionManager

def run_tests():
    session = SessionManager()
    
    prompts = [
        "Jarvis, I need you to analyze my local workspace structure, identify any markdown files created this week, summarize their key points into a single consolidated report, and save that report as a new file in my working directory. Walk me through your step-by-step plan before executing.",
        "Run a quick system check on our local SQLite knowledge graph. Count how many records are currently stored in the primary table and return the exact schema structure.",
        "Draft a brief Python script that parses a CSV file and handles missing rows. Before you finish, review your own code for potential edge cases (like type errors or division by zero), rewrite it to fix any flaws you find, and explain what you corrected.",
        "Remember that Python script we just talked about? Modify it so that it exports the results directly into a structured JSON format instead of printing to the console, and verify that it matches our workspace standards."
    ]
    
    report = "# Jarvis Live Execution Report (LLaMA 3.1 8B)\n\n"
    
    for i, prompt in enumerate(prompts):
        print(f"Running Test {i+1}...")
        report += f"## Test {i+1}\n**Prompt:** {prompt}\n\n**Jarvis Output:**\n"
        try:
            response = session.chat(prompt, mode="text")
            report += f"{response}\n\n"
        except Exception as e:
            report += f"**ERROR:** {e}\n\n"
            
    # Save to the root workspace
    output_path = Path(__file__).parent.parent / "test_execution_report.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"Done! Report saved to {output_path}")

if __name__ == "__main__":
    run_tests()
