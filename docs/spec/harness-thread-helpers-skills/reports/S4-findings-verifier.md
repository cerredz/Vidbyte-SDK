# S4 findings verifier: harness-thread-helpers-skills

STATUS: DONE · Diff `origin/main...462e6d45` (merge base `239c408a`) · Worktree HEAD `6eafd6c8` (`vidbyte/` and `tests/` identical to `462e6d45`) · No commits · Output: `../review.md`

## Verdict and counts
**MERGEABLE AFTER FIXES.** Confirmed: **2 Blockers, 4 Majors and 17 Minors** (R-7 to R-23; one Minor is the verifier's own). Downgraded: **3** (R-E4, R-V2 and R-V3, all to Minor). Raised: 1 (R-V4, Minor to Blocker). Lowered within confirmed: 1 (R-C1, Blocker to Major, merged into R-5). Refuted: **3** (the implementation-side direction of R-C3, its README deletion, and my own PWD blind-spot candidate).

## Environment used for every piece of evidence
- `PY=C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python`, run from the worktree.
- `HOME` and `USERPROFILE` point at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/home`, and every repro case re-points them into its own temp root.
- Only the repo stand-in `tests/features/harness_threads/fake_harness.py` is used as the vendor CLI, with fake keys. No real vendor CLI ran.
- pytest always takes `-p no:cacheprovider`. Nothing was installed and nothing under `vidbyte/` or `tests/` was edited.
- `git status --short` shows only the three untracked reviews and `review.md` (and, after this file, this report).

## Merge map
| Reviewer ID | Proposed | Final | Disposition |
|---|---|---|---|
| R-V4 | Minor | **R-1 Blocker** | Raised. Field-guide lesson, and #1036 R-1 precedent |
| R-E1 | Blocker | **R-2 Blocker** | Confirmed |
| R-C2 | Major | **R-3 Major** | Confirmed |
| R-C3 + R-E3 | Major + Major | **R-4 Major** | Confirmed as a test defect. The implementation direction and the README deletion are refuted |
| R-C1 + R-E2 + R-C4 | Blocker + Major + Major | **R-5 Major** | Confirmed. R-C1 lowered by the #1036 R-7 precedent |
| R-V1 | Major | **R-6 Major** | Confirmed. Not raised (reason below) |
| R-C5 | Minor | R-7 | trivial |
| R-C6 | Minor | R-8 | follow-up |
| R-V5 | Minor | R-9 | follow-up |
| R-V6 | Minor | R-10 | trivial |
| R-V7 | Minor | R-11 | trivial |
| R-V8 | Minor | R-12 | follow-up |
| R-V9 | Minor | R-13 | follow-up |
| R-E5 | Minor | R-14 | follow-up |
| R-E6 | Minor | R-15 | trivial (my own probe reproduces it) |
| R-E7 | Minor | R-16 | follow-up (spec and S2) |
| R-E8 | Minor | R-17 | trivial |
| R-E9 | Minor | R-18 | follow-up (S2) |
| R-E10 | Minor [scope-adding] | R-19 | follow-up (scope-adding stays a Minor follow-up, per the briefing) |
| R-E4 | Major | R-20 Minor | Downgraded, follow-up |
| R-V2 | Major | R-21 Minor | Downgraded, trivial marker plus follow-up |
| R-V3 | Major | R-22 Minor | Downgraded, follow-up |
| [verifier] | — | R-23 Minor | New, follow-up |
| [verifier] PWD | — | Refuted | See the adjudications |

Coverage: only the engineering review found the D-33 hole (R-2), and only the conformance review found the INV-7 search (R-3). R-C1, R-E2 and R-C4 are one root cause, in `hostkit/errors.py`, where the factory falls back to `request.thread_id`, which is `None` for a RUN.

## Verification of each Blocker and Major

### R-1 (R-V4): wide comments. CONFIRMED and raised to Blocker
Command, for each changed `vidbyte/*.py` at both revisions:
`git show <rev>:<f> | awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'`
The results are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/wide_main.txt` (16 lines) and `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/wide_head.txt` (23 lines). A line-number-insensitive diff prints exactly 7 new lines:
```
grok/store.py           # other OSError is store_unreadable naming the file (spec EC-13).
muse/helpers.py         # Read the requested thread; an unknown id is thread_not_found.
muse/wire.py            # -32020 is a thread Muse does not have; -32601 is a Muse too old
opencode/commands.py    # The plan function always runs the plan agent; a config that
opencode/helpers.py     # Read the id's row from opencode's session table, database-wide,
lib/constants/native_threads.py  # Command and skill evidence (§9.2, INV-8): the tool a run must call and
lib/constants/native_threads.py  # The latest epoch millisecond a datetime holds (9999-12-31T23:59.999Z).
```
At head they sit at `grok/store.py:213`, `muse/helpers.py:178`, `muse/wire.py:252`, `opencode/commands.py:95`, `opencode/helpers.py:169` and `constants:80`, `:388`, with widths 73, 75, 73, 73, 73, 75 and 73.

**Calibration.** The Blocker test is "contradicts … a field-guide lesson". `comment-format.md` records the owner's rejection of wide comment blocks, and #1036 review R-1 rated 73–75-column overruns in new code a Blocker (fixed @`b8305b44`). The conventions reviewer's Minor understates it. The fix is trivial.

### R-2 (R-E1): the anchoredSnapshot evidence check is satisfied by the SDK's own prompt. CONFIRMED Blocker
Code: `muse/commands.py:149-152` calls `NativeCommandEvidence.require_text(transcript, fragment=tool, …)` and then `fragment=fragment`, where the transcript is the whole `muse export` text. The templates at `constants:449-450` put both tokens into the prompt the SDK sends: `"Use the \`{skill}\` skill.\n\n{prompt}"` and `"Use the create_goal tool to set this goal, …"`.

My repro: `"$PY" C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/repro_muse_d33_rule.py "$W" <scratch>/rerun`
```
[goal, no create_goal call] shipped rule -> SUCCESS | structural rule -> muse.command_not_run
[goal, create_goal called] shipped rule -> SUCCESS | structural rule -> SUCCESS
[plan, reads bundled:import instead] shipped rule -> SUCCESS | structural rule -> muse.command_not_run
[plan, no tool call, text names read_skill] shipped rule -> SUCCESS | structural rule -> muse.command_not_run
[plan, reads bundled:plan] shipped rule -> SUCCESS | structural rule -> SUCCESS
```
I re-ran the engineering reviewer's `s4eng/repro_muse_goal_anchored.py` with HOME redirected (the original run did not redirect it):
```
[goal, anchoredSnapshot, exec never calls create_goal] RETURNED SUCCESS thread_id=f79738f1-…
[goal, inline history, exec never calls create_goal (control)] raised muse.command_not_run …
[plan, anchoredSnapshot, exec reads ANOTHER skill (bundled:import)] RETURNED SUCCESS …
[plan, inline history, exec reads ANOTHER skill (control)] raised muse.command_not_run …
```
**Why no test catches it.** The only anchored negative case is `test_harness_threads_muse_commands.py:116-123`, plan with `read_skill` dropped. In that case the template's id is still present but the tool name is not, so it fails as expected. There is no anchored goal negative, and no wrong-skill negative.

**Calibration.** This is a wrong result: a paid compacted run reports success with no proof. It defeats INV-8 ("fails closed"), FR-15 and the request's point that a skill function actually runs the skill. It is a Blocker, and spec D-33 itself prescribes the defect. So S5 must amend D-33 and the §9.2 evidence cells together with the code. The structural rule keeps both true cases green, and it keeps the existing `export_drop_tools` test giving `command_not_run`.

### R-3 (R-C2): `search_grok_threads` returns a stale duplicate. CONFIRMED Major
Code: `grok/helpers.py:157-158` matches on every file's `search_text` and only then calls `NativeThreadListing.newest(…)`, which dedupes the matches (`hostkit/listing.py:37-50`). Re-run of `s4c-inv29/search_dupe.py`, with HOME redirected:
```
list: [('T1', 'write the docs', '2026-10-09T00:00:00+00:00')]
search 'LOGIN': [('T1', 'fix the login bug', '2026-10-02T00:00:00+00:00')]
```
This breaks INV-7. It is a real gap, since EC-17 says one id can sit under two groups. It is not a Blocker: the trigger needs a thread duplicated across groups whose current text no longer matches, and the result is stale rather than unsafe. The property test cannot see it because `draw_store` (`test_harness_threads_listing_properties.py:36-53`) gives the duplicate copy the same title and summary (`:49-51`).

### R-4 (R-C3 + R-E3): the pack fails in the user's shell. CONFIRMED Major (test defect)
- `env -u DEEPSEEK_API_KEY` dropped, ambient key kept: `"$PY" -m pytest -q -p no:cacheprovider tests/features/harness_threads` gives `16 failed, 982 passed, 3 skipped in 88.77s`.
- `env -u DEEPSEEK_API_KEY "$PY" -m pytest -q -p no:cacheprovider tests/features/harness_threads` gives `998 passed, 3 skipped in 88.79s`.
- With both `DEEPSEEK_API_KEY` and `ZAI_API_KEY` set, plus my autouse plugin `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/plugin/s4v_hermetic.py` (it runs `monkeypatch.delenv` on the six `CREDENTIAL_NAMES`; loaded with `PYTHONPATH=<plugin dir> -p s4v_hermetic`), the result is `998 passed, 3 skipped in 88.41s`.

**Cause.** `fake_harness.py:36` watches six names, and the 10 `all(value is None …)` assertions check all six. `sandbox` (`conftest.py:262-270`) clears none of them. Every credential `setenv` in the pack happens in a test body, after `sandbox`, so clearing the names in `sandbox` cannot hide a test's own key.

**Direction (adjudication 1, below).** The fix goes in the tests, not the product.

### R-5 (R-C1 + R-E2 + R-C4): evidence-step errors drop the new id. CONFIRMED Major
Root cause: `NativeErrorFactory.failure` (`hostkit/errors.py:88-130`) resolves `newest_id = thread_id if thread_id is not None else (None if request is None else request.thread_id)`. A RUN request's `thread_id` is `None`, and `from_unexpected` (`:147`) and `from_launch_failure` (`:164`) take the same fallback. The Grok evidence read (`grok/commands.py:243`) passes `thread_id=` to `GrokStore.thread`. But the failure sites inside it (`store.py:121`, `:180`, `:205`, `:221`, `:227`) and `GrokHelperWire.thread_file` (`grok/wire.py:197-224`) never pass it on. The same holds for Muse: `MuseChildren._prepare_config` raises at `children.py:131` without the id, and `MuseHelperRun._export`'s `mkdir` (`muse/helpers.py:333`) has no handler.
- Re-run of `s4c-inv29/repro.py`: `malformed RAISED FailureCode.GROK_PROTOCOL_MISMATCH thread_id= None`. The controls `wrong-agent … GROK_COMMAND_NOT_RUN thread_id= 567de087-…` and `missing … thread_id= 75e65076-…` do carry the id.
- Re-run of `s4eng/repro_grok_plan_evidence_id.py`: `[plan; own summary.json has agent_name of the wrong type] raised grok.protocol_mismatch error.thread_id=None argv --session-id=['a360ae70-…']`. The garbled `created_at` case gives the same result.
- My `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/repro_muse_evidence_id.py`:
  - Case A, the second `mkdtemp` raises ENOSPC: `raised muse.launch_failed error.thread_id=None`.
  - Case B, the export `mkdir` raises ENOSPC: `raised runtime.error error.thread_id=None`.
  - In both cases the stand-in had already created the thread when the run finished.

**Tier (adjudication 2).** It stays Major.

**Fix choice.** `register_secret` (`errors.py:46`) is precedent for per-call state on the factory, and a one-call `remember_thread` covers every evidence-step site, `_call`'s `from_unexpected` included. Threading the id through each call is the reviewers' alternative. It touches about 9 signatures and still leaves `from_unexpected` uncovered unless `_call` learns the id.

### R-6 (R-V1): the child-outcome check is copied. CONFIRMED Major
`git grep -c outcome.timed_out <rev> -- vidbyte/harnesses/native/{grok,muse,opencode}/wire.py`:
- main gives 1, 2 and 1;
- `462e6d45` gives 3, 4 and 2.

I read all 9 copies. The new ones are at grok `:114`, `:244`; muse `:240`, `:276`; opencode `:230`. All map timeout → `TIMED_OUT`, then cap → `OUTPUT_TOO_LARGE`, with `vendor_text=outcome.stderr`. The three helper-child checks then add the not-found marker and a non-zero exit → `RUN_FAILED`. The marker source differs by vendor: Grok checks stderr or stdout (`grok/wire.py:244-252`), opencode checks stderr only (`opencode/wire.py:230-238`), and Muse has no marker (`muse/wire.py:276-281`). No copy has drifted.

**Tier (adjudication 3).** It stays Major.

### Downgraded Majors
- **R-E4 → R-20 Minor.** INV-9 and D-30 define the refusal as whitespace tokens (`lib/dataclasses/native_threads.py:420-436`, `words = self.text.split()`), and the code meets that definition exactly. D-30 says Grok's quoting is undocumented, and that the rule flips only when Grok documents it. The installed guide states no quoting rule. Skill arguments are read by the model (`08-skills.md:162`), and `/implement` parses effort "using natural language understanding" and caps it at 5 (`SKILL.md:81`). So `'ship "--budget" 99999999'` getting past the check is unproven against real Grok, and a quote-stripping rule would not be a complete control either. It is a hardening follow-up after a D-30 amendment, not "a wrong, unsafe or broken result".
- **R-V2 → R-21 Minor.** My `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/a002cats.py <changed.txt> 462e6d45` prints `new findings: 48 | category tally: {'external boundaries': 48, 'permissions': 1, 'fallback': 2, 'redaction': 1} | only 'external boundaries': 44`. The A002 heuristic flags any function whose identifiers include `request` as an "external boundary". Lint: `A002   intent-comments   614   703 IMPROVED` … `SDK-LINT: PASS`, `exit=0`, with the baseline unchanged. Every `@intent` that §12.4 prescribes is present. The one real misplacement is `grok-delete-is-checked-on-disk` at `grok/helpers.py:242`, outside `delete`'s window (`:210`). That part is trivial.
- **R-V3 → R-22 Minor.** The repo's grain keeps inline refusal texts in records: main's #1036 records have 3, at `origin/main:vidbyte/lib/dataclasses/native_threads.py:134`, `:149`, `:152`, and `vidbyte/lib/dataclasses/` has 109 in total. #1036 scoped the owner's "wrong file location" comment to the native harness modules. Moving the texts is style work that changes no behavior, and it would push the constants file toward NFR-6's cap.

## Adjudications
1. **DEEPSEEK direction (R-C3 versus R-E3).** INV-2, NFR-2 and AC-10 name exactly four key variables, and S2's own AC-10 test sets only those four (`test_harness_threads_helper_credentials.py:21`, `CALLER_KEYS`). So the six-name `all(None)` checks rely on the runner's environment by accident. Stripping `DEEPSEEK_API_KEY` or `ZAI_API_KEY` in the product would be wrong:
   - `ZAI_API_KEY` is not a vendor variable (opencode reads `ZHIPU_API_KEY`).
   - It would put test-only names into `NativeEnvironmentVariable` (pinned at `test_harness_threads_surface.py:63`).
   - It is a scope-adding control that still would not give least privilege. That is R-19, a follow-up per the briefing.

   The README sentence at `vidbyte/harnesses/README.md:179` describes the INV-2 boundary accurately and stays. **Verdict:** the test edit is confirmed. The implementation edit and the README deletion are refuted.
2. **R-C1 tier.** The conformance reviewer cited INV-29's "Every" as a weighted word. The weighted words are request.md §D, and INV-29 is spec text, not one of them. The carried #1036 words that apply here are "extensively handle errors for every single function" and "error messages need to be in much more detail". #1036's verifier applied those same words to R-7, where `runtime.error` dropped the caller's thread id, and rated it **Major**. The error here is still raised, classified, and given a cause and a next step; one field is missing. Keeping the tier consistent with that precedent gives Major. It is still a must-fix.
3. **R-V1 tier.** The briefing's Blocker test includes "contradicts AGENTS.md", and #1036 R-5 rated principle-5 duplication a Blocker. But the #1036 repair (`efae78a5`) deliberately left each reader's timeout and cap checks in place, and main merged with those 4 copies. So the merged precedent treats a per-reader outcome check as acceptable grain. What crosses into Major is three new helper-child checks in this PR, which repeat the not-found and exit mapping as well, for 9 copies in all. A human reviewer would flag that. Nothing is wrong yet, and nothing has drifted.
4. **R-E4.** See "Downgraded Majors". The rule matches the spec words, and the bypass cannot be proven offline.
5. **R-V2.** See "Downgraded Majors". It is a heuristic count, and the gate passes.
6. **[verifier] PWD and `auto()` blind spot. Refuted.** `"$PY" -c "from vidbyte.lib.enums.native_threads import NativeEnvironmentVariable as E; print(repr(E.PWD.value), [m for m in E if m.name != m.value])"` prints `'PWD' []`. The `_generate_next_value_` override at `lib/enums/native_threads.py:209-231` returns the name. Its comment at `:227-229` states why `auto()` is used (bandit S105 would misread a `"PWD"` literal). It is not a suppression, and the only use site is `opencode/helpers.py:234`.

## Blind-spot sweep (verifier)
- **R-23 [verifier].** The inline evidence check is a substring test, "args contains the skill id" (§9.2, `hostkit/evidence.py:36`). Running `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4v-helpers/repro_muse_skill_prefix.py` prints `[run_muse_skill('bundled:grill'), model read bundled:grill-and-record] RETURNED SUCCESS`. None of the four named wrappers' ids is a prefix of another bundled id, so only the raw `run_muse_skill` is exposed. Follow-up, with a §9.2 amendment.
- Checked and clean:
  - INV-28: `"$PY" -m pytest -q -p no:cacheprovider tests/test_session_failures.py tests/test_codex_failure_recovery.py` gives `97 passed in 1.01s`.
  - Wrapper shape and the `_call` except order.
  - The §8.4 counts.
  - `vidbyte/` and `tests/` identical between `462e6d45` and HEAD.
  - The README character count.
- Benign deviations, not tabled: `OpencodeWire._unknown_command` (`opencode/wire.py:146`) matches by substring rather than by prefix (it is stricter in context), and the delete wrappers use a bare `await` (the same value).
- `origin/main` moved to `3802b3c3` (#1148, compaction only). No native file is touched, so the merge is clean in principle. S5 must merge, not rebase.

## Test lines S5 needs authorized (the orchestrator must approve each one)
| Finding | File:line | Change | Kind |
|---|---|---|---|
| R-4 | `tests/features/harness_threads/conftest.py:262-270` (`sandbox`) | Before `return box`, add `monkeypatch.delenv(name, raising=False)` for each of the six `fake_harness.CREDENTIAL_NAMES`, and add a line to its comment | **Required** (it is the fix itself) |
| R-2 | `tests/features/harness_threads/test_harness_threads_muse_commands.py`, next to `:116-123` | Anchored negatives: goal with no `create_goal`; plan reading `bundled:import`; text that names `read_skill` with no call. Each expects `muse.command_not_run` | Required (route S2) |
| R-3 | `tests/features/harness_threads/test_harness_threads_listing_properties.py:49-51` | Give the second-group copy different texts | Optional (route S2) |
| R-5 | Grok commands and Muse commands test files | Plan with a malformed own `summary.json` gives `grok.protocol_mismatch` with the minted id; a Muse evidence config failure gives `muse.launch_failed` with the new id | Required (route S2) |
| R-16 | `tests/features/harness_threads/test_harness_threads_helper_surface.py:258` | Unpin `list_opencode_threads_since` if §12.4 is amended | Only if R-16 is taken |

## Fix interactions for S5
- R-5's `remember_thread` and R-6's static `child_problem` both edit `hostkit/errors.py`. Land R-6 first: it is pure and leaves call signatures unchanged. Then add R-5.
- R-17 (`except OSError` in `_export_file`) gains the id for free after R-5.
- R-2 needs the spec D-33 and §9.2 amendments before the code. The export `items` shape is the stand-in's, and the real shape is A-28 (probe g).
- R-1: every comment S5 adds or edits must pass the same `awk` check.
- Before R-6, re-read AGENTS.md principles 1 and 5, and check §8.4 before adding any class.
- Run the gate with `env -u DEEPSEEK_API_KEY` until R-4 lands, then without it as the proof.
