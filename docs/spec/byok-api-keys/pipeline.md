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
| S1 spec + review | running | 2026-10-12 16:52 | | reports/S1-spec-author.md | spec r1 e201a52b; review r1 c511e830 (SOUND WITH FIXES 0/6/0); r2 01b0bcf6; review r2 SOUND WITH FIXES 0/5/4 (R-7..R-15); author applying, then approved (cap reached) |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 live E2E (both repos) | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

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
- Spec r1 contract names: `ProviderKeyMatcher.provider_of / normalize / key_for / providers` in new `vidbyte/lib/registries/provider_keys.py`; `TextModelConfig.credentials()` → `TextCredentials(mode, provider_api_key, vidbyte_api_key)` with `.uses_gateway`, `.relays`; `VIDBYTE_PROVIDER_KEY_HEADER`; `TextModelMode.DIRECT`; agent kwargs `api_keys`, `vidbyte_api_key`, `model_mode`; `VidbyteGatewayTransport(..., provider_api_key=)`. — *source:* S1 author
- Import cycle (D-21): `vidbyte.lib.dataclasses.agents` loads before the registries package, so it imports the matcher inside `__post_init__`; everyone else imports from `vidbyte.lib.registries.provider_keys`. — *source:* S1 author
- C017: add the header by subscript with the imported constant right after the `Idempotency-Key` line; never `.update()`. — *source:* S1 author
- Today's fake test keys ("sk-mock", "test-key", "main-key") are refused by the classifier; build classifiable fakes at runtime and avoid scanner patterns (`AIza`+35 chars, `T3BlbkFJ`); spec §13 lists safe shapes. — *source:* S1 author
- Test seam: sibling pack `tests/features/sdk_managed_text/`; mock only `vidbyte.lib.runners.text.HttpTransport` and sleep; `patch.dict(os.environ, ..., clear=True)`; import feature symbols inside each test. Failure-message table G must keep every fact `test_managed_text_failures.py:126-146` checks. — *source:* S1 author
- `base.py` may grow by at most 25 net lines (spec budget). Tests running a real `TextModelRunner` in AUTO without a Vidbyte key now fail at construction; expect stragglers beyond §13's list. — *source:* S1 author
- origin/main moved to 3ed3c627 after base 52aab816; rebase at S6. — *source:* S1 author
- S1 review r1: SOUND WITH FIXES, 0 Blocker / 6 Major. Verified: D-21 import cycle real; C017 header tracing ok (`python lint/run.py --rule C017` → `C017 platform-route-contract 0 0 CLEAN`, `SDK-LINT: PASS`); D-13 deletion safe (`vidbyte_key_follows_provider` callers only `vidbyte/agents/fork.py:116`, `vidbyte/agents/settings/fallback.py:163`); §13 complete. — *source:* S1 reviewer
- `vidbyte/lib/dataclasses/config.py` already has five function-local imports (`:573,:610,:629,:673,:716`): precedent for D-21. — *source:* S1 reviewer
- Secret scanning: no in-repo scanner; GitHub push protection only. gitleaks-style rules exist for openai, anthropic (`sk-ant-api03-` + 93 chars + `AA`), gcp (`AIza` + 35); none for xai/deepseek/kimi/openrouter. Test fakes must avoid those shapes. — *source:* S1 reviewer
- `HarnessRedactor._ERROR_ASSIGNMENT` (`vidbyte/harnesses/serialization.py:70`) matches `[^\s,;]+`, stopping at a comma: tuples of keys are only partly redacted (R-5). — *source:* S1 reviewer
- `tests/test_output_schema_provider_dialect.py:102` builds `MistralProvider(..., api_key="k")`. — *source:* S1 reviewer

## Decisions the orchestrator made (continued)
- 2026-10-12 21:00 — R-2/Q-2 resolved YES from the user's words (Prompt 5 "makes sure that the user is inputting the correct api key that matches the provider/model"): non-empty `api_keys` with no key for the primary provider raises before any request; children of other providers relay-or-Vidbyte-paid per §B.2.
- 2026-10-12 21:00 — R-1/Q-1/R-3 resolved inside requested behavior (Prompt 6 "deterministically match", Prompt 5 "dont want developers to have to worry"): format-proven keys by format; unproven keys (generic `sk-`, providers without rules) by deterministic unique assignment against in-use providers, else raise; never route a key on an unsourced shape guess.
- 2026-10-12 21:00 — Both S1 agents were killed by an API session limit mid-task; resumed via SendMessage after reset; neither had written partial files.
- 2026-10-12 — S1 r2 (01b0bcf6, +458/-327) changed §8, §8.5 and §12's rows (new `ProviderKeys` record carried by children; unique-assignment matching; Vidbyte key accepted inside `api_keys`), so a scoped round-2 review runs (last allowed round).
- 2026-10-12 — Q-3 (relayed streaming in the default mode breaks) is consistent with the /talk default "streaming gap accepted"; carried to the round-2 reviewer to check the failure names `DIRECT`.
- Spec r2: `ProviderKeys` lives in `vidbyte/lib/dataclasses/agents.py`, built once and carried unchanged by every child (forks, fallbacks); `FallbackModel` loses its key field; the matcher imports `ProviderKeys` inside `match`, not at module level; `vidbyte.lib.constants`/`enums` import only enum modules. r1 row 16 is now row 3 and r1 rows 3–15 moved down one. Table F holds five sourced prefix rules (`sk-ant-`, `xai-`, `AIza`/`AQ.`, `sk-or-`, `vb_live_`). — *source:* S1 author r2
- 2026-10-12 — Round-2 rulings (cap reached; author applies once, sets approved):
  - R-7 accept: pair check on a passed-in ProviderKeys, no re-bind; it is treated like a child record, so INV-24 is skipped; docs advertise only the list form (NG-19).
  - R-8 accept option 1: at an AggregateAgent root, every spec-built proposer and the spec-built aggregator count as primaries for INV-24; a prebuilt aggregator means primary None.
  - R-9 accept option 1: persist the root's matched provider names (no secrets) in runtime_config and re-match against them on restore. Old sessions without the field match as a root.
  - R-10 accept the wording fix; Q-6 recorded, default no.
  - R-11 accept the doc fix, and Q-7 = YES (Prompt 5 "dont want developers to have to worry about this", Prompt 6 "Simply renames"): it is a matching refinement inside the requested behavior, not a new control. A lone remaining unproven key that exactly one keyless primary accepts binds to that primary.
  - R-12 accept.
  - R-13 accept the charset check on every resolved provider key, plus the 512 cap when relaying.
  - R-14 prefer construction-time checks if each is at most 5 lines in existing rows, else the wording fix.
  - R-15 accept the order fix, and add `vidbyte/lib/dataclasses/__init__.py` as a §12.3 row.
  - Prefix sources: a rule that ROUTES a key needs a first-party citation; drop `AQ.` unless Google's own docs show it (env var still works). Evidence for refuse-only claims may be secondary.
- 2026-10-12 — Corrected niche fact: the spec budget for `base.py` is +30 net lines (r2), not 25.
