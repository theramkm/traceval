# Test Fixtures

This directory contains synthetic logs and outputs used for testing traceval adapters and analytical stages.

## Traces and Stories

1. **tr-001 (Success / Golden)**: User asks for order status. LLM calls `order_lookup` which returns status `in_transit`. Result is successful.
2. **tr-002 (Tool Error)**: Refund request. Tool `stripe_lookup` returns a connection timeout error.
3. **tr-003 (LLM Error)**: LLM API error due to invalid credentials.
4. **tr-004 (Loop)**: KB search tool is invoked 3 times with the exact same query, representing a tool loop.
5. **tr-005 (Timeout)**: Traces start but are missing `ended_at`.
6. **tr-006 (Validation Error)**: Target output matches config regex patterns for JSON schema validation failure.
7. **tr-007 (Empty Output)**: Request processing resolves with empty response output.
8. **tr-008 (PII Data)**: Contains PII fields (email & credit card sequence) to verify scrubbers.
9. **tr-009 (Unknown)**: Opaque trace state.
10. **tr-010 (Simple success)**: Direct assistant output response.
11. **tr-011 (Latency timeout)**: Completed but exceeds runtime duration bounds.
12. **tr-012 (Success stripe lookup)**: Simple tool path resolving successfully.

## Backend export fixtures (otel_spans / langfuse_export / langsmith_runs)

Each backend file carries the same five stories (success with llm+tool,
tool error, llm error, timeout, tool loop) plus one corrupt line to test
warning handling. The Langfuse and OTel files additionally contain a
sixth trace (`lf-006` / `otel-006`) whose tool span is named
`create_ticket`, a name the demo agent never uses: it proves tool
detection relies on the documented signals (Langfuse input/output
heuristic, OTel gen_ai semantic-convention attributes), not on a tool
vocabulary.
