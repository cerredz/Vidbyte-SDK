# S5 repair 3: provider-onboarding-skill

Stage: S5 repair, iteration 3 of 8 · Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill` · Branch `feat/onboard-model-provider-skill` · Start `5d1cc44a` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1175 (draft, left a draft)

`<scratch>` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad`, and `<s5r3>` is `<scratch>/s5r3/`. It holds this iteration's raw page copies (`pages/`), their fetch log (`fetch-log.txt`), the quote file (`quotes/`), the mutation harness `mut_s5r3.py` and the gate logs.

Input: one coordinator-relayed lesson. SDK PR #1027's Meta key rule (table F, `LLM|`) no longer matches Meta's docs, because the format was recorded from a summarized read with no verbatim quote, no fetch timestamp and no archive copy. The coordinator asked for two requirements, each only if missing: (1) a verbatim, raw-fetched quote of the key-format sentence with its UTC fetch time; (2) when an existing table F row's source no longer shows its shape, keep the old shape and add the new one, never replace it silently. Budget: a one-sentence spec amendment plus a §16 row. No file under `tests/` changed (`git diff --name-only 5d1cc44a..HEAD -- tests` is empty). `provider_keys.py` and the registries README are untouched.

## Gate matrix

All gates ran in this worktree at HEAD `164ac9fd` (the skill and spec commit), in this iteration, in the order the brief gives.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (S2 pack) | `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` | PASS (63/63) | `63 passed in 2.80s` |
| lint | `git add -A`, then `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| full local gate, source | `PYTHONPATH="<worktree>" py -3.11 scripts/run_ci.py --stage source` (log `<s5r3>/gate-source.log`) | PASS except 1 inherited known-red test | log line 182 `SDK-LINT: PASS` · `E       AssertionError: assert 148 == 120` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 5832 passed, 16 skipped in 120.72s (0:02:00) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-provider-onboarding-skill).` |
| inherited proof | `git fetch origin main`; `git worktree add --detach "C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-r3-probe" origin/main` (6f5a7310); `PYTHONPATH="<probe>" py -3.11 -m pytest "<node>" -q -p no:cacheprovider`; `git worktree remove --force "<probe>"` | red on main too | `E       AssertionError: assert 167 == 120` · `1 failed in 1.68s` · `remove exit 0`, the probe path is gone, and `git worktree list` no longer shows it. The harness file is unchanged against base 72a4ade1 (`git diff --quiet` exit 0). The count differs because the branch sits on the older base. |
| MCP flake | — | not triggered | `test_cancelled_waiter_does_not_break_transport` passed inside the source stage; no rerun was needed. |
| import path | `PYTHONPATH="<worktree>" py -3.11 -c "import inspect, vidbyte; print(inspect.getfile(vidbyte))"` | PASS | `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py` |
| full local gate, package | `env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package` (exit 0) | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep | remote-only (dispatch) | not run; its inputs are unchanged | `git diff --name-only 72a4ade1..HEAD -- vidbyte .semgrep` lists nothing |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1175` | none attached (CI is dispatch-only) | `no checks reported on the 'feat/onboard-model-provider-skill' branch` (exit 1) |

This report and the verify-log entry are committed after these gates, in one `docs(spec)` commit, and lint was rerun on that tree.

## The premise, checked first against the raw page

The lesson was verified independently, using the skill's own capture method on the live page and not a summarizer:

- `<s5r3>/fetch-log.txt`: `2026-10-17T18:25:38Z https://dev.meta.ai/docs/authentication 200 https://dev.meta.ai/docs/authentication curl-exit=0`, and `2026-10-17T18:25:39Z https://dev.meta.ai/docs/authentication.md 200 … curl-exit=0`.
- The `.md` source, line 13, reads: "API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores:".
- Section 2's text-form command (`html.parser`), run on the saved HTML, joins the markup-split sentence. Section 2's quote check, `grep -F -b -o -f <s5r3>/quotes/meta-key-format.txt pages/authentication.html pages/authentication.txt`, prints `authentication.txt:3218:API keys start with LLM_ , followed by a numeric ID and the secret, separated by underscores:` (exit 0). The raw HTML alone does not hold the sentence in one piece; the text form does. So the procedure's existing method captures exactly this sentence, verbatim, with a UTC time, from the raw page.
- The README's Meta quote, "API keys look like this:", is now in neither form (`grep -c` gives 0 and 0). It never contained the prefix: the prefix in that row is a paraphrase. That row is the one that drifted.
- Side observation, outside this PR: the same authentication page now exports `MODEL_API_KEY`, while `PROVIDER_API_KEY_ENV_VARS` maps Meta to `META_API_KEY`, sourced from `https://dev.meta.ai/docs/muse-code`. That page still says `META_API_KEY` (`2026-10-17T18:32:33Z … muse-code.md 200`). Recorded for the separate Meta PR; not acted on here.

## Requirement 1: already met, plus one gap closed

Line by line, against provider-run.md at `164ac9fd` (line numbers after this iteration's edit; everything before line 128 is unchanged):

| Requirement part | Where the procedure already requires it |
|---|---|
| A key prefix is a fact that needs evidence | `:41` "A fact is a base URL, …, key prefix, …". |
| A summarized read is never the evidence | `:43` "A summarizing fetch tool may help you read a page, but it is never the evidence: every fact needs a quote from a saved page." |
| Raw fetch, UTC fetch time | `:45-51` one `curl -sSL` per page into `<evidence>/pages/`, and a `fetch-log.txt` line with `date -u +%FT%TZ`, the URL, the status, the final URL and curl's exit code. |
| Verbatim quote, checked mechanically | `:59-65` one line copied from the raw page or its text form, written with the file tool, and counted only when `grep -F -b -o -f` prints it with a byte offset; `facts.md` records the kind, value, URL, opened time, quote file, form and offset. |
| A statement of the prefix, not an example, for format binding | `:117-118` step 7 and the C2 rule: "only with a quoted first-party statement that its keys begin with P. An example key alone is not enough". |
| Archive copy after the run | The evidence directory is deleted after `PR_OPENED` (SKILL.md `## What each outcome leaves behind`, :172-176), so the durable copies are the PR body's Sources table (`:349`: one row per fact with URL, UTC open date and a quote of at most 200 characters that contains the value) and the committed README row (row C4, `:180`: "Opened on YYYY-MM-DD", URL, quote). |

Two judgments:

- **Time versus date.** The durable copies carry the UTC date, and the full UTC time lives only in `fetch-log.txt`, which is deleted with the evidence. Not changed: the user's own requirement is "cites every first-party source with the **date** it was opened" (request §C and §D), and a date is what a later drift check needs ("as of"). Changing D-16's Sources format would exceed the budget.
- **The gap closed.** Row C4's cell says only "quote". Section 5 tells the run to copy "the Meta entry for a key rule", and the Meta README row is the one row whose quote holds no prefix. So a run that copies its template faithfully could again commit a paraphrase, the lesson's root cause. One new note under "Notes on the rows", `:197`, closes it:
  > - **C4.** A table F row quotes the statement or example that documents P as the Sources table quotes it, so the quote contains P and is never a paraphrase of the page.

  It reuses the Sources rule (at most 200 characters, contains the value, inline code, `|` escaped), so it adds no new format. It allows "example" because row C1 may rest on a first-party example, as the xai row does; format binding (C2) still needs the statement. No spec sentence was needed: §12.3 C4 already says "quote", and the §16 row records the note.

Not done, as the brief says: no new fetch method. The raw HTML plus its text form is equivalent to a `.md` source, and the run above shows it on this exact page.

## Requirement 2: not covered before, now stated where the decision is made

### Root cause
Nothing in the skill forbade editing another vendor's key entries. `:20` says only "Edit only the files the wiring checklist names", and `provider_keys.py` and the registries README are named files. Section 5's "add only entries that are absent" is about the new vendor's entries. FR-11 cannot see such an edit either, because its path check allows every checklist path (review R-E7, follow-up).

### The change (provider-run.md)
1. **`## 3. Qualify` step 7, new paragraph `:129`, after the collision paragraph.** This is where the run reads `provider_keys.py`, the fixtures and both secondary sources, and so where it could notice a drift or want to make room for P:
   > Never edit or remove an existing vendor's `KEY_FORMATS` rule, `FORMAT_BOUND_PROVIDERS` entry or `RESERVED_PREFIXES` entry, or the README lines that document them: a new P that overlaps one is `key-prefix-collision`, never a reason to edit it. When a page this run opened from that vendor's own docs shows its keys in a shape its rule does not match, keep the rule, because keys issued in the old shape still exist, and record the difference under the PR's Follow-ups with the URL, its fetch-log date and a quote written as the Sources table writes one, so that a separate PR adds the new shape beside the old one and never replaces it.
2. **`## 9. Publish`, Follow-ups bullet `:348`.** One sentence was appended, so the section list carries the record:
   > List here too each existing vendor's key-shape difference that section 3's Key format step records.

### Choices and their flip conditions
- **Where.** In step 7, not in "Rules for the whole run". Step 7 is read at the moment the run handles key entries. It runs before any edit, and its rule then governs rows C1 to C4 and D2. Flip: if a review shows a run editing key entries outside step 7's reach, repeat the first sentence as a rule bullet.
- **"that vendor's own docs" only, not any page.** The gitleaks `facebook-access-token` rule already differs from Meta's rule by design (the README says so). A rule that fired on secondary sources would put the same false "drift" into every provider PR. A secondary-source shape still reaches the collision check through its third arm, which compares P with every existing vendor's gitleaks and GitHub patterns. Flip: if GitHub secret scanning starts naming a vendor's new format before the vendor's docs do, widen it to "or a secondary source", recorded as a hint.
- **Follow-ups, not a code change.** The skill onboards one new vendor per PR (FR-10, request §C "One provider per run, one PR per provider"), so adding Meta's `LLM_` shape belongs to its own PR. The quote follows the Sources rule, because Follow-ups text reaches the hosted `@claude` agent like any body text (T-2, EC-59). The URL is a page this run opened, so the URL rule at `:16` holds.
- **"edit or remove", not "change".** Row C1 places a new rule "before any rule whose prefix could also match". Inserting a rule before another one does not edit it, so the two rules cannot be read as conflicting.
- **The overlap clause.** This keeps the existing `key-prefix-collision` outcome as the only answer to an overlap. It closes the escape "narrow the old rule so P fits". The definition of an overlap ("one starts with the other") is unchanged.

### Spec (r9)
- D-13 gained one sentence (the end of its Decision cell): "A provider run never edits or removes an existing vendor's `KEY_FORMATS` rule, `FORMAT_BOUND_PROVIDERS` entry, `RESERVED_PREFIXES` entry or the README lines that document them (an overlap stays `key-prefix-collision`), and when a page it opened from that vendor's own docs shows another key shape, the PR's Follow-ups record the URL, the opened date and the quote, so that a separate PR adds the new shape beside the old one and never replaces it, because keys issued in the old shape still exist (r9, s5r3-1)."
- §16 row `s5r3-1`, source "coordinator-relayed lesson, 2026-10-17: #1027's Meta key rule drifted from Meta's docs", Major, accepted under the orchestrator's grant. It cites the requirement-1 lines and the C4 note.
- §17 row `r9`, `revision: 9`, status stays `reviewed`. Nothing else in the spec changed (`git diff --word-diff` shows one removed token, the old revision number `8`).

## Pinned sentences stay byte-identical

`git diff --word-diff=porcelain 5d1cc44a..164ac9fd -- .claude docs/spec/provider-onboarding-skill/spec.md` has exactly one removed token, `8` (the revision). Every other change is an addition. The Follow-ups line keeps its old text as a prefix and gains one sentence at the end. The pack gives `63 passed` before and after.

## For the S2 test author: what to pin, and the mutations that must turn red

`py -3.11 <s5r3>/mut_s5r3.py <worktree>` mutates the real provider-run.md in place, runs the pack, and restores the file byte for byte (it asserts this at the end). Today every row gives `63 passed`, so nothing pins the new text yet:

| Mutation | Today |
|---|---|
| CONTROL (no change) | `63 passed` |
| step-7 paragraph deleted | `63 passed` |
| rule A inverted: "You may edit or remove an existing vendor's" | `63 passed` |
| overlap → "a new P that overlaps one is a reason to edit it." | `63 passed` |
| "keep the rule" → "replace the rule" | `63 passed` |
| "beside the old one and never replaces it." → "in place of the old one." | `63 passed` |
| the Follow-ups record clause dropped | `63 passed` |
| the Follow-ups bullet's new sentence deleted | `63 passed` |
| C4 note deleted | `63 passed` |
| C4 note "so the quote contains P and is never a paraphrase of the page." → "or paraphrases the page." | `63 passed` |

The sentences to pin, each whole and on one prose line:
- In `## 3. Qualify`: "Never edit or remove an existing vendor's `KEY_FORMATS` rule, `FORMAT_BOUND_PROVIDERS` entry or `RESERVED_PREFIXES` entry, or the README lines that document them: a new P that overlaps one is `key-prefix-collision`, never a reason to edit it."
- The same line also holds: "When a page this run opened from that vendor's own docs shows its keys in a shape its rule does not match, keep the rule, because keys issued in the old shape still exist, and record the difference under the PR's Follow-ups with the URL, its fetch-log date and a quote written as the Sources table writes one, so that a separate PR adds the new shape beside the old one and never replaces it."
- In `## 9. Publish`, on the line holding `**Follow-ups**`: "List here too each existing vendor's key-shape difference that section 3's Key format step records."
- In `## 5. Wiring checklist`: "- **C4.** A table F row quotes the statement or example that documents P as the Sources table quotes it, so the quote contains P and is never a paraphrase of the page."
- A suggested negative check: no `## 3. Qualify` or `## 5. Wiring checklist` prose line matches `(?:replace|update|narrow|rewrite) (?:the|its|an existing|another vendor's) (?:vendor's )?(?:key )?rule`, or `in place of the old`.

## Open items
- **R-E7 stays a follow-up.** FR-11 still cannot machine-check that an existing vendor's key entries were left alone. The new rule is text. The smallest machine check would be a fifth FR-11 check: `git diff -U0 <base> <tip> -- vidbyte/lib/registries/provider_keys.py` has no removed line. That is a spec change beyond this budget.
- **Meta itself: a live key leak, outside this PR.** The repo still holds only `LLM|`. The separate PR the new rule describes is due now. It should keep `LLM|`, add `LLM_` in table F (which also reserves it), keep Meta format-bound, and quote the `.md` sentence above in its README row. `<s5r3>/meta_new_shape.py` runs `ProviderKeyMatcher.match` at this HEAD on fakes built by concatenation in both shapes (`PYTHONPATH=<worktree> py -3.11 -I …`):
  - A new-shape key fully matches no table F rule (`proves: []`).
  - Old shape, primary meta: bound to META.
  - New shape, primary meta: refused (`ConfigurationError`), so a Meta user with a current key cannot use the list form.
  - New shape plus a DeepSeek-style key, primary deepseek, other meta: refused.
  - **New shape alone, primary deepseek, other meta: bound to DEEPSEEK.** The lone-key rule sends a Meta key to another vendor. This is the cross-vendor misroute the user's method exists to prevent.

  This PR does not change it (the brief forbids touching `provider_keys.py`). It is the strongest reason to open the Meta PR next.
- **Seen, not acted on.** Meta's authentication page now exports `MODEL_API_KEY`; the muse-code page still says `META_API_KEY`.
