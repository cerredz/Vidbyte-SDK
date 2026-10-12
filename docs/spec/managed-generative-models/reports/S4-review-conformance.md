LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — Every FR, INV, AC and §12.3 row I traced holds on the paths I ran, including the §4 snippet run as written. However, the r5 cumulative retry deadline (INV-10, INV-16, EC-38) has no AC and no test: a mutant without it still passes all 32 pack tests. Four Minor consistency gaps (spec, README, one message) remain.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **The §4 snippet works as written.** With only `VIDBYTE_API_KEY` set and `vidbyte.lib.runners.text.HttpTransport` patched, it prints exactly `openai gpt-5.5` / `Hi` / `2`. It sends exactly one request: `POST https://vidbyte-backend.onrender.com/api/v1/models/generate` with the headers `authorization`, `content-type` and `Idempotency-Key` (32 hex characters, equal to the `idempotency_key` argument), timeout 630.0, and the body `{"provider":"openai","model":"gpt-5.5","body":{"model":"gpt-5.5","input":"Say hi in one word.","max_output_tokens":8192}}`. Building the second runner (`claude`) sends nothing, and it pins the `VIDBYTE_API_KEY` even when `ANTHROPIC_API_KEY` is set. Keep `TextModelRunner.__init__` pinning (`vidbyte/lib/runners/text.py:46-54`) and the per-call wrap inside async `arun` (`:77-84`) as they are.
- **Key selection matches the spec.**
  - `ProviderModelRegistry.find_vidbyte_api_key` (`vidbyte/lib/registries/models.py:173-193`) follows the INV-4 order for each provider: kimi reads `MOONSHOT_API_KEY`, a blank explicit key falls through, `" sk-x "` stays BYOK, and openrouter ignores `VIDBYTE_API_KEY`.
  - `resolve_vidbyte_api_key` is shared with `DecisionModelConfig`. Its outcomes and messages for blank, padded, 31-character and `vb_test_` keys are identical to the Decision outcomes at base.
  - Explicit managed mode never reads the provider env var: with only `OPENAI_API_KEY=vb_live_…` set, it raises "Missing Vidbyte API key…" with `error_kind`.
- **The failure mapping holds on every probed path.** Every row raises outside the `except` block (`__cause__` and `__context__` are `None`, `response_excerpt` is `None`). Only 409, 502 or an answer that is not a JSON object is re-sent, always with the same key, with waits of 0.5 s and 1.0 s. A relayed vendor `{"error": {...}}` and an `"error": "true"` string are not read as the gateway's `"error": true`. The r5 deadline stops re-sends: a 0.4 s timeout gives 1 POST and "did not re-send"; 0.6 s gives 2 POSTs and "re-sends in this call: 1".
- **Boundaries and budget hold.**
  - Production `.py` files change only under `vidbyte/lib/` (9 files in `git diff origin/main...a80f0660`).
  - Nothing under `vidbyte/providers/` or `vidbyte/agents/` changes, nor `pyproject.toml`, `contracts/` or `vidbyte/lib/http/__init__.py`.
  - The §8.4 budget is met exactly: 2 files, 3 classes, 1 field + 8 constants, 0 env vars, 0 dependencies.
  - No `vb_live_` literal exists outside `VIDBYTE_API_KEY_PREFIX` in `vidbyte/lib/` (C020 = 2, both in `providers/typesafe.py`, per NG-7).
  - The S2 test files are byte-identical to `2eb7e3e5`, and the code diff has no suppressions. The only baseline change is C020 4→2.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Major] [every-ID: the test that proves it] vidbyte/lib/http/vidbyte_gateway.py:177 — No AC and no test proves the r5 cumulative retry deadline (INV-10, INV-16, EC-38), so the S2 pack passes with the deadline check deleted
  Evidence:
  - The code at `vidbyte_gateway.py:177` is `if not answer.retryable() or loop.time() + retry_wait >= deadline:`.
  - `grep -rn -i "deadline\|loop.time\|get_running_loop\|did not re-send\|re-sends in this call\|EC-38" tests/features/sdk_managed_text/` prints nothing.
  - `test-plan.md:3` reads "Spec: … spec.md r4". The pack was written before r5 and has no deadline row. Spec §6.2 (AC-1..AC-27) has no deadline AC, and EC-38 (`spec.md:284`) is "Guarded by INV-10, INV-16, accepted" with no proof.
  - Mutation test, run in memory with no file edits: I removed ` or loop.time() + retry_wait >= deadline` from `VidbyteGatewayTransport.request` with `exec`, then ran `pytest.main(["-q","-p","no:cacheprovider","tests/features/sdk_managed_text"])`. Output: `MUTANT: deadline check removed in memory` and then `32 passed in 0.32s`.
  Failure:
  - Input and state: the gateway answers 502 at about 600 s, for example at its own total deadline (EC-38).
  - With a broken or missing deadline, the SDK re-sends twice more after the call's 630 s budget. Each re-send forwards again after the claim was released (EC-38), so Vidbyte can pay the provider up to three times for one call, and the worst case grows past about 21 minutes.
  - A wrong deadline base, or wrong "re-sends in this call: N" or "did not re-send" wording (§9.2 rows 3, 5 and 6, deviation 4), would also ship green.
  - S064 proves only that some deadline comparison exists, not that it is correct. A human reviewer would write: "r5 changed binding retry behavior; which test proves a slow 502 gets at most one re-send?"
  Smallest fix: Add one new test without editing any S2 file, for example a new `tests/features/sdk_managed_text/test_managed_text_deadline.py`. It drives `VidbyteGatewayTransport` directly with a scripted inner transport that answers 502 three times, with `SLEEP_TARGET` patched to a no-op, and asserts two cases:
  - `timeout_seconds=0.4` gives exactly 1 POST and a message containing "did not re-send".
  - `timeout_seconds=0.6` gives exactly 2 POSTs with one key and "re-sends in this call: 1".
  This setup is deterministic, because the real clock barely moves while sleep is a no-op. Then add an AC-28 row to spec §6.2 and a matching coverage-map row to the test plan.
  Spec IDs: INV-10, INV-16, EC-38, D-10, §9.2 "Retries (binding)", §17 deviation 4; FR-4.

R-C2 [Minor] [user's words: "managed streaming rejected with a clear error"] vidbyte/lib/runners/streaming_text.py:65 — For 4 of the 6 managed providers, the streaming refusal tells the user a fix that does not work
  Evidence:
  - The message at `:65` is `f"Streaming is not available in Vidbyte-managed mode. Use TextModelRunner, or set {env_var} to stream with your own key."`.
  - Probe output: `STREAMING_SUPPORTED_PROVIDERS: ['anthropic', 'openai']`.
  - Managed gemini gives `Streaming is not available in Vidbyte-managed mode. Use TextModelRunner, or set GEMINI_API_KEY to stream with your own key.` After following that advice, with `GEMINI_API_KEY` set, the result is `StreamingTextModelRunner supports: anthropic, openai.`. xai behaves the same way with `XAI_API_KEY`.
  Failure: With only `VIDBYTE_API_KEY` set and provider gemini, xai, deepseek or kimi, the user is told to set their provider key to stream. Doing so produces a second refusal. AC-13 asks for a message that names "the fix", and request.md §C asks for "a clear error". The wording follows EC-16 literally, so the spec carries the same defect.
  Smallest fix: When the provider is not in `STREAMING_SUPPORTED_PROVIDERS`, change the second clause to "set GEMINI_API_KEY to call gemini with your own key; StreamingTextModelRunner streams only anthropic and openai". The message still contains "managed", "TextModelRunner" and the env var, and `details` is unchanged, so `test_streaming_refuses_managed_state_but_still_streams_byok_beside_a_vidbyte_key` still passes. Update the EC-16 "User sees" text to match.
  Spec IDs: AC-13, EC-16, FR-7, D-15; request.md §C (SDK scope).

R-C3 [Minor] [deviations: recorded but not propagated] docs/spec/managed-generative-models/spec.md:272 — Deviations 1 and 2 are recorded in §17, but the binding EC-26 row and the §15 risk note (`spec.md:852`) still state the opposite
  Evidence:
  - The EC-26 row says the user sees "Vidbyte returned HTTP 404".
  - Probe: the scripted answer `404 {"detail":"Not Found"}` produces `Vidbyte managed openai request failed: openai returned HTTP 404 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed.` This follows the orchestrator decision that §9.2 row 6 decides it.
  - The §15 risk note says the vendored copy "lacks those routes" (agent runs). But `git diff origin/main...a80f0660 -- lint/contracts/vidbyte-platform-contract.json` adds `agent_runs.finish`, `agent_runs.records` and `agent_runs.start`, plus four `agent_run_*` error codes.
  Failure: S6 and later readers of EC-26 expect a message that the code never emits, and §15 states a false fact about the vendored contract. The spec's own rule is that rows are binding and §17 only logs history.
  Smallest fix: Rewrite the EC-26 "User sees" cell to the row-6 message, citing the orchestrator decision, and rewrite or strike the §15 risk note. Edit only the spec text, with no code change.
  Spec IDs: EC-26, §15 risk note, §17 deviations 1–2.

R-C4 [Minor] [user's words; scope-adding] docs/spec/managed-generative-models/spec.md:70 — The weighted phrase "all of the generative model calls" holds for 6 of the 11 text providers, and NG-5 credits the GLM, MiniMax, Meta and Mistral exclusion to request.md §C, which does not exclude them
  Evidence:
  - request.md:21 (Prompt 2): "all of the generative model calls of the sdk".
  - request.md:61, §C, excludes only "the Codex app-server path …, OpenRouter …, non-text modalities, and streaming".
  - spec.md:70, NG-5, says "request.md §C excludes them".
  - The real reason is backend spec NG-9: "Dispatching GLM, MiniMax, Meta or Mistral. — Why not: the credential loader maps no key for any of them, and Mistral has no pricebook entry".
  - In code, `VIDBYTE_MANAGED_TEXT_PROVIDERS` (`vidbyte/lib/constants/jev.py:69-76`) gates step 3. Probe: `find_vidbyte_api_key("openrouter")` with only `VIDBYTE_API_KEY` set returns `None`.
  Failure: With only `VIDBYTE_API_KEY` set, a GLM, MiniMax, Meta or Mistral text call raises "Missing API key for provider glm…", so those tokens never carry the markup. The README lists the six providers, so nothing is hidden, but the user's words are only partly met, and the spec misquotes the user's own notes.
  Smallest fix: Correct NG-5's source to backend NG-9 and Q-3, and have S6 state the six-provider limit in the PR body. Serving more providers is [scope-adding] (backend credentials and pricebook first) and is a follow-up for the user, not for the repair loop.
  Spec IDs: G-1, NFR-1, NG-5; request.md §D "all of the generative model calls".

R-C5 [Minor] [weighted word in user-facing docs] README.md:286 — The README promises that "a retry is never billed twice", but spec EC-39 says this fails during a replay-store outage
  Evidence:
  - README.md:286: "the gateway answers it from its saved result and a retry is never billed twice."
  - spec.md:285, EC-39: "A normal answer, possibly billed twice".
  - AC-18 (spec.md:232) itself requires the wording "so a retry is never billed twice", so the spec contradicts itself and the README copies the absolute claim.
  Failure: Suppose the replay store is down and the first attempt is cut off by an edge page after the gateway already billed it. The same-key retry is then forwarded and billed again, which the README told the developer cannot happen.
  Smallest fix: Qualify AC-18 and README.md:286 with one sentence each, for example "…so the gateway normally answers it from its saved result instead of billing it again". Make no code change.
  Spec IDs: AC-18, EC-39, INV-16.

VERIFIED CLAIMS:
1. **Spec §4 / AC-1 ("produces exactly the shown result"): HELD.** I ran the snippet as written through a heredoc, with `HttpTransport` patched at `vidbyte.lib.runners.text`. The output and the single recorded request are listed in "gets right" above.
2. **S3 and orchestrator: "32 passed" for the pack: HELD.** Result: `32 passed in 0.94s`.
3. **S3: full suite "3004 passed, 1 skipped": HELD.** Result: `3004 passed, 1 skipped in 17.92s`.
4. **S3: lint C017 0, C018 1, C019 0, C020 2, S064 4, `SDK-LINT: PASS` (AC-14 gate, NFR-5): HELD.** Each rule was re-run on its own, and the full `python lint/run.py` also passed.
5. **S3: "no test file was changed" (§14 Never): HELD.**
   - `git diff --stat e91cf822..a80f0660 -- tests` and `git diff 2eb7e3e5 a80f0660 --stat -- tests/features/sdk_managed_text` are both empty.
   - `git diff --name-status origin/main...a80f0660 -- tests` shows only 7 `A` (added) files.
6. **AC-19 and S3: production `.py` files only under `vidbyte/lib/`: HELD** for `origin/main...a80f0660` and for `e91cf822..a80f0660` (the same 9 files). The spec's original command `git diff --name-only c0752931...HEAD` does not hold as written: it lists 122 non-lib `.py` files from the main merge. S3's amendment in the AC-19 proof cell is correct.
7. **S3, row 11: contract blob `56d4d0b3`, no BOM, `models.generate` route present: HELD.** `git hash-object` printed `56d4d0b373994f5de6affd675ed4c209e64d589d`, the first bytes are `{\n`, and the diff adds the `models.generate` row with `POST /api/v1/models/generate`, `API_KEY` and `models:invoke`.
8. **S3, "option A as built" (deadline, re-send counts, wording): HELD by probe.** 502×3 at 630 s gives 3 POSTs, "re-sends in this call: 2"; 0.6 s gives 2 POSTs, "…: 1"; 0.4 s gives 1 POST, "did not re-send". However, no repo test proves this (R-C1).
9. **§8.4 budget and NFR-3/NFR-6: HELD.** The jev.py diff adds exactly 8 constants. The classes are `TextModelMode`, `VidbyteGatewayTransport` and `_GatewayAnswer`. `pyproject.toml` and `contracts/` are unchanged.
10. **INV-15 (no markup in the SDK): HELD.** A grep of the code diff for markup, 0.02, basis, bps, fee and 200 matched only a docstring.
11. **INV-19 and D-14 (Decision behavior unchanged): HELD.** The probe covered `""`, `"  "`, a padded key, a 31-character key and `vb_test_`. Outcomes and messages are identical to base, and the pattern `re.escape("vb_live_")` equals the old literal.
12. **§14 Never and NFR-5: HELD.** The code diff has no `noqa`, `type: ignore`, `pragma` or `nosemgrep`, no `except BaseException` and no in-`except` `raise … from`. The only baseline edit is `"C020": 4 → 2`. The code has 0 `model_gateway_` literals.
13. **ID walk.** I walked FR-1..FR-14, NFR-1..NFR-8, INV-1..INV-23, AC-1..AC-27, EC-1..EC-39 and §12.3 rows 1–15 (row 7 withdrawn, and `http/__init__.py` is untouched). Every item is met in code, or accepted by spec or orchestrator decision, except those listed as R-C1..R-C5.
14. **§5 diagram compared with the call path: HELD,** with two cosmetic divergences:
    - In explicit `VIDBYTE_MANAGED` mode, the code skips `find_vidbyte_api_key` and goes straight to `resolve_vidbyte_api_key`.
    - The retry edge "with retries left" omits the r5 deadline condition.
15. **AC-18 full fact list (assigned to S4 review): HELD for all 13 facts.** Fee, on and off, the per-provider rule including children, six providers, 8,192 and both `extra_body` cap rules, 630 s per attempt, retries with the same `Idempotency-Key` plus the deadline and the ~21-minute worst case, no retry on network failure or timeout, the 120 s outer-timeout example, 2,000,000 bytes, streaming refused, refused fields, Vidbyte's provider accounts, BYOK unbilled. The one wording problem is R-C5.
16. **AC-17 (`scripts/run_ci.py`): NOT RE-RUN,** because the briefing forbids it. Its lint and full-suite parts were re-run and pass.

COMMANDS RUN:
- `git diff --stat origin/main...a80f0660`: 31 files changed, 4671 insertions(+), 21 deletions(-). The merge-base is `00cbd6dbd12e3a8d7c92ec7ffbe2ed04e8273ec5`.
- `git diff origin/main...a80f0660 -- vidbyte/... lint/... README.md`: each hunk read, plus the whole files `vidbyte_gateway.py`, `text.py` and the TextModelConfig part of `model_configs.py`.
- `PYTHONPATH=$(pwd) python - <<EOF` (the §4 snippet with `HttpTransport` patched): `openai gpt-5.5` / `Hi` / `2` / `requests: 1` / `POST https://vidbyte-backend.onrender.com/api/v1/models/generate` / `timeout 630.0 idem arg == header True True`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider`: `32 passed in 0.94s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=line`: `3004 passed, 1 skipped in 17.92s`.
- `python lint/run.py`: `S064 RATCHETED: 4 known finding(s)` … `SDK-LINT: PASS`.
- `python lint/run.py --rule C017|C018|C019|C020|S064` gave:
  - `C017 … 0 0 CLEAN`
  - `C018 RATCHETED: 1`
  - `C019 … 0 0 CLEAN`
  - `C020 RATCHETED: 2`
  - `S064 RATCHETED: 4`
  - each followed by `SDK-LINT: PASS`
- `python lint/run.py --rule C020 --all`: the 2 findings are `vidbyte/providers/typesafe.py:255` and `:271`.
- Gateway probe, a heredoc driving `VidbyteGatewayTransport` with scripted answers. Results:
  - EC-26 404: "openai returned HTTP 404 through the Vidbyte gateway; … not billed."
  - 502×3: 3 POSTs, "(re-sends in this call: 2)".
  - 0.4 s: 1 POST, "did not re-send it".
  - 0.6 s: 2 POSTs.
  - 200 HTML ×3: 3 POSTs, edge message.
  - In every case, `__context__` and `__cause__` are `None` and `response_excerpt` is `None`.
- Mutation probe, in memory with no file written: `MUTANT: deadline check removed in memory` / `32 passed in 0.32s`.
- Streaming probe: `managed: … set GEMINI_API_KEY to stream with your own key.` / `after following the advice ( GEMINI_API_KEY set ): StreamingTextModelRunner supports: anthropic, openai.`
- Fall-through and Decision probe: kimi uses `MOONSHOT=vb: True`; openrouter with VIDBYTE only gives `None`; explicit managed with only `OPENAI_API_KEY=vb` gives `Missing Vidbyte API key…`; Decision padded key ok, 31 characters gives the format error.
- `git diff --name-only c0752931...a80f0660 -- '*.py' ':!tests' | grep -vc '^vidbyte/lib/'`: `122`. The same command over `origin/main...` and `e91cf822..` lists 9 files, all under `vidbyte/lib/`.
- `git diff 2eb7e3e5 a80f0660 --stat -- tests/features/sdk_managed_text`: empty.
- `git hash-object lint/contracts/vidbyte-platform-contract.json`: `56d4d0b373994f5de6affd675ed4c209e64d589d`.
- `grep -rn "vb_live_" vidbyte --include=*.py`: `jev.py:62` (the owner constant) and `providers/typesafe.py:255,271`.
- `grep -rn -i "deadline|loop.time|…|EC-38" tests/features/sdk_managed_text/`: no output.
- Read-only read of the backend spec §9.2 (r4) for wire facts: allowed lists, `"error": true` discriminator, 413 measurement, NG-9.
