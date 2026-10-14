# ClaudeHost (Claude Code as atomic functions and agent tools)

## Folder Description / Intent

This folder holds the feature tests for `ClaudeHost`, the host that wraps claude-agent-sdk 0.2.165 in 15 small coroutine functions, and for `ClaudeTools`, which exposes the same functions as agent tools. The tests are offline: the only fake is the vendor SDK, patched in through `ClaudeSdkLoader.load`, so no test needs the optional `claude` extra, a `claude` binary, a login or the network. The behavior itself lives in `vidbyte/harnesses/native/claude/`, `vidbyte/lib/dataclasses/claude.py`, `vidbyte/lib/dataclasses/claude_host.py`, `vidbyte/lib/enums/claude.py`, `vidbyte/lib/constants/claude.py`, `vidbyte/tools/builtins/claude/` and `vidbyte/tools/toolsets/claude.py`, not here. The contract comes from `docs/spec/claude-host/spec.md`.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` defines the contract, the invariants, the known failure modes, and the strategies left out on purpose.
- `claude_host_fixtures.py` provides the fake SDK (client, options, messages, errors, history functions and MCP server factory, all with the 0.2.165 names and fields), the message factories, `TicketTool`, and the `ClaudeHostCase` base class.
- `test_claude_host_acceptance.py` runs the developer snippet in its ready and not-ready forms, the orchestrator agent snippet under `arun`, and the sync `run()` refusal.
- `test_claude_host_contract.py` covers the import boundary, the marker bytes, the failure-code block and next steps, the constants, the enums, the record shapes, the public host surface, the pyproject extra, and the REPO_MAP and README insertions.
- `test_claude_host_request.py` covers the field mapping onto `ClaudeAgentOptions`, image prompts, record validation, and the custom-tool MCP server.
- `test_claude_host_turns.py` covers the spawn snapshot, waits, result fields, failure classification and exception mapping, usage, `hooks_applied`, injected results, and disconnect errors.
- `test_claude_host_stops.py` covers steer, interrupt, `aclose` and the loop guard, the never-cancelled close, the time budget, the interrupt grace, and pending-steer discards.
- `test_claude_host_admission.py` covers continue, launch, rate-limit refusals, the live cap, busy session ids, empty and mistyped arguments, CLI path choice, and session-id natural keys.
- `test_claude_host_history.py` covers fork, the session list, info and messages, and their text rendering.
- `test_claude_host_readiness.py` covers the missing extra, version and auth-mode checks, models, the CLI lookup, start failures, and the sign-in and version rules.
- `test_claude_host_tools.py` covers the per-tool contract, the toolset order and permissions, wrong JSON types, the MCP listing, and success rendering.
- `test_claude_host_security.py` covers secret and error-text markers, validation that never echoes values, extra model arguments against the bound request, and foreign handle ids.
- `test_claude_host_review_gaps.py` covers what the S4 review found broken or unguarded: a steered prompt's own outcome, a steer that starts while the previous result is unread, a continue racing `aclose`, SDK record drift, per-model rate-limit windows, D-29's overage and reset-time conditions, a steer whose interrupt fails, and a cancelled `aclose`.

## Logs

- 2026-10-13 - Pack added red, ahead of the implementation, from spec r3 (S2 test author).
- 2026-10-13 - Added `test_claude_host_review_gaps.py` for the S4 review findings R-1, R-2, R-3, R-5, R-6 and R-7, against spec r5 (S5 repair). The 165 earlier tests are unchanged.
