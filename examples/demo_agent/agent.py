import argparse
import os

from fastapi import FastAPI
from pydantic import BaseModel

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
    input_text = data.input.lower()

    # 1. Buggy regression mode behavior
    if BUGGY_MODE:
        if "order" in input_text:
            return AgentOutput(
                output="I could not find your order.",
                tool_calls=[],  # Skips calling order_lookup tool!
            )
        if "stripe" in input_text or "refund" in input_text:
            return AgentOutput(
                output="Your refund cannot be processed at this time.",
                tool_calls=[],  # Skips calling stripe_lookup!
            )
        return AgentOutput(output="Something went wrong.", tool_calls=[])

    # 2. Healthy normal behavior
    if "order" in input_text:
        # Normal order lookup flow
        order_id = "12345"
        for word in input_text.split():
            if word.isdigit():
                order_id = word
                break
        return AgentOutput(
            output=f"Your order {order_id} is currently in transit.",
            tool_calls=[{"name": "order_lookup"}],
        )

    elif "stripe" in input_text or "refund" in input_text:
        # Normal refund stripe lookup flow
        return AgentOutput(
            output="Refund of $50 has been successfully processed via Stripe.",
            tool_calls=[{"name": "stripe_lookup"}],
        )

    elif "knowledge" in input_text or "search" in input_text:
        # Knowledge base search flow
        return AgentOutput(
            output="Found answer in documentation: update your credentials.",
            tool_calls=[{"name": "kb_search"}],
        )

    # General fallback
    return AgentOutput(
        output="Hello! I can help you with order lookups, refunds, or searches.",
        tool_calls=[],
    )


def invoke_agent(input_text: str) -> dict:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(run_agent(AgentInput(input=input_text)))
        return {"output": res.output, "tool_calls": res.tool_calls}
    finally:
        loop.close()


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
