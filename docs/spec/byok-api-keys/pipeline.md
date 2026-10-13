---
slug: byok-api-keys
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys
branch: feat/byok-api-keys
base_commit: 52aab816ab922f3d47de926e2c8a2506c2542d86
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1027
until: none
started: 2026-10-12 16:20
companion: backend run byok-fee-relay at C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-byok-fee-relay (cerredz/Vidbyte)
---

# Pipeline: Agents take vidbyte_api_key and a list of provider api_keys, and every text call relays through the Vidbyte gateway (SDK half)

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-12 16:20 | 2026-10-12 16:50 | reports/S0-scout.md | base 52aab816; code-map 4 sections |
| S1 spec + review | done | 2026-10-12 16:52 | 2026-10-12 | reports/S1-spec-author.md | spec r1 e201a52b; review r1 c511e830 (SOUND WITH FIXES 0/6/0); r2 01b0bcf6; review r2 SOUND WITH FIXES 0/5/4 (R-7..R-15); r3 74f0b83d approved; r4 91e69211 approved |
| S2 tests | done | 2026-10-12 | 2026-10-13 | reports/S2-test-author.md | S2_HEAD c88f2d32 on origin/main 595a7260 (23 commits ahead, unpushed); 117 new tests red; 36 superseded files + 8 post-rebase straggler files; full 308F/3786P/13S/7E (orchestrator re-run identical); main baseline 3984P/0F |
| S3 implement | done | 2026-10-13 | 2026-10-13 | reports/S3-implementer.md | S3_HEAD 23dff561 (code at 3481ed66); draft PR #1027; 41 rows; full 4101P/13S/0F; pack 117/117; SDK-LINT PASS (A001 643→641); run_ci source+package PASS; semgrep 0; remote CI + Static policy success @3481ed66; budget 1 file/3 classes/0 deps, base.py +26/30 |
| S4 adversarial review | done | 2026-10-13 | 2026-10-13 | reports/S4-review-*.md, reports/S4-findings-verifier.md | review.md: MERGEABLE AFTER FIXES; confirmed 1 Blocker / 9 Major / 8 Minor; refuted 0 (3 sub-claims corrected) |
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

- 2026-10-13 — Every running agent was stopped by an API session limit (HTTP 429): backend S4 reviewers C/V/E, SDK S2 author and its helper. After the reset, ListAgents showed no live pipeline agent. Backend worktree clean, no S4 reports written. SDK S2 left 24 modified tests plus the new pack, uncommitted. Each agent resumed via SendMessage; the SDK S2 author is told to verify its dead helper's edits and not to spawn helpers again.
- 2026-10-13 — S2 ambiguities 1–6 + two notes ruled to match the tests' bindings; spec r5 e349ee46 (wording only, Proof column unchanged). Items 7 (M-9 vs M-14 order) and 8 (DIRECT runner pinning) left unspecified: tests assert only `error_kind` / do not depend on them.
- 2026-10-13 — origin/main is 48 commits past base 52aab816, touching 78 files, including 8 test files S2 edited and §12.3's `vidbyte/harnesses/serialization.py`. Rebase the unpushed branch (docs and tests only) onto origin/main NOW, before S3, via the S2 author, who owns test conflicts, plus a static straggler hunt over main's new or changed tests. This is cheaper than an S6 rebase with implementation code. S2_HEAD is re-recorded after the rebase.

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

- Branch rebased twice: onto b53c8811, then onto 595a7260 (#1023). Main's only §12.3-row change is row 16: `HarnessRedactor._ERROR_ASSIGNMENT` now opens with a lookbehind (#993) instead of ``; apply `keys?` and the list/tuple alternatives to that regex and keep the lookbehind. Main also changed adapter files anthropic.py, compatible.py, gemini.py, openai.py, xai.py (vidbyte/providers) and lib/http parser.py, transport.py; none is a §12.3 row. — *source:* S2 rebase
- Post-rebase stragglers updated in 8 test files (test-plan §5 "(post-rebase straggler)"): compatible (GLM; MiniMax added to `_PROVIDER_TEST_KEYS`), deepseek, openrouter, output_schema_provider_dialect (incl. #1023's openai Responses test), streaming_text_runner, text_model_runner, and new `test_gemini_provider_text.py`. Every Gemini fake is `"AQ" + "." + "x"*40`. — *source:* S2 rebase
- Spec §13 line numbers for test_output_schema_provider_dialect.py (`:91`, `:102`) and other moved files are stale after the rebases; the tests are the contract. — *source:* S2 rebase
- Red reason groups (test-plan §3): `AttributeError: DIRECT` 126 (119 + 7 setUp); the rest are behaviour groups. Manual-script test `ManualScriptTests` points at `scripts/test-new-runners.py:315`. — *source:* S2

- S3 deviations to know: provider env-var table moved to `vidbyte/lib/constants/jev.py` `PROVIDER_API_KEY_ENV_VARS` with `ProviderModelRegistry.API_KEY_ENV_VARS` aliasing the same dict (A006 ruling); `lint/rules/s014_provider_model_registry_parity.py` reads that literal (S014 ruling, mutation-proven); two lint follow-up commits (12d8aa74, 24de2be2) and S009/URL fixes (4b23e3d9, d1eef1aa); provider_keys.py 296 lines (NFR-4 ≤ 300); OpenAI admin-key doc URL 404 → row 35 cites OpenAI's raw openapi.yaml; row 20 commit cites AC-21 instead of AC-18. — *source:* S3
- Global semgrep is broken (global `mcp` 2.3.0); a working semgrep 1.170.1 venv is at scratchpad `semgrep-venv` (put `/c/...` form on PATH). `python lint/run.py --rule X --all` needs `PYTHONIOENCODING=utf-8`. — *source:* S3
- `scripts/test-async-http-transport.py` and `test-openai-compatible-chat-trace-inputs.py` fail identically at 140b17ed (pre-existing; CI only compiles scripts). — *source:* S3
- origin/main is 2 commits past 595a7260 (66f8353a) touching none of this branch's files; not rebased. — *source:* S3

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
- 2026-10-12 — r3 open items ruled:
  - `AQ.` routes to gemini. A vendor's official GitHub org counts as first-party for both OpenAI (`sk-proj-`) and Google (google-gemini cookbook). Google staff replies on discuss.ai.google.dev (Google-run) say AI Studio now issues only `AQ.` keys, so refusing them would block most new Gemini users.
  - `RESERVED_PREFIXES` is accepted as a refuse-only guard, now holding only `sk-svcacct-`.
  - Applied as r4, no review (the cap is reached; the change is narrow).
- Spec r3 new names: `ProviderKeyMatcher.RESERVED_PREFIXES`; `match(..., require_primary_key=True)` with `primary` as a str or tuple; `ProviderKeys.matched_primary` / `matched_others`; `VIDBYTE_PROVIDER_KEY_PATTERN = r"[!-~]+"`; `VIDBYTE_PROVIDER_KEY_MAX_LENGTH = 512`; `runtime_config["key_providers"]` (names only; the session serializer strips only names containing API_KEY, TOKEN, SECRET, PASSWORD, CREDENTIAL or AUTH). xAI `xai-client-secret.` tokens contain a dot and are refused. — *source:* S1 author r3
- 2026-10-12 — Accepted r4's near-miss reservation: every table F prefix stays reserved, derived from `KEY_FORMATS`, so a key with a table F prefix that does not fully match, such as a dotted `xai-client-secret.` token, is refused rather than unique-assigned to another vendor. Applying the strict wording of ruling 2 would have opened a wrong-vendor path.
- 2026-10-12 — Spec approved at r4 after 2 review rounds (cap) and two orchestrator-ruling revisions. Q-3 (streaming in default mode) defaults to no: refuse, naming DIRECT. Q-4 (per-model mode) defaults to no. Q-5 (fail at build without a Vidbyte key) defaults to no. Q-6 (refuse `T3BlbkFJ` for non-openai) defaults to no.
- 2026-10-12 — S2 straggler plan: stragglers (tests that only fail once INV-7 or INV-24 is enforced) cannot be found by a pre-implementation red run. The S2 author hunts them statically. Any found later by S3/S5 go back to a test-author pass (the implementer may not edit tests), each logged here.
- 2026-10-12 — Environment hazard: this machine's shell exports `DEEPSEEK_API_KEY` (possibly a real key). `VIDBYTE_API_KEY` and `GROK_API_KEY` are user-scope registry variables, not inherited by Bash. Every test run uses `env -u DEEPSEEK_API_KEY`, and every test clears the environment with `patch.dict(os.environ, {...}, clear=True)`.
- S2 tests read private seams `TextModelRunner._config` (via `AgentFallback.build_runner(i)._config.credentials()`) and `BaseAgent._runner_for_model()`; keep both. `AgentFallbackSettings.resolved_models(primary=…)` is still called, with a keyless `FallbackModel`. `test_fallback_runner_inherits_the_agent_timeout` runs in DIRECT (a gateway runner floors 300 s to 630 s). `ProposerSpec(" DeepSeek ", …)` must normalize to deepseek. Fake keys are concatenated on purpose (C020, push protection). — *source:* S2
- AC-28 (`run_ci.py` green and C017 `CLEAN`) is owed by the implementer. — *source:* S2
- 2026-10-13 — S2 done after two rebases (52aab816 → b53c8811 → 595a7260). Orchestrator re-proved red at c88f2d32: full `308 failed, 3786 passed, 13 skipped, 7 errors`; pack `117 failed`; `import vidbyte` resolves to the worktree with PYTHONPATH. Spec set to `status: tests-written`; S3 launched.
- 2026-10-13 — S3 BLOCKED at row 17 on lint A006 (37 vs 34): cycle provider_keys → registries.models (M-18/M-19 env-var names) → modality_detector → provider_keys. Ruled option B without asking the user (code placement, answered by artifacts): move the provider→env-var table to `vidbyte/lib/constants/jev.py` (row 2) as `PROVIDER_API_KEY_ENV_VARS`; `ProviderModelRegistry.API_KEY_ENV_VARS` aliases the same dict object (row 6); the matcher imports the constant at module level. Sources: spec row 4 already lists `vidbyte.lib.constants.jev` among the matcher's allowed module-level imports; AGENTS.md puts constants in `vidbyte/lib/constants/`; §8.4 allows no second new file; option A breaks NFR-4's 300-line cap; option C (raise baseline) is forbidden. Both touched files are §12.3 rows.
- 2026-10-13 — S3 BLOCKED at the Phase 5 gate (all 41 rows committed, HEAD 8eaeb609, unpushed). Two rulings: (1) option B broke lint S014 (provider-model-registry-parity reads `API_KEY_ENV_VARS` as a dict literal in models.py; it is now an alias). Ruled option E: S014 reads the literal from `vidbyte/lib/constants/jev.py` `PROVIDER_API_KEY_ENV_VARS` when the registry attribute is not a literal. Parity stays equally strict (a missing literal still reports every provider). It is a `lint/` file outside §12.3, authorized here because it follows the A006 ruling, on condition of a mutation proof (delete one entry → S014 reports exactly 1) and the rule's own tests. F (two literals) rejected: drift. G (revert B) rejected: brings back the A006 cycle. (2) Straggler `tests/test_jev_compute.py::JevComputeCheckpointTests::test_a_chosen_specialist_runs_without_a_checkpoint` runs AUTO with no Vidbyte key (INV-7). Routed to the S2 test author to add `model_mode: TextModelMode.DIRECT` to that file's `_settings`, the same treatment as the other stragglers. The test checks checkpointing, not credentials.
- 2026-10-13 — S3 done. Orchestrator spot-check at 23dff561: tree clean and pushed; the only test commit since 140b17ed is S2's c0ab2b0a; lint/baseline.json only lowers A001 643→641; `SDK-LINT: PASS`; full `4101 passed, 13 skipped`; pack `117 passed`; remote CI + Static policy success at 3481ed66 (later commits are docs-only). S4 launched.
- 2026-10-13 — S4 done. Orchestrator spot-check: every review.md row carries the verifier's own evidence and a path:line. Re-ran `verify/calldepth.py` (6 chains at HEAD, matches R-1) and read S014 `:46` (`aliased = set(...) == {"__line__"}` treats `{}` as an alias, matches R-9). My earlier "Parity stays equally strict" condition on the S014 ruling was not met; R-9 restores it.
- 2026-10-13 — OPEN ITEM 1 (R-10) ruled option (a): widen all four `api_keys` annotations to accept the list form, using the same union BaseAgent/Runner/Session already use (`ProviderKeys | Iterable[str | None]` on TextModelConfig and JevAgentSettings; `Sequence[str | None]` on the two tuple fields). Narrow inline at the five read sites so S009 stays at 350, with no new helper inside `credentials()` (that would bring R-1 back). Source: Prompt 6 "List only". The user's chosen input form must type-check on every public surface that takes it. The repair agent records the §9.1/§8.5 annotation change in spec §17.
- 2026-10-13 — OPEN ITEM 2 (R-17) ruled: fix now with mode-agnostic wording, no transport plumbing and no §8.5 change. For a non-relayed gateway 402, the message says to top up the Vidbyte wallet. It may advise adding a provider key only as conditional on TextModelMode.AUTO, so it is correct both in AUTO-without-key and in VIDBYTE_MANAGED. Every substring an existing test asserts on is kept. Rejected "defer": Prompt 5 "Do not stop until this feature is perfect", and the message gives advice that has no effect. Rejected "plumb mode into the transport": it is a §8.5 change, and wording alone fixes the defect.
- 2026-10-13 — R-18 (`vb_test_` not reserved) stays a [scope-adding] follow-up for the final report, default no: Table F defines only `vb_live_`.
- 2026-10-13 — Routing for S5 iteration 1. First, a fresh test agent adds T-2..T-6 exactly as review.md specifies (T-6 red until R-6 lands). This is a fresh agent, not the S2 author, because ListAgents shows no resumable S2 agent. Then a fresh repair agent fixes R-1, R-6, R-7, R-8, R-9, R-10 and R-17 in one iteration (most of them edit model_configs.py), plus trivial Minors R-11..R-15. R-16 only if provider_keys.py stays ≤ 300 lines. The two agents run in sequence so they never commit to the shared worktree at the same time.

