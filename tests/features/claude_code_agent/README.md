# Claude Code harness agent tests

## Folder Description / Intent

This folder tests `ClaudeCodeHarnessAgent` (`vidbyte.agents.claude_code`) offline, against a stand-in for Claude Code's `claude` executable that replays the print-mode stream-json shapes observed live on Claude Code 2.1.314, plus one live test that is skipped unless `VIDBYTE_LIVE_CLAUDE_CODE=1`. The stand-in is found through `PATH`, as the real program is, so every test sees the exact argv, stdin, working folder and environment a real `claude` would receive.

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, its failure modes and the strategies left out.
- `fake_claude.py` is the `claude` stand-in: it parses the joined argv, reads the stdin message, keeps a session store keyed by working folder, logs what it received and prints the observed events or a scripted failure.
- `claude_code_support.py` builds the sandbox (the stand-in on a `PATH` of its own, temp folders redirected, credentials cleared, a parent Claude Code session's variables set), test settings and the process liveness check.
- `conftest.py` provides the `sandbox` fixture.
- `test_claude_code_agent.py` covers successful runs: structured output, resume, cost and model, the command line, stdin, the instructions file, the child environment, the workspace lifecycle, serialized runs and the synchronous twin.
- `test_claude_code_failures.py` raises every `ClaudeCodeFailureKind` from its real condition, and covers the timeout and cancellation tree stop and credential scrubbing.
- `test_claude_code_records.py` covers settings and record validation.
- `test_claude_code_surface.py` covers the public surface the cross-repo contract pins and the public-API contract file.
- `test_claude_code_live.py` runs two real turns on the machine's Claude login when `VIDBYTE_LIVE_CLAUDE_CODE=1`.

## Logs

- 2026-10-30 - Created with the agent for vidbyte-sdk 0.4.2. The live test passed once on Claude Code 2.1.314 with the haiku alias before the pull request.
