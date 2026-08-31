from core.orchestrator.agent_loop import AgentExecutionLoop
loop = AgentExecutionLoop()
prompt = "research PSX 2020-2026, top 10 high-performance stocks, top companies, trend after COVID"
plan = loop._direct_route(prompt)
print(f"Plan: {plan}")
