# S4 findings verifier — meta-muse-managed-text

Inputs read in full:
- the three reviews: `S4-review-conformance.md`, `S4-review-conventions.md`, `S4-review-engineering.md`;
- `spec.md` r3, `request.md`, the `review.md` format in `report-formats.md`;
- field guide `init.md`, `comment-format.md`, and `provider-api-contracts.md`;
- `vidbyte/lib/registries/provider_keys.py` and the registries README table F/A rows.

Diff: `git diff origin/main...2ba4a678`, merge base `845a4d9b`. Worktree HEAD is `ee873166`; the orchestrator committed the reviewer reports during this run, and no source changed. I made no source edits and no git state changes. I wrote only `review.md` and this file. The base package was extracted with `git archive 845a4d9b vidbyte | tar -x` into the scratchpad, so no worktree was created.

## 1. Merge map

| Original | Lens | Proposed | Merged ID | Final | Note |
|---|---|---|---|---|---|
| R-C1 | conformance | Blocker | **R-1** | Blocker, CONFIRMED | root cause: the META row neither proves nor reserves `LLM_` |
| R-C2 | conformance | Major | **R-1** | merged (same root cause) | inherited from base; the R-1 fix removes it |
| — | verifier | — | **R-1** (fix steps 2, 4, 5) | — | blind spots: registries README Table A claim, the §12.5 live check path, the stale test comment |
| R-V1 | conventions | Major | **R-2** | Major, CONFIRMED | |
| R-E1 | engineering | Minor | **R-3** | Minor | closed by R-1 subtest (c), verified |
| R-C3 | conformance | Minor | **R-4** | Minor | de-duplicated with conventions' "S6-owned" PR-body note |
| (S6 note) | conventions | — | **R-4** | Minor | |
| R-C4 | conformance | Minor | **R-5** | Minor, trivial | |
| R-V2 | conventions | Minor | **R-6** | Minor, follow-up | |
| R-V3 | conventions | Minor | **R-7** | Minor, trivial | |
| R-V4 | conventions | Minor | **R-8** | Minor, follow-up | |
| R-E2 | engineering | Minor | **R-9** | Minor, trivial (PR body) | |
| R-E3 | engineering | Minor | **R-10** | Minor, trivial (spec / PR body) | |
| — | verifier | — | **R-11** | Minor, follow-up | Run A's contract and tests use the undocumented shape |

Totals: confirmed Blockers 1, Majors 1, Minors 9. No finding refuted. No finding downgraded. One Major (R-C2) was merged up into a Blocker. One verdict-level claim (engineering "SOUND", claim 6) was refuted for the documented key shape.

## 2. Verification of every Blocker and Major

### R-1 (R-C1 + R-C2): Meta's documented key shape is not proven

**First-party source.** I fetched it myself and did not use the scratchpad cache. curl ran at `Sat Oct 17 12:06:19 UTC 2026` into `scratchpad/s4v-meta-live/`. WebFetch on both the `.md` and HTML URLs agreed.

- `https://dev.meta.ai/docs/authentication.md` (200, 2692 bytes) says:
  > API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores:

  The example that follows is an `LLM_` tag, a 16-digit ID, `_`, and an elided secret. It is not copied here.
- The rendered HTML (`https://dev.meta.ai/docs/authentication`, 200, 184188 bytes) carries the same sentence and example.
- `https://dev.meta.ai/docs/error-handling.md`:
  - `:70`: "Malformed API key (not in `LLM_{id}_{secret}` format)"
  - `:509`: "**Cause:** API key not in `LLM_{numeric_id}_{secret}` format."
  - `:511`: "… The key should start with `LLM_`."
- `grep -c 'LLM|'` returns 0 on authentication, error-handling, quickstart, muse-code/auth, api-reference, and sdks (`.md`), and on `llms.txt`.

**Is there a first-party source for `LLM|`?**
- No current first-party page shows it.
- `git log -S 'LLM|' -- vidbyte/lib/registries/provider_keys.py` gives exactly one commit: `72a4ade1 2026-10-15 … (#1027)`.
- Its source row (`vidbyte/lib/registries/README.md:55`) says: "Opened on 2026-10-15. https://dev.meta.ai/docs/authentication …: "API keys look like this:" an `LLM\|` tag …". It also leans on the gitleaks `facebook-access-token` rule (secondary).
- Today's page has different wording ("API keys start with …"), so the page was rewritten after 2026-10-15. Whether it ever showed `LLM|` cannot be verified: `web.archive.org/cdx` returned "Internet Archive: Temporarily Offline".
- WebSearch found no source for an `LLM|` Meta key format.
- **Conclusion:** `LLM_` is the only shape Meta documents today. `LLM|` is unverifiable, so it is kept as a legacy shape, not removed.

**Execution.** `scratchpad/s4v_probe.py` is my own script. It fakes only `vidbyte.lib.runners.text.HttpTransport` and `os.environ`, builds every key by concatenation, and runs the §4 snippet extracted verbatim from spec.md. Keys: `UNDER = "LLM" + "_" + "1"*15 + "_" + "m"*32` and `PIPE = "LLM" + "|" + "1"*15 + "|" + "m"*32`.

HEAD (`PYTHONPATH=<wt>`):
```
served set has META: True
[1] sec4 verbatim (key via api_keys) | <META LLM_ shape> | printed=[] | requests=[] | error=ConfigurationError: api_keys[1] (52 characters) has no prefix that proves its provider, and none of the providers configured here (meta, anthropic) can take such a key. ...
[1] sec4 verbatim (key via api_keys) | <META LLM| shape> | printed=['from-meta', 'Hello'] | requests=[('meta', '<META LLM| shape>', 32768), ('meta', 'None', 32768)] | error=None
[1] sec4 minus api_keys line (key via META_API_KEY only) | <META LLM_ shape> | printed=['from-meta', 'Hello'] | requests=[('meta', '<META LLM_ shape>', 32768), ('meta', 'None', 32768)]
[1] sec4 minus api_keys line (key via META_API_KEY only) | <META LLM| shape> | printed=['from-meta', 'Hello'] | requests=[('meta', '<META LLM| shape>', 32768), ('meta', 'None', 32768)]
[2] anthropic+kimi (no meta configured) | <META LLM_ shape> | result=from-kimi | requests=[('anthropic', '<K_ANT>', 32768), ('kimi', '<META LLM_ shape>', 32768)]
[2] anthropic+kimi+meta | <META LLM_ shape> | result=from-kimi | requests=[('anthropic', '<K_ANT>', 32768), ('kimi', '<META LLM_ shape>', 32768)]
[2] anthropic+kimi+meta | <META LLM| shape> | result=from-kimi | requests=[('anthropic', '<K_ANT>', 32768), ('kimi', 'None', 32768)]
[3] TextModelConfig(deepseek, AUTO, api_keys=[<META LLM_ shape>]) | requests=[('deepseek', '<META LLM_ shape>', 32768)]
[3] TextModelConfig(kimi, AUTO, api_keys=[<META LLM_ shape>]) | requests=[('kimi', '<META LLM_ shape>', 32768)]
[3] TextModelConfig(meta, AUTO, api_keys=[<META LLM_ shape>]) | requests=[] | error=ConfigurationError: ... has no prefix that proves its provider ...
[4] provider_of(LLM_)= None  provider_of(LLM|)= ModelProvider.META
[4] accepts_unproven(kimi|deepseek|mistral|glm|minimax, LLM_)=True ; meta=False ; openai=False
```

Base (`PYTHONPATH=scratchpad/s4v-base-src`, from `git archive 845a4d9b`):
- `served set has META: False`.
- `[1] sec4 verbatim … LLM_ … ConfigurationError: … has no prefix that proves its provider` is the same M-6 as at HEAD. The `LLM|` and env-only cases end in `AgentExecutionError`, because meta is unserved at base.
- Case `[2]` (both kimi lines) and case `[3]` (deepseek and kimi lines) match HEAD byte for byte. For the `LLM_` key: `('kimi', '<META LLM_ shape>')` and `('deepseek', '<META LLM_ shape>')`.

**Was it introduced by this PR?** The root cause (`provider_keys.py:53-55`) and the misroute (R-C2) both predate it: `provider_keys.py` has no diff in `845a4d9b..2ba4a678`, and the base probe is identical. What this PR adds:
- it delivers the must-have path that the bug defeats (§4, G-1, AC-1 P0);
- it adds a user-facing claim that `LLM|` proves a Meta key (README row 2(c), `README.md:292`);
- the spec §4 comment instructs the `LLM|` shape;
- its test pack uses only the `LLM|` shape. `K_META` and `K_META_2` (`provider_keys_fixtures.py:39,41`) and both `ORACLE_KEYS[META]` entries (`test_managed_text_acceptance.py:53`, `test_managed_text_wire_contract.py:37`) are all pipe-shaped, so AC-1, AC-2, AC-6, AC-11, and EC-11 cannot fail for this reason.

**Spec check.**
- G-1 and AC-1 ("fake keys of their providers' shapes") and request §D ("Want users to be able to use muse models with their meta/muse api keys") are not met for the shape Meta issues.
- Request §C asks: "Confirm that a Meta key reaches only `provider: "meta"` envelopes". Spec T-1 claims it holds. It does not hold for the documented shape.
- The registries README Table A (`:62`) promises fail-closed: "If that is ever wrong, a real key is refused, never sent to another vendor." That promise is false for `LLM_`, because `LLM_` is not a reserved prefix.
- **Existing guard?** None. `accepts_unproven` reserves only the `LLM|` prefix (`provider_keys.py:89-91`), so an `LLM_` key falls through to "any" for deepseek, kimi, glm, minimax, and mistral (Table A).

**Classification: CONFIRMED, Blocker.** It is a wrong result on the P0 path. It violates two weighted words: "use muse models with their meta/muse api keys", and "a key goes only to the vendor it was matched to" in the user's sense of the vendor that issued it. It also contradicts the field-guide lesson "Mirror the vendor's API reference page exactly" (`provider-api-contracts.md`). Following the briefing, it is not refuted on scope grounds. The fix touches `provider_keys.py`, which is outside §12.3, so it needs a spec amendment (orchestrator).

**Fix verified in memory.** `s4v_probe.py --fix` widens the META row to prefixes `("LLM|","LLM_")` and pattern `LLM(?:\|[0-9]+\|[A-Za-z0-9_-]+|_[0-9]+_[A-Za-z0-9_-]+)`:
```
[1] sec4 verbatim (key via api_keys) | <META LLM_ shape> | printed=['from-meta', 'Hello'] | requests=[('meta', '<META LLM_ shape>', 32768), ('meta', 'None', 32768)] | error=None
[2] anthropic+kimi (no meta configured) | <META LLM_ shape> | ... ('kimi', 'None', 32768)
[3] TextModelConfig(deepseek, AUTO, api_keys=[<META LLM_ shape>]) | requests=[] | error=ConfigurationError: ... holds keys for meta but none for deepseek ...
[4] provider_of(LLM_)= ModelProvider.META ; accepts_unproven(<every provider>, LLM_ and malformed LLM_)=False
```
Area suite with the widening plugin (`scratchpad/s4v_plugins/s4v_widen.py`):
```
FAILED tests/features/sdk_provider_keys/test_provider_keys_contract.py::NamesAndConstantsTests::test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes
1 failed, 182 passed in 1.37s
```
The one failure is the table-F pin (`:71`, `{"LLM|"}`), which changes by design and needs the test grant. The property tests stay green.

**Collision check (blind spot).** `scratchpad/s4v_collision.py`, run over all 15 `K_*` fixture keys:
```
provider_of changed: none
accepts_unproven changed: none
prefix overlaps across providers: none
other rows fullmatching a Meta-shaped key: none
```
- No other `KEY_FORMATS` row can match a key that starts with `LLM`. The rows are `sk-ant-`, `sk-or-`, `sk-proj-`/`sk-svcacct-`/`sk-admin-`, `xai-`, `AIza`/`AQ.`.
- Reserving `LLM_` *strengthens* M-6: a malformed `LLM_` key that kimi or deepseek used to take is now refused everywhere.
- None of the unproven-key vendors has a sourced key format (Table A: "their docs show only placeholders"). So no sourced shape of theirs starts with `LLM_`; this rests on absence of evidence, not on proof.
- **Residual risk:** Meta's example secret is elided, so the secret's character set (`[A-Za-z0-9_-]`) is unverified for both shapes. Only a live call settles it. That is why fix step 5 requires the §12.5 live check to pass the key through `api_keys`.

**Smallest fix compared with the reviewer's.**
- I adopt the reviewer's regex. It is the smallest change that also removes R-C2.
- My smaller README variant, "`LLM_` or `LLM|` (Meta)", keeps the substring AC-13 asserts (`test_managed_text_acceptance.py:244`), so the S2 README test needs no edit.
- The reviewer's fallback (drop the README claim and tell users to use `META_API_KEY`) is **not sufficient**: it leaves the R-C2 misroute in place, and it meets the must-have only on the env path.

### R-2 (R-V1): 52 test comment lines are over 72 columns

**Count.** My awk over `git diff -U0 origin/main...2ba4a678 -- '*.py'` counts added lines whose first non-blank character is `#`:
```
tests/features/sdk_managed_text/test_managed_text_acceptance.py: 10 of 10 over 72
tests/features/sdk_provider_keys/test_provider_keys_acceptance.py: 8 of 8 over 72
tests/features/sdk_provider_keys/test_provider_keys_failures.py: 7 of 7 over 72
... (12 test files, every added comment line over 72)
vidbyte/lib/constants/jev.py: 0 of 4 over 72
TOTAL over 72: 52
```

**Scope.**
- `comment-format.md` applies "When: Writing or editing any `#` comment in SDK code that runs past one line". Its Do adds: "A single-line comment that would pass 72 columns becomes a wrapped block too."
- Evidence commit `f7a02bae` (2026-10-10, "fix: resolve review comments on PR #690") touched `tests/features/coding_agent/test_coding_agent_cli.py`. All 10 of its added `#` lines measure 67–70 columns (`git show f7a02bae -- tests | grep -E '^\+\s*#'`). So the lesson's own evidence applies it to a test file.
- Spec §11 and §12.4 row 3 apply the entry only to `jev.py`. That is how S2 came to miss it.

**Classification: CONFIRMED, Major** (the reviewer's severity, kept). Under the rubric, contradicting a field-guide lesson is Blocker-class. It stays Major for three reasons:
- the entry is scoped to "SDK code" and is "Not a lint rule";
- the same packs' pre-existing comments are wide, merged after the lesson existed (conventions measured 20/21 and 11/11 on `origin/main`);
- it changes no behavior.

It is not Minor, because the owner has rejected this exact pattern in review before.

**Fix.** Comment-only. Re-wrap the 52 lines, and apply the same width to every comment R-1 adds. Order: R-1 first, then R-2.

## 3. Minors, passed through

R-3 to R-10 are the reviewers' findings, de-duplicated. I sanity-checked the cheap ones:
- **R-7:** `ruff check --no-cache --isolated --preview --select E301,E302,E303,E305` on the two files gives `Found 1 error.` Line `:493` is `self.assertNotIn(K_META, flat(request))`, followed by one blank line, then `class NonTextModelKeyTests`. `test_provider_keys_failures.py` has `META_UNSUPPORTED_MODEL` at `:208` and `META_MISSING_KEY` at `:210`, after the classes at `:62`, `:89`, `:109`, and `:169`.
- **R-8:** `README_SECTION_HEADING.search` appears at `test_managed_text_acceptance.py:198,219` and `test_provider_keys_acceptance.py:381`.
- **R-9:** `dispatcher.py:70` is `return await self._record_dispatch_failure(state, dispatch, exc)`.
- **R-5:** `sed -n '84p;87p;113p;116p' jev.py` prints `})`, the cap constant, `GLM_API_KEY`, and `META_API_KEY`. `grep -c` finds 5 citations of `jev.py:84` and 2 of `jev.py:113`.
- **R-3 (R-E1)** was re-classified on the merits. It is a real, mutant-proven gap in the INV-4 tests. It stays Minor because the code is correct and R-1's subtest (c) closes it. Proof, from `scratchpad/s4v_mutant_vs_r1_subtest.py` (anthropic 401, `api_keys=[K_ANT, <meta key>]`, kimi fallback):
  ```
  fix=False mutant=False key=LLM_: meta key on kimi envelope=True -> subtest FAILS   (red first, today)
  fix=False mutant=False key=LLM|: meta key on kimi envelope=False -> subtest passes
  fix=True  mutant=False key=LLM_: meta key on kimi envelope=False -> subtest passes  (green after R-1)
  fix=True  mutant=True  key=LLM_: meta key on kimi envelope=True -> subtest FAILS   (kills meta_key_to_keyless)
  fix=True  mutant=True  key=LLM|: meta key on kimi envelope=True -> subtest FAILS   (kills it for the old shape too)
  ```
- **R-11 [verifier]:** Run A's worktree `git grep` (excluding `docs`) finds the `LLM|` shape only in backend *tests*: `generative_gateway_fakes.py:47`, `test_generative_gateway_meta.py:173` (`assert key.count("|") == 2  # Meta's documented LLM|<app id>|<secret> shape`), `test_generative_gateway_meta_secrecy.py:3`, `test_generative_gateway_missing_key.py:98`, and `test_credentials_loader_provider_keys.py:31`. The production relay pattern is `[!-~]+` (wire contract §9.2), so no behavior changes. Note for Run A.

## 4. Disagreements between reviewers, adjudicated

1. **Engineering "SOUND, 16 runs, violations=none" against conformance R-C2 "a Meta key is relayed on kimi".** Both are right about the code. Engineering fed only `K_META` (`LLM|`); conformance fed `LLM_`. My probe reproduces both:
   - `LLM|` → kimi relay `None`;
   - `LLM_` → kimi relay = the Meta key, at both HEAD and base.

   Resolution: the engineering verdict is refused for the documented shape, and R-C2 is merged into R-1.
2. **Conformance rates R-C2 Major because it predates the PR, but rates R-C1 Blocker.** One root cause and one fix, so they are merged, and the merged finding takes the higher severity, per the procedure.
3. **Conventions rates R-V1 Major; conformance's claim 4 and engineering's claim 12 say the comment width "HELD".** Those two checked only `jev.py` (67/67/69/42), which does comply. No conflict: R-V1 is about the test files.
4. **Conventions rates R-V2–R-V4 Minor; engineering's R-E1 is Minor.** Kept. R-E1 gets a fix path through R-1.

## 5. Interactions the repair agent must respect

- **R-1 before R-2.** R-1 adds comments in `provider_keys.py` and in tests. They must already be 72 columns wide or less, and R-2's awk recount runs after them.
- **The R-1 README edit.** Use "`LLM_` or `LLM|` (Meta)" so that AC-13 (`test_managed_text_acceptance.py:244`, which asserts the substring "`LLM|` (Meta)") stays green. Re-wrap the bullet to about 78 columns (row 2(c) style).
- **`provider_keys.py` COMMON MODIFICATION PATTERNS.** A `KEY_FORMATS` change must carry its source in a comment in the module and in the registries README "Provider Key Format Sources". `vidbyte/lib/registries/README.md` is a folder README under A009's 40,000-character cap.
- **Test edits need the orchestrator's grant:**
  - `test_provider_keys_contract.py:71` (pre-existing, outside S2's set);
  - the matching table at `test_provider_keys_matching.py:144`;
  - a new `K_META_DOC` fixture;
  - the subtests;
  - comment fixes at `test_provider_keys_matching.py:268` and `FEATURE.md:70`.

  Build every fake by concatenation.
- **Never export PYTHONPATH before `run_ci.py`.** The area command needs `env -u DEEPSEEK_API_KEY`.

## 6. Commands run (final lines)

- `curl -sS -L -A Mozilla/5.0 https://dev.meta.ai/docs/{authentication,error-handling,quickstart}.md` → `authentication 200 2692 …`, `error-handling 200 30145 …`, `quickstart 200 10273 …`. `date -u`: `Sat Oct 17 12:06:19 UTC 2026`.
- WebFetch on `https://dev.meta.ai/docs/authentication(.md)` and `…/error-handling.md`: the same sentences, and "The page doesn't mention any "LLM|" pipe-delimited format".
- `curl … web.archive.org/cdx/search/cdx?url=dev.meta.ai/docs/authentication*` → `Internet Archive: Temporarily Offline`.
- `git log --format='%h %ad %s' --date=iso -S 'LLM|' -- vidbyte/lib/registries/provider_keys.py` → `72a4ade1 2026-10-15 18:20:38 -0400 feat(lib,agents): … (#1027)`.
- `git archive 845a4d9b vidbyte | tar -x -C scratchpad/s4v-base-src`. Then `git diff --stat 845a4d9b 2ba4a678 -- vidbyte` → `vidbyte/lib/constants/jev.py | 7 +++++--` / `1 file changed, 5 insertions(+), 2 deletions(-)`.
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 scratchpad/s4v_probe.py <spec>`, in three forms: at HEAD, at base, and at HEAD with `--fix`. Output is quoted in §2.
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider` →
  ```
  .......................................                                  [100%]
  183 passed in 1.96s
  ```
- The same command with `PYTHONPATH="$(pwd);scratchpad/s4v_plugins" … -p s4v_widen --tb=line` →
  ```
  FAILED tests/features/sdk_provider_keys/test_provider_keys_contract.py::NamesAndConstantsTests::test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes
  1 failed, 182 passed in 1.37s
  ```
- `PYTHONPATH=$(pwd) py -3.11 scratchpad/s4v_collision.py <wt>` → `provider_of changed: none` / `accepts_unproven changed: none` / `prefix overlaps across providers: none` / `other rows fullmatching a Meta-shaped key: none`.
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 scratchpad/s4v_mutant_vs_r1_subtest.py` → 8 lines, quoted in §3.
- `git diff -U0 origin/main...2ba4a678 -- '*.py' | awk …` → `TOTAL over 72: 52`.
- `git show --stat f7a02bae`; `git show f7a02bae -- tests | grep -E '^\+\s*#'` → 10 lines, max 70 columns.
- `py -3.11 -m ruff check --no-cache --isolated --preview --select E301,E302,E303,E305 <agents.py> <failures.py>` → `Found 1 error.`
- `git grep -c -E 'K_META|"LLM" \+ "\|"' -- tests` → 65 references across 11 files.
- Run A worktree: `git grep -n -E 'LLM\||LLM_' -- ':!docs'` → test files only (§3).

I did not re-run lint or `run_ci.py`; lint belongs to the conventions lens, which ran it and got `SDK-LINT: PASS`. No scratch worktree was created. Scratch artifacts are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`: `s4v_probe.py`, `s4v_collision.py`, `s4v_mutant_vs_r1_subtest.py`, `s4v_plugins/s4v_widen.py`, `s4v-meta-live/`, and `s4v-base-src/`.
