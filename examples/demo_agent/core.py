"""Thin wrapper: the demo agent now ships inside the package so
`traceval demo` works from a plain pip install. Kept so existing
`--target examples.demo_agent.core:invoke_agent` invocations still work.
"""

from traceval.demo.agent import invoke_agent, run_agent_logic

__all__ = ["invoke_agent", "run_agent_logic"]
