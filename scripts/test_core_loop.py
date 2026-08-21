import os
import yaml
from pathlib import Path
from core.orchestrator.hot_loader import hot_loader
from core.config import settings

def run_diagnostic():
    print("--- Starting Core Loop Diagnostic ---")
    
    # 1. Setup Dummy Sandbox Data
    sandbox_dir = settings.default_workspace_dir
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    input_file = sandbox_dir / "loop_test_input.txt"
    output_file = sandbox_dir / "loop_test_output.txt"
    
    # Clean up any previous runs
    if output_file.exists():
        output_file.unlink()
        
    # Write the source file for the LLM to read
    input_text = "jarvis core loop is working perfectly"
    with open(input_file, "w") as f:
        f.write(input_text)
    print(f"Created input file at: {input_file}")

    # 2. Create Temporary Blueprint for HotLoader
    blueprint_path = sandbox_dir / "temp_blueprint.yaml"
    blueprint_data = {
        "custom_sub_agents": [
            {
                "name": "diagnostic_agent",
                "role": "Data Transformer",
                "goal": "Read a file, transform its contents, and write a new file.",
                "backstory": "You are a precise data transformer. You follow instructions exactly.",
                "tools": ["FileManagementToolkit.read_file", "FileManagementToolkit.write_file"]
            }
        ]
    }
    with open(blueprint_path, "w") as f:
        yaml.dump(blueprint_data, f)
    
    print("\nLoading diagnostic_agent via HotLoader...")
    agent = hot_loader.load(blueprint_path, "diagnostic_agent")
    
    from crewai import Task, Crew
    
    # 4. Execute Task (The true test of the Core Loop)
    task_description = (
        f"Read the file '{input_file.name}'. Take the exact text from that file, "
        f"convert all of the text to UPPERCASE, and then use your write_file tool "
        f"to save the uppercase text to a new file named '{output_file.name}'."
    )
    
    task = Task(
        description=task_description,
        agent=agent,
        expected_output="A confirmation message that the file was written."
    )
    
    crew = Crew(agents=[agent], tasks=[task])
    
    print("\nAssigning Task:")
    print(task_description)
    print("\n--- Executing LLM ---")
    
    # CrewAI Agent direct execution
    result = crew.kickoff()
    
    print("\n--- Execution Complete ---")
    print(f"LLM Final Output: {result}")
    
    # 5. Validation
    if output_file.exists():
        with open(output_file, "r") as f:
            final_text = f.read().strip()
        print(f"\n[VALIDATION] Output file found!")
        print(f"[VALIDATION] Contents: '{final_text}'")
        
        if final_text == input_text.upper():
            print("\n✅ SUCCESS: Core loop did not drop context. ReAct loop is stable.")
        else:
            print("\n❌ FAILED: File was created but contents were wrong. Hallucination/Context loss occurred.")
    else:
        print(f"\n❌ FAILED: Output file was never created at {output_file}. LLM failed to use the write tool.")

    # Cleanup temp blueprint
    if blueprint_path.exists():
        blueprint_path.unlink()

if __name__ == "__main__":
    run_diagnostic()
