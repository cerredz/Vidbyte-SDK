# Classifier tools

Tools in this folder give a small, structured judgment to a fast, calibrated
decision model instead of spending the main model's reasoning on it. Each tool
returns a probability for every allowed answer, so the agent can tell a
confident verdict from a close call.

## File Index

- `__init__.py` - Re-exports the classifier tools. Open this when you add a tool to the family.
- `jev_decide.py` - `JevDecideTool`, the `jev_decide` tool backed by TypeSafe's Jev model. Open this to change argument parsing, the model-facing text, fail-open error codes, or decision records.

## Using `jev_decide`

```python
from vidbyte import Agent
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev_settings import JevDecideSettings
from vidbyte.tools import JevDecideTool

tool = JevDecideTool(settings=JevDecideSettings(decision=DecisionModelConfig(), min_confidence=None))
agent = Agent(name="triage", system_prompt="...", tools=[tool])
```

- **Credentials:** set `TYPESAFE_API_KEY`, or pass `api_key` in
  `DecisionModelConfig`. Without a key, the tool reports "unavailable" and the
  agent carries on without it.
- **Cost:** each call is recorded in the agent's `UsageTracker` under provider
  `typesafe`. Jev bills $0.042 per million input tokens, and output tokens are
  free.
- **Thresholds:** `min_confidence` is application policy and defaults to
  `None`. The tool always returns the full distribution.
- **Data egress:** the `state` text is sent to TypeSafe's API. Credential-like
  assignments and the configured key are redacted first, but callers remain
  responsible for what else they put in the state.
- **Failure codes** (in `ToolResult.metadata["error"]`):
  - `invalid_arguments`: the call's arguments were malformed.
  - `jev_unavailable`: no API key is configured.
  - `jev_unauthorized`: TypeSafe rejected the key (HTTP 401). The tool is then disabled for the rest of its life.
  - `jev_rate_limited`: TypeSafe returned HTTP 429 or 529.
  - `jev_invalid_request`: TypeSafe rejected the request shape (HTTP 422).
  - `jev_request_failed`: TypeSafe could not be reached.
  - `jev_bad_response`: the answer could not be read. The call is still billed.
