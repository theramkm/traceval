# Running the suite against your agent: the target contract

`traceval run <evals_dir> --target <target>` accepts two target forms. Both
are resolved once per session; an unresolvable target prints one clear
`ERROR:` line at the top of the output, records a `target_resolution` entry
in the run report's `errors` list, and the run exits nonzero.

## HTTP target

Pass any `http://` or `https://` URL. For every case, traceval sends:

```
POST <your url>
Content-Type: application/json

{"input": "<the case's task text>"}
```

with a 30 second timeout. Non-2xx responses fail the case.

The JSON response is interpreted as follows:

| Field | Meaning |
| --- | --- |
| `output` / `final_output` / `response` | The agent's answer, checked in that priority order; the first present key wins. |
| any other key | Fallback: if none of the three keys exist, the first non-`tool_calls` value is stringified and used as the output. A non-object response body is stringified whole. |
| `tool_calls` (optional) | List of tool invocations, either `{"name": "..."}` objects or plain strings. Only the names are kept. |

`tool_calls` exists so the `tool_sequence` check (did the agent call the
recorded tools, in order) and the `no_tool_loop` check (did it avoid calling
the same tool 3+ times consecutively) have something to score. If your
endpoint omits it, generated `tool_sequence` checks will fail; either return
the names or delete those checks from the case YAML.

If the URL is unreachable (connection refused, invalid URL) traceval prints
the one-line `ERROR:` at session start; cases still run and fail
individually so the run report stays complete.

### Minimal FastAPI implementation

```python
# my_agent.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class AgentInput(BaseModel):
    input: str


@app.post("/agent")
def run_agent(payload: AgentInput) -> dict:
    # Call your real agent here.
    answer = f"You asked: {payload.input}"
    return {
        "output": answer,
        "tool_calls": [{"name": "kb_search"}],
    }
```

```bash
uvicorn my_agent:app --port 8000 &
traceval run evals/ --target http://127.0.0.1:8000/agent --judge fake
```

## Callable target

Pass `module:function` (one colon). traceval inserts the current working
directory into `sys.path`, imports the module, and calls the function with
the case's task text as a single string argument:

```python
def invoke_agent(input_text: str) -> dict: ...
```

Accepted return shapes:

- a dict, interpreted exactly like the HTTP response above
  (`output`/`final_output`/`response` priority, optional `tool_calls`)
- an object with an `.output` attribute (and optional `.tool_calls`)
- anything else, stringified whole and used as the output

```bash
traceval run evals/ --target myapp.agent:invoke_agent --judge fake
```

Because the working directory is importable, `myapp/agent.py` in your repo
root works without installation. A bad module path or missing attribute
produces the same one-line `ERROR:` plus a self-describing run report.
