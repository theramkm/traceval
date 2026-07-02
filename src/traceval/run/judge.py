# ruff: noqa: E501
import json
import os
from typing import Protocol, cast

import httpx


class JudgeResult:
    def __init__(self, score: float, reasons: list[str]) -> None:
        self.score = score
        self.reasons = reasons


class Judge(Protocol):
    def score(
        self,
        rubric: str,
        input_text: str,
        output_text: str,
        reference: str | None,
    ) -> JudgeResult: ...


# Global judge calls budget counter
_JUDGE_CALL_COUNT = 0
MAX_JUDGE_CALLS_LIMIT = 200


def get_judge_call_count() -> int:
    return _JUDGE_CALL_COUNT


def reset_judge_call_count() -> None:
    global _JUDGE_CALL_COUNT
    _JUDGE_CALL_COUNT = 0


class FakeJudge:
    def score(
        self,
        rubric: str,
        input_text: str,
        output_text: str,
        reference: str | None,
    ) -> JudgeResult:
        global _JUDGE_CALL_COUNT
        _JUDGE_CALL_COUNT += 1

        if _JUDGE_CALL_COUNT > MAX_JUDGE_CALLS_LIMIT:
            return JudgeResult(
                score=0.0,
                reasons=["Judge call budget exceeded limit of 200 calls."],
            )

        # Heuristic keyword overlap check for deterministic offline testing
        # Check if output_text shares any words of length >= 4 with input_text or reference
        overlap = False
        words_out = {w.lower() for w in output_text.split() if len(w) >= 4}

        words_ref = set()
        if reference:
            words_ref = {w.lower() for w in reference.split() if len(w) >= 4}

        words_in = {w.lower() for w in input_text.split() if len(w) >= 4}

        # If overlap with reference or input
        if words_out.intersection(words_ref) or words_out.intersection(words_in):
            overlap = True

        score_val = 1.0 if overlap else 0.5
        return JudgeResult(
            score=score_val,
            reasons=[f"FakeJudge: overlap evaluated (score={score_val})"],
        )


class OpenAICompatJudge:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        # Fallbacks for key
        self.api_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )

        # If base url is default but GEMINI key is present, redirect to Gemini's OpenAI endpoint
        if (
            "openai.com" in self.base_url
            and os.environ.get("GEMINI_API_KEY")
            and not os.environ.get("OPENAI_API_KEY")
        ):
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            self.model = "gemini-2.5-flash"

    def score(
        self,
        rubric: str,
        input_text: str,
        output_text: str,
        reference: str | None,
    ) -> JudgeResult:
        global _JUDGE_CALL_COUNT
        _JUDGE_CALL_COUNT += 1

        if _JUDGE_CALL_COUNT > MAX_JUDGE_CALLS_LIMIT:
            return JudgeResult(
                score=0.0,
                reasons=["Judge call budget exceeded limit of 200 calls."],
            )

        if not self.api_key:
            raise ValueError("No API Key found. Set GEMINI_API_KEY or OPENAI_API_KEY.")

        prompt = f"""You are an expert evaluator. Evaluate the assistant's output against the rubric.

Rubric:
{rubric}

Task Input:
{input_text}

Assistant Output:
{output_text}

Golden Reference Output:
{reference or "None"}

Evaluate and return a JSON object in this exact schema:
{{
  "score": <float between 0.0 and 1.0>,
  "reasons": ["reason list"]
}}
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful grading assistant that outputs JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        # Request with retry
        for attempt in range(2):
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=20.0,
                )
                resp.raise_for_status()
                result_data = resp.json()
                content = result_data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                score_val = float(parsed.get("score", 0.0))
                reasons_list = parsed.get("reasons", ["No reasons provided"])
                return JudgeResult(score=score_val, reasons=reasons_list)
            except Exception as e:
                if attempt == 1:
                    return JudgeResult(
                        score=0.0,
                        reasons=[f"OpenAICompatJudge request failed after retry: {e}"],
                    )

        return JudgeResult(score=0.0, reasons=["Judge request failed."])


def resolve_judge(judge_str: str) -> Judge:
    if judge_str == "fake":
        return cast(Judge, FakeJudge())

    # parse options if provided as gpt-4o:url
    parts = judge_str.split(":", 1)
    if len(parts) == 2:
        model, url = parts
        return cast(Judge, OpenAICompatJudge(model=model, base_url=url))

    return cast(Judge, OpenAICompatJudge(model=judge_str))
