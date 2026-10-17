LENS: conformance (S5 final re-review, round 1)
VERDICT: SOUND — Every r4 requirement holds in the code on every path I probed, both Meta key shapes included. The two new findings are Minor: one is spec wording, and one is a follow-up that nothing yet carries forward.

Diff reviewed: `git diff origin/main...dfa21027` (merge base `845a4d9b`). The worktree HEAD `359b72f2` adds only a `pipeline.md` line. I also reviewed every change since S3_HEAD `2ba4a678`, including the merge-forward `db5ad22b` (T `22fe9fc5`, P' `c6d88e88`). Spec r4 (`04729669`; its Proof column was filled in `263fa4e9`).

## FIX CONFIRMATION

- **R-1 — confirmed.**
  - *Matcher row.* `provider_keys.py:59` is the §8.5 row byte for byte. A differential check against `845a4d9b`'s matcher over 176,013 generated keys (22,357 of them starting with `LLM_`) gives 0 INV-17 mismatches and 0 INV-16 violations.
  - *§4 snippet.* Run verbatim in both shapes, every AC-1 clause passes.
  - *Misrouting.* The AC-17 probe found 0 Meta keys on a non-meta request.
  - *Root README.* `README.md:292` reads "`LLM_` or `LLM|` (Meta)".
  - *Registries README.* The row at `vidbyte/lib/registries/README.md:55` is true against the live page. My curl at 21:54 UTC gave sha256 `065bf421…d008f4`, the same as S5's fetch. `LLM|` appears 0 times on the page.
- **R-2 — confirmed.** 0 of the 216 added `#` lines are over 72 columns, on the final tree.
- **R-3 — confirmed.** `S4E_MUTANT=meta_key_to_keyless` gives `1 failed, 191 passed`. The one failure is `MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own`.
- **R-4 — confirmed.** The canonical sentence appears in 7 places in the spec (lines 18, 59, 192, 238, 384, 583, 751), identical in each. No "(§12.5)" variant is left. `pipeline.md:60` says "8 occurrences", which is a miscount; spec §16 correctly says 7.
- **R-5 — confirmed.** `jev.py:84` and `jev.py:113` now appear only in the §16 and §17 history rows (spec 775, 777, 787, 799). The constants are at `jev.py:87` (the cap) and `:116` (the `ModelProvider.META` entry).
- **R-6 — confirmed.** The six COMMON MODIFICATION PATTERNS lines name `SERVED`, `PROVIDER_KEYS`, `POOL`/`PROVEN`, `MANAGED_PROVIDERS`, `ORACLE_KEYS`/`CAP_FIELD`/`EMITTED_KEYS`/`FULL_CONFIG` and `_CHAT_PROVIDERS`. `mt/FEATURE.md` mentions `ORACLE_KEYS` 0 times.
- **R-7 — confirmed.** Ruff E301–E305 over the changed `.py` files prints `All checks passed!`. In `test_provider_keys_failures.py`, the two constants now sit at `:63` and `:67`, after `RELAY_FORBIDDEN` at `:60`.
- **R-8 — open follow-up, by design.** Spec §12.5 Follow-ups lists it (spec.md:596).
- **R-9 — confirmed.** EC-16 has a "Team" bullet. Its citations are accurate: `dispatcher.py:69-70` catches the failure, and `:118-124` records the `dispatch_boundary_error` blocker.
- **R-10 — confirmed.** Spec §12.5 now has call (c), the real key through `api_keys`, and call (d), `VIDBYTE_MANAGED` (spec.md:605-606).
- **R-11 — confirmed.** Spec §9.2 records the discrepancy (spec.md:369). `context/wire-contract.md` has a single commit, `75761b81` (S0), so it was never edited.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The production change is the smallest the spec allows.** One `KEY_FORMATS` row and its 6-line comment changed (70/71/69/72/69/63 columns in the git blob), plus one registries README row and two root README lines. No method, message, other row, row order, `FORMAT_BOUND_PROVIDERS`, `RESERVED_PREFIXES` or header changed. The fix relies on the existing behavior that every literal prefix is reserved automatically, so no new code was needed.
- **The fix is self-contained and was carried forward without changing Run B.**
  - P' is byte-identical to P.
  - The merge `db5ad22b` leaves the tree hash at `f98262f8` (the same as `91c77abf`).
  - From exported copies of the hotfix commits, T alone gives `12 failed, 126 passed`, and T plus P' gives `138 passed`.
- **Fail-closed holds everywhere I probed.** Each case was refused at construction, sent nothing, and put no key text in the message:
  - a malformed `LLM_` key (M-6);
  - a lone Meta key for a kimi, deepseek, mistral, glm or minimax config (M-18);
  - an off-class secret in `api_keys` (EC-18), which still relays from `META_API_KEY`.
- **Scope and budget hold.** There are 0 new files. Outside `docs/` and `tests/`, exactly the four files in §12.3 rows 1, 2, 4 and 5 changed. `lint/baseline.json` and `lint/pricebook_vintage_lock.json` are unchanged. `git diff 263fa4e9..HEAD -- tests` is empty. No skip, xfail or suppression was added. No complete key literal appears in the diff or in any of the 40 commit messages, and all 40 carry the attribution line.

## FINDINGS (new only)

**R-C1 [Minor] [spec-precision]** `docs/spec/meta-muse-managed-text/spec.md:164` (INV-16), `:194` (AC-17 (iii)), `:383` (§9.4); the code is `vidbyte/lib/dataclasses/model_configs.py:91-100`. **The spec says a malformed `LLM_` key gets M-6 in every mode "because matching runs before the mode is used". For a `TextModelConfig`, the gateway-shape check runs first.**
- **Evidence.** `model_configs.py:95-96` calls `_require_gateway_shape` before `ProviderKeyMatcher.match` at `:100`. The comment at `:91-94` says this is deliberate. My probe built `TextModelConfig` with `api_keys=[<malformed LLM_ key>]` and got:
  - openrouter, mistral, glm and minimax in `AUTO` or `VIDBYTE_MANAGED`: `UnsupportedProviderError` (M-12). It is not a `ConfigurationError`, and it is not M-6.
  - The same four providers in `DIRECT`: `ConfigurationError` M-6, with no key text.
  - An `Agent` with a mistral primary in `AUTO`: M-6, because agents match at construction.
- **Failure.** No key goes anywhere in any of these cases, so the safety property holds. The problem is the text. AC-17 (iii) says "for any provider … Construction raises M-6", and a test written from that sentence for any of those four providers in a gateway mode fails. The existing proof test avoids the case only because it builds mistral, glm and minimax in `DIRECT`. EC-8 and EC-17 (M-18 "for a non-meta primary") have the same gap.
- **Smallest fix.** Spec text only, at the next revision or as a §16 note. INV-16's last sentence would read: "…is refused at construction, before any request: with M-6, or first with M-12 when a `TextModelConfig` names a provider the gateway does not serve in a gateway mode (`_require_gateway_shape` runs before matching, `model_configs.py:91-100`)." AC-17 (iii) would say "for any provider its mode accepts". No code or test change is needed.
- **Spec IDs:** INV-16, AC-17, EC-8, EC-17, §9.4.

**R-C2 [Minor] [coverage → follow-up]** `tests/features/sdk_managed_text/test_managed_text_acceptance.py:256`; spec.md:596 (§12.5 Follow-ups). **No test binds AC-13's r4 clause "`LLM_` or `LLM|` (Meta)", and no follow-up list carries that gap into the PR.**
- **Evidence.** The test asserts only `assertIn("`LLM|` (Meta)", prefixes)`. test-plan.md:225 records it as an "Open item". `pipeline.md:62` says S5 and the re-review check it by hand. I checked it by hand: `README.md:292` is correct today. But §12.5 Follow-ups, from which S6 writes the PR body, lists R-6, R-8 and R-11, and not this item.
- **Failure.** An edit that deletes "`LLM_` or " from the bullet passes the whole suite. The README would then again name only the form Meta no longer documents, which is R-1 part (c). Once S6 is done, nothing records that the clause is untested.
- **Smallest fix.** S6 adds one line to the PR body's Follow-ups: "AC-13: no test binds the `LLM_` half of the README Prefixes bullet; add `assertIn('`LLM_` or `LLM|` (Meta)', prefixes)` under a test-change grant." Adding that assertion now would be `[scope-adding]`, because it needs a grant.
- **Spec IDs:** AC-13, FR-7.

## VERIFIED CLAIMS

1. **The META `KEY_FORMATS` row equals §8.5, and no other row changed (INV-17). HELD.**
   - Prefixes are `("LLM|","LLM_")`, the pattern string matches exactly, and the flags are the default.
   - The other five rows match `845a4d9b` in prefixes, patterns and flags. So do the order, `FORMAT_BOUND_PROVIDERS`, `RESERVED_PREFIXES`, `OPENAI_*` and `DUPLICATE_KEY_MESSAGE`.
   - Over 176,013 keys there are 0 mismatches for keys that do not start with `LLM_`. That set covers lowercase `llm_`/`llm|`, `LLM-`, `LLMx`, every other row's prefix, and non-ASCII digits.
2. **The comment block meets AC-18. HELD.** Its lines are 70/71/69/72/69/63 columns in the LF blob; the CRLF working copy adds nothing, as shown with `od`. It quotes Meta's sentence and cites the URL, the date 2026-10-17 and the kept `LLM|` form. `LLM[_|][0-9]` matches 0 times, so no key literal is copied.
3. **The registries README meta row is truthful and dated. HELD.**
   - My curl of `authentication.md` returned HTTP 200, 2,692 bytes, sha256 identical to S5's. Line 13 is the quoted sentence.
   - `error-handling.md:509` says "API key not in `LLM_{numeric_id}_{secret}` format".
   - `LLM|` appears 0 times on either page, so "that page no longer shows the `LLM\|` form" is true.
   - The kept Muse Code sentence is still true: `muse-code.md:40` and `muse-code/auth.md:29` say `META_API_KEY`.
4. **The root README Prefixes bullet reads "`LLM_` or `LLM|` (Meta)". HELD.** It is at `README.md:292`; the re-wrapped lines are 70 and 57 columns. No test binds the `LLM_` half (R-C2).
5. **AC-17: a Meta key is never relayed to kimi or deepseek. HELD.**
   - Agent with an anthropic primary answered 401, then a kimi or deepseek fallback, with or without a meta fallback, in both shapes: 8 of 8 rows have no relay on the other provider's request and no Meta key anywhere in it.
   - Meta primary answered 401, then a kimi or deepseek fallback: 4 of 4 clean.
   - A lone Meta key for kimi, deepseek, mistral, glm or minimax: 10 of 10 give M-18, with no key text.
   - Five malformed `LLM_` keys, each on 3 roots: 15 of 15 give M-6.
   - A kimi runner in `AUTO` or `DIRECT` with `[unproven key, Meta key]`: kimi relays its own key or none, and the Meta key is never the bearer.
6. **The canonical merge-prerequisite sentence is identical in all 8 places. HELD, but the count is 7.** All occurrences are byte-identical. The 8th `grep -c` line is the coordinator's own quote, "merges only after Run A is deployed".
7. **The merge-forward `db5ad22b` changed no file. HELD.** `git diff 91c77abf db5ad22b --stat` is empty, both tree hashes are `f98262f8f20f…`, and T and P' are ancestors of `dfa21027`.
8. **The area suite gives `192 passed`. HELD:** `192 passed in 2.63s`.
9. **Lint passes. HELD:** `SDK-LINT: PASS`, exit 0, with 0 REGRESSED or ERRORED lines.
10. **The orchestrator's full source stage at `8033c08c` covers the reviewed code. HELD.** `git diff --stat 8033c08c dfa21027 -- . ':!docs'` is empty.
11. **Every Proof-column node in spec §6.2 exists and passes. HELD.** All 25 unique node IDs give `25 passed in 1.26s`. The named subTest labels exist: `shape=` at acceptance.py:124, modes.py:420 and agents.py:510, and the two `LLM_` cases at wire_contract.py:215-216.
12. **No test was weakened. HELD.**
    - The r4 delta removed 26 lines that contain "assert". 18 reappear verbatim.
    - 1 is the granted `{"LLM|"}` → `{"LLM|","LLM_"}` pin.
    - 5 became loop variables over `(K_META, …), (K_META_DOC, …)`, and every loop still includes the original key. They are at modes.py:419-427, acceptance.py:123-164 and acceptance.py:345-357.
    - The other 2 are a comment and a COMMON MODIFICATION PATTERNS line that merely contain the word.
13. **The S2b test author's edit to the spec touched only the Proof column. HELD**, by word diff of `263fa4e9`.
14. **INV-15: the Muse price row is unchanged. HELD.** It resolves to 1.25 input, 4.25 output and 0.15 cache read. Meta's `pricing-rate-limits.md:39-41` still shows $0.15, $1.25 and $4.25.
15. **INV-14 and the endpoint refusal still hold for meta. HELD.** Streaming in either gateway mode raises `UnsupportedProviderError`. A custom endpoint raises `ConfigurationError` (M-13).
16. **§14 says to cite W- IDs in commit messages. PARTIAL.** None of `23c4e9c4`, `4af4d8e0`, `9309eed0`, `874890bd`, `22fe9fc5` or `c6d88e88` names W-5. They do cite FR, INV and AC IDs. These commits are pushed, so I make no finding.

## COMMANDS RUN

- `git diff --stat origin/main...dfa21027 -- . ':!docs'` → `22 files changed, 906 insertions(+), 85 deletions(-)`; 0 added files.
- `git diff --stat 263fa4e9..HEAD -- tests` → empty.
- `git diff origin/main...HEAD -- lint/baseline.json lint/pricebook_vintage_lock.json | wc -l` → `0`.
- `git diff 91c77abf db5ad22b --stat` → empty. `rev-parse` of both trees → `f98262f8f20f2c324371dde751a1ed0d1e469cdd` twice.
- `diff <(git diff 9309eed0^ 9309eed0) <(git diff c6d88e88^ c6d88e88)` → `identical`.
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider` → `192 passed in 2.63s`. The import check printed `…\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py`.
- `py -3.11 lint/run.py` → `exit=0` / `S063 IMPROVED 4 -> 3 …` / `S064 RATCHETED: 4 known finding(s) …` / `SDK-LINT: PASS`; REGRESSED or ERRORED: 0.
- `curl https://dev.meta.ai/docs/{authentication,error-handling,muse-code,muse-code/auth,pricing-rate-limits}.md` → all HTTP 200. authentication.md is 2,692 bytes, sha256 `065bf421…d008f4`. `grep -c 'LLM|'` gives `0` on both key pages.
- `<scratchpad>/s5rr_snippet_ac1.py` (§4 extracted verbatim from the spec, inner transport faked) → for both `LLM_` and `LLM|`: `requests=2 (agent=1, paid=1) printed=['Hi', 'Hello'] error=none`, all 16 checks PASS, ending `RESULT: AC-1 holds in both shapes`.
- `<scratchpad>/s5rr_ac17_probe.py` → `RESULT: no Meta key reached a non-meta request; every refusal held`.
- `<scratchpad>/s5rr_inv17_diff.py <base matcher from git show 845a4d9b>` → `8.5 row: True True True True` / `other rows identical: True` / `keys=176013 (LLM_-prefixed 22357); INV-17 mismatches=0; INV-16 violations=0`.
- An inline probe of a malformed `LLM_` key on openrouter, mistral, glm and minimax in each mode → `UnsupportedProviderError` in `auto` and `vidbyte_managed`, `ConfigurationError … M6=True keytext=False` in `direct`, and `agent mistral AUTO ConfigurationError M6= True`. This is R-C1.
- An inline EC-18 probe → `api_keys: ConfigurationError M6= True keytext= False` / `META_API_KEY: relayed==odd True gateway True`.
- `S4E_MUTANT=meta_key_to_keyless … -p s4e_mutants` → `1 failed, 191 passed in 1.94s`.
- `pytest <25 proof node IDs from spec §6.2>` → `25 passed in 1.26s`.
- `git archive 22fe9fc5` and `git archive c6d88e88` into the scratchpad, then the `sdk_provider_keys` pack → `12 failed, 126 passed in 2.60s` and `138 passed in 2.89s`.
- `ruff check --select E301,E302,E303,E305 <changed .py>` → `All checks passed!`. The R-2 awk prints `0` lines over 72 out of `216` added `#` lines.
- `gh pr view 1180` → `isDraft: true`, `state: OPEN`, `headRefOid: dfa21027…`. `gh pr list --head fix/meta-llm-key-shape` → `[]`.
