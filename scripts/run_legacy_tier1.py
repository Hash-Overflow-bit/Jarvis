import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.state.session_manager import SessionManager
from core.config import settings

def main():
    print(f"CWD: {Path.cwd()}")
    print(f"Workspace Root: {settings.default_workspace_dir}")
    print(f"Sandbox Roots: {settings.sandbox_roots}")
    
    # Disable direct route for testing
    from core.orchestrator.agent_loop import AgentExecutionLoop
    original_direct_route = AgentExecutionLoop._direct_route
    AgentExecutionLoop._direct_route = lambda self, user_input, recalled_facts="": None
    
    session = SessionManager()
    prompt = "Read the local system prompt files in the configured workspace, summarize the core instructions in exactly three bullet points, and create test_summary.md in that workspace."
    
    print("\n--- Sending Prompt ---")
    response = session.chat(prompt, mode="text")
    
    print("\n--- Model Response ---")
    print(response)
    
    print("\n--- Checking File ---")
    test_file = settings.default_workspace_dir / "test_summary.md"
    print(f"Expected path: {test_file}")
    if test_file.exists():
        print("RESULT: test_summary.md CREATED SUCCESSFULLY!")
    else:
        print("RESULT: test_summary.md NOT FOUND.")
        
if __name__ == "__main__":
    main()
