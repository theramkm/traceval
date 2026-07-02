"""Thin wrapper: the trace generator now ships inside the package
(traceval.demo.traces) so `traceval demo` works from a plain pip install.
"""

from pathlib import Path

from traceval.demo.traces import generate_traces_file

if __name__ == "__main__":
    out = Path(__file__).parent / "synthetic_traces.jsonl"
    generate_traces_file(out)
