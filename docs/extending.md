# Extension points

traceval has three: custom outcome rules, a redaction hook, and judge
configuration.

## Custom outcome rules (`traceval analyze --rules my_rules.py`)

The file must expose a module-level `RULES` list. Each entry is either a
`Rule` object from `traceval.analyze.outcomes` or a bare callable with the
signature `(Trace) -> Outcome | None`. Return `None` to pass; the first
rule that returns an `Outcome` wins. **User rules run before the
built-ins**, so they can override any built-in label.

```python
# my_rules.py
from traceval.analyze.outcomes import Rule
from traceval.model import Outcome, Trace


def escalation(trace: Trace) -> Outcome | None:
    if trace.final_output and "escalate to human" in trace.final_output.lower():
        return Outcome(
            label="bad_output",
            reason="agent escalated instead of resolving",
            rule_id="R_USER_ESCALATION",
            labeled_by="user_rule",
        )
    return None


RULES = [Rule("R_USER_ESCALATION", "Escalations count as failures", escalation)]
```

```bash
traceval analyze traces.db --rules my_rules.py -o analysis
```

`Outcome` requires `label` (one of `success`, `tool_error`,
`validation_error`, `loop`, `timeout`, `bad_output`, `unknown`), `reason`,
and `labeled_by`; `rule_id` is optional but shows up in reports, so set it.
Built-in rules run afterwards in this order: `R_TOOL_ERROR`, `R_LLM_ERROR`,
`R_LOOP`, `R_TIMEOUT`, `R_VALIDATION`, `R_EMPTY_OUTPUT`,
`R_DEFAULT_SUCCESS`, `R_UNKNOWN`.

## Redaction hook (`traceval generate --redact-hook module:function`)

A `str -> str` function applied to case inputs and reference outputs before
they are written to YAML, after the built-in scrubbers (emails, credit
cards, phone numbers, API tokens). The module is imported from the current
working directory.

```python
# my_redactions.py
import re


def scrub(text: str) -> str:
    return re.sub(r"ACC-\d{6}", "[REDACTED_ACCOUNT]", text)
```

```bash
traceval generate traces.db -o evals --include-failures --redact-hook my_redactions:scrub
```

## Judge configuration (`traceval run --judge ...`)

| Value | Behavior |
| --- | --- |
| `fake` (default) | Deterministic offline judge: keyword-overlap heuristic, never gates a run at the generated `min_score`. Use it in CI without API keys. |
| `<model>` | `OpenAICompatJudge` against `https://api.openai.com/v1` with that model, e.g. `--judge gpt-4o-mini`. |
| `<model>:<base_url>` | Any OpenAI-compatible endpoint, e.g. `--judge llama3:http://localhost:11434/v1`. |

API keys come from the environment: `OPENAI_API_KEY` first, then
`GEMINI_API_KEY`. If only `GEMINI_API_KEY` is set and the base URL is the
OpenAI default, traceval automatically routes to Gemini's OpenAI-compatible
endpoint (`https://generativelanguage.googleapis.com/v1beta/openai`) with
model `gemini-2.5-flash`.

Judge calls are budget-capped at 200 per run (hardcoded); calls beyond the
budget score 0.0 with an explanatory reason. Validate any real judge with
`traceval calibrate` before trusting its scores.

## `traceval.yaml` reference

`traceval generate` writes this scaffold next to the suite. Honest status
of every key:

| Key | Default | Consumed today? |
| --- | --- | --- |
| `schema_version` | `"1"` | No, informational. |
| `target.default_url` | `http://localhost:8000/agent` | **Yes**: used as the target when `traceval run` is invoked without `--target`. |
| `target.timeout_s` | `30` | No: the HTTP timeout is fixed at 30s in code. |
| `judge.default_provider` | `fake` | No: the CLI's `--judge` default (`fake`) applies instead. |
| `judge.max_judge_calls` | `200` | No: the 200-call budget is hardcoded. |

The unconsumed keys document intended configuration surface; treat them as
reserved.
