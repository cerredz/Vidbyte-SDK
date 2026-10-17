LENS: engineering
VERDICT: SOUND — the one-member change routes every key correctly in all 16 probed runs and adds no new failure mode, retry, or log path. Three Minor gaps remain: a T-1 negative test, the EC-16 example list, and the live check's coverage of the paid path.

WHAT THE IMPLEMENTATION GETS RIGHT
- The production diff is exactly one enum member plus a comment (`vidbyte/lib/constants/jev.py:72-83`, 5+/2-). Key routing stays on the exact-match `ProviderKeys.key_for` (`vidbyte/lib/dataclasses/agents.py:283-291`). Across 8 scenarios × base/branch, no key ever reached another provider's envelope. The scenarios cover fallbacks in both directions, forks in both directions, an aggregate, a mixed list with `META_API_KEY` set, and the grader in `VIDBYTE_MANAGED`.
- META is format-bound (`provider_keys.py:55`, `:60`), so an `LLM|` key cannot bind to another provider. M-18 picks up `meta` through the set (`provider_keys.py:308`), and the AC-4 path never reads `META_API_KEY` during credential resolution.
- The test pack is not vacuous. All 15 new tests are red on a real detached `845a4d9b` worktree, each for the meta-unserved reason, and 6 of 7 in-memory mutants are killed.
- Nothing was invented or leaked:
  - `pricing.py`, `lint/pricebook_vintage_lock.json`, and `lint/baseline.json` are unchanged, and the Muse 1.1 row resolves to 1.25/4.25/0.15.
  - No key-shape literal appears in the diff or the commit messages.
  - The `DIRECT` golden is byte-identical to base.
  - The real `HttpTransport` has no logging at all, so the faked seam in AC-14 hides no log path.

FINDINGS (ranked, most severe first)

R-E1 [Minor] [test quality] tests/features/sdk_provider_keys/test_provider_keys_agents.py:429-443 — No test can fail if a Meta key from `api_keys` rides on a non-meta call that holds no key of its own.
  Evidence: The in-memory mutant `meta_key_to_keyless` makes `ProviderKeys.key_for(p)` return the META key when `p` is not meta and has no key. The area suite still ends `183 passed in 1.36s`. The effect probe (`s4e_mutant_effect_probe.py`) uses `Agent(provider="meta", api_keys=[K_META], fallback=["anthropic/claude-sonnet-5"])` with Meta answering 401. Without the mutant it sends `[('meta', 'K_META'), ('anthropic', None)]`. With the mutant it sends `[('meta', 'K_META'), ('anthropic', 'K_META')]`. Every test that pairs a meta call with a non-meta call gives the non-meta side its own key, so a substitution has no state in which to show up:
  - AC-11 uses `api_keys=[K_ANTHROPIC, K_META]` (`:431`);
  - in the grader test, the anthropic member holds `ANTHROPIC_API_KEY`;
  - `MetaRelayTests` makes only meta calls.
  Failure: A regression lends the matched Meta key to a keyless fallback or fork. The Meta key then rides in `X-Vidbyte-Provider-Key` on a `provider: "anthropic"` envelope, and the gateway forwards it to Anthropic, which is the T-1 harm. The area suite stays green. (A generic "lone key" substitution is already caught by 5 tests, so the gap is only the Meta-specific case.)
  Smallest fix: Add one subtest beside AC-11. Use `api_keys=[K_META]` only, a cleared environment, Meta answering 401, and an Anthropic fallback. Assert that the anthropic request has `provider_key_header(...) is None`, exactly 3 headers, and `K_META not in flat(request)`.
  Spec IDs: INV-4 (first sentence), T-1, AC-11

R-E2 [Minor] [failure modes / billing disclosure] vidbyte/agents/multi/dispatcher.py:69-70 — EC-16's example list leaves out multi-agent team workers. This failure-tolerant composition now bills a Muse worker that used to fail and be contained.
  Evidence:
  - `dispatch()` catches the failure: `except Exception as exc: return await self._record_dispatch_failure(state, dispatch, exc)` (`:69-70`).
  - `_record_dispatch_failure` records `TaskBlocker(code="dispatch_boundary_error", ..., retryable=True)` and returns `False` instead of raising (`:118-124`).
  - `git grep` for `return_exceptions` and `except ... VidbyteSdkError` turns up no other unlisted text-model composition. The other hits are MCP attach/close, Jev alignment (TypeSafe decision model), and Jev sub-agents that reuse the main agent's own model.
  Failure: Take a multi-agent team in `AUTO` whose worker names a Muse model.
  - At base, every dispatch to that worker failed at runner construction (M-12). The ledger recorded a retryable blocker, the manager carried on, and nothing was billed.
  - On this branch, the worker runs a full agent loop and bills: FEE_ONLY with a Meta key, otherwise TOTAL. Each dispatch makes `max_invocation_retries + 1` invocations (default 0 + 1, `transfer.py:56`).
  - The §12.5 Compatibility bullet does not name this composition. The spec does call its list "not a closed list".
  Smallest fix: Add "multi-agent team workers that name a Muse model" to the PR body's Compatibility examples (the §12.5 behavior-change bullet). Text only.
  Spec IDs: EC-16, FR-8, AC-15

R-E3 [Minor] [observability / verification] docs/spec/meta-muse-managed-text/spec.md:540-552 — The pre-merge live check exercises only the relay path. Merge prerequisite 2 ("ops has provisioned the backend's `META_API_KEY`") is never verified end to end.
  Evidence:
  - §12.5 specifies "two `AUTO` relay calls on `muse-spark-1.1` with the same keys (`VIDBYTE_API_KEY` and `META_API_KEY` set)".
  - The wire contract answers 502 for "Vidbyte-paid call with no Vidbyte Meta key configured" and also for "Vidbyte-paid call that Meta refuses with 401, 402, or 403".
  - The SDK re-sends both (`vidbyte_gateway.py:73`) and words both alike: "unavailable or refused Vidbyte's own account … the cause is not known" (`:134-136`; D-5 keeps the body's remedy hidden).
  Failure: Suppose ops provisions a mistyped or revoked backend key. Prerequisite 2 then reads as met. After merge and release, every Vidbyte-paid Muse call fails 502 after 3 sends, with 3 status-page 5xx errors per call and a message that cannot name the cause. That covers `VIDBYTE_MANAGED`, `AUTO` without a Meta key, and keyless forks, fallbacks, and grader members. The weighted words "both Vidbyte-paid and with the user's own key" are only half-checked live.
  Smallest fix: Add a call (c) to the live-check recipe and record its status in the PR body: `TextModelRunner(TextModelConfig(provider="meta", model="muse-spark-1.1", mode=TextModelMode.VIDBYTE_MANAGED)).run("Say hi.")`. It passes when the call returns. No code change.
  Spec IDs: §12.5, FR-8, AC-15, EC-2, G-2

VERIFIED CLAIMS
1. Implementer: "only `jev.py` changes in `vidbyte/` (5+/2-)". HELD (`git diff --stat 845a4d9b..2ba4a678 -- vidbyte` → `1 file changed, 5 insertions(+), 2 deletions(-)`). The README diff is 7+/-7, with only the three bullets changed.
2. Implementer: "modified no test file". HELD (`git diff --stat 856e3c0a..2ba4a678 -- tests` is empty).
3. Test plan: "24 tests red at HEAD, all for the meta-unserved reason". HELD on a real detached base worktree carrying the branch's tests: `24 failed, 159 passed`. The 24 include all 15 new tests, so none passes on base by accident.
4. Test plan mutation table: HELD on an independent re-run. Results:
   - `configs_only` (META missing from `provider_keys`' view) is killed by the EC-6 M-18 test.
   - The README with no `LLM|` edit is killed by AC-13.
   - A meta-specific removal of the gateway cap is killed by 11 tests.
   - My extra mutants `string_meta` (the string `"meta"`; 6 tests) and `managed_reads_meta_env` (AC-4) are killed.
   - `meta_key_to_keyless` survives (R-E1).
5. S2 grant edits weakened no assertion. HELD. `git diff 82a3bd8e..856e3c0a -- tests` removes 0 `def test_` or `assert` lines. The removed lines are table rows and signatures that match the test-plan before/after table. The one coverage removal is the `("meta","llama-4")` refused row, by design; it is replaced by the INV-1 positive test, which keeps the endpoint and streaming negatives for meta.
6. INV-4 / T-1 (the key goes only to Meta): HELD in the code. `s4e_key_routing_probe.py` reports `violations=none` in all 16 runs. It is under-tested in one state (R-E1).
7. INV-3 / AC-4 (`VIDBYTE_MANAGED` never reads `META_API_KEY`): HELD for credential resolution. The grader still reads it to pick members (the spec carve-out). Probe 8 shows that in `VIDBYTE_MANAGED`, a set `META_API_KEY` adds a Vidbyte-paid meta member (`('meta', None, 32768)`) and the key is never sent. EC-16 discloses the TOTAL billing.
8. EC-16 / EC-11 disclosed paths: HELD.
   - The grader and aggregate are confirmed by probe: base drops meta, branch adds it.
   - The critic catch is at `independent_critic.py:82-85`. The brief writer catches at `writer.py:146` and `:160`. Fanout has `return_exceptions = True` at `types.py:486`.
   - Forks keep the parent's record: probe 4 relays `K_META`, and the S2 test covers `META_API_KEY` and the paid case.
   - The handoff reuses the source's runner cache and model (`handoff.py:65-75`).
   - One path is missing from the examples (R-E2).
9. 502 re-send is harmless and bounded: HELD.
   - At most 2 re-sends (`JEV_DEFAULT_RETRY_COUNT = 2`), with waits of 0.5 s then 1.0 s, inside one call deadline (`vidbyte_gateway.py:200-216`). AC-8 asserts 3 sends, `[0.5, 1.0]`, and identical headers.
   - The missing-key 502 is wire step 5, before the idempotency claim (step 7) and before any I/O, so nothing is billed.
   - Replay of upstream 502s after step 7 is the backend's behavior. It is provider-generic and unchanged by this PR.
10. INV-9 / AC-14 (no key in logs or errors): HELD.
    - The relayed 400 and 401 reasons (`vidbyte_gateway.py:100-104`) use only `provider.value`, the status, and the variable name `META_API_KEY`, never a value.
    - `_send` keeps only the exception class (`:233-239`).
    - `vidbyte/lib/http/transport.py` has no logging. httpx/h11 accept a `|`-bearing relay header value (h11 serialization check → `True`).
11. A-2 disclosure: ADEQUATE.
    - Every probed agent body carries `max_tokens` 32,768, and the live check's `TextModelRunner` call sends the same body.
    - The control call isolates the cap, because a relayed 400 withholds Meta's text.
    - The check sits at merge, the last point this PR can enforce.
    - The relayed-400 hint "check your own meta key" would mislead if A-2 is false. EC-3 accepts that.
12. INV-15, NFR-2, NFR-3: HELD. The price row is `input 1.25, output 4.25, cache_read 0.15`. The three files show an empty `git diff --stat`. `git diff | grep -E '^\+.*LLM\|[0-9]'` finds nothing. The comment lines measure 67/67/69/42 columns.
13. Lint (`SDK-LINT: PASS`) was not re-run; that belongs to the conventions lens and was kept out to save memory.

COMMANDS RUN
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider` (HEAD `94d3f381`) → `183 passed in 1.99s`
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 <scratchpad>/s4e_key_routing_probe.py` → 16 lines, every one `violations=none`. Base vs branch:
  - aggregate base `[openai, anthropic]` vs branch `[meta K_META, openai, anthropic]`;
  - grader `VIDBYTE_MANAGED` base `['anthropic']` vs branch `['anthropic','meta']` with `('meta', None, 32768)`.
- `S4E_MUTANT=<m> PYTHONPATH="$(pwd);<scratchpad>/plugins" py -3.11 -m pytest <area> -p s4e_mutants --tb=no`:
  - `string_meta` → `6 failed, 177 passed`
  - `configs_only` → `1 failed, 182 passed`
  - `meta_no_cap` → `11 failed, 172 passed`
  - `meta_key_to_keyless` → `183 passed` (survives)
  - `lone_key` → `5 failed, 178 passed`
  - `managed_reads_meta_env` → `1 failed, 182 passed`
  - `readme_no_llm_prefix` → `1 failed, 182 passed`
- `py -3.11 <scratchpad>/s4e_mutant_effect_probe.py` →
  - `unmutated: ... [('meta', 'K_META'), ('anthropic', None)]`
  - `meta_to_keyless: ... ('anthropic', 'K_META')]`
  - `lone_key: ... ('anthropic', 'K_META')]`
- Real base check:
  - `git worktree add --detach <scratchpad>/s4e-base 845a4d9b`;
  - `git -C <base> checkout 2ba4a678 -- tests/features/sdk_managed_text tests/features/sdk_provider_keys`;
  - area pytest with `PYTHONPATH=<base>` → `24 failed, 159 passed in 2.17s`;
  - `git worktree remove --force <base>` → `git worktree list | grep -c s4e-base` = `0`, and the review worktree is still clean.
- `git diff --stat` checks (vidbyte, README, tests after S2, pricing/lock/baseline) → as in claims 1, 2, and 12.
- The price-row resolve, the `awk` comment-width check, and the h11 header serialization → as in claims 10 and 12.

Scratch files (not committed):
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/s4e_key_routing_probe.py`
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/s4e_mutant_effect_probe.py`
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/plugins/s4e_mutants.py`
