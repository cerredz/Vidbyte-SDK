LENS: conformance
VERDICT: SOUND — Every repair commit (R-1 to R-6, M-1, M-2, M-3, M-4, M-5, M-7, M-9, M-14) holds against its evidence, and none introduced a regression. Three Minor items remain: two are docs drift for the S6 sync, and one is a test gap.

Scope of this re-review: `git diff 573a9f5f..c826ec07` (20 files), read file by file with the whole of each changed file open, plus the six orchestrator focus items. In this range, production behavior changed in exactly two methods:
- `TextModelConfig.validate` (R-2);
- `StreamingTextModelRunner._refuse_managed_streaming` (M-1).

Every other production file is AST-identical to 573a9f5f once comments and docstrings are ignored (command 9). The S4 conformance verdicts for code paths the repair did not touch therefore carry over unchanged.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- **R-2 is a true no-op on behavior.** `validate()` now calls `ProviderModelRegistry.resolve_api_key(provider, self.api_key)` (`vidbyte/lib/dataclasses/model_configs.py:105`).
  - I compared 1,944 configs (6 providers × 9 explicit keys × 9 environments × 2 modes × 2 endpoints) between 573a9f5f and HEAD. `validate`, `is_vidbyte_managed`, `resolved_api_key` and `resolved_vidbyte_api_key` give identical results in every case.
  - One BYOK `validate()` now makes `{is_vidbyte_managed: 1, find_vidbyte_api_key: 1, resolved_api_key: 0}` calls.
  - Keep it.
- **The deadline test file is deterministic and kills every mutant in the table** (`tests/features/sdk_managed_text/test_managed_text_deadline.py`).
  - How it works: a fake loop clock starts at 1000 s, and the steps of 0, 600 and 629.5 s land exactly on the boundaries.
  - `shorten_attempt` gives "4 failed, 3 passed" on 10 of 10 runs. The "timing luck" in verify-log applies only to the older pack, which survives it on 4 of 4 runs.
  - Do not swap in a real clock.
- **The R-4 wrap is the safe form.** It is a context manager inside the async body (`tests/test_jev_run_state_relation.py:501`), not a decorator.
  - `git diff -w` shows no assertion change.
  - Full suite with a fake live-format `VIDBYTE_API_KEY` and a network block: 3011 passed, 1 skipped, and 0 blocked requests. A positive control, run outside pytest, shows the block catches a gateway POST.
- **The boundaries still hold.** The vendored contract is byte-identical to backend `ceabda93e` (blob `56d4d0b3…`, no BOM). The repair touched nothing under `lint/`, `vidbyte/providers/`, `vidbyte/agents/`, `pyproject.toml` or `vidbyte/lib/http/__init__.py`. Lint ends with `SDK-LINT: PASS` (A002 652, C017 0, C018 1, C019 0, C020 2, S020 1/1, S064 4/4). The §4 snippet still prints exactly `openai gpt-5.5` / `Hi` / `2` from one gateway POST.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Minor] [deviations / docs drift] docs/spec/managed-generative-models/spec.md:241 (end of §6.2); test-plan.md:3, :20; vidbyte/lib/http/vidbyte_gateway.py:9 — The r5 deadline now has tests, but the spec and its other records still do not point to them
  Evidence:
  - `grep -c "AC-28\|test_managed_text_deadline" spec.md` → 0. §6.2 ends at AC-26 (line 241), so no acceptance row or proof covers INV-10's or INV-16's cumulative deadline or EC-38. review.md R-6's smallest fix explicitly required "add AC-28 to spec §6.2".
  - `test-plan.md:20` still maps EC-38 to `test_gateway_errors_raise_credential_safe_errors_after_one_post_or_three_for_a_502`. That test cannot fail on the deadline: with the older 32 tests alone, `MUT=shorten_attempt` gives "32 passed, 7 deselected" on 4 of 4 runs, and S4 showed the same for `no_deadline`, `deadline_gt` and `deadline_after_first`.
  - `test-plan.md:3` reads "spec.md r4", but the spec is r5.
  - `vidbyte_gateway.py:9`, the TESTS field of the module header, lists failures, wire_contract and acceptance, but not the deadline file that tests this module's deadline (grep count 0).
  Failure: A reader, or a later agent, who follows the spec's proof column or the test plan for EC-38 lands on a test that passes with the deadline deleted. Nothing in the spec, the test plan or the module header names the file that actually guards the rule. This is the same false coverage claim that R-6 cited, now only in the documents.
  Smallest fix:
  - Add an AC-28 row to §6.2 (Given a managed call and the gateway transport driven under a fake loop clock; When 502 answers take 0, 600 or 629.5 s; Then 3, 2 or 1 POSTs, waits `[0.5, 1.0]`, `[0.5]` or `[]`, every attempt at 630.0, and messages "re-sends in this call: 2/1" or "did not re-send"), with the four `CumulativeDeadlineTests` and `LastAttemptTests` names as proof.
  - Repoint `test-plan.md:20` EC-38 to the new file and set its header to r5.
  - Add the file to the gateway module's TESTS line.
  Rating and plan: Minor. Nothing changes behavior, and the test itself exists and is strong. The orchestrator's plan, that the S6 PR author syncs these, holds with one caveat: `vidbyte_gateway.py:9` is a production file. S6 needs that one header line in its grant, or it becomes a follow-up.
  Spec IDs: INV-10, INV-16, EC-38, §9.2 "Retries"; review R-6 (doc step); agentic-engineering file-header practice.

R-C2 [Minor] [request fidelity / docs drift] README.md:269-270; vidbyte/lib/runners/streaming_text.py:27-28, :58-59; spec.md:262 (EC-16) — M-1 removed the dead-end streaming advice from the error message, but the same advice remains on three other surfaces
  Evidence:
  - `README.md:269-270`: "**Streaming:** `StreamingTextModelRunner` refuses managed mode. Use `TextModelRunner`, or set the provider's own key to stream."
  - `streaming_text.py:27-28` (main-function narration): "so the caller learns why and how to stream with their own key instead."
  - `streaming_text.py:58-59` (`@intent`): "refusing here sends nothing and names both ways forward."
  - EC-16 (`spec.md:262`) still gives only "Use TextModelRunner, or set `<PROVIDER>_API_KEY` to stream with your own key." The §17 row at `spec.md:911` records the difference "for the record".
  - Probe: with `VIDBYTE_API_KEY` set and provider gemini, the managed refusal now correctly says "streaming supports only anthropic, openai, so setting GEMINI_API_KEY would not make gemini stream either". If the reader follows the README instead and sets `GEMINI_API_KEY=fake-gemini`, the result is `UnsupportedProviderError | StreamingTextModelRunner supports: anthropic, openai.`
  Failure: A developer on gemini, xai, deepseek or kimi (4 of the 6 managed providers) who reads the README sets their provider key to stream and gets a second refusal. That is the exact dead end M-1 was meant to remove. In addition:
  - the two code comments now describe behavior that is gone for those providers (AGENTS.md style 2: "update its comments in the same edit so they never describe behavior that is gone");
  - EC-16 contradicts the code for those providers.
  Smallest fix:
  - README: "Use `TextModelRunner`, or, for OpenAI and Anthropic, set the provider's own key to stream."
  - `streaming_text.py:27-28`: "… so the caller learns why, and how to stream with their own key where this runner can stream that provider."
  - `streaming_text.py:58-59`: "names the ways forward that exist for this provider."
  - EC-16: add the second wording for the providers that cannot stream.
  The README and spec edits fit the S6 docs sync. The two comment edits touch a production file.
  Spec IDs: AC-18 (README states the limitations accurately), EC-16, AC-13, FR-7; review M-1. The comment part is [out-of-lens] (conventions, AGENTS.md style 2) and was introduced by repair commit 69ee8aaa.

R-C3 [Minor] [verify-don't-trust / test quality] tests/features/sdk_managed_text/test_managed_text_deadline.py:40, :100, :125 — Every deadline case uses a timeout equal to the floor, so a deadline taken from the floor constant instead of the call's own timeout passes all 39 tests
  Evidence:
  - The file pins `FLOOR_TIMEOUT = 630.0` (`:40`), passes it as the only timeout (`:100`), and asserts `timeout_seconds == 630.0` (`:125`).
  - I ran an inline pytest plugin, with no file written, that replaces `deadline = loop.time() + timeout_seconds` with `deadline = loop.time() + VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS` in `vidbyte_gateway.py:171`. Result on the full pack: "39 passed in 0.31s".
  - A direct probe with `timeout_seconds=900` and a 502 after 700 s gives:
    - real code: `(2 POSTs, [900.0, 900.0], waits [0.5], "re-sends in this call: 1")`;
    - mutant: `(1 POST, [900.0], waits [], "…the call's 900 s timeout left no time for another attempt.")`.
    The mutant also states a false reason.
  Failure: A later edit that ties the deadline to the 630 s floor constant breaks INV-10 for every caller whose timeout is above 630 s (AC-9 lists 900.0). For example, a 502 after 700 s is not re-sent although the spec allows one, and the error blames the 900 s timeout. No test fails.
  Smallest fix: Add one case to `CumulativeDeadlineTests`: timeout 900.0 and step 700.0 → 2 POSTs, waits `[0.5]`, both attempts at 900.0, and "re-sends in this call: 1". This needs `GatewayCall` and `assert_full_timeout_and_one_key` to take the timeout as a parameter instead of the hard-coded 630.0. The code is correct today, so this protects against a future regression and does not fix a current one.
  Spec IDs: INV-10 ("deadline = loop.time() + timeout_seconds, taken once before the first POST from the floored timeout"), D-10, §9.2 "Retries", AC-9.

VERIFIED CLAIMS:

Orchestrator focus items (verdict on each):
1. **FEATURE.md regression: none; the premise does not hold.** The sentence "Nothing else is retried, including a missing response." is still present, at `tests/features/sdk_managed_text/FEATURE.md:12`.
   - `git diff --word-diff 573a9f5f..c826ec07` shows M-14 only replaced "s." with "s, and only while the call's one deadline … made." before that sentence. Nothing was deleted.
   - The sentence is still the code's behavior: `retryable()` returns False when no answer arrived (`vidbyte_gateway.py:69-70`), and it re-sends only a non-JSON-object body or a 409 or 502 (`:71`).
   - Each attempt leaves the inner `retry_count` at its default of 0 (`vidbyte_gateway.py:203`; `transport.py:40`), so there is no hidden inner retry either.
2. **R-4 isolation: holds.** The wrap is `with patch.dict(os.environ, {"VIDBYTE_API_KEY": ""}):` inside `async def test_legacy_mode_keeps_per_run_begin_semantics` (`tests/test_jev_run_state_relation.py:501`). It is not a decorator, and `patch` was already imported (`:21`).
   - `git diff -w` adds only `import os`, a 3-line comment and the `with` line. No assertion changed.
   - Run alone with a fake key under netstack with `-s`: "1 passed", 0 BLOCKED, no "never awaited" warning.
   - Is the test still meaningful? Yes. A blank value is treated like an unset one by both resolvers (`registries/models.py:192` and `:201`), so the test runs exactly as it does in CI. At base, `VIDBYTE_API_KEY` had no effect on text runners.
3. **R-2 fall-through order and placeholder: holds on every path.** Evidence: the 1,944-case differential (0 differences), and an AST comparison showing `TextModelConfig.validate` is the only changed method in `model_configs.py`.
   - The order still comes from the unchanged `find_vidbyte_api_key` (`registries/models.py:181-192`): explicit key, then provider env var, then `VIDBYTE_API_KEY` for the six managed providers only.
   - The BYOK branch's `resolve_api_key` reads explicit key, then env var, exactly as the base `resolved_api_key()` did.
   - The placeholder branch in `resolved_api_key` (`model_configs.py:137-138`) is unchanged.
   - A non-string `api_key` in BYOK still raises `AttributeError`, as at base, in 108 of 108 such cases.
4. **R-6 test quality: holds for the table, with a gap beyond it (R-C3).** Kills with the new file:
   - `no_deadline` 2 failed; `deadline_gt` 1; `deadline_after_first` 2; `shorten_attempt` 4; `resends_off_by_one` 1; `auto_shape_unchecked` 2; `mut_first` 2.
   - `shorten_attempt` failed 4 tests on 10 of 10 runs, and the whole pack gives "4 failed, 35 passed" on 3 of 3.
   - Each of the 7 tests is killed by at least one mutant.
   - The "timing luck" survives only without the new file: "32 passed, 7 deselected" on 4 of 4 runs.
5. **Docs drift: confirmed and rated Minor; the S6 plan holds** (R-C1, R-C2).
   - Correction to the briefing: there is no AC-28 row at all (grep count 0), so this is a missing row, not a stale one.
   - The orchestrator's list was missing two items: the README streaming line, and the gateway module's TESTS header, which is a production file and needs a grant.
6. **Contract: byte-identical.** All four of these give `56d4d0b373994f5de6affd675ed4c209e64d589d`:
   - `git -C …/vidbyte show ceabda93…:contracts/vidbyte-platform-contract.json | git hash-object --stdin`;
   - `git rev-parse HEAD:lint/…json`;
   - `git rev-parse c826ec07:lint/…json`;
   - `git hash-object` of the working copy.
   The first bytes are `{\n`, so there is no BOM. The file is untouched in the repair range.

Each repair against its evidence:
- **R-1 holds.** The markers now sit directly above the code they explain:
  - `text.py:38`, above `self._managed =` at `:45`;
  - `text.py:70`, above `transport = self._transport` at `:75`;
  - `vidbyte_gateway.py:156`, above `gateway_headers =` at `:161`;
  - the BYOK narration at `model_configs.py:139-140`, above the BYOK return at `:141`.
  A002 is 652 with no new name.
- **R-5 holds.** An awk scan of the seven touched files finds an `@intent` preceded by a comment only at the 6 pre-existing Decision markers (`model_configs.py:421-489`). The PR adds 17 `@intent` lines (16 plus M-5). No `#` line added in the repair is over 72 columns.
- **M-5 holds.** `vidbyte_gateway.py:131` has the `@intent`, and the claim it makes (one transport per call) matches `text.py:76-82`.
- **M-1 holds in code.** A probe of all six providers: openai and anthropic keep "set <ENV> to stream with your own key". gemini, kimi, xai and deepseek get "streaming supports only anthropic, openai, so setting <ENV> would not make <p> stream either". All six name managed mode, `TextModelRunner` and the env var, which satisfies AC-13 and §12.3 row 9. The gaps it left are R-C2.
- **M-2 holds.** A 404 `{"detail":"Not Found"}` gives one POST and "openai returned HTTP 404 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed." This matches EC-26 and deviation 1. The vendored contract has the four `agent_run_*` codes, so the §15 risk note is true.
- **M-3 holds.** Backend spec `:68` (NG-9) and `:1225` (Q-3) say what NG-5 now cites.
- **M-4 holds.** `README.md:286-287` and AC-18 are both qualified by the replay-store outage. Every re-send starts within 630 s of the first POST, which is inside the 900 s replay window, so "only an outage … can bill a retry twice" holds for the SDK's own re-sends.
- **M-7 holds.** The `jev.py` header fields now cover the gateway values, the citation resolves, and the `model_configs.py` inventory mentions the placeholder.
- **M-9 holds.** `mut_first` and `auto_shape_unchecked` are killed (above).
- **M-14 holds** (focus item 1).
- **R-3 holds.** S020 is 1/1, and the pack README index lists the new file.

Per-ID walk (the repair delta only; untouched code keeps its S4 verdict):
- **INV-4, INV-5, INV-17, INV-18, INV-21, FR-2, FR-3, AC-3, AC-4, AC-5, AC-22: held.** The R-2 change is proven equivalent.
- **INV-13, FR-7, AC-13: held.** EC-16's text is stale (R-C2).
- **INV-10, INV-16, EC-38: held in code and now tested.** The proof trail is missing (R-C1) and there is a gap above the floor (R-C3).
- **AC-1: held.** I ran the §4 snippet as written, with `vidbyte.lib.runners.text.HttpTransport` replaced by a recorder:
  - output `openai gpt-5.5` / `Hi` / `2`;
  - 1 request, `POST https://vidbyte-backend.onrender.com/api/v1/models/generate`;
  - headers exactly `authorization`, `content-type: application/json` and a 32-hex `idempotency-key` equal to the `idempotency_key` argument;
  - envelope `{"provider": "openai", "model": "gpt-5.5", "body": {"model": "gpt-5.5", "input": "Say hi in one word.", "max_output_tokens": 8192}}`, timeout 630.0;
  - building the `claude` runner sent nothing.
  The test-plan form of AC-1 also passes.
- **AC-14, AC-17, FR-11, FR-13, NFR-5: held** (lint and contract above). I did not run `run_ci.py`: its package stage installs the package, which the briefing forbids. I ran its components (lint, full suite) directly.
- **AC-18, FR-12, NFR-8: held**, apart from the streaming line (R-C2).
- **AC-19, NFR-4: held.** The repair touched no production file outside `vidbyte/lib/`.
- **NFR-6: held.** 0 network attempts with a fake key across the full suite.
- **NFR-3 and §8.4: held.** The repair added 0 production files, classes, constants or dependencies.
- **INV-19, INV-20, INV-22, INV-23: held** (the code is AST-identical).

§5 diagram: no new divergence. `validate` still reaches `find_vidbyte_api_key` through `is_vidbyte_managed`.

request.md §A and §C: the repair reverses no decision and adds no scope.

§14 "Never" in the repair range:
- no secrets (regex scan of added lines finds none);
- no `noqa`, `type: ignore`, skip or xfail;
- no baseline change;
- the only edit to an existing test is the granted R-4 wrap, with assertions unchanged;
- S2 files changed only by the granted pack README bullet and FEATURE.md bullet (`git diff 2eb7e3e5..c826ec07 -- tests/features/sdk_managed_text/`).

Commit IDs (note, not a finding): 8 of the 12 repair commits cite only review IDs, not spec FR, AC or W IDs (§14 "Always: Cite IDs"). Examples are 92d3d690, 745f8efe and 69ee8aaa. review.md maps each review ID to spec IDs, and the commits are already pushed, so rewriting history is not worth it.

COMMANDS RUN:
1. `git log --oneline -25`; `git diff --stat 573a9f5f..c826ec07` → `20 files changed, 1104 insertions(+), 83 deletions(-)`.
2. `env -u DEEPSEEK_API_KEY -u VIDBYTE_API_KEY PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider` → `39 passed in 0.90s`.
3. `env -u DEEPSEEK_API_KEY -u VIDBYTE_API_KEY PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` → `3011 passed, 1 skipped in 15.32s`.
4. Full suite with fake `VIDBYTE_API_KEY=vb_live_z…` plus `-s -p netstack` → `3011 passed, 1 skipped in 15.82s`, 0 `BLOCKED` lines. Positive control (`python -c`, the same plugin, a `TextModelRunner` call) → `BLOCKED https://vidbyte-backend.onrender.com/api/v1/models/generate`.
5. The R-4 test alone, with the fake key, `-s -p netstack` → `1 passed in 0.67s`, 0 BLOCKED.
6. `MUT=<id> … pytest test_managed_text_deadline.py -p mutplug` for the 6 mutants, plus `-p mut_first` → 2/1/2/4/1/2 failed and 2 failed (see above). `shorten_attempt` ×10 → `4 failed, 3 passed` each time. The pack without the new file ×4 → `32 passed, 7 deselected`. The whole pack ×3 → `4 failed, 35 passed`.
7. Inline plugin via `pytest.main(..., plugins=[Mut()])` with the deadline taken from the floor constant → `39 passed in 0.31s`. Direct probe at timeout 900 and step 700 → real 2 POSTs, mutant 1 POST.
8. `python lint/run.py` → `A002 … 652 703 IMPROVED` … `S020 … 1 1 RATCHETED` … `S064 … 4 4 RATCHETED` / `SDK-LINT: PASS`. `git status --short` is empty before and after.
9. AST comparison of the 6 production files at 573a9f5f and c826ec07, ignoring docstrings → 4 files identical; `model_configs.py` changed only in `TextModelConfig.validate`; `streaming_text.py` changed only in `_refuse_managed_streaming`.
10. 1,944-case differential of `model_configs` at 573a9f5f against HEAD → `cases 1944 diffs 0`. Call-count probe → `{'is_vidbyte_managed': 1, 'find_vidbyte_api_key': 1}`.
11. Contract: `git -C …/vidbyte show ceabda93…:contracts/vidbyte-platform-contract.json | git hash-object --stdin`, `git rev-parse HEAD:` and `c826ec07:`, and `git hash-object` → all `56d4d0b373994f5de6affd675ed4c209e64d589d`. `od -c` shows `{ \n`.
12. `git diff origin/main...c826ec07 -- lint/baseline.json` → only `"C020": 4 → 2`. `git diff --name-status e91cf822..c826ec07` → production `.py` only under `vidbyte/lib/`.
13. AC-1 test → `1 passed`. The §4 snippet as written, with a recording transport → the output shown above.
14. Probes: managed streaming refusal for 6 providers; README path for gemini → `StreamingTextModelRunner supports: anthropic, openai.`; 404 EC-26 → 1 POST and the row 6 message.
15. Greps:
    - `AC-28` and `test_managed_text_deadline` in `spec.md`, `test-plan.md` and `vidbyte_gateway.py` → 0 each;
    - all 30 spec proof references (`file::Class::test`) exist;
    - the awk `@intent` placement scan, and a scan for added comment lines over 72 columns (none);
    - secret and suppression scans of the repair diff (none in code);
    - backend spec NG-9 and Q-3 lines.
