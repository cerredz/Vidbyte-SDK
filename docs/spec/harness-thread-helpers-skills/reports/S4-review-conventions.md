LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the PR follows the package's placement, header, narration and one-level-deep rules, but it copies the child-outcome check into five more places, adds 45 A002 intent-comment findings that pass only because the lint baseline has room to spare, and writes 21 refusal texts inline in the records file.

Reviewed: `git diff origin/main...462e6d45` (merge base `239c408a`; the worktree head `6eafd6c8` differs only in `pipeline.md`). Sources: AGENTS.md principles 1–5 and the Placement Rules; the field-guide entries in `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`; spec r3 §12.4 and §12.5; house style; the lint loop; commit hygiene.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **Principles 1 and 2 hold.** An AST scan of every changed `vidbyte/*.py` finds no new same-class A→B→C chain. The only nested callables are two sort-key lambdas; principle 1 allows callbacks. Every flow and `execute` is narrated. Each of the 6 new public classes has exactly one guarded `_call` with #1036's except order: `CancelledError`, then `NativeThreadError`, then `ConfigurationError`, then `Exception`.
- **Placement is correct.**
  - The 6 new enums are in `vidbyte/lib/enums/native_threads.py` and exported from `vidbyte/lib/enums/__init__.py`.
  - The new records are frozen and slotted in `vidbyte/lib/dataclasses/native_threads.py`.
  - The 10 new modules hold no module-level code and stay at or under 366 lines.
  - The records file is 598 lines (cap 600) and the constants file 836 (cap 900).
  - The INV-15 static-policy test and both surface tests pass.
- **§12.5 docs are done.**
  - The README native bullet covers every item AC-26 lists: helper families, `GrokThreadScope.SDK`/`USER`, the 24 command and skill functions, the evidence rule, `command_not_run`, the "Not offered" rows, EC-72/74/76/78 and `permission_mode=GrokPermissionMode.ACCEPT_EDITS`.
  - The EC-44 sentence is replaced by the EC-63/T-6 sentence.
  - The README is 15,074 characters, and A009 is CLEAN.
  - The REPO_MAP entry names listing, reading, lineage, search, delete and verified command runs.
  - No `.env.example`, changelog or `llms.txt` file changed.
- **Lint and commit hygiene hold.**
  - The loop ends `SDK-LINT: PASS`, and `git diff origin/main...462e6d45 -- lint/` is empty.
  - No suppression was added.
  - Apart from A002 (R-V2), no rule has a new finding in a changed file. The A003 and S062 rows in `lib/errors/base.py` were already on main.
  - All 51 commits carry `Co-Authored-By: Claude` and cite W/FR/INV IDs.
  - The diff has no `.pyc` file.

## FINDINGS

**R-V1 [Major] [principle-5 / field-guide] `vidbyte/harnesses/native/grok/wire.py:240-252` — the helper child-outcome check is now written five more times, and the refused-member mapping three times**

- **Evidence:**
  - The check "`timed_out` → TIMED_OUT, then `stdout_truncated` → OUTPUT_TOO_LARGE" is repeated with the same `seconds=`/`cap_bytes=` arguments. `git grep -c outcome.timed_out` over the wire readers finds 4 copies on main and 9 at head.
  - The 5 new copies are:
    - `grok/wire.py:114-117` (`GrokStreamWire.read`);
    - `grok/wire.py:244-247` (`GrokHelperWire._checked`);
    - `opencode/wire.py:230-233` (`OpencodeHelperWire._checked`);
    - `muse/wire.py:240-243` (`MuseSessionWire.result`);
    - `muse/wire.py:276-279` (`MuseSessionWire.exited`).
  - Three of them (`GrokHelperWire._checked`, `OpencodeHelperWire._checked` and `MuseSessionWire.exited`) also repeat the tail "non-zero exit → RUN_FAILED". The two `_checked` copies also share the not-found branch; only the marker differs.
  - "ConfigurationError → `details[NATIVE_FIELD_DETAIL_KEY]` → vendor member → PROTOCOL_MISMATCH" is written three times: `grok/wire.py:221-224`, `opencode/wire.py:281-283` and `muse/wire.py:359-362`.
  - The spec never names per-wire `_checked` methods (grep of spec.md finds none). S3 deviation (1) added `exited` as yet another copy.
- **Failure:**
  - AGENTS.md principle 5 names "parsing a provider's response" as its example of logic to write once.
  - `strict-config-dataclasses.md:18-21` says: "Two independent inline copies of the same rule drift silently."
  - #1036 review R-5 was a **Blocker** for the same pattern in these same three wire files.
  - Any change to the check's order or arguments has to be made at 9 sites. The copies already differ: `OpencodeHelperWire._checked` takes no `thread_id`, while the Grok and Muse copies pass one.
- **Smallest fix:**
  - Add one static class beside `NativeErrorFactory` in `hostkit/errors.py`. A new file would break the §8.4 budget of 10. For example, `NativeChildCheck.check(outcome, request, errors, *, thread_id, not_found: str | None)` runs timeout → cap → not-found marker → non-zero exit.
  - Add one `refused_member(exc, members) -> str` beside it.
  - It calls `errors.failure`, which belongs to another class, so principle 1 holds. Putting it on `NativeErrorFactory` itself would recreate #1036 R-3's `check → failure → _context_sentences` chain.
  - Call it from the 5 new sites and the 3 summary readers.
- **Spec IDs:** §12.4 ("A step that two flows share is a private helper"); INV-16; AGENTS.md principle 5; #1036 R-5.

**R-V2 [Major] [lint / agentic-intent] `vidbyte/harnesses/native/grok/helpers.py:210` — the PR adds 45 A002 findings, and the gate passes only because the baseline has room left over**

- **Evidence:**
  - `lint/run.py --rule A002 --all --format json` lists 68 A002 findings in changed files.
  - Running the rule's own `IntentAnalyzer` on git blobs gives 559 findings at merge base `239c408a` and 604 at `462e6d45`, an increase of 45.
  - Per file, by function name: 20 on main and 65 at head.
  - The new modules account for most of them: `grok/helpers.py` 9, `muse/helpers.py` 8, `opencode/wire.py` +7, `grok/wire.py` +5, `opencode/helpers.py` 4, `muse/wire.py` +3, and so on.
  - Lint prints `A002 intent-comments 614 703 IMPROVED` because main had already dropped well below the 703 baseline.
  - One concrete miss: `# @intent grok-delete-is-checked-on-disk` sits at `grok/helpers.py:242`. That is 32 lines below `def delete` at `:210`, outside the rule's window of def−4 to def+20, so the rule the spec asked to mark does not count.
  - S3 reports that "the IMPROVED rules were left alone". That is true, but the PR absorbed 45 new findings into that headroom.
- **Failure:**
  - A002 is `severity = "blocking"` (`lint/rules/a002_intent_comments.py:89`).
  - `class-bound-helpers.md:42` says: "A002 intent-comments passes, since a new boundary function needs its own `@intent` block."
  - `blocking-lint-invariants.md` (A003 entry) says a ratchet holds new code "to a stricter bar than its neighbors".
  - The next `--update-baseline` locks these 45 in as permanent debt.
  - A reviewer who runs `--rule A002 --all` sees 45 new rows, all in this PR's files.
- **Smallest fix:**
  - Move `grok-delete-is-checked-on-disk` into `delete`'s first 20 lines.
  - Give each flagged new function a `# @intent <rule-name>` first line on its existing opening comment. Most of them already state a boundary rule (the keyless child, the fixed bounds, the not-found mapping).
  - Re-run the per-file comparison until it shows `new=[]` for the 10 new modules.
- **Spec IDs:** §12.4 ("Domain rules carry a `# @intent <name>` block within 20 lines of their `def`"; "New code changes nothing in `lint/baseline.json`"); NFR-5.

**R-V3 [Major] [KD-9 / house-rule placement] `vidbyte/lib/dataclasses/native_threads.py:242` — 21 new refusal texts are hardcoded inline, while the same record uses named `_RULE` constants**

- **Evidence:**
  - `grep -c 'raise ConfigurationError(f\?"'` on the records file gives 3 on main and 24 at head.
  - The 21 new lines are `:215, :218, :242, :265, :274, :279, :287, :295, :301, :306, :355, :372, :375, :386, :391, :395, :404, :418, :420, :444, :542`. Examples:
    - `:242` `f"operation must be a thread helper of {self.harness.value}; got {self.operation.value}."`
    - `:386` `"budget_tokens is taken only by /goal."`
  - The PR also added a group headed "Refusal rules of the command records, named in invalid_argument" (`constants/native_threads.py:713-717`: `GROK_TEXT_FLAG_RULE`, `GROK_GOAL_RESERVED_RULE`, `GROK_DESIGN_DOC_SPACE_RULE` and `OPENCODE_PLAN_AGENT_RULE`). Those constants are used at `:377`, `:433` and `:436` of the very record whose `:372`, `:375` and `:386-:420` stay inline.
- **Failure:**
  - request.md KD-9 restates the owner's #1036 rule: "constants and hardcoded strings live in `vidbyte/lib/constants/native_threads.py`". The owner comment behind it reads "wrong file location for all of these".
  - §12.4 says: "Every number and text is a named constant in `vidbyte/lib/constants/native_threads.py`."
  - One record now mixes both styles, so the next refusal text has no clear home.
- **Smallest fix:**
  - Move the 21 texts into the existing "Refusal rules" group as `.format` templates, the way `GROK_TEXT_FLAG_RULE` already is.
  - This also takes the records file away from its 600-line cap (598 now). The constants file grows to about 860 lines, still within 900 (see R-V8).
  - `details={"field": …}` stays as it is: §12.4 prescribes that literal key for records.
- **Spec IDs:** KD-9; §12.4; FR-16; #1036 KD-7.

**R-V4 [Minor] [comment-format] `vidbyte/harnesses/native/muse/helpers.py:178` — 7 added comment lines run past 72 columns**

- **Evidence:**
  - `awk 'length($0) > 72'` on comment lines prints:
    - `grok/store.py:213` (73)
    - `muse/helpers.py:178` (75)
    - `muse/wire.py:252` (73)
    - `opencode/commands.py:95` (73)
    - `opencode/helpers.py:169` (73)
    - `lib/constants/native_threads.py:80` (75)
    - `lib/constants/native_threads.py:388` (73)
  - None of these are on main. The `failure.py` and `base.py` hits were already on main.
- **Failure:** `comment-format.md:3-7` requires every comment line to wrap at 72 columns, indent included. Its Check is exactly this awk command, which must print nothing for the files you touched.
- **Smallest fix:** Rewrap the 7 blocks. Keep each `# @intent` line inside its def+20 window.
- **Spec IDs:** §12.4 ("≤ 72-column comment blocks").

**R-V5 [Minor] [principle-5-in-module] `vidbyte/harnesses/native/opencode/helpers.py:136-144` — `list` and `search` repeat the session-list step and the workspace filter; only one copy carries its `@intent`**

- **Evidence:**
  - `:136-137` and `:154-155` build the same `--format json --max-count NATIVE_OPENCODE_SCAN_MAX` options and make the same `_child(... session list ...)` call.
  - `:143-144` and `:156-161` repeat the `os.path.normcase(directory) == wanted` filter.
  - The domain rule `# @intent opencode-list-keeps-the-workspace-rows` (`:139`) guards only the `list` copy.
- **Failure:**
  - §12.4 says "A step that two flows share is a private helper."
  - If one copy of the workspace filter changes (for example, the EC-28 subfolder rule), search and list disagree.
- **Smallest fix:**
  - Move the directory filter, with its `@intent`, into `OpencodeHelperWire.sessions(outcome, request, errors)`, which already has `request.workspace`.
  - Name the options pair once.
  - Both flows keep one `_child` call, so there is still no two-deep chain.
- **Spec IDs:** §12.4; D-19; EC-28.

**R-V6 [Minor] [house-style] `vidbyte/harnesses/native/grok/commands.py:242-251` — the evidence check under `@intent grok-command-evidence-fails-closed` ends without a default and would fail open**

- **Evidence:**
  - The branches run `if agent is not None` / `elif command is GrokCommand.CODE_REVIEW` / `elif command is not None`, then `return result`.
  - If both are `None`, no evidence check runs.
  - This is unreachable today only because `GrokCommandArguments._checked_target` (`lib/dataclasses/native_threads.py:353-354`) refuses the case.
- **Failure:**
  - House style asks for dispatch with an explicit default.
  - The intent block four lines above promises fail-closed behaviour, but the code silently relies on a check in another layer.
- **Smallest fix:** Make the last branch `else:`. The record guarantees a command there.
- **Spec IDs:** INV-8; INV-24; §12.4 (`@intent` evidence fails closed).

**R-V7 [Minor] [header-accuracy] `vidbyte/lib/enums/native_threads.py:9` — three docs no longer match the code**

- **Evidence:**
  - (a) The enums header still says "FUNCTION INVENTORY: No functions." `NativeEnvironmentVariable._generate_next_value_` (`:209-213`) is a function, added so that `PWD = auto()` (`:231`) yields `"PWD"`. The value is verified correct.
  - (b) `vidbyte/harnesses/README.md`, end of the native bullet, still says "The shared plumbing (error factory, launcher resolution, skills folders) lives in `hostkit/`". REPO_MAP and `hostkit/__init__.py` were updated to add listing order and evidence checks.
  - (c) `muse/children.py:48`, `:62` and `:139` cite "spec INV-9" and "spec EC-34", which are #1036's numbers. The header at `:5` cites this spec's INV-14. In this spec, INV-9 is "No caller value becomes a flag" and EC-34 is a Muse launcher refusal, so the moved comments now point at the wrong rules.
- **Failure:**
  - §12.4 says "Every modified module's header is updated to match its new contents" (lint A001 checks only that the fields exist, not that they are accurate).
  - AGENTS.md says to regenerate a wrong README or map entry rather than leave it.
- **Smallest fix:**
  - (a) Name `_generate_next_value_` in the FUNCTION INVENTORY.
  - (b) Add "listing order and evidence checks" to the README sentence.
  - (c) Write "#1036 INV-9" and "#1036 EC-34" in the three moved comments. The comment text otherwise stays verbatim.
- **Spec IDs:** §12.4 (A001 header line); §12.5 README bullet; D-10.

**R-V8 [Minor] [principle-3] `vidbyte/lib/constants/native_threads.py:1` — the constants file grew from 452 to 836 lines and is heading toward four digits**

- **Evidence:**
  - `wc -l` gives 836, under NFR-6's 900.
  - The records file is at 598 of its 600.
  - R-V3's fix adds about 25 lines to the constants file.
- **Failure:**
  - AGENTS.md principle 3 says: "when a file heads toward four digits, split it ... before adding more."
  - The next native feature cannot add constants without breaking NFR-6.
- **Smallest fix:** No change in this PR. As a follow-up, split the texts (sentences, causes and next steps) into a sibling `vidbyte/lib/constants/native_thread_texts.py`.
- **Spec IDs:** NFR-6; §12.4 (file sizes).

**R-V9 [Minor] [commit-hygiene] commits `0b7516f3` and `c89c0373` — the two lint-repair commits each span 3–4 work items**

- **Evidence:**
  - `0b7516f3` is `[W-1, W-4, W-5, W-6]`: it changes the enums, records, constants and all three wires.
  - `c89c0373` is `[W-3, W-4, W-5]`.
  - By their own messages, both bring A007, S008, S009, S051 or S054 back to baseline. So, by that account, the feature commits they repair were not lint-clean on their own: `ad12d7d2`, `c12ce245`, `b8f0610c` and `2ffcac65` for the first; `76297896`, `f3429925`, `509bc733` and `9b197327` for the second.
  - Everything else is clean: one subject per change, IDs cited, all 51 commits carry the trailer, and there is no bytecode.
- **Failure:** Bisecting this range lands on red-lint commits, and the one-work-item-per-commit rule is broken twice.
- **Smallest fix:** No history rewrite is needed. S5 fix commits should each cite one finding and work item and be lint-clean on their own (run `lint/run.py` after `git add`).
- **Spec IDs:** §12.3 phase order; §12.4 ("lint is run after `git add`").

## VERIFIED CLAIMS

1. **S3: "10 new files, 2,034 lines" — TRUE.** `git diff --diff-filter=A --name-only origin/main...462e6d45 -- vidbyte/` lists 10 files, totalling 2,034 lines. The largest new module is 366 lines (`muse/helpers.py`), within NFR-6's 600.
2. **S3: "lint PASS, baseline unchanged" — TRUE, but incomplete.** The loop ends `SDK-LINT: PASS` and the `lint/` diff is empty. However, A002 grew by 45 inside baseline headroom (R-V2). Every other ratcheted rule has 0 findings in changed files, except A003 and S062 in `lib/errors/base.py`, which were already on main.
3. **S3 deviation 9: "`PWD = auto()` yields `PWD`" — TRUE.** `NativeEnvironmentVariable.PWD.value == 'PWD'`, and every member's value equals its name. auto() is a working way to avoid the bandit S105 false positive without a `noqa` (which the spec forbids); only the header is stale (R-V7a).
4. **§12.5 README and REPO_MAP — TRUE.**
   - The README is 15,074 characters (40,000 allowed) and A009 is CLEAN.
   - The EC-44 sentence is gone, replaced by "Grok still loads your `~/.claude` hooks … (EC-63, T-6)".
   - Every AC-26 item is present.
   - The REPO_MAP entry names listing, reading, lineage, search, delete and verified command runs.
5. **INV-1 export count — TRUE.**
   - `vidbyte.harnesses.native.__all__` has 68 names: 23 helpers (22 plus `init_muse_workspace`) and 24 command and skill functions.
   - The 6 new enums are imported and listed in `lib/enums/__init__.py`.
6. **§12.4 "one guarded `_call` with #1036's except order" — TRUE.** 6/6 classes have one `_call` each, with except order `CancelledError` → `NativeThreadError` → `ConfigurationError` → `Exception`.
7. **§12.4 principle 1 — TRUE.** `depth.py` reports no new chain. The only chain is `FailureCode.from_exception → _from_exception_name → _from_exception_fallback`, which is on main. The only nested callables are the sort-key lambdas in `grok/store.py:167` and `hostkit/listing.py:51`.
8. **§12.4 `@intent` list — mostly TRUE.** The intents for scope home, no-create read, evidence fails closed (×3), workflows off for goal, slash commands not expanded, export in an empty folder, PWD overlay and keyless helper child (`opencode/helpers.py:224`) are all present. `grok-delete-is-checked-on-disk` falls outside A002's window (R-V2).
9. **The moved Muse `@intent` blocks are kept verbatim — TRUE.** `muse-key-and-skills-through-a-private-config-home` and `muse-wsl-run-is-reaped` moved from `muse/threads.py` to `muse/children.py:42` and `:95`.
10. **INV-15 test coverage — has a blind spot, no violation.** The test skips bools and reads `-1` as `UnaryOp(USub, Constant(1))`, so it allows it. New code uses `[-1]` 4 times (`grok/helpers.py:183`, `opencode/helpers.py:192`, `grok/wire.py:147`, `:158`); main had none. Bool literals are already used this way on main. Not raised as a finding.
11. **AC-22 wording — known spec typo.** AC-22 names `AGENT-LINT: PASS`, but the tool prints only `SDK-LINT: PASS`. This matches S3 deviation 11 and is wording only.

## COMMANDS RUN

- `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python lint/run.py` → exit 0, 1m14s. Final lines:
  ```
  S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline
  S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all
  SDK-LINT: PASS
  ```
  Table rows of note: `A002 614 703 IMPROVED`, `A009 0 0 CLEAN`, `C002 9 9 RATCHETED`, `S054 3 3 RATCHETED`.
- `$PY lint/run.py --rule <R> --all --format json` for 41 rules (A001–A008, C001–C020, S001–S064 ratcheted/improved), each grepped against the changed-file list. Final lines:
  ```
  A001 lines-mentioning-changed-files=0
  A002 lines-mentioning-changed-files=68
  A003 lines-mentioning-changed-files=36   (all vidbyte/lib/errors/base.py, on main)
  S062 lines-mentioning-changed-files=3    (base.py:491-501, on main)
  ```
  Every other rule printed `=0`.
- `$PY -B scratchpad/s4conv/a002cmp.py changed.txt 462e6d45` (rule's `IntentAnalyzer` on `git show` blobs, per file) → `TOTAL main=20 head=65`.
- `$PY -B scratchpad/s4conv/a002total.py 462e6d45 origin/main 239c408a` →
  ```
  462e6d45: A002 findings=604
  origin/main: A002 findings=554
  239c408a: A002 findings=559
  ```
- `$PY -B scratchpad/s4conv/depth.py <31 changed vidbyte .py files>` → final lines:
  ```
  vidbyte/harnesses/native/grok/store.py: GrokStore.thread defines nested lambda at line 167
  vidbyte/harnesses/native/hostkit/listing.py: NativeThreadListing.newest defines nested lambda at line 51
  vidbyte/lib/enums/failure.py: FailureCode.from_exception -> _from_exception_name -> _from_exception_fallback
  ```
- `git show 462e6d45:<f> | awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'` over the changed files, then the same at origin/main → 7 new lines (R-V4); the remaining `failure.py`/`base.py` hits are identical on main.
- `git grep -c outcome.timed_out origin/main|462e6d45 -- vidbyte/harnesses/native/` → wires: main grok 1, muse 2, opencode 1; head grok 3, muse 4, opencode 2.
- `git show <rev>:vidbyte/lib/dataclasses/native_threads.py | grep -c 'raise ConfigurationError(f\?"'` → main `3`, head `24`.
- `git diff origin/main...462e6d45 --stat -- lint/` → (empty). `git diff --name-only origin/main...462e6d45 | grep -c -E '\.pyc$|__pycache__'` → `0`.
- `git show 462e6d45:vidbyte/harnesses/README.md | wc -c` → `15074` (main `10791`).
- `for c in $(git rev-list origin/main..462e6d45); do git log -1 --format=%B $c | grep -q '^Co-Authored-By: Claude' || echo missing $c; done; echo checked` → `checked` (51 commits, none missing).
- `env -u DEEPSEEK_API_KEY PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -p no:cacheprovider -q tests/features/harness_threads/test_harness_threads_static_policy.py …_helper_surface.py …_surface.py` → `49 passed in 1.97s`.
- `$PY -B -c "from vidbyte.lib.enums.native_threads import NativeEnvironmentVariable as E; print(repr(E.PWD.value), all(m.value == m.name for m in E))"` → `'PWD' True`.
- `git status --short` after all runs → only the S4 reports are untracked; no tracked file changed.

Scratch scripts (outside the repo): `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\8ba228e7-1bc7-41fd-a637-c0f10b927957\scratchpad\s4conv\depth.py`, `...\a002cmp.py`, `...\a002total.py`.
