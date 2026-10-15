# S6 PR author report: byok-api-keys (SDK)

**Status: BLOCKED.** The merge of `origin/main` is clean, but the merged tree fails 4 tests. All 4 come from one test helper that main added (#1038), and that helper still passes the `api_key=` argument this PR removed. Per the stage rules I did not fix it and did not push. I undid my own unpushed merge with `git reset --hard 58fd652b`. The branch, the remote, and PR #1027 are unchanged. I did not write `pr-body.md`, finalize the spec, or edit the PR.

## 1. Merge

- `git fetch origin main` gave `origin/main` = `8387d666` (#1039). The branch was 14 commits behind it and 124 ahead. The merge base is `595a7260` (#1023).
- `git merge --no-ff origin/main -m "Merge origin/main into feat/byok-api-keys"` produced merge commit `29fd3578` with no textual conflict. Main's side touched 47 files: +752 / -46.
- `29fd3578` was never pushed. `origin/feat/byok-api-keys` is still `58fd652b`. No CI or Static policy run was dispatched.

## 2. Gates on the merged HEAD `29fd3578`

| Gate | Command | Final lines |
|---|---|---|
| Lint | `PYTHONIOENCODING=utf-8 env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" python lint/run.py` | `SDK-LINT: PASS` |
| Source | `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" python scripts/run_ci.py --stage source` | `4 failed, 4137 passed, 13 skipped in 38.04s` / `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| Package | `env -u DEEPSEEK_API_KEY -u PYTHONPATH python scripts/run_ci.py --stage package` | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Semgrep test | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` (semgrep 1.170.1, scratchpad venv) | `1/1: ✓ All tests passed` |
| Semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | `Ran 1 rule on 894 files: 0 findings.` |

`import vidbyte` resolved to the worktree (`…\vidbyte-sdk-byok-api-keys\vidbyte\__init__.py`) for every PYTHONPATH run.

## 3. The failing tests

```
FAILED tests/test_output_schema_provider_dialect.py::GeminiSchemaWithFunctionsTests::test_gemini_2_with_functions_and_no_system_creates_the_instruction
FAILED tests/test_output_schema_provider_dialect.py::GeminiSchemaWithFunctionsTests::test_gemini_2_with_functions_sends_schema_as_instructions
FAILED tests/test_output_schema_provider_dialect.py::GeminiSchemaWithFunctionsTests::test_gemini_2_without_functions_keeps_native_schema
FAILED tests/test_output_schema_provider_dialect.py::GeminiSchemaWithFunctionsTests::test_gemini_3_with_functions_keeps_native_schema
================= 4 failed, 4137 passed, 13 skipped in 38.04s =================
```

- **Cause.** All four tests call the helper `_gemini_payload`, at `tests/test_output_schema_provider_dialect.py:245` in the merged tree:
  `return GeminiProvider(model=model, api_key="k")._create_payload(config, "triage", system, None)`
  `GeminiProvider._build_text_config` (`vidbyte/providers/gemini.py:49`) forwards the option to `TextModelConfig(**config_options)`, which raises `TypeError: TextModelConfig.__init__() got an unexpected keyword argument 'api_key'`.
- **Origin.** The helper arrived in main's `ab47a5f4` (#1038, "output_schema agents run on Gemini 2.x"). At `58fd652b` the file does not contain it, so the fix can only land on top of the merge.
- **Only straggler.** `git diff 595a7260 origin/main | grep '^+.*api_key'` returns exactly this one line. No other code that main added uses the removed argument.
- **Likely fix (for the test author; I did not apply it).** Change the helper to match line 229 of the same file, which this PR already migrated:
  `GeminiProvider(model=model, api_keys=[GEMINI_TEST_KEY], mode=TextModelMode.DIRECT)`.
  Both names are already imported in that file. The failures are `TypeError`s at construction, so they are deterministic, not flaky.

## 4. Work already done that stays valid on resume

**Diff read.** I read `git diff origin/main...HEAD` for every non-test source file:

- matcher, record, and runner: `provider_keys.py`, `model_configs.py`, `agents.py` (ProviderKeys, AgentRunnerConfig, FallbackModel), `vidbyte_gateway.py`, `text.py`, `streaming_text.py`, `utility.py`, `router.py`, `modality_detector.py`
- registries and constants: `models.py`, `constants/jev.py`, `enums/text_model.py`, `credential_keys.py`
- agents: `base.py`, `fallback.py`, `settings/fallback.py`, `fork.py`, `aggregation.py`, and Jev settings, agent, brief writer, and the 8 Jev children
- sessions, harness redactor, and the context-minimal-fanout paradigm

The call path matches spec §5: `Agent` → `ProviderKeyMatcher.match` → `AgentRunnerConfig.api_keys` → `Runner._config_options` (text gets the record plus the mode) → `TextModelConfig.__post_init__` (the record passes through) → `TextModelRunner.__init__` → `credentials()` → `TextCredentials` → `VidbyteGatewayTransport(api_key=Vidbyte key, provider_api_key=…)`. A DIRECT call keeps the adapter's own transport and vendor auth.

**Spec §4 snippet, run offline on merged tree `29fd3578`.**

- Setup: script `scratchpad/s6_snippet_run.py`. Fake keys were built by concatenation (`VIDBYTE_API_KEY_PREFIX + "a"*40`, `"xai-" + "a"*40`, `"sk-ant-" + "b"*40`) and set as environment variables. `vidbyte.lib.runners.text.HttpTransport` was patched with a scripted 200 chat-completions `isDone` answer, and every non-loopback socket connect was blocked.
- The snippet ran exactly as written and printed `Hi`.
- Wire record: 1 request. `url_is_gateway=True envelope_provider='xai' envelope_model='grok-4.5' bearer_is_vidbyte_key=True relay_header_sent=True relay_header_is_xai_key=True anthropic_key_anywhere=False idempotency_key_sent=True`.
- The `offline` agent was built with `model_mode=direct` and holds no Vidbyte key.

**Breaking-change claims, checked offline at `58fd652b`** (`scratchpad/s6_breaking_checks.py`, environment cleared, fake keys):

- `Agent(api_key=…)` raises `TypeError: BaseAgent.__init__() got an unexpected keyword argument 'api_key'`. `TextModelConfig(api_key=…)` raises the same `TypeError`. There is no alias.
- **Correction to the briefing.** AUTO with provider keys and no Vidbyte key does not raise when the `Agent` is constructed.
  - It raises when the text runner is built, before any request.
  - `TextModelRunner(provider="xai", …, api_keys=[xai])` raises `ConfigurationError: Missing Vidbyte API key. Pass vidbyte_api_key or set VIDBYTE_API_KEY, or use mode=TextModelMode.DIRECT to call the provider with your own key and no Vidbyte fee.`
  - Through an agent, the first `agent.run` raises `AgentExecutionError: Agent 'a' failed to generate a reply.`, with that `ConfigurationError` as its `__cause__`.
  - This matches spec §5 ("raises when the runner is built"). The PR body must say "when the runner is built", not "at construction".
- In AUTO, `StreamingTextModelRunner` raises `UnsupportedProviderError: StreamingTextModelRunner streams only straight from the provider, and this config's mode is TextModelMode.AUTO. Set mode=TextModelMode.DIRECT …`. In DIRECT it builds.
- `create_runner_for_modality(None, provider="xai", model="grok-4.5", api_key=…)` raises `ConfigurationError: create_runner takes api_keys, a list of provider keys, for a text model; api_key is not accepted.` (M-17).
- A Grok key on an openai agent raises M-18 at `Agent` construction.
- Additional breaking items found in the diff, to list in the body:
  - `FallbackModel` lost `api_key`.
  - `AgentRunnerConfig.api_key` became `api_keys: ProviderKeys`, plus `model_mode`.
  - `JevAgentSettings.api_key`, `JevRunBriefSettings.api_key`, and `AgentRoleSettings.api_key` became `api_keys`.
  - `Session.resume` / `fork_from` and `BaseAgent.restore` take `api_keys` (+ `vidbyte_api_key`).
  - `ProviderModelRegistry.find_vidbyte_api_key`, `vidbyte_key_follows_provider`, `TextModelConfig.is_vidbyte_managed`, and `TextModelConfig.resolved_vidbyte_api_key` are removed.
  - Gateway failures now read `Vidbyte gateway <provider> request failed: …` (was `Vidbyte managed …`).

## 5. Open items found so far (no source or test changed)

1. **Straggler (blocking).** `tests/test_output_schema_provider_dialect.py:245` (merged tree), as described in §3.
2. **Minor wording, not raised in any review.** `TEXT_REMEDY` (`vidbyte/lib/dataclasses/model_configs.py:51`) tells the caller to "use mode=TextModelMode.DIRECT". The streaming refusal and the gateway-shape refusals use the same `mode=` wording. That is right for `TextModelConfig`, but an `Agent` caller's argument is `model_mode=`. Candidate follow-up; it does not block.
3. **R-D2 confirmed in code.** `CredentialKeyPolicy._SECRET_KEYS` (`vidbyte/lib/util/credential_keys.py:55-80`) holds `provider_key` but not `providerkey` or `provider_keys`, and no suffix catches `provider_keys`. This is the known follow-up.

## 6. Not done (resume from here)

Steps 1 (re-merge, gates, push, remote checks) through 9 remain. When the straggler is fixed on top of a merge commit:

1. Re-run all 5 gates on that HEAD.
2. Push, dispatch CI and Static policy, and confirm `headSha`.
3. Write `pr-body.md`, using the snippet and check results above, re-run on the new HEAD.
4. Finalize the spec frontmatter and the §17 r5 row, commit, push, and re-dispatch.
5. Update the PR title and body, keeping it a draft.

Field-guide candidates: not reached.

## 7. Worktree state left behind

HEAD is `58fd652b`, equal to `origin/feat/byok-api-keys`. The only change is this report, which is untracked and not committed.
