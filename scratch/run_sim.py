from core.orchestrator.agent_loop import AgentExecutionLoop

prompt1 = "Create A on Desktop. Inside it create B. Inside B create test.txt containing hello. Read it back and verify its exact path and content."
prompt2 = "Generate a short project status report with Summary, Progress, Risks, and Next Steps"

loop = AgentExecutionLoop(use_tools=True)

print("=== PROMPT 1 ===")
print("Prompt:", prompt1)
plan1 = loop._direct_route(prompt1)
print("Plan:", plan1)
res1 = loop.run(prompt1)
print("Final Response:\n" + res1)

print("\n=== PROMPT 2 ===")
print("Prompt:", prompt2)
plan2 = loop._direct_route(prompt2)
print("Plan:", plan2)
res2 = loop.run(prompt2)
print("Final Response:\n" + res2)
