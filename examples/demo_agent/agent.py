import argparse
import os

from fastapi import FastAPI
from pydantic import BaseModel

from examples.demo_agent.core import run_agent_logic

app = FastAPI(title="traceval Demo Agent")

# Config state
BUGGY_MODE = os.environ.get("BUGGY", "false").lower() == "true"


class AgentInput(BaseModel):
    input: str


class AgentOutput(BaseModel):
    output: str
    tool_calls: list[dict]


@app.post("/agent", response_model=AgentOutput)
async def run_agent(data: AgentInput):
    res = run_agent_logic(data.input, buggy=BUGGY_MODE)
    return AgentOutput(output=res["output"], tool_calls=res["tool_calls"])


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--buggy", action="store_true", help="Run in buggy regression mode"
    )
    parser.add_argument("--port", type=int, default=8000, help="Port to run on")
    args = parser.parse_args()

    if args.buggy:
        BUGGY_MODE = True
        print("⚠️ Running in BUGGY REGRESSION mode")
    else:
        print("✅ Running in HEALTHY normal mode")

    uvicorn.run(app, host="127.0.0.1", port=args.port)
