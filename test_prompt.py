import asyncio
from core.orchestrator.agent_loop import AgentExecutionLoop

loop = AgentExecutionLoop()
prompt = "Prepare a comprehensive, sourced analysis of how artificial intelligence is transforming supply-chain operations. The document should be no shorter than 2,000 words and should be saved to my Desktop as ai_supply_chain_report.txt"
print("Running prompt...")
loop._run_traced(prompt)
