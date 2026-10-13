# S3 implementer report: byok-api-keys (SDK half)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys`, branch `feat/byok-api-keys`, started at HEAD `140b17ed` on origin/main `595a7260`.

## 0. Drift check (Phase 2)

`git fetch origin` then `git diff --stat 52aab816..origin/main` over every spec §12.3 and §11 path: only `vidbyte/harnesses/serialization.py` (row 16, #993 lookbehind, already known) and `vidbyte/sessions/stores/file.py` (not a §12.3 row) changed. origin/main is still `595a7260`; no new commits since the S2 rebase. Proceeded.

`env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` printed the worktree path.

## 1. Progress log (one line per committed row)

| Row | Commit | Files | Tests run |
|---|---|---|---|
| 1 | cbf79d5f | `vidbyte/lib/enums/text_model.py` | contract constants test: 1 passed |
| 2 | 1bbb7215 | `vidbyte/lib/constants/jev.py` | `test_the_new_mode_and_the_wire_constants_have_their_contract_values`: 1 passed |
| 3 | c53e262b | `vidbyte/lib/dataclasses/agents.py` | `test_agent_runner_config_refuses_a_raw_list_and_a_string_mode`: 1 passed; `import vidbyte` OK |
| 41 | 7717d1d2 | `vidbyte/lib/dataclasses/__init__.py` | `from vidbyte.lib.dataclasses import ProviderKeys` OK |
| 4 | 1881d9de | `vidbyte/lib/registries/provider_keys.py` (new) | property file + matcher-only matching tests: 19 passed; 11 others wait on rows 7, 17, 24 (TypeError on `api_keys`); both import checks OK |
| 5 | 81f09bc2 | `vidbyte/lib/registries/__init__.py` | `from vidbyte.lib.registries import ProviderKeyMatcher` OK; both import checks OK |
| 6 | 6738ab9a | `vidbyte/lib/registries/models.py` | `-k "find_provider_api_key or decision_keeps"`: 2 passed; both import checks OK |
| 7 | 5b622500 | `vidbyte/lib/dataclasses/model_configs.py` | modes + matching + property: 34 passed; 12 others wait on rows 9, 10, 17, 24, 30 |
| 8 | 49826aaf | `vidbyte/lib/http/vidbyte_gateway.py` | `import vidbyte` OK (exercised through row 9) |
| 9 | 91acc96c | `vidbyte/lib/runners/text.py` | modes + failures + wire: 30 passed; 2 streaming tests wait on row 10 |
| 10 | 726a977c | `vidbyte/lib/runners/streaming_text.py` | modes + `tests/test_streaming_text_runner.py`: 37 passed |
| 11 | cf98d5fb | `vidbyte/lib/runners/utility.py` | Runner smoke check (text gets `api_keys` + `mode`, image gets `api_key`); signature defaults as §8.5 |
| 12 | 0a2fa7c9 | `vidbyte/lib/agents/modality_detector.py` | `-k create_runner` (M-17, both factories): 1 passed; image runner gets `key_for` |
| 13 | 6cd3c9f0 | `vidbyte/lib/runners/router.py` | same M-17 test: 1 passed |
| 14 | 6a3c7f17 | `vidbyte/lib/util/credential_keys.py` | policy check of the 12 names in the security test: all as expected |
| 15 | 79925328 | `vidbyte/lib/dataclasses/agent_descriptor.py` | security `-k "descriptor or credential_key or policy"`: 2 passed |
| 16 | 7a936087 | `vidbyte/harnesses/serialization.py` | security `-k redactor` + `tests/test_harness_redaction.py`: 6 passed |
| 19 | e2545ede | `vidbyte/agents/settings/fallback.py` | committed before row 18 so `AgentFallback.providers_in` never names a missing method; with row 18: `tests/test_agent_settings_validation.py` 10 passed, 5 waited on row 17 |
| 18 | 9bfa6760 | `vidbyte/agents/fallback.py` | as row 19; after row 17, `tests/test_agent_settings_validation.py`: 84 passed |
| 17 | 1648da90 | `vidbyte/agents/base.py` | `tests/features/sdk_provider_keys/` + `tests/test_agent_settings_validation.py`: 183 passed, 18 failed (every failure is a later row: fork/handoff/continual-trace/aggregate/Jev/paradigm/session call sites still pass `api_key`, plus README, scripts, Jev settings); both import checks OK |
| lint | 12d8aa74 | rows 3, 4, 7, 8, 12, 18 follow-up | a full `python lint/run.py` after row 17 showed S051 +4 (I001 on four new long imports), S062 +9 (implicitly joined message literals), S008 +1 (C901 on `create_runner`). Each message is now one literal, the imports use ruff's wrapped form, and `create_runner` moves option building into `_config_options`. Ruff on every changed file: no count above base |
| NFR-4 | 24de2be2 | `vidbyte/lib/registries/provider_keys.py` | the new module was 393 lines against NFR-4's "under 300". One-line messages and signatures, tighter comments, and `dict.fromkeys` in `_provider_names` bring it to 296 lines. Same 183 passed / 18 failed as before; both import checks OK |
| A006 | d079e32b | `vidbyte/lib/constants/jev.py`, `vidbyte/lib/registries/models.py`, `vidbyte/lib/registries/provider_keys.py` | orchestrator option B (ruling in pipeline.md at 6c55c282): the table is now `PROVIDER_API_KEY_ENV_VARS` in jev.py; `ProviderModelRegistry.API_KEY_ENV_VARS is PROVIDER_API_KEY_ENV_VARS` (and so is `vidbyte.lib.config.constants.API_KEY_ENV_VARS`) asserts True; `--rule A006`: `A006 directed-dependency-graph 34 34 RATCHETED`; provider-keys pack + settings + grader: 196 passed, 18 failed (same 18 as before) |
| 20 | b7852e75 | `vidbyte/agents/fork.py` | fork tests (`tests/test_agent_fork_isolation.py`, `test_fork_tool.py`, `test_workflow_agent_forks.py`) + provider-keys `-k fork`: 55 passed, 3 waiting on rows 22 and 31. The commit message cites AC-21 by mistake; the AC this row serves is AC-18 (left as is, no rewrite) |
| 21 | db434c31 | `vidbyte/agents/aggregation.py` | provider-keys `-k aggregate`: 3 passed; with `tests/test_aggregate_agent.py`: 40 passed, 1 waiting on row 31 (`Session._restore_agent` passes `api_key`) |
| 22 | bf00532f | `vidbyte/agents/handoff.py` | handoff + continual-trace test files: 134 passed; `test_forks_handoff_and_continual_trace_agents_carry_the_parents_record_and_direct_mode`: 1 passed (with row 23) |
| 23 | ef50907b | `vidbyte/agents/continual_trace.py` | as row 22 |
| 24 | a26348cf | `vidbyte/agents/jev/settings.py` | contract `test_jev_settings_check_their_mode_and_match_their_list`: passed; the field-order and settings-root tests now fail only on `AgentRoleSettings` (row 29) |
| lint | a5bc04a9 | `vidbyte/agents/aggregation.py` (row 21 follow-up) | the new dataclass import line was over isort's length (S051 I001); wrapped with `ruff --fix --select I001` |
| 25 | 51216098 | `vidbyte/agents/jev/agent.py` | `import vidbyte` OK; tested with rows 26 and 27 |
| 26 | bc22357f | `vidbyte/agents/jev/brief/writer.py` | tested with row 27 |
| 27 | 07df3733 | the seven Jev call sites (bulk_work, compute/clone, compute/swarm, done/handoff, done/reviewer, done/run_state, gate/clarification) | `tests/test_jev*.py`: 429 passed, 1 failed (`test_jev_compute.py::JevComputeCheckpointTests::test_a_chosen_specialist_runs_without_a_checkpoint`, see section 6); provider-keys pack: 106 passed, 11 failed (rows 29-39) |
| 28 | 55b05d48 (+ 74dccd92 rewrap) | `vidbyte/agents/codex/fallback.py` | comment text only; the attempt comment was rewrapped to 72 columns in a follow-up commit |
| 29 | 7c455e5a | `vidbyte/paradigms/context_minimal_fanout/types.py` | provider-keys `-k "field_order or string_bytes or role_settings"`: 3 passed |
| 30 | 4849dcc8 | `vidbyte/paradigms/context_minimal_fanout/paradigm.py` | `tests/test_context_minimal_fanout_agents.py`: 11 passed |
| 31 | 0e46f90b | `vidbyte/sessions/session.py` | sessions + restore + aggregate tests: 225 passed, 3 waiting on row 32 (`fork_recovery` passes `api_key`) |
| 32 | d40833a7 | `vidbyte/sessions/failure/recovery/fork_recovery.py` | provider-keys sessions + `tests/test_session_failures.py` + `tests/test_durable_sessions.py`: 173 passed |
| types | f73011fc | rows 3, 4, 7, 9 follow-up (`agents.py`, `provider_keys.py`, `model_configs.py`, `text.py`) | four `# type: ignore` comments I had added (a suppression the rules forbid) are replaced by real narrowing; provider-keys + managed pack + text runner tests: 183 passed, 2 failed (README row 33, scripts row 39) |
| 33 | e870813f | `README.md` | the managed section is the two-key section (relay, Vidbyte-paid, DIRECT, matching rules, modes, gateway rules; list form only, no `ProviderKeys`); `Session.resume(..., api_keys=[tenant_key])`; the waits section says "gateway attempt" / "gateway errors". Both README fact tests: 15 passed |
| 34 | 4cd8fc9b | `vidbyte/agents/README.md` | bare-name comment, `FallbackModel` example without `api_key` (key in the agent's `api_keys`), one paragraph on `vidbyte_api_key` / `api_keys` / `model_mode`; 21,365 characters (A009 limit 40,000) |
| 35 | 5b40db71 | `vidbyte/lib/registries/README.md`, `vidbyte/lib/registries/provider_keys.py` (two source comments) | `## Provider Key Format Sources`; every URL opened with WebFetch on 2026-10-13 (see section 7) |
| 36 | 56959e85 | `llms.txt` | `:1113` scrub sentence. The agent/model section ("Agents and Modalities") lists no agent parameters, so the conditional extra sentence was not added |
| 37 | 6a1c041d | `skills/usage/create_agent.md` | signature lines and the Model bullet list `api_keys`, `vidbyte_api_key`, `model_mode` |
| 38 | 61c7b4e4 | `skills/sessions.md` | `:174` scrub line |
| 39 | d301e2f6 | `scripts/test-new-runners.py`, `scripts/test-async-http-transport.py`, `scripts/test-openai-compatible-chat-trace-inputs.py` | every `TextModelConfig(` takes `api_keys=[FAKE_<PROVIDER>_KEY], mode=TextModelMode.DIRECT` (fakes built from parts, one per provider used); the Anthropic header check compares against the fake. `test-new-runners.py`: 43/43 passed. The other two fail exactly as they do at the base `140b17ed` (`BaseAgent(... runner=...)` TypeError at line 299; `test_existing_payload_fields_still_pass_through` 9/10), both pre-existing and not on this feature's path. Contract scripts test passes; ruff on the three files: 131 at base, 130 now |
| S009 | 4b23e3d9 | `vidbyte/agents/aggregation.py` (row 21 follow-up) | the full lint after row 39 showed S009 351/350: the one-line aggregator conditional left `provider` typed `str \| None`. Two branches let mypy narrow it; `--rule S009`: `S009 RATCHETED: 350 known finding(s)` / `SDK-LINT: PASS`; aggregate tests 41 passed |
| 40 | d83024ec | `lint/baseline.json` | full lint showed `A001 IMPROVED 643 -> 641`; `--rule A001 --update-baseline` changed only `"A001": 643` to `641` |

## 2. Budget (§8.4), final at d1eef1aa

- New files: 1 (`vidbyte/lib/registries/provider_keys.py`, 296 lines; NFR-4 limit 300).
- New classes: 3 (`ProviderKeys`, `ProviderKeyMatcher`, `TextCredentials`).
- New dependencies: 0.
- `vidbyte/agents/base.py`: `git diff --numstat 140b17ed -- vidbyte/agents/base.py` gives `34 8`, so +26 net (limit +30).
- Files touched outside §12.3: none. Every changed path is a §12.3 row; `provider_keys.py` (row 4) also took two source-comment fixes in the row 35 commits. No test file changed (`git log 140b17ed..HEAD -- tests/` is empty).

## 3. Deviations

1. `_check_record` also refuses a Vidbyte-prefixed key held as a provider key (INV-13).
2. Row 16 leaves out `(?:\w+_)?`; the #993 lookbehind already redacts prefixed names.
3. (Resolved by option B, d079e32b.) The provider-to-variable table moved from `ProviderModelRegistry` into `vidbyte/lib/constants/jev.py` as `PROVIDER_API_KEY_ENV_VARS`. `ProviderModelRegistry.API_KEY_ENV_VARS` is the same dict object, and the matcher imports the constant at module level, so it never imports the models registry. Spec line 1044's reference to `ProviderModelRegistry.API_KEY_ENV_VARS` still holds by identity.
4. `_provider_names` drops unknown provider names; the root's own provider check reports them.
5. `OPENAI_KEY_PREFIX` is a named `ClassVar` for table A's openai `sk-` rule.
6. The M-15 message names the mode as `TextModelMode.{name}`.
7. Row 19 was committed before row 18.
8. URL-only comment lines exceed 72 columns.
9. Row 12: the matcher import and the M-17 check sit in a new private leaf, `ModalityDetector._config_options`, not in `create_runner` itself, so `create_runner` stays under C901's limit (S008 at baseline).
10. Follow-up commits fix rows already committed, because the rules forbid a rebase: 12d8aa74 (lint), 24de2be2 (NFR-4 compaction), a5bc04a9 (I001), 74dccd92 (72-column rewrap), f73011fc (four `# type: ignore` comments I had added, replaced by narrowing), 4b23e3d9 (S009 narrowing in aggregation), d1eef1aa (URL-only source comment). 4b23e3d9's message was amended once, before any push, to correct its tags.
11. Row 20's commit message cites AC-21; the AC it serves is AC-18. Left as is (no rewrite).
12. Row 26: the brief writer names its provider `provider` (`brief.provider` if set, else the settings provider) and matches its own list only when it has one; without one it carries the main agent's record.
13. Row 29: `AgentRoleSettings.__post_init__` builds `ProviderKeys(vidbyte_api_key=...)` only to run the record's Vidbyte-key format check (INV-26); it keeps no record.
14. Row 33: two words outside the rewritten span changed ("one gateway attempt", "gateway errors"), because `AUTO` relay calls go through the gateway too.
15. Row 34: the `FallbackModel` example shows `temperature=0.2`, since a `FallbackModel` no longer carries a key; the key sits in the agent's `api_keys`.
16. Row 35: the spec's `sk-admin-` page (developers.openai.com admin_api_keys create) answered 404 and help.openai.com answered 403, so the README cites what opened: OpenAI's OpenAPI description (raw `openapi.yaml`, `POST /organization/admin_api_keys` example `value`). The Google API-keys page answered 301 to docs.cloud.google.com. The two code comments in `provider_keys.py` follow. Example keys are described, never copied.
17. Row 36: "Agents and Modalities" in `llms.txt` lists no agent parameters, so the conditional extra sentence was not added.
18. Row 37 shows `api_keys: Sequence[str] | None = None` as the row says (list form only, NG-19); the real annotation is `ProviderKeys | Iterable[str | None] | None`.
19. Row 39: `test-async-http-transport.py` (TypeError at line 299, `BaseAgent(... runner=...)`) and `test-openai-compatible-chat-trace-inputs.py` (9/10) fail identically at base `140b17ed`; not fixed (outside the row; CI only compiles scripts).
20. Semgrep ran from a scratch venv (semgrep 1.170.1 + mcp 1.23.3): the global semgrep 1.170.1 cannot start, because the global `mcp` is now 2.3.0, which removed `mcp.server.fastmcp`.

## 4. Gates at HEAD d1eef1aa

Full lint, `env -u DEEPSEEK_API_KEY PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) python lint/run.py` (also the first step of `run_ci.py --stage source`):

```
A006   directed-dependency-graph                  34     34 RATCHETED
C017   platform-route-contract                     0      0 CLEAN
S009   staged-mypy-contracts                     350    350 RATCHETED
S014   provider-model-registry-parity             14      0 REGRESSED
S014 REGRESSED: 14 finding(s), allowance 0.
SDK-LINT: FAIL
CI failed: Command failed with exit code 1: ...python.exe ...lint/run.py
```

S014 is the only regression; see section 6. Every other rule is RATCHETED, CLEAN, or IMPROVED.

- Source stage (`env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`): FAIL at its first step, lint (S014). Its later steps, run one by one: `python -m compileall -q vidbyte` exit 0; `context write-path integrity: ok`; `context primitive introductions: ok`; `reasoning trace contracts: ok (182 tools, 55 shapes)`.
- Full pytest (`env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/`): `1 failed, 4100 passed, 13 skipped in 34.43s`. The one failure is the straggler in section 7.
- Package stage (`env -u DEEPSEEK_API_KEY python scripts/run_ci.py --stage package`): `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.`
- Semgrep 1.170.1 (static-policy.yml commands): `semgrep --test ...`: `1/1: All tests passed`; `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`: `Ran 1 rule on 894 files: 0 findings.`; the same rule on `vidbyte/lib/registries/provider_keys.py`: `Ran 1 rule on 1 file: 0 findings.`
- Feature packs (`tests/features/sdk_provider_keys/ tests/features/sdk_managed_text/`): `156 passed`.

## 5. Resolved: import cycle that D-21 did not resolve (§14 "Ask first"; ruling: option B)

The three new A006 findings are one cycle:

```
vidbyte/lib/registries/provider_keys.py | from vidbyte.lib.registries.models import ProviderModelRegistry   (deferred, inside match)
vidbyte/lib/registries/models.py        | from vidbyte.lib.agents.modality_detector import ModalityDetector (module level, pre-existing)
vidbyte/lib/agents/modality_detector.py | from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher (function-local, row 12)
```

- The spec needs all three edges:
  - M-18 and M-19 must name the provider's variable (`DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY`, …). Spec line 1044 says those names come from `ProviderModelRegistry.API_KEY_ENV_VARS`, and AC-32, AC-38 and EC-35 test them.
  - Row 12 requires the function-local matcher import in `modality_detector`.
  - `models.py` already imports `ModalityDetector` at module level.
- NFR-4 requires A006 to stay at baseline, and A006 counts function-local imports.
- Evidence: I swapped the deferred `ProviderModelRegistry` import for a placeholder (uncommitted, reverted). `python lint/run.py --rule A006` then printed `A006 directed-dependency-graph 34 34 RATCHETED`, against 37 with the import.

The options:

- **A. Move the table into the matcher.** `ProviderKeyMatcher.API_KEY_ENV_VARS` would hold the 14 entries, and `ProviderModelRegistry.API_KEY_ENV_VARS` would alias that same dict. `models.py` would import `provider_keys` at module level, which forms no cycle. Rows 4 and 6 cover both files. The cost: `provider_keys.py` grows to about 312 lines, over NFR-4's 300.
- **B. Move the table into `vidbyte/lib/constants/jev.py` (row 2).** It would become `PROVIDER_API_KEY_ENV_VARS: dict[ModelProvider, str]`, next to `VIDBYTE_API_KEY_ENV_VAR` and the provider-key header constants. That module already imports `ModelProvider`.
  - `ProviderModelRegistry.API_KEY_ENV_VARS` stays as an alias of the same dict, so `vidbyte.lib.config.constants` and every reader are unchanged.
  - The matcher imports the constant at module level and drops its `models` import.
  - `provider_keys.py` stays at about 297 lines. No new file is needed.
- **C. Raise the A006 baseline to 37.** My rules forbid it and NFR-4 rules it out. It is listed only for completeness.

**Recommendation: B.** It is the smallest change that leaves A006 at 34 and `provider_keys.py` under 300 lines. It keeps one table, and it changes no public name. The one oddity is that a table covering every provider sits in the Jev constants module. That module already holds the gateway's other key constants.

Ruling: option B, applied in d079e32b. A006 is back to 34.

## 6. Open: S014 regression from option B (blocks the push)

`lint/rules/s014_provider_model_registry_parity.py` reads `API_KEY_ENV_VARS` statically, as a dict literal inside `class ProviderModelRegistry` in `vidbyte/lib/registries/models.py` (`_class_dict`, `PARITY_MAPS`). Option B (d079e32b) made that attribute `= PROVIDER_API_KEY_ENV_VARS`, a name, so the rule finds no entries and reports all 14 providers missing: `S014 REGRESSED: 14 finding(s), allowance 0`. The option B proof ran only A006 and tests, so it missed this. The ruling (one dict object, literal in `constants/jev.py`) and S014 (literal in `models.py`) cannot both hold, and my rules forbid editing a lint rule or raising a baseline without a ruling.

Options:

- **E. S014 follows the alias.** When the class attribute holds no literal, the rule reads `PROVIDER_API_KEY_ENV_VARS` from `vidbyte/lib/constants/jev.py` with the same ModelProvider-key extraction. Parity stays exactly as strict (14 entries checked against the enum). Trial patch, applied and reverted, saved at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/5bfc4a32-d2a9-4a4d-a6e5-3f472a0fe403/scratchpad/option-E-s014.patch` (about 15 lines): `S014 provider-model-registry-parity 0 0 CLEAN` / `SDK-LINT: PASS`. Cost: a change under `lint/`, outside §12.3.
- **F. Two literals.** Restore the 14-entry literal in `models.py` and keep the one in `jev.py`. S014 and A006 both pass, but the ruling's "same dict object" breaks, the table is duplicated, and nothing guards drift (I may not add a test).
- **G. Revert option B and break the cycle elsewhere.** Every other route needs a §8.5 signature change (the matcher takes the variable names as an argument) or a façade import that only hides the cycle from A006, which A006's own guidance rejects.

Recommendation: **E**. It keeps the ruling, one table, and the rule's full strength.

## 7. Stragglers (pre-existing tests that fail only because of the new key rules; not edited)

- `tests/test_jev_compute.py::JevComputeCheckpointTests::test_a_chosen_specialist_runs_without_a_checkpoint`: `ConfigurationError: Missing Vidbyte API key. Pass vidbyte_api_key or set VIDBYTE_API_KEY, or use mode=TextModelMode.DIRECT ...`, wrapped as `AgentExecutionError` at `vidbyte/agents/base.py:936`. `_settings()` builds `JevAgentSettings(..., api_keys=["sk-main-key"])` in the default `AUTO` with no Vidbyte key, and the agent builds its runner in `generate_reply` (pre-existing), so INV-7 (table R, M-9) makes it raise. S2 moved this file to `api_keys` in 938fb795 without adding `model_mode=TextModelMode.DIRECT` or a `VIDBYTE_API_KEY`. Test vs spec: INV-7. Likely fix (S2's): add `"model_mode": TextModelMode.DIRECT` to `_settings`.

## 8. Not done because of section 6 and 7 (BLOCKED)

Push, draft PR, the spec frontmatter `pr:`/`status:` commit, CI and Static policy dispatch, and Phase 7 (§6.2 Proof cells, §17 r5 row). Everything is committed locally on `feat/byok-api-keys` at d1eef1aa plus this report's commit; nothing is pushed.
