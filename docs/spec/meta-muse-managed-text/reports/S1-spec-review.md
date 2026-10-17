# S1 spec review: meta-muse-managed-text r1

Reviewer: S1 spec reviewer (adversarial), round 1. Read-only review of `spec.md` r1 at worktree HEAD `42aee6c6` (code byte-identical to `845a4d9b`, which is still `origin/main` per `git ls-remote` on 2026-10-17). All probes fake only the inner HTTP transport and `os.environ`, and widen `VIDBYTE_MANAGED_TEXT_PROVIDERS` in memory in the three modules that hold the name (`vidbyte.lib.constants.jev`, `vidbyte.lib.dataclasses.model_configs`, `vidbyte.lib.registries.provider_keys`). Probe scripts: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/` (`s1_probe.py`, `s1_cap_probe.py`, `s1_grader_probe.py`, `s1_fallback_base_probe.py`, `plugins/s1_widen.py`).

VERDICT: SOUND WITH FIXES — the one-constant design is correct and proven on every gateway route (cap, relay, paid, floor), but the spec's "no call that worked at base_commit changes" is false for fan-out compositions, its cap fallback has no workaround on the Agent path it leads with, and §12.5 misses the repo's PR-template rule.

## WHAT THE SPEC GETS RIGHT

- **The core mechanism holds on every route.** `VIDBYTE_MANAGED_TEXT_PROVIDERS` has exactly three readers (`model_configs.py:204-205`, `provider_keys.py:308`, the declaration). `VidbyteGatewayTransport` is built in one place (`text.py:92`), and `run_text` has one caller (`text.py:100`). Both sit in the class whose `__init__` pins the 32,768 cap and the 630 s floor whenever `credentials.uses_gateway` is true (`text.py:57-62`). With only the set widened, every route forwarded `max_tokens: 32768`. The cap-probe evidence is under VERIFIED CLAIMS.
- **D-2 keeps `max_tokens`, and Meta's own docs support it.** I re-fetched the docs on 2026-10-17 and the quotes match. Keeping `max_tokens` leaves `DIRECT` byte-identical. It also matches the managed-text pack's rule that no managed body carries `max_completion_tokens` (`test_managed_text_wire_contract.py:130`).
- **The §13 facts are accurate and useful.** Widening the set flips exactly the two tests named. A pytest plugin run of the area gave `2 failed, 166 passed`, and the 561 meta-referencing tests outside the packs all pass. The ORACLE_KEYS KeyError trap, the format-bound oracle key, the `_CHAT_PROVIDERS` usage-shape gap, and the false comment at `test_provider_keys_modes.py:379` are all real.
- **The spec fits the wire contract exactly and keeps its scope tight.** These claims match `context/wire-contract.md` §9.2 word for word:
  - the 422 for unserved Muse ids;
  - step 5 (missing Vidbyte Meta key, 502) runs before step 6 (pricebook, 422);
  - FEE_ONLY vs TOTAL billing;
  - the 1 to 512 visible-ASCII header bounds.

  No price is invented. Every extra is a `Q-n` with default no.

## FINDINGS

R-1 [Major] [L5/L1] §9.4, §6.3 EC-11, §12.5 — Widening the set adds new billed Muse calls to configurations that work today, and §9.4 says the opposite
  Evidence: The spec says "No call that worked at `base_commit` changes" (§9.4). EC-11 and the PR-body behavior-change line name only fallback chains. Three paths in the code contradict it:
  - *Grader.* `MultiProviderAgenticGraderRuntimeAlgorithm.arun` calls `ProviderModelRegistry.resolve_active(None, …)`. When `provider_models` is unset, that resolves every provider with an env key (`models.py:418-428`), which includes `meta` when `META_API_KEY` is set. Each trial builds its runner inside `_run_provider_trial` (`multi_provider_agentic_grader.py:93`). The trials run under `asyncio.gather(..., return_exceptions=True)` (`:87`), and `_collect_candidates` skips exceptions (`:121`).
  - *Aggregate.* `AggregateAgent` swallows a failed proposer the same way (`aggregation.py:97`, `:129`).
  - *Fanout.* `context_minimal_fanout` defaults to `return_exceptions = True` (`types.py:486`).

  End-to-end probe (`s1_grader_probe.py`): an AUTO agent on the grader, with env `VIDBYTE_API_KEY`, `ANTHROPIC_API_KEY`, and `META_API_KEY`, and `provider_models` unset.
  - At base: `anthropic relay: ANTHROPIC_API_KEY` twice, and no meta request (the meta trial raised `UnsupportedProviderError` and was dropped).
  - Widened: `anthropic …`, then `meta relay: META_API_KEY cap: 32768`, then `anthropic …`.
  Failure: Input: a grader agent that runs fine today, with `META_API_KEY` in the environment for other tools. After this change:
  - each run makes one more Muse call, which Meta bills to the user's account, plus Vidbyte's 2% fee;
  - the user's Meta key is sent to Vidbyte's backend for the first time, in a run that never named `meta`;
  - the grader may pick a different winner.

  With `model_mode=VIDBYTE_MANAGED`, the extra trial is billed TOTAL instead. Aggregate proposers and fanout members that name `meta` likewise turn from a silently failed member into a billed call. Forks and handoffs to `meta` from a parent with no Meta key go Vidbyte-paid with no M-18 check, because children never re-match (probe: `Agent.fork to meta … relay=none cap={'max_tokens': 32768}`). The PR body as specified tells the reviewer and operator about none of this. That is the payments-engineering failure the briefing asked about: a billed path the user never opted into.
  Smallest fix:
  - Replace the §9.4 sentence with the true statement: no `DIRECT` call changes, and no single-provider call that succeeded changes.
  - Add EC-16 for fan-outs that swallow a failed member: the grader with `provider_models` unset (meta is included by env key), aggregate proposers, and fanout members. Each now makes a billed Muse call, and the grader relays `META_API_KEY`.
  - Extend EC-11 to forks and handoffs (Vidbyte-paid when the parent holds no Meta key).
  - Add both to FR-8 and to the §12.5 "behavior change" bullet.
  - Add a §13 fact so S2 can pin it. The seam is `ModalityDetector.create_runner` under the router fixture. `s1_grader_probe.py` shows a working agent-level harness.
  - Optional, `[scope-adding]` Q-6: "Exclude a provider the gateway newly serves from the grader's environment-resolved trials?" Default no.

R-2 [Major] [L5/L10] §6.3 EC-3, §15 A-2, §12.5 — A-2 decides every Agent call, Agents cannot set the cap, and nothing checks A-2 before merge
  Evidence: EC-3 says "Workaround: set `max_output_tokens`". But `BaseAgent.__init__` takes no `max_output_tokens`. Its `max_tokens` is a loop budget (`base.py:317-321`), and the only option an agent passes to its runner is `timeout_seconds` (`base.py:1662`). In the probe, `Agent(..., max_tokens=100)` forwarded `cap={'max_tokens': 32768}`.

  Meta's first-party docs (fetched 2026-10-17) give no output limit for `muse-spark-1.1`:
  - https://dev.meta.ai/docs/models: "All take text, image, video, audio, and PDF input, return text, and have a 1,048,576-token context window."
  - https://dev.meta.ai/docs/quickstart gives a limit only for 1.3: "Model: \"muse-spark-1.3\" … Limits: context 1048576, output 131072".
  - https://dev.meta.ai/docs/protocols/chat-completions: "Requesting more than the model's configured maximum returns `HTTP 400`."

  The six providers already served get no per-model clamp either. `text.py:57-62` applies one default to all of them, so A-2 matches the existing pattern, but nothing has verified it.
  Failure: If `muse-spark-1.1`'s configured maximum is below 32,768, every `Agent` Muse call in a gateway mode (the §4 path, AC-1) gets Meta's 400. The message then gives the misleading "check your own meta key" hint (`vidbyte_gateway.py:104`). The only way out is `DIRECT`, so the feature fails for agents. This would first show up in users' hands, because no step in §12 makes a real call.
  Smallest fix:
  - Correct EC-3: Agent users have no cap setting, so their only workaround is `TextModelMode.DIRECT`. `TextModelRunner` and config users can set `max_output_tokens`.
  - Add a pre-merge check to §12.5 and the PR body, run by the user or ops with their own key after #710 is deployed: one relay call on `muse-spark-1.1` with no `max_output_tokens` must return 2xx. Quote its status in the PR. A 400 flips D-3 before merge.

  This is verification only and adds no product surface.

R-3 [Major] [L8] §12.5 — §12.5 omits the repo's pull-request template, which CONTRIBUTING.md requires
  Evidence: `CONTRIBUTING.md:75-83` says "Use the pull-request template and include: … Compatibility or migration implications. Commands run and relevant output. Documentation changes. Any follow-up work…". The template, `.github/pull_request_template.md`, has the sections Motivation, Changes, Compatibility, Verification (with a checklist), and Follow-ups. §12.5 lists six PR-body facts but never names the template, and §11 says "AGENTS.md states none" of the PR conventions.
  Failure: An implementer or PR author who follows §12 alone writes a free-form body. The R-1 behavior changes then have no "Compatibility" home, and the Run A Q-1 hotfix and this spec's Q-1..Q-5 have no "Follow-ups" home. That draws a convention comment, or loses the merge-order warning among loose bullets.
  Smallest fix: Add a §12.5 row: "Fill `.github/pull_request_template.md`." Map the content to its sections:
  - Compatibility: the behavior change, EC-11 and the new EC-16.
  - Verification: the gate commands and their final lines, the pre-existing red test, and the R-2 smoke.
  - Follow-ups: Run A Q-1, plus Q-1..Q-6.
  - Motivation or Changes: the merge order and the ops prerequisite, stated first.

  Cite `CONTRIBUTING.md:75`.

R-4 [Minor] [L1/L8] §3 NG-8 / §15 Q-4 — The section that will name Meta as served still teaches the wrong way to supply a Meta key
  Evidence: The "Prefixes" bullet (`README.md:290-293`) lists `sk-ant-`, `sk-or-`, `sk-proj-`, `sk-admin-`, `xai-`, and `AIza`/`AQ.`, but not `LLM|`. The next bullet (`:294-297`) says a key "without such a prefix, such as a DeepSeek, Kimi, or Mistral key, goes to the one configured model … that can take it". META is format-bound and never takes an unproven key (`provider_keys.py:60`, `vidbyte/lib/registries/README.md` table A). The user's own must-have is "use muse models with their meta/muse api keys", and the section `jev.py:6` ties to the provider set is the one row 2 edits.
  Failure: A Muse developer reads the section after this PR. It now says Meta is served, but it implies that their `LLM|…` key binds by elimination like a Kimi key, which is not how it binds.
  Smallest fix: Promote the `LLM|` half of Q-4 to a required row 2(c): add "`LLM|` (Meta)" to the Prefixes bullet. This documents existing behavior inside the mandated section, so it is not a feature. Leave `sk-svcacct-` in Q-4.

R-5 [Minor] [L10] §6.1 INV-4, INV-5, INV-9, AC-1 — Three invariants are worded more absolutely than the code allows, so a blind test author can write a test that fails on correct code
  Evidence:
  - *INV-4* says "No other provider's key is ever sent on a `meta` request". T-1 and byok EC-14 accept that `META_API_KEY` is trusted by its name, so any value in it, even another vendor's key, is relayed on `meta` calls.
  - *INV-5* says "Every `meta` gateway body carries the output cap as a JSON integer". In the probe, `extra_body={"max_tokens": None}` forwarded `cap={'max_tokens': None}`. The SDK adds and removes nothing after the `extra_body` merge (`compatible.py:131-134`).
  - *INV-9* includes "a log line, or a trace payload", but no AC tests either, and §13 names no tracer or log seam.
  - *AC-1* (the Agent route) does not assert the cap. Only AC-5 (`TextModelRunner`) pins it.
  Failure: A property test of INV-4 over arbitrary `META_API_KEY` values, or of INV-5 over arbitrary `extra_body`, goes red against a correct build. INV-9's trace and log clause stays untested.
  Smallest fix:
  - Scope INV-4 to keys from `api_keys` and their format-bound matching. Name EC-14 as the accepted exception.
  - Add to INV-5: "unless the caller sets `max_tokens` in `extra_body`, which the SDK forwards unchanged".
  - For INV-9, either name the trace seam (the tracer fixture the byok packs use) or narrow the clause to what AC-14 checks.
  - Add "and the body's `max_tokens` is 32,768" to AC-1.

R-6 [Minor] [L4] §12.3 row 1(b) — The new comment cites a draft PR with no commit, unlike the line it extends
  Evidence: The precedent comment pins a commit: "backend spec r3 section 9.2.8 at commit a14b37e7e" (`jev.py:72-73`). The wire contract is pinned at "r4 at commit `c395349bd`" (`context/wire-contract.md:3`). Row 1(b)'s example cites "cerredz/Vidbyte#710 (meta-muse-gateway spec section 9.2)", which is a draft PR whose spec can still change.
  Failure: The comment's source drifts silently if #710's spec is revised before merge, which breaks the source-cited-set precedent.
  Smallest fix: Cite "cerredz/Vidbyte#710 meta-muse-gateway spec r4 section 9.2 at commit c395349bd", wrapped within 72 columns.

## VERIFIED CLAIMS

**The coordinator's cap claim holds on every route.** The claim is that `text.py:57-62` defaults the cap to 32,768 in every gateway mode. `s1_cap_probe.py` widened the set and recorded the forwarded body on each route:

| Route | Relay | Forwarded cap | Other body keys |
|---|---|---|---|
| `Agent.arun` AUTO, `api_keys` Meta key, `@tool echo` (2-turn loop: echo, then isDone) | `META(api_keys)` on both turns | `{'max_tokens': 32768}` on both turns | messages, model, tools |
| `Agent.run`, `model_mode=VIDBYTE_MANAGED`, `META_API_KEY` set | none | `{'max_tokens': 32768}` | |
| `Agent.arun` AUTO, no Meta key (Vidbyte-paid) | none | `{'max_tokens': 32768}` | |
| `Agent.run` AUTO, `META_API_KEY` in env only | `META(env)` | `{'max_tokens': 32768}` | |
| Fallback anthropic (gateway 503) → `meta/muse-spark-1.1` | Meta on the meta hop | `{'max_tokens': 32768}` on both hops | |
| Fallback meta (gateway 422) → anthropic | Meta on the meta hop | `{'max_tokens': 32768}` on both hops | |
| `Agent.fork` to meta | none | `{'max_tokens': 32768}` | |
| `ModalityDetector.create_runner` (the grader, critic, and judge trial path) | `META(env)` | `{'max_tokens': 32768}` | |
| `TextModelRunner`, `extra_body` `max_completion_tokens=50` | | `{'max_tokens': 32768, 'max_completion_tokens': 50}` (EC-5 holds) | |
| `TextModelRunner`, `extra_body` `max_tokens=None` | | `{'max_tokens': None}` (caller removes the cap; R-5) | |

Other route checks:
- `StreamingTextModelRunner` refuses `meta` in AUTO and in VIDBYTE_MANAGED with `UnsupportedProviderError` (INV-14 holds).
- No CLI or MCP route exists. `vidbyte/cli` holds only skills, and `vidbyte/mcp_server` is empty.
- `get_text_provider` and the raw adapters never build the gateway transport.

**How the default is pinned in tests.**
- AC-5 and INV-5 pin it on `TextModelRunner`.
- The existing `OutputCapTests` (`test_managed_text_wire_contract.py:121-130`) iterates `MANAGED_MODELS`. Once S2 adds META there, removing the default fails that test.
- The Agent route is covered only structurally (R-5 adds AC-1).

**No regression for existing meta users, except R-1.**
- The default `TextModelMode` is AUTO (`model_configs.py:76`, `agents/base.py:108`).
- *DIRECT.* Unchanged. The probe's DIRECT body and the gateway body minus `max_tokens` compare equal, and DIRECT keeps a 60 s timeout and `api.meta.ai`.
- *AUTO with `META_API_KEY` set and no Vidbyte key.* Before: `UnsupportedProviderError` at config build. After: `ConfigurationError` "Missing Vidbyte API key … or use mode=TextModelMode.DIRECT" at runner build. Still no call, so not a silent switch.
- *AUTO with both keys in the environment.* Before: refused. After: relays `META_API_KEY` (FEE_ONLY).
- *Agent with a meta primary, at base.* It builds, then fails at run with `AgentExecutionError` and no fallback hop (`s1_fallback_base_probe.py`). No working agent changes.
- *Fan-outs that swallow a failed member (R-1).* These are the only configurations that worked at base and now bill.

**Core relay and paid claims.**
- AUTO relay: exactly 4 headers (`Idempotency-Key`, `X-Vidbyte-Provider-Key`, `authorization`, `content-type`), timeout 630.0.
- Paid: exactly 3 headers. VIDBYTE_MANAGED sends no Meta key anywhere in the request.
- §4 snippet: prints "Hi". The Anthropic key appears in no request.

**Meta docs.** These claims held when I re-fetched the docs on 2026-10-17:
- `max_tokens` alias: chat-completions.md:405 "The deprecated alias `max_tokens` is still accepted".
- reasoning.md:390 "`max_tokens` (Chat Completions) … cap reasoning tokens plus visible output tokens combined".
- schemas: `max_tokens` "Deprecated in favor of `max_completion_tokens`".
- Context 1,048,576. Output 131072 is given for 1.3 only.
- Prices: $1.25 / $4.25 / $0.15 per 1M tokens for Standard 1.1, equal to `pricing.py:284`.
- "`stop` | Not supported on reasoning models"; "Only `n=1` is supported".

The docs now also list `muse-wonder-1.0`, which the SDK does not know. That is outside this scope.

**Wire contract.** These claims held against `context/wire-contract.md`:
- EC-1: 422 `model_gateway_unsupported_model` for every Muse id except 1.1 and its snapshots.
- EC-2: the 502 at step 5, before the pricebook check at step 6.
- EC-14: a `meta/` id gets 422 `harness_validation_failed`.
- T-2: checks 6 and 8.
- T-4: idempotency.
- FEE_ONLY / TOTAL billing.

The Run A rows A-3, A-7, EC-11, EC-27, EC-29, EC-30, Q-1, and Q-4 are cited correctly.

**Code facts.** These held:
- `transport.py` behavior:
  - 409, 502, and non-JSON answers are re-sent twice with waits of 0.5 s and then 1.0 s;
  - a 422 is not re-sent;
  - the error is raised with no cause chained;
  - errors are worded by status only (AC-7, AC-8, AC-9, EC-13).
- `bearer_headers` returns exactly `authorization` and `content-type`.
- `ProviderKeyMatcher` holds the Meta rule at `:55`, META is format-bound at `:60`, and M-18 is at `:308`.
- `MetaProvider` and `KimiProvider` are bare subclasses (`compatible.py:239`, `:243`). Both use the `openai` tool wire format, the same as each other.
- META is `PROMPT_ONLY` (`structured_output.py:47`) and uses `ChatCompletionUsage` (`model_provider.py:72`).
- Every `path:line` the spec gives for `vidbyte_gateway.py` (:107, :181, :192, :195, :208) and `jev.py` (:72-81, :84, :88, :113) is correct.

**README.**
- The section spans `README.md:236-383`.
- The Providers bullet is at :337-339 and the cap bullet at :343-345.
- The two README tests bind the listed facts (`test_managed_text_acceptance.py:189-194`, `test_provider_keys_acceptance.py:298-305`).
- The section contains no "meta" substring today, so a README test for "Meta" goes red at base as it should.

**Map and docs files.**
- `REPO_MAP.md`, `llms.txt`, and `artifacts/file_index.md` have no gateway entry.
- `vidbyte/lib/README.md`, `vidbyte/agents/README.md`, `vidbyte/providers/README.md`, and `vidbyte/lib/registries/README.md` have no `## Notes for agents`.
- The repo has no CHANGELOG file (`pyproject.toml:59` points to GitHub releases).
- `contracts/sdk-public-api.json` and lint C016 are not affected, because the constant is not a root export.

**Gates and commands.**
- Lint ends with `SDK-LINT: PASS` (`lint/core/report.py:58`). The code-map's "AGENT-LINT" is wrong, and the spec already corrects it.
- semgrep fails locally with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`, and the remote workflow pins 1.170.1 (`static-policy.yml:24-30`).
- The harness test `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` is still red at `845a4d9b` (1 failed). PR #1147 is still OPEN. This change touches no path that the other branch-scoped `harness_threads` checks diff (`vidbyte/tools`, `vidbyte/lib/configs`).

**Tests that flip.**
- The widened-set plugin run of the area gives `2 failed, 166 passed`, exactly `GatewayShapeTests::…both_gateway_modes` and `KeySelectionTests::test_managed_state_refuses_every_provider_the_gateway_does_not_serve`.
- At base the area gives `168 passed`.
- The meta-referencing suites elsewhere, run widened, give `561 passed`.

**One claim did not hold.** §9.4 says "No call that worked at `base_commit` changes" (R-1).
