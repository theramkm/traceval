import os
from typing import Any


def run_agent_logic(input_text: str, buggy: bool = False) -> dict[str, Any]:
    input_text = input_text.lower()

    # 1. Buggy regression mode behavior
    if buggy:
        if "order" in input_text:
            return {
                "output": "I could not find your order.",
                "tool_calls": [],  # Skips calling order_lookup tool!
            }
        if "stripe" in input_text or "refund" in input_text:
            return {
                "output": "Your refund cannot be processed at this time.",
                "tool_calls": [],  # Skips calling stripe_lookup!
            }
        return {"output": "Something went wrong.", "tool_calls": []}

    # 2. Healthy normal behavior
    if "order" in input_text:
        # Normal order lookup flow
        order_id = "12345"
        for word in input_text.split():
            if word.isdigit():
                order_id = word
                break
        return {
            "output": f"Your order {order_id} is currently in transit.",
            "tool_calls": [{"name": "order_lookup"}],
        }

    elif "stripe" in input_text or "refund" in input_text:
        # Normal refund stripe lookup flow
        return {
            "output": "Refund of $50 has been successfully processed via Stripe.",
            "tool_calls": [{"name": "stripe_lookup"}],
        }

    elif "knowledge" in input_text or "search" in input_text:
        # Knowledge base search flow
        return {
            "output": "Found answer in documentation: update your credentials.",
            "tool_calls": [{"name": "kb_search"}],
        }

    # General fallback
    return {
        "output": "Hello! I can help you with order lookups, refunds, or searches.",
        "tool_calls": [],
    }


def invoke_agent(input_text: str) -> dict[str, Any]:
    buggy = os.environ.get("BUGGY", "false").lower() == "true"
    return run_agent_logic(input_text, buggy=buggy)
