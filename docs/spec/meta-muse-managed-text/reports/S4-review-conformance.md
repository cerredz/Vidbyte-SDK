LENS: conformance
VERDICT: NEEDS REWORK — the diff matches spec r3 line for line, but the spec's Meta key shape (`LLM|<id>|<secret>`) contradicts Meta's own authentication page (`LLM_<id>_<secret>`). With a key in the shape Meta issues, the user's must-have path fails: the §4 snippet raises at construction, and the key can be relayed to Kimi. AC-1 cannot catch this, because every test fakes the SDK's shape, not Meta's.

Review target: `git diff origin/main...2ba4a678` (merge base `845a4d9b`). Spec r3, test-plan, request §A–§D, AGENTS.md, field guide, and wire contract all read in full.

WHAT THE IMPLEMENTATION GETS RIGHT (so nobody "fixes" what works)
- `vidbyte/lib/constants/jev.py:72-83` matches §12.3 row 1 exactly. It adds the enum member `ModelProvider.META` (not a string), keeps the `frozenset[ModelProvider]` annotation, and uses the 4-line comment word for word at 67/67/69/42 columns. It leaves `__all__`, the header, and every other constant untouched. It is the only production code change, and it reaches every reader of the set: the M-12 message now reads "serves only: anthropic, deepseek, gemini, kimi, meta, openai, xai", and the M-18 message offers "Vidbyte's own meta account".
- `README.md` changes only the three bullets row 2 names (Providers, Output cap, Prefixes). Every fact the two older README tests bind is still present.
- With the SDK-rule key shape, every weighted-word path I drove holds:
  - AUTO with a list key relays it, list before `META_API_KEY`;
  - AUTO with only `META_API_KEY` relays the env key;
  - AUTO with no key and `VIDBYTE_MANAGED` (agent and runner) relay nothing;
  - `arun`, fallback to Muse, and fork all hold;
  - the cap is `max_tokens` 32768 on every meta body, with no `max_completion_tokens`;
  - the timeout is 630;
  - a relayed 401 is sent once and leaks no key in the message or in DEBUG logs;
  - a custom endpoint and streaming are still refused for meta.
- The tests can fail. With META removed from the set in memory, 23 of the 24 meta tests fail; the 24th is the README test. No test was deleted or skipped, and no `assert` line was removed. `lint/baseline.json`, `lint/pricebook_vintage_lock.json`, and `pricing.py` are unchanged, and `META/muse-spark-1.1` still resolves to 1.25 / 4.25 / 0.15.

FINDINGS (ranked, most severe first)

R-C1 [Blocker] [request fidelity / AC-1 proof] `vidbyte/lib/registries/provider_keys.py:53-55` (pre-existing rule this PR depends on), `README.md:292` (this PR's row 2(c)), `docs/spec/meta-muse-managed-text/spec.md:87-88` (§4) — The user's own Meta key in `api_keys` is refused at construction. AC-1 passes only because its fake key is not in Meta's documented shape.
  Evidence:
  - Meta's first-party authentication page, the very URL `provider_keys.py:54` cites for the rule, says: "API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores: `LLM_1607358788850350_nx9.....LJY`". This is from a live WebFetch of https://dev.meta.ai/docs/authentication.md on 2026-10-17. The same text is in this session's copy, `scratchpad/meta-docs/md/authentication.md`, fetched 2026-10-16 22:05.
  - The Common issues entry on https://dev.meta.ai/docs/error-handling, a page spec §9.2 and §11 cite, says: "**Cause:** API key not in `LLM_{numeric_id}_{secret}` format. … The key should start with `LLM_`." (`scratchpad/meta-docs/error-handling.md:509-511`).
  - The SDK proves only `re.compile(r"LLM\|[0-9]+\|[A-Za-z0-9_-]+")` with prefix `("LLM|",)`, and META is in `FORMAT_BOUND_PROVIDERS`, so it takes no unproven key.
  - This PR's README row 2(c) now tells users "`LLM|` (Meta)" is the prefix that proves a Meta key, and spec §4 says "your Meta key, LLM|<your Meta app id>|<your Meta secret>". No Meta page in the scratchpad mentions `LLM|`. Spec §11's "First-party Meta facts" never states the key format.
  - `s4c_snippet_documented_key.py` runs spec §4 verbatim and changes only the shape of the `META_API_KEY` value:
    `documented LLM_<id>_<secret>: printed=[] requests=0 error=ConfigurationError: api_keys[1] (53 characters) has no prefix that proves its provider, and none of the providers configured here (meta, anthropic) can take such a key. …`
    `sdk-rule LLM|<id>|<secret>: printed=['Hi', 'Hello'] requests=2 error=None`
  Failure: A developer pastes the key Meta's dashboard issues into `api_keys`, either the §4 / G-1 / AC-1 (P0) pattern or the README's mixed-list pattern. The Agent or `TextModelConfig` raises M-6 before any request. So "Want users to be able to use muse models with their meta/muse api keys" (request §D) holds only on the `META_API_KEY` path. The AC-1, AC-2, AC-6, AC-11, and EC-11 tests all use `K_META = "LLM" + "|" + …`, so none of them can fail for this reason. The §12.5 pre-merge live check also cannot catch it, because it passes the key only through `META_API_KEY`. This also contradicts the field-guide lesson "Mirror the vendor's API reference page exactly, not a launch post or earlier design" (`provider-api-contracts.md`).
  Smallest fix (needs spec r4; touching `provider_keys.py` is §14 "Ask first", so the orchestrator or user must approve):
  - Add Meta's documented shape to the META row of `KEY_FORMATS`, keeping `LLM|` in case old keys exist: prefixes `("LLM|", "LLM_")`, regex `LLM(?:\|[0-9]+\|[A-Za-z0-9_-]+|_[0-9]+_[A-Za-z0-9_-]+)`.
  - Change the README Prefixes bullet and the §4 comment to Meta's documented `LLM_` form.
  - Add a concatenated `"LLM" + "_" + "1" * 16 + "_" + "s" * 32` fake to the AC-1 and AC-2 tests.
  - Make the §12.5 live check pass the real key through `api_keys`, not only through `META_API_KEY`.

  If the matcher change is declined, the minimum is: remove "`LLM|` (Meta)" from the README, tell Meta users in the README and in the PR body to use `META_API_KEY`, and record the gap as an open question (Q-n).
  Spec IDs: G-1, FR-2, AC-1, AC-2, AC-13, FR-7, D-7, NFR-3 (fakes should be the vendor's shape), request §D "use muse models with their meta/muse api keys"

R-C2 [Major] [request fidelity / security constraint] `vidbyte/lib/registries/provider_keys.py:55,60` and README "Other keys" bullet (`README.md:294-297`) — A real Meta key in a mixed list is relayed on a `provider: "kimi"` envelope. Request §C asked the run to confirm this cannot happen, and the spec says it holds.
  Evidence:
  - Request §C asks: "Confirm that a Meta key reaches only `provider: "meta"` envelopes." It also states: "a Meta key is relayed only on a `provider: "meta"` call."
  - Spec T-1 claims "Matching binds an `LLM|`-prefixed key only to `meta`". That is true only for a shape Meta does not issue (R-C1).
  - `s4c_misroute.py` builds an AUTO `Agent(provider="anthropic", api_keys=[K_ANT, <LLM_ key>], fallback=["kimi/kimi-k2.7-code", "meta/muse-spark-1.1"])`, and Anthropic answers 401:
    `envelope provider=anthropic relay=K_ANT`
    `envelope provider=kimi relay=<META_KEY in LLM_ shape>` → result `from-kimi`
  - `trace_llm_underscore.py` shows the same thing without HTTP: `anthropic primary + meta,kimi others -> {'kimi': '<LLM_KEY>', …}` and `deepseek primary + meta other -> {'deepseek': '<LLM_KEY>'}`.
  Failure: Following this PR's guidance to mix Meta keys into `api_keys`, a user whose list also configures DeepSeek, Kimi, or Mistral sends their Meta secret through the gateway to that vendor. The "Other keys" rule binds it to the one model that takes unproven keys. The mechanism predates this PR (#1027, and DIRECT does the same), so the rating is Major, not Blocker. But the request put exactly this check in scope, and the spec signed it off on an unverified key shape.
  Smallest fix: the R-C1 matcher row. Once the key is format-bound to `meta`, the unproven-key path can no longer take it. Add one failing-first test: `[K_ANT, <LLM_ fake>]` with a Kimi fallback must never put the Meta fake on a non-meta envelope.
  Spec IDs: INV-4, T-1, FR-2, request §C (security) and §D "a key goes only to the vendor it was matched to"

R-C3 [Minor] [spec internal consistency / AC-15] `spec.md:184` (AC-15) vs the live draft PR #1180 body — The "word for word" merge-prerequisite sentence contains "(§12.5)", which points nowhere in a PR body. The draft already deviates from it, while the S3 report says it carries the sentence.
  Evidence: All 7 spec copies are identical (`grep -o "This PR merges only after[^\"]*has passed" spec.md | sort | uniq -c` → `7`). `gh pr view 1180 --json body` reads: "Do not merge: this PR merges only after … and after the pre-merge live check (spec §12.5) has passed." That is lowercase "this" and "(spec §12.5)". `S3-implementer.md:66` says the placeholder "already carries the canonical merge-prerequisites sentence".
  Failure: S6 must choose between an exact copy with a dangling "§12.5" and a useful reference that fails AC-15's "word for word".
  Smallest fix: add one clause to AC-15: "(§12.5)" may be written as a link to `docs/spec/meta-muse-managed-text/spec.md` §12.5. Otherwise the text stays verbatim.
  Spec IDs: AC-15, FR-8

R-C4 [Minor] [spec citations] `spec.md` INV-5, D-3, §2/§8.4 and others — `jev.py:84` (5 citations) and `jev.py:113` (2 citations) point to the wrong lines once this change lands.
  Evidence: On this branch, `sed -n '84p;87p;113p;116p' vidbyte/lib/constants/jev.py` prints `})`, `VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS: int = 32_768`, `ModelProvider.GLM: "GLM_API_KEY",`, and `ModelProvider.META: "META_API_KEY",`. At `845a4d9b`, line 84 is the cap constant and line 113 is `META_API_KEY`.
  Failure: Once the spec lands in `docs/`, a reader of INV-5 (P0) or of S6's "cap evidence" who follows `jev.py:84` lands on the set's closing brace. The orchestrator briefing already repeats "jev.py:84".
  Smallest fix: cite the constants by name (`jev.py:VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS`), or use `:87` and `:116`, in the spec and in the S6 PR body.
  Spec IDs: INV-5, D-3, §8.4

VERIFIED CLAIMS
1. "Only `jev.py` changes in `vidbyte/`, 5+/2-." HELD: the diff shows one hunk pair at lines 72-83.
2. "baseline.json, pricebook lock, and pricing.py unchanged." HELD: `git diff 845a4d9b 2ba4a678 -- lint/baseline.json lint/pricebook_vintage_lock.json | wc -l` gives 0, and the Muse 1.1 row resolves to 1.25 / 4.25 / 0.15 (INV-15).
3. "No key-shape literal in the diff or the commit messages." HELD: `git diff … | grep -E 'LLM\|[0-9]'` prints nothing. Every Meta fake is concatenated. Every commit ends with the attribution line.
4. "The comment matches §12.3 1(b) word for word, at ≤72 columns." HELD: 67/67/69/42.
5. "Area: 183 passed." HELD: `183 passed in 1.97s`.
6. "24 red at HEAD for the meta-unserved reason; the tests can fail." HELD: un-widening the set in memory gives `23 failed, 160 passed`. The 24th is the README test, which the README edit satisfies.
7. "Lint: SDK-LINT: PASS." HELD: re-run, exit 0.
8. "15 new tests; no assertion weakened; edits only under the grant." HELD:
   - 15 added `def test_`, 0 removed, 0 removed `assert` lines.
   - The only deletion is the granted `("meta","llama-4")` row.
   - `PROVIDER_KEYS[META]`, `K_META_2`, and `GatewayCall(model=, mode=)` fall outside the grant's named tables, but they are additive or strengthen tests, and existing callers behave the same.
9. "AC-1: the §4 snippet works." HELD with the SDK-rule fake: 2 POSTs to the gateway; agent attempt `provider=meta`, 4 headers, relay = Meta key, `max_tokens=32768`, timeout 630; paid call 3 headers. The Anthropic key is in no request. DID NOT HOLD with Meta's documented shape (R-C1).
10. "The relay is already vendor-exact; META accepts only Meta-shaped keys" (pipeline.md scout fact; spec T-1). DID NOT HOLD for keys in Meta's documented shape (R-C2).
11. The canonical merge sentence is identical everywhere it is repeated. HELD: 7 identical copies (TL;DR, §2, AC-15, FR-8, §9.4, §12.5, A-3).
12. "The placeholder PR body carries the canonical sentence." PARTLY: the content is the same, the words differ (R-C3).
13. Wire contract:
    - EC-1 (only `muse-spark-1.1` and its dated forms served), EC-2 (step 5 before step 6 gives 502, not 422), EC-15 (422 before #710), and the FEE_ONLY/TOTAL wording all match `context/wire-contract.md` §9.2.
    - The header pattern `[!-~]+` accepts both `LLM|` and `LLM_`, so the backend relay is unaffected by R-C1.
    - The wire contract's line "Meta's documented key shape `LLM|<app id>|<secret>`" is itself wrong; that is a note for Run A, and harmless there.
14. `publish.yml` is `workflow_dispatch`, which is the basis of the §12.5 merge-gate argument. HELD.
15. §8.4 budget is 0/0/0/0/0/0. HELD. Files outside §12.3: only `docs/spec/meta-muse-managed-text/**` and the S2 test packs (row 3). None under other specs or maps.
16. Deviations the implementer reported:
    - the extra S001 IMPROVED;
    - 6260 vs 6245 tests;
    - origin/main moved.

    All three are necessary or harmless, and none changes the build. I found no unreported production deviation.
17. §5 diagram vs the actual call path. Two divergences, neither of which changes behavior:
    - For an `Agent`, node D runs first, in `BaseAgent.__init__` (`base.py:191`, so M-18 fires at construction). Nodes B and C run only when the agent builds its runner during `run`. So for agents, an unserved-provider refusal arrives at run time, wrapped in `AgentExecutionError`, not "at construction" as §5's prose says.
    - Node G's `MetaProvider._create_payload` is inherited from `OpenAICompatibleProvider._create_payload` (`compatible.py:58`).

COMMANDS RUN
- `git diff --stat origin/main...2ba4a678` → `30 files changed, 2832 insertions(+), 51 deletions(-)`. Production files: `README.md` (14) and `jev.py` (7).
- `git diff origin/main...2ba4a678 -- vidbyte README.md lint` → the jev.py and README hunks only. The lint/ diff is empty.
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider` → `183 passed in 1.97s`
- The same command with `-p s4c_unwiden` (META removed from the set in jev, model_configs, and provider_keys) → `23 failed, 160 passed in 1.35s`
- `PYTHONPATH=$(pwd) py -3.11 scratchpad/s4c_snippet.py <wt>` (spec §4 verbatim) → `PRINTED: ['Hi', 'Hello']`, `REQUESTS: 2`, `ANTHROPIC_KEY_IN_ANY_REQUEST: False`, `META_KEY_OCCURRENCES_PER_REQUEST: [1, 0]`
- `… scratchpad/s4c_snippet_documented_key.py <wt>` → `documented LLM_<id>_<secret>: printed=[] requests=0 error=ConfigurationError …` and `sdk-rule LLM|<id>|<secret>: printed=['Hi', 'Hello'] requests=2 error=None`
- `… scratchpad/s4c_paths.py` → all 10 path cases as listed in "gets right". M-12 reads "serves only: anthropic, deepseek, gemini, kimi, meta, openai, xai", and the relay 401 run reports `sends: 1  K_META in logs: False`.
- `… scratchpad/trace_llm_underscore.py` → `provider_of(underscore) = None`; `accepts_unproven(meta, underscore) = False`; `anthropic primary + meta,kimi others -> {'kimi': '<LLM_KEY>', …}`
- `… scratchpad/s4c_misroute.py` → `envelope provider=kimi relay=<META_KEY in LLM_ shape>`
- WebFetch https://dev.meta.ai/docs/authentication.md → "API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores" / `LLM_1607358788850350_nx9.....LJY`
- `py -3.11 lint/run.py` → `SDK-LINT: PASS` (exit 0)
- `gh pr view 1180 --json …` → draft, OPEN, head `94d3f381`, placeholder body as quoted in R-C3
- `git log --format=%B 845a4d9b..2ba4a678 | grep Co-Authored` → present on all 20 commits
- `git diff origin/main...2ba4a678 -- tests | grep -cE '^\+\s+(async )?def test_'` → 15; removed `def test_` → 0
