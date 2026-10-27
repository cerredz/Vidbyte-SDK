# Design Doc: An unconfigured priced tool is an error and is never billed

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-27
**Last Updated:** 2026-10-27

## 1. Overview

Every prebuilt search and fetch tool (`PricedOperationTool`) that has no provider client returns
`_contract_result(...)`, which is a success result that carries an `operation_usage` annotation. The runtime prices that
annotation as a real operation (`AgentRuntime._record_operation_usage`). So a client-less `ExaSearchTool()` records a
$0.007 Exa charge for a search that was never sent, and the model is told that the search ran. Linkup (search and
fetch) and OpenAlex have no client path at all, so every call to them is a phantom charge. This change adds one base
helper, `_unconfigured_result()`. It returns an error that declares no usage, and every client-less branch returns it.
The runtime already prices nothing for an error that has no usage annotation, so no runtime change is needed.

## 2. Goals & Non-Goals

### Goals
- A priced operation tool that cannot send its request returns `ToolStatus.ERROR` with `metadata["error"] ==
  "unconfigured"` and no `operation_usage`.
- No operation is recorded in the ledger, so `max_spend_usd` and gateway billing see $0 for that call.
- The model is told the tool is not configured instead of being told that a search ran.
- Client-bound tools, and the zero-cost `DirectHttpFetchTool`, which performs a real GET, are unchanged.

### Non-Goals
- Adding Linkup, OpenAlex or Semantic Scholar clients.
- Changing `_contract_result`, which `DirectHttpFetchTool` and test probes use for real, priced work.

## 3. Background & Context

`vidbyte/tools/README.md` describes the stub as a way to wire a tool in before credentials exist. That wiring still
works; only the billing and the false success go away. The skill doc `skills/usage/available_tools.md` lists every tool
as `XTool()` with no client, so users copy exactly the shape that phantom-bills. Reproduced offline by
`repro_18_stub_tools_billed.py`, which exits 1 on `origin/main` f0896962.

## 4. Requirements

### Functional Requirements
1. With no client, these tools return the unconfigured error: Brave, Browserbase search, Exa, Tavily search, Linkup
   search, Parallel search, OpenAlex, Semantic Scholar, Firecrawl, Browserbase fetch, Parallel extract, Tavily extract
   and Linkup fetch.
2. The error carries no `operation_usage`, so `PricedOperationTool.declares_usage(result)` is False.
3. Argument errors (`missing_url`) keep precedence over the unconfigured error and are unchanged.
4. The message names the tool and the provider, and says that no request was sent.

### Non-Functional Requirements
- No network access. The change only removes behavior. Nothing new is logged.

## 5. High-Level Design

```
tool.execute (no client) -> _unconfigured_result() -> ToolResult.error(no operation_usage)
runtime._billable_attempts: error and not declares_usage -> 0 -> no record_operation
```

## 6. Detailed Design

### 6.1 PricedOperationTool._unconfigured_result
**File:** `vidbyte/tools/builtins/operations/base.py` (Modified)
```python
def _unconfigured_result(self) -> ToolResult
```
It returns `ToolResult.error(self.name, "<tool> is not configured: it has no <provider> client, so no <operation> request
was sent.", metadata={"error": "unconfigured"})`.

### 6.2 Search and fetch tools
**Files:** `search.py`, `fetch.py` (Modified). Each `if self._client is None:` branch, and each tool that has no client
path at all (Linkup, OpenAlex, Semantic Scholar), returns `self._unconfigured_result()`.

## 7. Data Model Changes
N/A: `ToolResult` is unchanged. Only a new `metadata["error"]` value, `"unconfigured"`, is added.

## 8. API Changes
Behavior change: a client-less priced tool returns an error instead of a priced success. No signatures change.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/tools/builtins/operations/base.py` | Add `_unconfigured_result` |
| MODIFY | `vidbyte/tools/builtins/operations/search.py` | Eight client-less branches |
| MODIFY | `vidbyte/tools/builtins/operations/fetch.py` | Five client-less branches |
| MODIFY | `tests/test_operation_fetch_url_list.py` | Prove the url fallback through a recording client, not the stub |
| CREATE | `tests/test_unconfigured_operation_tools.py` | Regression tests |
| MODIFY | `vidbyte/tools/README.md`, `skills/usage/available_tools.md` | Document the unconfigured result |
| CREATE | `docs/design/unconfigured-tools-not-billed.md` | This doc |

## 10. Testing Plan

### Unit Tests
- `test_a_tool_without_a_client_is_an_unconfigured_error` runs for each of the 13 tools with valid arguments. The
  result is an ERROR with `error == "unconfigured"`, and `declares_usage` is False. [Silent Failure]
- `test_the_unconfigured_message_names_the_tool_and_says_nothing_was_sent` checks that the model is not told a search
  ran. [Silent Failure]
- `test_a_missing_argument_still_wins_over_unconfigured` checks that firecrawl with no urls reports `missing_url`.
  [Edge Case]
- `test_linkup_ignores_a_foreign_client_and_stays_unconfigured` checks that a client bound to a tool with no client path
  still records nothing. [Hidden Assumption]
- `test_firecrawl_fetch_accepts_url_with_empty_urls` (updated) checks that a recording client receives the single url.
  [Edge Case]

### Integration Tests
- `test_an_agent_calling_an_unconfigured_tool_records_no_operation`: an agent loop on a scripted runner calls
  `exa_search` on `ExaSearchTool()`. The ledger then has zero operations, the run's cost equals the model calls alone,
  and the next model prompt carries the unconfigured error. [Silent Failure]
- `test_a_configured_tool_still_records_its_operation`: the control case, with a fake client. [Hidden Failure]

### Manual / QA
1. Given `origin/main`, when `repro_18_stub_tools_billed.py` runs, then it exits 1. On this branch it exits 0.

## 11. Dependencies & External Services
None. Tests use scripted runners and fake clients.

## 12. Rollout & Deployment
Gateway customers get this fix only after an SDK release and a backend pin bump. Then a client-less tool call costs
nothing and returns an error to the model. Rollback is a revert.

## 13. Open Questions
- [ ] Should the SDK refuse a client-less priced tool at agent construction? This change keeps the README's
  "wire it in before credentials exist" behavior.

## 14. Alternatives Considered
### Skip pricing client-less results in the runtime
- Why rejected: the model would still be told that a search ran, and the runtime would need to know about each tool's
  client.
### Remove the client-less tools
- Why rejected: it is a public API break, and it is not needed for billing correctness.
