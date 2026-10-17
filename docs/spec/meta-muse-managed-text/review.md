# Adversarial review: Let the SDK's gateway text modes (AUTO and VIDBYTE_MANAGED) use provider meta

Diff reviewed: `origin/main...2ba4a678` (merge base `845a4d9b`; worktree HEAD `ee873166` adds only reviewer reports) · Lenses: conformance, conventions, engineering · Verifier: reports/S4-findings-verifier.md

## Verdict
NEEDS REWORK — The production diff is correct as specified. But the spec's Meta key shape (`LLM|<id>|<secret>`) is not the shape Meta's own authentication page documents today (`LLM_<id>_<secret>`). With the documented key in `api_keys`, the user's must-have path (§4, G-1, AC-1) is refused at construction. In a mixed list, the same key is relayed to Kimi or DeepSeek. No test can catch either failure, because every fake uses the undocumented shape.

## Confirmed findings (must fix) — 2
| ID | Severity | Lens | Where (path:line) | Finding (claim) | Evidence (verifier's own) | Smallest fix | Status |
|---|---|---|---|---|---|---|---|
| R-1 | Blocker | conformance (R-C1, R-C2 merged) + verifier | `vidbyte/lib/registries/provider_keys.py:53-55` (root cause; pre-existing since #1027 `72a4ade1`); `README.md:292` (this PR's row 2(c)); `docs/spec/meta-muse-managed-text/spec.md:87-88` (§4) | Meta's documented key shape `LLM_<numeric id>_<secret>` matches no `KEY_FORMATS` rule, and `LLM_` is not a reserved prefix. Two failures follow:<br>(a) **The must-have fails.** A user's real Meta key in `api_keys` raises M-6 at construction. This is the §4 / G-1 / AC-1 (P0) path. Only the `META_API_KEY`-only path works.<br>(b) **The key goes to the wrong vendor.** In any list where an unproven-key provider (Kimi, DeepSeek, Mistral, GLM, MiniMax) is configured, the Meta key binds to that provider by elimination and is relayed on its envelope. That breaks request §C "a Meta key is relayed only on a `provider: "meta"` call" and spec T-1 / INV-4.<br>(c) **The PR documents the wrong shape.** README row 2(c) now tells users `LLM\|` is the prefix that proves a Meta key.<br>(d) **No test can fail for this.** Every Meta fake (`K_META`, `K_META_2`, both `ORACLE_KEYS`) uses the `LLM\|` shape.<br>(b) is inherited byte for byte from base. (a) defeats this PR's deliverable. | **First-party source, fetched live by curl on 2026-10-17 12:06 UTC:**<br>• https://dev.meta.ai/docs/authentication.md says "API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores". The HTML page gives the same text.<br>• https://dev.meta.ai/docs/error-handling.md:509 gives the cause "API key not in `LLM_{numeric_id}_{secret}` format", and :511 says "The key should start with `LLM_`".<br>• `LLM\|` appears 0 times in the authentication, error-handling, quickstart, muse-code/auth, api-reference, and sdks pages, and in llms.txt.<br>**Probe** `s4v_probe.py`, with the spec §4 snippet run verbatim:<br>• HEAD, `LLM_` key → `ConfigurationError: api_keys[1] … has no prefix that proves its provider, and none of the providers configured here (meta, anthropic) can take such a key`, with 0 requests.<br>• HEAD, `LLM\|` key → 2 requests, both `meta`, relay = Meta key, `max_tokens` 32768.<br>• §4 without the `api_keys` line (key in `META_API_KEY` only) → works for both shapes.<br>• Misroute: anthropic primary answering 401, `api_keys=[K_ANT, LLM_ key]`, kimi fallback → `('kimi', '<META LLM_ shape>')`. This happens with or without meta configured, and identically at base `845a4d9b` (`git archive` copy).<br>• `TextModelConfig(deepseek or kimi, AUTO, api_keys=[LLM_ key])` → relayed on the `deepseek` / `kimi` envelope, at base and at HEAD.<br>**Fix check:** with the row widened in memory, all of the above go right: §4 relays the `LLM_` key on `meta`, kimi gets `None`, a lone `LLM_` key for deepseek gets M-18, and `accepts_unproven(<any>, LLM_…)` is False. The area suite gives `1 failed, 182 passed`, and the one failure is the table-F pin (by design). | See **R-1 fix detail** below. Production change: one `KEY_FORMATS` row, its source comment and registries README row, and one README bullet. The production file is **outside spec §12.3**, so the spec needs an amendment (orchestrator). Tests (needs grant): the table-F pin plus three subtests. | open |
| R-2 | Major | conventions (R-V1) | `tests/features/sdk_provider_keys/test_provider_keys_modes.py:260` and 51 more added or edited `#` lines across 12 test files | All 52 of the `#` comment lines this PR adds or edits in the two test packs are wider than 72 columns (up to 154). That breaks field-guide `comment-format.md`. The 4 lines in `jev.py` comply. | Verifier's awk over `git diff -U0 origin/main...2ba4a678 -- '*.py'`, counting added `#` lines: `TOTAL over 72: 52`. Per file: acceptance (managed) 10/10, provider_keys acceptance 8/8, failures 7/7, agents 4/4, modes 4/4, wire_contract (keys) 4/4, managed fixtures 4/4, security 3/3, wire_contract (managed) 3/3, keys fixtures 2/2, matching 2/2, deadline 1/1, `jev.py` 0/4.<br>**Scope:** the entry's Do says "A single-line comment that would pass 72 columns becomes a wrapped block too". Its evidence commit `f7a02bae` wrapped all 10 of its *test-file* comment lines at 67–70 columns (`git show f7a02bae -- tests`). | Re-wrap only those 52 lines as PEP 8 blocks of at most 72 columns, directly above the code they explain. Change no code or assertion, and leave the pre-existing wide lines alone. Re-run the awk-over-diff check until `TOTAL over 72: 0`. Do it **after** R-1, so the comments R-1 adds are wrapped too. | open |

**Why R-2 stays Major and is not raised to Blocker:** the entry is scoped to "SDK code", says "Not a lint rule … leave untouched files alone", and the same packs carry pre-existing wide comments that merged after the lesson existed. It changes no behavior. But the owner has rejected exactly this before, so it would draw a review comment, which makes it more than Minor.

### R-1 fix detail
1. **`vidbyte/lib/registries/provider_keys.py:53-55`.** Change the META row to prefixes `("LLM|", "LLM_")` and the pattern to
   `re.compile(r"LLM(?:\|[0-9]+\|[A-Za-z0-9_-]+|_[0-9]+_[A-Za-z0-9_-]+)")`.
   - Rewrite the comment above it as a block of at most 72 columns that quotes the 2026-10-17 page sentence.
   - Keep `LLM|`. The tests reference the `LLM|` fakes 65 times across 11 files (`git grep -c`), #1027 cited it from the same URL on 2026-10-15 (`vidbyte/lib/registries/README.md:55`), and no other vendor uses the prefix. Its first-party source can no longer be verified (the Internet Archive was offline on 2026-10-17), so record that as an open question rather than deleting it.
   - **Alternative, larger:** a separate META row for `LLM_`. It is not needed.
2. **`vidbyte/lib/registries/README.md:55`** (required by `provider_keys.py`'s own COMMON MODIFICATION PATTERNS). Add the `LLM_` shape with its quote and date. Table A's "a real key is refused, never sent to another vendor" (`:62`) is false today for `LLM_` keys and becomes true with step 1.
3. **`README.md:290-293`, the Prefixes bullet.** Write "`LLM_` or `LLM|` (Meta)" and re-wrap the bullet to the section's width. The substring "`LLM|` (Meta)" keeps AC-13's assertion (`test_managed_text_acceptance.py:244`) green with no test edit.
4. **Tests (orchestrator grant required).**
   - `tests/features/sdk_provider_keys/test_provider_keys_contract.py:71`: the META prefix set becomes `{"LLM|", "LLM_"}`. This is the only area test the fix turns red; verified by the in-memory widening.
   - Add `K_META_DOC = "LLM" + "_" + "1" * 16 + "_" + "m" * 32` to `provider_keys_fixtures.py`.
   - Subtest (a): an `("LLM_", K_META_DOC, ModelProvider.META)` row in the proven-key table at `test_provider_keys_matching.py:144`.
   - Subtest (b): the AC-1 snippet test also run with `META_API_KEY = K_META_DOC`.
   - Subtest (c), failing first: an `AUTO` anthropic primary answering 401, `api_keys=[K_ANTHROPIC, <Meta key>]`, a kimi fallback. Assert the kimi request has no relay header and no Meta key anywhere. Run it as a subTest over both `K_META` and `K_META_DOC`.
     - Verified by `s4v_mutant_vs_r1_subtest.py`: it fails at HEAD for `LLM_` and passes after the fix.
     - It kills the engineering lens's surviving `meta_key_to_keyless` mutant for both shapes, which closes R-3.
   - Fix the comment `test_provider_keys_matching.py:268` ("Meta issues only LLM| keys"), which is false, and `FEATURE.md:70`'s shape text.
5. **Spec r4 (orchestrator).**
   - Correct the shape text at §4 :87-88, §5 :138, EC-8, EC-10, FR-7, D-7, §9.2, T-1, §12.3 row 2(c), and §12.4 :514.
   - Add Meta's key format to §11's "First-party Meta facts".
   - Add the files above to §12.3.
   - Make the §12.5 live check pass the real key through `api_keys` at least once. Meta's example secret is elided, so the secret's character set is unverified for either shape, and only a live call proves it.
   - `context/wire-contract.md:16` and Run A's backend *tests* (`generative_gateway_fakes.py:47`, `test_generative_gateway_meta.py:173`) state the same wrong shape. Run A's production relay check is shape-agnostic (`[!-~]+`), so this is a note for Run A, not an SDK change (R-11).
6. **Out of scope:** binding *other* unproven keys by elimination is #1027's documented design (README "Other keys" bullet). The fix removes only the Meta instance, which is all that request §C asks.

## Refuted or downgraded by the verifier — 2 reviewer claims adjudicated (0 findings refuted)
| ID | Original severity | Why refuted / downgraded (evidence) |
|---|---|---|
| R-C2 (conformance) | Major | **Not refuted; merged into R-1.** It has the same root cause (the META row does not prove or reserve `LLM_`), and the R-1 fix removes it: kimi gets `None` with the row widened (probe `--fix`, case [2]). The misroute is inherited from base `845a4d9b`, byte-identical (probe on the `git archive` copy), so it is not introduced by this PR. It stays in scope because request §C asked the run to confirm exactly this property. |
| Engineering verdict "SOUND"; VERIFIED CLAIM 6 "INV-4 / T-1 HELD … violations=none in all 16 runs" | — | **Refuted for the documented key shape.** The 16 runs used only `K_META` (`LLM\|` shape). The verifier's probe reproduces engineering's result for `LLM\|` (kimi relay `None`) and conformance's for `LLM_` (kimi relay = the Meta key). The lenses agree on the code; they differ only in which key shape they fed it. |

## Minor findings (fix if trivial, otherwise follow-ups)
| ID | Where | Finding | Status |
|---|---|---|---|
| R-3 (R-E1) | `tests/features/sdk_provider_keys/test_provider_keys_agents.py:429-443` | No test fails if a Meta key from `api_keys` rides on a non-meta call that holds no key of its own: the `meta_key_to_keyless` mutant survives with the area suite at `183 passed`. This is a real hole in the INV-4 tests, but the code is correct today. Classified Minor because the code is correct; it would be Major if it were the only guard. | open, **closed by R-1 subtest (c)** (verified: that subtest kills the mutant in both shapes). Without R-1, use the engineering lens's subtest: `api_keys=[K_META]` only, Meta 401, anthropic fallback, assert no relay header. |
| R-4 (R-C3 + conventions S6 note) | `spec.md:184` (AC-15); draft PR #1180 body | The "word for word" merge-prerequisite sentence contains "(§12.5)", which points nowhere in a PR body. The placeholder body already deviates ("Do not merge: this PR …", "(spec §12.5)"). | open, follow-up (spec r4: allow "(§12.5)" as a link to the spec; S6 writes the body) |
| R-5 (R-C4) | `spec.md` INV-5, D-3, §8.4, §9.3 | `jev.py:84` (5 citations) and `jev.py:113` (2) now point at `})` and `GLM_API_KEY`. The cap constant is at `:87` and `META_API_KEY` at `:116` (verifier `sed -n`). | open, trivial (cite the constants by name; orchestrator, spec text) |
| R-6 (R-V2) | `test_provider_keys_modes.py:6`, `test_managed_text_deadline.py:6`, `test_managed_text_wire_contract.py:6`, `managed_text_fixtures.py:7`, `tests/features/sdk_managed_text/FEATURE.md:70` | The COMMON MODIFICATION PATTERNS lines do not name `SERVED`, `MANAGED_PROVIDERS`, `FULL_CONFIG`/`ORACLE_KEYS`/`CAP_FIELD`, or `_CHAT_PROVIDERS`, so a stale table stays silent when the next provider joins. The `ORACLE_KEYS` trap sits in "Known Failure Modes", which lists feature failures, not harness traps. | open, follow-up (one clause per CMP line; test-pack docs need the grant) |
| R-7 (R-V3) | `tests/features/sdk_provider_keys/test_provider_keys_agents.py:494`; `test_provider_keys_failures.py:208-210` | E302: one blank line before `class NonTextModelKeyTests`. Verifier's ruff run: `Found 1 error`. The two `META_*` constants sit mid-file after four classes; every other constant is at `:42-59`. | open, trivial |
| R-8 (R-V4) | `tests/features/sdk_managed_text/test_managed_text_acceptance.py:218-224` | The README-section extraction block is copied a third time: `:198`, `:219`, and `test_provider_keys_acceptance.py:381` (verifier grep). | open, follow-up (`readme_section()` helper beside `readme_bullet`) |
| R-9 (R-E2) | `vidbyte/agents/multi/dispatcher.py:69-70` | EC-16's examples omit multi-agent team workers, whose failure `dispatch()` records as a retryable blocker. A Muse worker that used to fail and be contained now runs and bills. | open, trivial (PR-body Compatibility text, S6) |
| R-10 (R-E3) | `spec.md:540-552` (§12.5 live check) | The live check exercises only relay calls, so merge prerequisite 2 (the backend's `META_API_KEY`) is never verified end to end. | open, trivial (add a `VIDBYTE_MANAGED` call (c) to the recipe; spec and PR-body text). Pair it with R-1 step 5, which adds an `api_keys` call. |
| R-11 [verifier] | `docs/spec/meta-muse-managed-text/context/wire-contract.md:16`; Run A `backend/tests/features/model_gateway/generative_gateway_fakes.py:47`, `test_generative_gateway_meta.py:173`, `test_generative_gateway_meta_secrecy.py:3` | Run A's wire contract and backend tests also call `LLM\|<app id>\|<secret>` "Meta's documented key shape". Production relay validation is shape-agnostic (`[!-~]+`, 1–512), so no behavior is wrong, but the fakes use an undocumented shape. | open, follow-up (note for Run A; no SDK change) |

## What the implementation gets right (so nobody "fixes" it)
- **`vidbyte/lib/constants/jev.py:72-83` is exactly §12.3 row 1.**
  - `ModelProvider.META` is an enum member, not a string. The set is still a `frozenset[ModelProvider]` literal with 7 members.
  - The 4-line comment is a PEP 8 block directly above the set, measuring 67/67/69/42 columns. It keeps the `a14b37e7e` citation for the six and cites #710 at `c395349bd`.
  - The header (whose PURPOSE says "provider set" with no count), `__all__`, and every other constant are byte-identical.
  - It is the only production change, and it reaches every reader of the set. M-12 now reads "serves only: anthropic, deepseek, gemini, kimi, meta, openai, xai", and M-18 offers "Vidbyte's own meta account".
- **`README.md` changes exactly the three named bullets** (7+/7-), re-wrapped at 45–77 columns. Every fact the two older README tests bind is still present, and the section never says `ProviderKeys`. The `LLM|` (Meta) text accurately documents the matcher's *current* rule. R-1 adds the documented `LLM_` form beside it; it does not remove it.
- **No other served-provider list exists outside `docs/` and `tests/`.** `REPO_MAP.md`, `llms.txt`, and `artifacts/file_index.md` have no gateway entry, and there is no `.env.example`, so "no map, llms, or env change" is correct.
- **With a key the matcher proves, every weighted-word path holds:**
  - In AUTO, a list key is relayed, the list before `META_API_KEY`.
  - In AUTO with only `META_API_KEY`, the env key is relayed, in **either** shape (verifier probe).
  - In AUTO with no key, and always in `VIDBYTE_MANAGED` (agent and runner), nothing is relayed.
  - `arun`, fallback to Muse, and fork all hold.
  - Every meta body carries `max_tokens` 32768 and no `max_completion_tokens`, and the timeout is 630 s.
  - A relayed 401 is sent once and leaks no key in the message or in DEBUG logs.
  - A custom endpoint and streaming are still refused for meta.
- **Key routing stays on the exact-match `ProviderKeys.key_for`** (`vidbyte/lib/dataclasses/agents.py:283-291`). Across 8 scenarios × base/branch with `LLM|` keys, no key reached another provider's envelope: fallbacks and forks in both directions, aggregate, a mixed list with `META_API_KEY`, and the grader in `VIDBYTE_MANAGED`. META is format-bound (`provider_keys.py:55`, `:60`), M-18 picks up `meta` through the set (`:308`), and AC-4 never reads `META_API_KEY` during credential resolution.
- **The tests can fail.**
  - All 15 new tests are red on a real `845a4d9b` base for the meta-unserved reason (24 failed in total).
  - Removing META from the set in memory fails 23 of the 24 meta tests; the 24th is the README test.
  - 6 of 7 mutants are killed.
  - No test was deleted or skipped, and no `assert` was removed. The only removed row is the granted `("meta", "llama-4")` row, whose positive case moved to the new INV-1 test.
- **The test packs honor their own modification patterns.**
  - The patterns that already existed were followed (`jev.py:6`, `managed_text_fixtures.py:7`, RELAY_KEYS and CAP_FIELD, UNMANAGED, EMITTED_KEYS taken from spec §9.2, not the adapter).
  - Every "six" is gone (grep: 0), and the FEATURE.md and README File Index and Logs entries are updated.
  - Every touched header cites the meta IDs, and no fixture gained a module-level import.
- **Nothing was invented or leaked.**
  - `pricing.py`, `lint/pricebook_vintage_lock.json`, and `lint/baseline.json` are unchanged, and Muse 1.1 resolves to 1.25/4.25/0.15.
  - Every fake key is concatenated; there are 0 key-shape literals in the diff or the commit messages.
  - The `DIRECT` golden is byte-identical to base.
  - `HttpTransport` has no logging path.
  - `py -3.11 lint/run.py` ends `SDK-LINT: PASS` with 0 REGRESSED.
- **Commit hygiene.** The three product commits each carry one work item with W-, FR-, and AC- IDs. All 20 commits carry the attribution line. No `.pyc` file and no secret is in the diff, and the branch merges cleanly with the moved `origin/main` (`git merge-tree` exits 0).
