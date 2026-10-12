---
slug: byok-api-keys
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys
branch: feat/byok-api-keys
base_commit: 52aab816ab922f3d47de926e2c8a2506c2542d86
pr:
until: none
started: 2026-10-12 16:20
companion: backend run byok-fee-relay at C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-byok-fee-relay (cerredz/Vidbyte)
---

# Pipeline: Agents take vidbyte_api_key and a list of provider api_keys, and every text call relays through the Vidbyte gateway (SDK half)

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-12 16:20 | 2026-10-12 16:50 | reports/S0-scout.md | base 52aab816; code-map 4 sections |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 live E2E (both repos) | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-12 16:20 — Run backend and SDK as two parallel pipelines, joined by a wire contract fixed in request.md §C — the user asked for both repos; the contract is small and fixing it lets both proceed at once.
- 2026-10-12 16:20 — Header name fixed as `X-Vidbyte-Provider-Key` — `X-Api-Key` is already a Vidbyte-key auth header in the backend; Sentry's default filter drops neither name, so the backend scrubs it explicitly.
- 2026-10-12 16:20 — Treat the /talk Needs-you defaults (AUTO requires a Vidbyte key with DIRECT explicit; 200 bps unchanged; streaming gap accepted) as accepted — Prompt 5 opened "great, just to be clear" and contested none.
- 2026-10-12 16:20 — Add a "live E2E" step after both repair loops converge — Prompt 5 asks for live grok testing with the real keys; Prompt 6 chose the local-backend path.

## User replies (verbatim)
- 2026-10-12 16:15 — Clarifying answers recorded verbatim in request.md §A Prompt 6.

## Niche facts accumulated (carried into every later briefing)
- Lint and semgrep scan only git-tracked files (`lint/core/discovery.py:76-85`); `git add` new files before trusting either. — *source:* S0
- SDK lint pass line is `SDK-LINT: PASS`; semgrep is not in `run_ci.py`, only in `.github/workflows/static-policy.yml`. — *source:* S0
- C020 flags any literal containing `vb_live_` (error messages included); build from `VIDBYTE_API_KEY_PREFIX`. It does not flag `sk-ant-`, `xai-`, `AIza`. — *source:* S0
- Pricebook lookup needs a provider; `pricing.py` imports `registries/models.py`; model→provider is `ProviderModelRegistry.provider_for_model` (`vidbyte/lib/registries/models.py:330`). — *source:* S0
- `TextModelConfig.api_key` is the 3rd positional field; tests pin field order (`tests/features/sdk_managed_text/test_managed_text_selection.py:47-51,284,286`). — *source:* S0
- `AgentRunnerConfig.api_key` (`vidbyte/lib/dataclasses/agents.py:204`) lacks `repr=False`; `repr(agent.runner_config)` prints the key today. — *source:* S0
- Text and Decision share `resolve_vidbyte_api_key` ("Pass api_key" message); `test_managed_text_selection.py:327-347` asserts identical messages. — *source:* S0
- Header constant should follow `JEV_MANAGED_RUN_ID_HEADER` (`vidbyte/lib/constants/jev.py:55`); gateway headers built only at `vidbyte_gateway.py:161-162`. — *source:* S0
- Rename surface: 175 lines / 52 files of `api_key` in `vidbyte/` (text-model keys: 30 files / 95 lines; other secrets: 16 files; plumbing/guards: 6 files); tests: 186 `api_key=` in 44 files (~112 text/agent). Includes AggregateAgent, continual-trace and handoff agents, Jev settings, session resume/fork, paradigm role settings, and `Runner` passing the agent key to image/video/audio/embedding configs. — *source:* S0
- 3 of 4 name-based credential guards and the harness free-text regex miss `api_keys`; only the session serializer's substring match catches it. — *source:* S0
- No provider key-format knowledge exists in the SDK; only `VIDBYTE_API_KEY_PREFIX`/`PATTERN` and redaction regexes for `vb_live_` and `xai-`. — *source:* S0
- Existing tests use fake keys like "main-key", "PARENTKEY", "sk-explicit" that a strict classifier would reject; existing tests pin provider-key-wins-in-AUTO, `api_key=vb_live_` switching, BYOK streaming in AUTO, and the 402 "provider key" wording. — *source:* S0
- Unverified: whether C017 still classifies the gateway request as API_KEY with a second header (`python lint/run.py --rule C017`). — *source:* S0
- Vidbyte-SDK PRs get no automatic checks: `gh workflow run CI --ref feat/byok-api-keys` and `gh workflow run "Static policy" --ref feat/byok-api-keys`; required `Source / Python 3.11`, `Source / Python 3.12`, `Package`. — *source:* orchestrator memory
