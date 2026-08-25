import logging
import sys
from pathlib import Path

# Setup logging to console to see plan generation details
logging.basicConfig(level=logging.INFO)

# Add project root to python path
sys.path.append(str(Path(__file__).parent.parent))

from core.orchestrator.agent_loop import AgentExecutionLoop
from core.config import settings

print("Using model:", settings.ollama_model)

loop = AgentExecutionLoop()
# Enable debug prints to stdout
import builtins
response = loop.run(
    "Jarvis, locate and read the transactions.csv file on my desktop, calculate the total revenue, total expenses, and net profit/loss, and then write a clean summary report named financial_report.md inside the content_test folder on my desktop."
)
print("--- RESPONSE ---")
print(response)
print("----------------")
