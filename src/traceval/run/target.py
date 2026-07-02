import importlib
import os
import sys
from typing import Any, Protocol, cast

import httpx


class Target(Protocol):
    def invoke(self, input_text: str) -> dict[str, Any]: ...


class HttpTarget:
    def __init__(self, url: str) -> None:
        self.url = url

    def invoke(self, input_text: str) -> dict[str, Any]:
        payload = {"input": input_text}
        resp = httpx.post(self.url, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        output_str = ""
        tool_calls = []

        if isinstance(data, dict):
            # Parse output
            for key in ["output", "final_output", "response"]:
                if key in data:
                    output_str = str(data[key])
                    break
            else:
                if data:
                    # check if tool_calls not the only key
                    keys = [k for k in data.keys() if k != "tool_calls"]
                    if keys:
                        output_str = str(data[keys[0]])

            # Parse tool calls
            t_calls = data.get("tool_calls", [])
            if isinstance(t_calls, list):
                for item in t_calls:
                    if isinstance(item, dict) and "name" in item:
                        tool_calls.append(str(item["name"]))
                    else:
                        tool_calls.append(str(item))
        else:
            output_str = str(data)

        return {"output": output_str, "tool_calls": tool_calls}


class CallableTarget:
    def __init__(self, target_str: str) -> None:
        parts = target_str.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"Callable target must be in format module:function. Got {target_str}"
            )
        mod_name, func_name = parts
        # Ensure cwd is in python path
        sys.path.insert(0, os.getcwd())
        mod = importlib.import_module(mod_name)
        self.func = getattr(mod, func_name)

    def invoke(self, input_text: str) -> dict[str, Any]:
        res = self.func(input_text)
        output_str = ""
        tool_calls = []

        if isinstance(res, dict):
            for key in ["output", "final_output", "response"]:
                if key in res:
                    output_str = str(res[key])
                    break
            else:
                if res:
                    keys = [k for k in res.keys() if k != "tool_calls"]
                    if keys:
                        output_str = str(res[keys[0]])
            t_calls = res.get("tool_calls", [])
            if isinstance(t_calls, list):
                tool_calls = [
                    str(tc.get("name") if isinstance(tc, dict) else tc)
                    for tc in t_calls
                ]
        elif hasattr(res, "output"):
            output_str = str(res.output)
            t_calls = getattr(res, "tool_calls", [])
            if isinstance(t_calls, list):
                tool_calls = [
                    str(tc.get("name") if isinstance(tc, dict) else tc)
                    for tc in t_calls
                ]
        else:
            output_str = str(res)

        return {"output": output_str, "tool_calls": tool_calls}


def resolve_target(target_str: str) -> Target:
    if target_str.startswith(("http://", "https://")):
        return cast(Target, HttpTarget(target_str))
    return cast(Target, CallableTarget(target_str))
