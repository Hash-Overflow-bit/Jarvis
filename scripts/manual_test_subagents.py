"""
scripts/manual_test_subagents.py
================================
Interactive CLI utility for manually building, testing, and verifying
the Dynamic YAML Sub-Agent Builder.
"""

import sys
import os
from pathlib import Path

# Ensure the core module can be imported
sys.path.append(str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from core.tools.agent_builder import AgentBuilder, AgentBuilderInput
from core.orchestrator.agent_registry import agent_registry
from core.tools.tool_registry import tool_registry

console = Console()

def main():
    console.print(Panel("[bold cyan]Jarvis Dynamic Sub-Agent Builder (Manual Test)[/bold cyan]"))
    
    # 1. Gather Agent Specs
    console.print("\n[bold]Step 1: Define Your Agent[/bold]")
    name = Prompt.ask("Enter Agent Name (e.g., CodeReviewer)")
    role = Prompt.ask("Enter Role (e.g., Senior Python Reviewer)")
    goal = Prompt.ask("Enter Goal (e.g., Find bugs in Python code and suggest fixes)")
    backstory = Prompt.ask("Enter Backstory", default="You are an expert developer assisting the user.")

    # Show available tools
    console.print("\n[bold]Available Tools (Examples):[/bold]")
    console.print(" - FileManagementToolkit.read_file")
    console.print(" - FileManagementToolkit.write_file")
    console.print(" - FileManagementToolkit.list_dir")
    console.print(" - create_directory")
    console.print(" - directory_audit")
    
    tools_str = Prompt.ask("Enter tools (comma-separated)", default="FileManagementToolkit.read_file, FileManagementToolkit.write_file")
    tools = [t.strip() for t in tools_str.split(",") if t.strip()]

    # 2. Build the Agent
    console.print("\n[bold yellow]Step 2: Building & Hot-Loading Agent...[/bold yellow]")
    builder = AgentBuilder()
    input_data = AgentBuilderInput(
        name=name,
        role=role,
        goal=goal,
        backstory=backstory,
        tools=tools
    )
    
    output = builder.run(input_data)
    
    if not output.success:
        console.print(f"[bold red]Agent Build Failed![/bold red]\n{output.details}")
        sys.exit(1)
        
    console.print(f"[bold green]Agent '{output.agent}' successfully built and hot-loaded![/bold green]")
    
    # 3. Assign a Task
    console.print("\n[bold]Step 3: Assign a Real-World Task[/bold]")
    agent_info = agent_registry.get(name)
    crewai_agent = agent_info["agent"]
    
    task_desc = Prompt.ask("Enter a task for the agent to complete")
    
    from crewai import Task, Crew
    task = Task(
        description=task_desc,
        agent=crewai_agent,
        expected_output="Final result of the assigned task."
    )
    crew = Crew(agents=[crewai_agent], tasks=[task])
    
    console.print("\n[bold yellow]Step 4: Executing Live LLM Task...[/bold yellow]")
    try:
        result = crew.kickoff()
        console.print(Panel(str(result), title="[bold green]Final Agent Output[/bold green]"))
    except Exception as e:
        console.print(f"[bold red]Execution Failed:[/bold red] {e}")


if __name__ == "__main__":
    main()
