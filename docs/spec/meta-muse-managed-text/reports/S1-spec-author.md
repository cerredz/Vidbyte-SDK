# S1 spec author report: meta-muse-managed-text

- **Stage:** S1 spec author, revision r1
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text`
- **Branch:** `feat/meta-muse-managed-text`
- **Commit:** `8ec7dda6 docs(spec): add meta-muse-managed-text spec r1`. It contains only `docs/spec/meta-muse-managed-text/spec.md`. Its parent is `75761b81`, and the code is identical to `845a4d9b`.
- **Files created:** 2, `spec.md` (committed) and this report (left uncommitted for the orchestrator). No production code, test, stub, or prototype was written in the worktree.

## What I read

- **Rules:**
  - `AGENTS.md`, in full.
  - `vidbyte/lib/README.md` and `vidbyte/lib/registries/README.md`.
  - The `jev.py`, `text.py`, and test-pack headers (COMMON MODIFICATION PATTERNS, WHAT NOT TO DO, ROLE IN CODEBASE).
  - Field guide: comment-format, local-ci-verification, provider-api-contracts, review-scope, operation-pricebook-rates, blocking-lint-invariants, strict-config-dataclasses, declarative-config-resolution.
  - `vidbyte-gates.md`.
- **Allowed docs:**
  - `request.md`, `context/code-map.md`, `context/wire-contract.md`, and `reports/S0-scout.md`.
  - The byok spec: the gateway-served providers, mode resolution (table R), relay, table G, EC-15, M-12, and D-11.
  - The Run A spec (§9.2-9.4; §15 A-3, A-7, Q-1, Q-4; EC-24, EC-27, EC-29, EC-30) and its PR-body sections, read-only from the Run A worktree.
- **Production code, read and traced end to end:**
  - `vidbyte/lib/constants/jev.py`
  - `vidbyte/lib/dataclasses/model_configs.py`
  - `vidbyte/lib/registries/{provider_keys,models,pricing}.py`
  - `vidbyte/lib/runners/{text,streaming_text,types}.py`
  - `vidbyte/lib/http/vidbyte_gateway.py`
  - `vidbyte/providers/compatible.py`
  - `vidbyte/agents/{base,fallback,runtime}.py`
  - `vidbyte/lib/dataclasses/agents.py`
  - Plus the META rows of `constants/runners.py`, `configs/structured_output.py`, and `enums/model_provider.py`.
- **Tests (facts only, for §13):** every module that names served providers or META in `tests/features/sdk_managed_text/` and `tests/features/sdk_provider_keys/`.
- **First-party Meta docs:** fetched 2026-10-16 as Markdown from `https://dev.meta.ai/docs/<page>.md`. Pages: `protocols/chat-completions`, `reasoning`, `api-reference/chat-completions/schemas`, `models`, `quickstart`, `pricing-rate-limits`, `error-handling`. No secondary site was used.

## How the design was verified (independent of my reading)

All of the following were scratchpad-only and never committed. They live under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`.

1. **Baseline at `845a4d9b`:**
   - Area run: `168 passed in 2.00s`.
   - `py -3.11 scripts/run_ci.py` (PYTHONPATH unset): `SDK-LINT: PASS`; pytest `1 failed, 6245 passed, 16 skipped`. The failure is the known harness_threads `148 == 120` test.
   - `--stage package`: `CI passed.`
   - The MCP stdio flake passed 3 of 3 times.
2. **`probe_meta_gateway.py`:** widens `VIDBYTE_MANAGED_TEXT_PROVIDERS` with META in memory only, then drives the unchanged runner, adapter, and transport with the packs' own fakes. Results:
   - **AUTO relay from a mixed list:** one gateway POST, 4 headers, the relay header equal to the Meta key, the Anthropic key absent. Envelope `{"provider":"meta","model":"muse-spark-1.1","body":{"max_tokens":32768,...}}`, timeout 630.
   - **AUTO paid:** 3 headers.
   - **Environment relay with cap 100:** `max_tokens` 100.
   - **VIDBYTE_MANAGED:** no relay header.
   - **DIRECT:** unchanged, to `api.meta.ai`, with no `max_tokens` and timeout 60.
   - **422:** 1 attempt.
   - **Paid 502:** 3 attempts, with waits of 0.5 s and 1.0 s.
   - **Messages:** M-12 now lists meta, and M-18 offers "Vidbyte's own meta account".

   This is the evidence for D-1, "the constant is the only gate".
3. **`probe_plugin/widen_meta_probe.py`:** a pytest plugin that widens the set in memory, run over the whole suite: `3 failed, 6243 passed, 16 skipped`. The failures are exactly the two by-design gateway-refusal tests (named in §13) plus the pre-existing harness test. No other test depends on meta being refused.

## Approaches weighed

- **Chosen (D-1, D-2):** add `ModelProvider.META` to the set. Keep `max_tokens`. Update two README bullets and the comment above the set. S2 extends the pack tables.
- **Smaller, rejected:**
  - *No SDK change; developers use DIRECT.* This fails FR-1 and G-3, because Muse traffic keeps skipping the fee.
  - *The constant alone, with no docs.* This fails FR-7, because `jev.py:6` requires the README managed-mode section to change together with the set.
- **Larger, rejected:**
  - *A per-provider gateway capability table* (cap field, served models, default cap). No second provider-specific rule exists to justify it. It is D-1's runner-up, with an explicit flip condition.
  - *An SDK allowlist of served Muse ids* (D-4, Q-2). It would drift from the backend pin, and no served provider has one.
  - *`MetaProvider` emits `max_completion_tokens`* (D-2's runner-up). This is Run A's recommendation; see the disagreement below.
- **Budget:** 0 new files, classes, dependencies, config keys, tables, or endpoints. The production diff is about 5 lines in one file, plus 2 README bullets.

## Where I disagree with the request, the scout, or Run A (with evidence)

1. **Run A and wire contract §9.2 say Run B should send the cap as `max_completion_tokens`, because whether `max_tokens` counts reasoning is unverified (A-3).** Meta's own pages settle A-3:
   - `reasoning`: "`max_tokens` (Chat Completions) and `max_output_tokens` (Responses API) cap reasoning tokens plus visible output tokens combined".
   - `protocols/chat-completions`: "The deprecated alias `max_tokens` is still accepted."

   So `max_tokens` bounds exactly what `max_completion_tokens` bounds. Switching fields would change DIRECT bodies, or make the adapter mode-aware, for no admission or hold benefit. It would also contradict `test_managed_text_wire_contract.py:130` (no managed body carries `max_completion_tokens`) and the README's chat-dialect guidance. The spec keeps `max_tokens` (D-2) and states the flip if Meta drops the alias (A-4).
2. **The request and wire contract premise that every meta gateway call "answers `output_cap_missing`" unless Run B adds a cap is wrong for SDK traffic.** `TextModelRunner.__init__` (`text.py:57-62`) already pins 32,768 for every gateway mode, so `MetaProvider` already writes `max_tokens`. The probe confirmed it. The scout said the same, and I agree with the scout.
3. **The request hint to model the change on Kimi and DeepSeek.** Only Kimi has the same shape: `MetaProvider` and `KimiProvider` are bare subclasses, while DeepSeek overrides `_extract_chat_text`. The spec names Kimi as the sibling. This agrees with the scout.
4. **The scout's open question about whether a model or endpoint map, a request builder, a cap rule, or an export must change.** None must. The probe and the full-suite plugin run prove it beyond the scout's reading.
5. **The scout listed `docs/spec/managed-generative-models/spec.md` among the code headers' citations.** It was not named for reading, so I did not read it.
6. **`vidbyte-gates.md:28` says the lint final line is `AGENT-LINT: PASS`.** In this repo it is `SDK-LINT: PASS` (observed). §11 records the observed line.
7. **The scout listed pytest versions, `testpaths`, Meta's `metadata` acceptance, and Muse's output maximum as unverified.** The first three are now verified (`pyproject.toml:48-49, :78-79`; Meta's schemas page lists `metadata`). The output maximum for `muse-spark-1.1` stays unverified (A-2).

## Deviations and environment notes

- **Semgrep fails locally at import:** `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`, mcp 2.x. It is not part of `run_ci.py`. I installed nothing. §11 records it as remote-only.
- **The scratchpad held Meta doc files from an earlier S1 attempt** (21:58). Every quote in the spec comes from my fresh downloads at 22:34.
- **The Stage E fact check corrected the draft before commit:**
  - Two signatures in §8.5: `TextModelRunner` has `provider`/`model` keywords, and `Agent` is the `BaseAgent` alias with no `**options`.
  - A `create_runner` mention, which does not exist.
  - An M-15 label.
  - Three wire-contract overstatements: a hold sized from "the larger value", the claim that "the backend never logs the header", and "idempotency scoped per API key".
  - A PR #1147 reference taken from memory, not from the repo.

## Stage E self-check

- **FR → INV/AC:** every FR maps. FR-1 → INV-1, AC-1, AC-10; FR-2 → INV-2, AC-2; FR-3 → INV-3, AC-3, AC-4; FR-4 → INV-5, AC-5; FR-5 → AC-7; FR-6 → INV-10, AC-10; FR-7 → AC-13; FR-8 → AC-15.
- **AC → W:** every AC maps. W-1 covers AC-1..12 and AC-14, W-2 covers AC-13, and W-4 covers AC-15.
- **Edge cases:** EC-1..EC-15 are each guarded by an INV or D, or accepted as a named limitation.
- **Threats:** T-1..T-4 each name a control and where it sits.
- **Contract names:** the §4, §8.5, and §12.3 names match: `VIDBYTE_MANAGED_TEXT_PROVIDERS`, `ModelProvider.META`, `TextModelConfig`, `TextModelMode`, `TextModelRunner`, `Agent`/`BaseAgent` keywords, `.text`, and `.content`.
- **Budget:** 0 new files, matching §8.4.
- **Weighted words:** each one in request.md §D maps to an INV, NFR, or AC (INV-1, INV-4, INV-9, INV-15, NFR-1..3, AC-1..4, AC-15).
- **Commands:** the §11 commands were run on this machine, and their final lines are quoted.
- **Template:** the headings diff against `spec-template.md` is empty. The only extra frontmatter key is the requested `wire_contract`.
- **Tests:** none in the spec.
- **Key literals:** no key-shaped literal (grep for `LLM|<digits>|…`, `vb_live_…`, `sk-ant-…`: none).

## Assumptions I am least sure of

1. **A-2:** that `muse-spark-1.1`'s configured maximum output is at least 32,768. Meta publishes `output 131072` only for 1.3 and a 1,048,576-token shared context for all three versions. If this is wrong, every capless meta gateway call gets Meta's 400, and the relay wording then wrongly hints at a bad key (EC-3).
2. **EC-5:** how the gateway sizes its hold when both `max_tokens` and `max_completion_tokens` are present, and how Meta treats both. Neither is documented. It is reachable only through `extra_body`.
3. **A-5:** that the gateway relays Meta's 2xx JSON unchanged, so the existing parser reads it. This is stated by the wire contract but untested against a live #710 deployment.

## Notes for Run A (backend), not blocking here

- The missing-key 502 `subtitle` never reaches SDK users (Q-1, default no). The PR body's deploy order is the mitigation.
- The `-contributor` ids under Vidbyte's key are Run A's Q-4 (Q-3 here, default no).
- Run A's A-3 is answered by Meta's `reasoning` page (quoted above). Run A may close it.

## Revision r2 (review round 1, 2026-10-17)

- **Commit:** `4046e75c docs(spec): revise meta-muse-managed-text spec r2 (review round 1: R-1..R-6)`, spec only.
- **Triage:** all six findings were accepted, after I re-verified each one's evidence against the code. None was rejected. The design, the budget (0 new files), and the IDs are unchanged, and the only new IDs are EC-16 and Q-6.
- **Independent checks I ran before accepting:**
  - **R-1:** I re-ran the reviewer's `s1_grader_probe.py` myself. At base it sent 2 `anthropic` requests. Widened, it also sent 1 `meta` request that relayed `META_API_KEY` with `max_tokens` 32,768. I also read `resolve_active` and `_resolve_from_environment` (`models.py:274-279`, `:418-428`); the grader at `:61`, `:87`, `:93`, `:121`; `aggregation.py:97`, `:129`; `ContextMinimalFanoutSettings.return_exceptions` (`types.py:486`); and the fork and handoff pass-through (`fork.py:68`, `handoff.py:68`, `provider_keys.py:124-135`).
  - **R-2:** `base.py:317-321` (`max_tokens` is the loop budget) and `:1662` (only `timeout_seconds` reaches the runner).
  - **R-3:** `CONTRIBUTING.md:75-83` and `.github/pull_request_template.md`.
  - **R-4:** `README.md:290-297`. A grep of the tests that read `README.md` found none that binds the Prefixes bullet.
  - **R-5:** found the log seam (`test_provider_keys_security.py:106-121`). No trace seam exists, so the INV-9 trace clause is handed to byok INV-22 instead of being claimed.
  - **R-6:** checked read-only in the Run A worktree that `c395349bd` is on `origin/feat/meta-muse-gateway` and that spec §9.2-9.4 are identical through `da96273c0`.
- **Coordinator's cap confirmation:** INV-5 and D-3 now cite `VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS` at `jev.py:84`, applied by `text.py:57-62`. D-2 quotes https://dev.meta.ai/docs/reasoning ("cap reasoning tokens plus visible output tokens combined"), which I re-checked against the saved page (reasoning.md:390).
- **One propagation beyond the review:** INV-3 said `VIDBYTE_MANAGED` "never reads `META_API_KEY`". EC-16 shows the grader reads it to choose members, so INV-3 is now scoped to the call's credential resolution. Otherwise a test author could write a test that fails on correct code.
- **Assumption still least sure of:** A-2, the output limit for `muse-spark-1.1`. It now has a named pre-merge check, but only the user or ops can run it: it needs real keys and a deployed #710.
