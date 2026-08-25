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
    "clone this repo https://github.com/Hash-Overflow-bit/trackfun.git"
)
print("--- RESPONSE ---")
print(response)
print("----------------")
