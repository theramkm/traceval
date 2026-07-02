"""Built-in demo: a mock customer-service agent (healthy and buggy modes)
and a deterministic synthetic-trace generator. Ships in the wheel so
`traceval demo` works from a plain pip install, no repo clone needed.
"""

from traceval.demo.agent import invoke_agent, run_agent_logic
from traceval.demo.traces import generate_traces_file

__all__ = ["generate_traces_file", "invoke_agent", "run_agent_logic"]
