# Provider Operation Tools

This folder contains model-facing adapters for provider API endpoints that are not common normalized search or fetch operations.

## File index

- `browserbase.py` — Browserbase session and context lifecycle tools.
- `exa.py` — Exa answer, Webset, and monitor tools.
- `tavily.py` — Tavily map, crawl, and research tools.
- `parallel.py` — Parallel Chat, Task, FindAll, and Monitor tools.

## Invariants

Each adapter declares one stable tool name and delegates network work to an injected provider client. Provider-reported dollars never replace pricebook cost. Session capabilities, credentials, and signed URLs must not reach model-visible output.

## Logs

- 2026-07-29: Created as the extensibility boundary for provider-specific endpoints; common search/fetch normalization remains in the parent operation modules.
