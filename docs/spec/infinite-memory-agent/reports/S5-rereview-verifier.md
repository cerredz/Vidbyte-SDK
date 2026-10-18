# S5 re-review round 1: findings verifier — InfiniteMemory agent

Input: one post-repair conformance re-review (`reports/S5-rereview.md`: R-C1, R-C2, R-C3) plus two observations from the briefing (A, B). Diff `origin/main...e2b76a60`; worktree HEAD 9f2bb33d differs from it only in docs. Output: the section "Re-review round 1 (post-repair) — verified" appended to `review.md`, plus one line under its top `## Verdict`. Rows R-1..R-25 were left as they were.

`$V` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/316f126c-6db0-45d5-b506-cdb76c0921d5/scratchpad/s5-rrverifier`. Every probe there is the verifier's own, except `$V/rr/`, which holds copies of the reviewer's scripts used for cross-checks. `$V/fix` is a `git archive HEAD` export with `git init` and a base commit, so lint can read `git ls-files`. `$V/apply_fixes.py` applies the trial fixes to it.

## Verdict

MERGEABLE AFTER FIXES: 2 confirmed Majors (R-26, R-27), 0 Blockers, 2 Minors (R-28, R-29), 1 sub-claim downgraded, and 2 observations not filed.

## Merge map

| Original | Merged | Disposition |
|---|---|---|
| R-C1 [Major] | R-26 | CONFIRMED, Major |
| R-C2 [Major]: the supersede and new-note encode cases, plus the staged-entry case from `r1_guard.py` | R-27 | CONFIRMED, Major. One root cause: no encode check before the first of two writes, or before staging. |
| R-C2 [Major]: the Windows-lock sub-case | R-29 | DOWNGRADED to Minor (`follow-up`) |
| R-C3 [Minor] | R-28 | Passed through as Minor, with one item added by the verifier (the stale §17 bullet on runtimes.py); tagged `trivial`, **needs: spec edit** |
| Observation A (two `pair_finished` records) | — | Not filed; no spec ID promises a single record |
| Observation B (catalog strictness) | — | Not filed; R-7's requirement stands, and the documentation gap is inside R-28 |

## Verifications

### R-26 (R-C1): a read-only seed blocks every later construction. CONFIRMED, Major.

- **Code path.**
  - `agent.py:54` builds `InfiniteWorkspace(settings.workspace)` on every `InfiniteMemoryAgent(...)`.
  - `workspace.py:78-79` copies each seed on every construction through `self.backend.copy`.
  - That copy is `local.py:73`, `shutil.copy2`, which runs `copyfile` and then `copystat`, so the mode bits are copied too.
  - `copyfile` opens the destination for writing, and that open fails when the destination is read-only.
  - At def85360 the code was `shutil.copyfile(seed, …)`, which copies no mode bits, so the copy was always writable.
- **Own probe:** `PYTHONPATH=$(pwd) python $V/c1_ro_seed.py $V/work_c1` at the worktree prints:
  ```
  1st construction: built | copy writable: False | copy == source: True
  2nd construction (same memory/): PermissionError: [Errno 13] Permission denied: '…\\memory\\seed\\brief.md'
  3rd construction (source made writable and edited): PermissionError: [Errno 13] Permission denied: '…\\memory\\seed\\brief.md'
  ```
  The 3rd line rules out the "skip an identical copy" alternative: after the source changes, the old read-only copy still blocks the overwrite.
- **Reviewer's script cross-check:** `python $V/rr/ro_seed.py` prints `seed copy writable: False`, `agent B construction raised PermissionError …`, and `resume-process construction raised PermissionError …`.
- **Spec.**
  - INV-21: "Each seed file is copied, overwriting, to `seed/<basename>`." This is broken on the second construction.
  - §9.2: construction "passes on any `ConfigurationError` from the settings or the workspace setup". A raw `PermissionError` is outside that contract.
  - §4's last paragraph and AC-30 cover a second agent on the same folder.
  - D-6 and A-2 make the workspace persist.
  - request.md §D "Unattended, resumable": `resume()` from a new process must build the agent first.
  - D-24 says "read-only through tools, and there is no file-mode knob". The fix keeps both: `_note_path` (`workspace.py:295`) refuses `seed/`, and no setting is added.
- **Existing guard?** None. No test builds twice over a read-only seed: `grep -n seed_files tests/features/infinite_memory_agent/*.py` finds 9 lines: `acceptance.py:71` (AC-1, one build), `workspace.py:166, 215, 412` (one build each), and `contract.py:260-264, 325` (refused settings). None builds twice. The only record is the KNOWN EDGE CASES sentence (`workspace.py:9`).
- **Severity.** Kept at Major, not Blocker. The failure is loud and happens at construction, before any journal or workspace state changes. Nothing is lost. It needs a read-only seed, which is not the default. One chmod recovers it.
- **Fix trial** (`python $V/apply_fixes.py $V/fix both`):
  - **The change.** It binds `copy`, calls `self.backend.copy(Path(seed), copy)` and then `copy.chmod(copy.stat().st_mode | stat.S_IWRITE)`, adds `import stat`, adds one comment clause, and drops the KNOWN EDGE CASES sentence.
  - **Result.** The probe prints `built | copy writable: True | copy == source: True` for all three constructions, and the reviewer's `ro_seed.py` prints `agent B built: OK` and `resume agent built: OK`.
  - **Lint.** S061 lists only `write_text`, `write_bytes`, `read_text`, `read_bytes`, `copy`, `copy2`, `copyfile`, `move`, and `extractall` (`lint/rules/s061_bounded_safe_path.py:27-29`), so `chmod` is not flagged.
- **Alternatives considered.**
  - Going back to `shutil.copyfile` is rejected: S061 counts a `copyfile` on a dynamic path, so S061 would go 5 → 6.
  - Copying through `backend.read_text` and `backend.write_text` is rejected. Universal newlines would turn CRLF into LF, which breaks AC-1's "equals `brief.md`", and a non-UTF-8 seed would fail.
  - A mode option on `LocalFileSystemBackend.copy` is rejected because it is outside §12.3.

### R-27 (R-C2): refused two-file writes are partial. CONFIRMED, Major.

- **Code path.**
  - `commit_entry` builds `changed` as superseded first, then entries (`workspace.py:137-139`), and writes it in a loop at `:146-147`.
  - `write_note` builds `changed` as the note first, then `files.jsonl` (`:167-170`), and writes it in a loop at `:172-173`.
  - `_replace` encodes the text only inside `file.write` (`:319-320`). A `UnicodeEncodeError` on the second file therefore comes after the first `os.replace`.
  - `_entry_rules` (`:256-271`) has no encode check, so `check_entry` stages unencodable text.
  - The tools catch `ValueError` and answer "Nothing was saved …" (`memory.py:160, 214`; `infinite_memory.json:24`).
  - `_commit` catches only `ToolExecutionError` (`launch.py:347`). A `UnicodeEncodeError` there therefore reaches the pair guard and gives UNCHECKED. That is conformant with INV-29 as written, but it comes from staging something that could never commit.
- **Own probe:** `PYTHONPATH=$(pwd) python $V/c2_partial.py $V/work_c2` at the worktree drives the model-facing tools directly:
  ```
  2 remember surrogate supersedes=1: ERROR ToolResult(… output="Nothing was saved, because the call needs a change: 'utf-8' codec can't e…
  3 same call again: ERROR …
     changed files: ['superseded.jsonl']
     superseded ids: [1, 1] | live ids: [1]
  4 write_note notes/a.md, surrogate description: ERROR … "Nothing was saved, …
     changed files: ['notes/a.md'] | files.jsonl paths: [] | files_written: []
  5 write_note notes/b.md (allowance is 1 new file): OK … 'Saved the file notes/b.md.\nQuota left: … and 0 …
     new notes on disk: ['notes/a.md', 'notes/b.md'] | created counter: 1
  6 generator remember surrogate: OK … "Staged as s1. …
     commit of that staged entry raises: UnicodeEncodeError …
  ```
- **Reviewer's script cross-check, end to end:** `python $V/rr/r1_guard.py` at HEAD shows three things:
  - `a/gen [remember] "Staged as s2 …"` for the surrogate entry.
  - Pair a gets `Status: done. Verdict: unchecked.`
  - `entries.jsonl texts: ['a first fact', 'b fact']`, so the valid s3 `a third fact` is lost.
- **Spec.** INV-19 says "A refused write changes nothing on disk", and INV-32 says "The call writes nothing". INV-20 requires a description on create and a per-agent cap of new files; step 5 shows two new files from one agent against `INFINITE_NEW_FILES_PER_AGENT = 1`. INV-12 says the verifier receives the paths the generator wrote, but `files_written` stays empty. The README (line 70) says "a refused write changes nothing".
- **Existing guard?** None for two-file writes. The R-8 test's cases are single-file (`test_infinite_memory_workspace.py:494-500`: remember without `supersedes`, an append to an existing note, and an edit).
- **Reachability.** A lone surrogate is what a model's JSON `\ud83d` escape without its pair decodes to. This is the same input S4 accepted for R-1 and R-8, and the R-8 test uses it.
- **Fix trial**, on the same `$V/fix` copy as R-26:
  - **The change, in two places.**
    - In `_entry_rules`: `for value in (draft.text, *draft.refs): value.encode("utf-8")`.
    - In `write_note`, before the write loop: `for content in changed.values(): content.encode("utf-8")`.
  - **Own probe after the fix.**
    - Steps 2–3 give `changed files: []` and `superseded ids: [] | live ids: [1]`.
    - Step 4 gives `changed files: [] | files.jsonl paths: []`.
    - Step 5 gives `new notes on disk: ['notes/b.md']`.
    - Step 6 gives `ERROR … Nothing was saved`.
  - **`r1_guard.py` after the fix.**
    - The surrogate `remember` gives `[tool_error kind=execution_error] Nothing was saved …`.
    - Pair a gives `Status: done. Verdict: passed.`
    - `entries.jsonl texts: ['a first fact', 'a third fact', 'b fact']`.
    - `pair_finished per key: {'root/a': 1, 'root/b': 1}`.
  - **Why `commit_entry` needs no encode loop of its own once `_entry_rules` checks:**
    - tags match `INFINITE_TAG_PATTERN`, an ASCII slug;
    - `by`, `verified_by`, and `run` are built from ASCII patterns (`INFINITE_TASK_NAME_PATTERN`, `INFINITE_RUN_ID_PATTERN`, and `INFINITE_ROOT_KEY`);
    - `at` comes from `isoformat`;
    - the kept and moved lines were decoded with `errors="replace"`.
  - **The reviewer's fix** also encodes `changed` in `commit_entry`. It is equally correct and costs two more lines, so it is kept as the alternative.
- **One comment line in the trial is 73 columns:** `            # Encode every text first, so a refused write writes nothing.`. The repair must rewrap it (field guide `comment-format.md`).

### R-29 (part of R-C2, the Windows lock). DOWNGRADED to Minor.

- **Own probe:** `python $V/c2_lock.py $V/work_c2` prints:
  ```
  remember alpha: success
  supersede while held: error | Nothing was saved, because the call needs a change: [WinError 5] Access is denied: …
  live ids: [1] | superseded ids: [1]
  retry after release: success | live ids: [2] | superseded ids: [1, 1]
  ```
  With the R-26 and R-27 trial fixes applied, the output is the same. Those fixes do not touch this case.
- **Why Minor.**
  - **Narrow trigger.** It needs a second process that holds the file open without `FILE_SHARE_DELETE` at the instant of the second `os.replace`, which only Windows enforces.
  - **The state is not new.** A crash leaves the same state, which `workspace.py:9` documents ("leaves the line in both files rather than in neither"). Ids stay unique because the next id is the `max` over live and superseded ids (`workspace.py:127`).
  - **The fix costs more than the effect.** Restoring the first file needs a rollback path that holds the old text. Naming the case needs a spec edit to INV-19. Either is more than this effect warrants under "dont overengineer anthing".
- **Fix options for the follow-up.** Either restore the first file from the text read under the lock (production), or name the limitation in INV-19 and the README (**needs: spec edit**).

### R-28 (R-C3): the repair's rules are not in the spec. Minor, `trivial`, needs: spec edit.

- **Rules the repair added that the spec does not record.** Each is checked against the code:
  - **Note path, one line:** `workspace.py:280-281` refuses a path that breaks across lines.
  - **Note path, no colon:** `:289-290` refuses a path that holds a colon. INV-20 lists only three path rules.
  - **Model catalog check:** `settings.py:206-213` refuses a model the catalog does not hold. §9.3 says only "same meaning as `BaseAgent`".
  - **Neither appears in the docs:**
    - `grep -n -i "colon\|ProviderModelRegistry\|INFINITE_MIN_CAP\|ascii\|copy2\|STRICT_MODEL" spec.md` prints nothing.
    - `grep -i "catalog\|STRICT\|colon\|ascii" vidbyte/agents/infinite/README.md` finds nothing.
  - **`INFINITE_MIN_CAP`:** defined at `vidbyte/lib/constants/infinite.py:28`, and not in the spec.
  - **ASCII journal:** `journal.py:190` writes `json.dumps(record)`, so the journal is now ASCII-escaped. §9.1 and D-25 do not say this.
- **[verifier] A stale §17 bullet.** §17's S3 deviation says `runtimes.py`'s f-strings were merged. After R-5 (c4822ebb), `git diff origin/main...HEAD -- vidbyte/lib/registries/runtimes.py` shows only `+ from vidbyte.agents.infinite import InfiniteMemoryRuntime` and `+ AgentRuntimeType.INFINITE_MEMORY: InfiniteMemoryRuntime,`.
- **Dropped item.** The reviewer's fifth item, that seed copies keep their mode bits, is moot once R-26 lands.
- **Tagging.** This is `trivial` and needs no code. The spec part is an orchestrator spec edit. The README clause is a production doc change the repair agent can make.

### Observation A: two `pair_finished` records for one key. Not filed.

- **Reviewer's injection script:** `python $V/rr/r1_finish_fault.py after-write` prints:
  ```
  launch result: ### Pair a (root/a) | Status: done. Verdict: unchecked. | … Review: [Errno 28] No space left on device | Entries saved: #1 …
  pair_finished per key: {'root/a': 2, 'root/b': 1}
  a's recorded verdicts: ['passed', 'unchecked'] | entries.jsonl lines: 1
  journal re-reads; root/a card verdict: unchecked
  ```
  `before-write` prints `{'root/a': 1, 'root/b': 1}`.
- **Searching the spec for a single-record promise.** `grep -n -i "exactly once\|once per key\|one pair_finished\|pair_finished" spec.md test-plan.md request.md` finds:
  - INV-25: "`pair_finished(key, card)` is written after that pair's commit."
  - INV-29: "Either way `pair_finished` is written."
  - "Exactly once" only for usage (INV-35).
  - The test plan's "exactly one `pair_finished`" belongs to the R-1 triggers, and that test passes.
- **Two records are consistent with the spec.**
  - INV-25: a record counts only "flushed and fsynced", so the first line never counted.
  - `pair_finished` updates `_cards` only after `_append` returns (`journal.py:102-103`), and `_parse` keeps the last record per key (`:167`).
  - So the in-process card and the re-read card agree, and INV-26 replays that card.
- **Reachability.** It needs a storage fault that fails `flush` or `fsync` after a complete write. A full disk usually also fails the second write in the error path, which is EC-41's accepted limitation.

### Observation B: the model catalog is checked strictly. Not filed.

- **Own probe:** `PYTHONPATH=$(pwd) python $V/obs_b_models.py $V/work_b` prints:
  ```
  openai/gpt-4.1 | infinite: ok | config BaseAgentSettings: ok | BaseAgent: built, runner TextModelRunner
  openai/gpt-4.1-2025-04-14 | infinite: refused (…) | config BaseAgentSettings: ConfigurationError: Unrecognized model 'gpt-4.1-2025-04-14'. … | BaseAgent: built, runner TextModelRunner
  openai/anthropic/claude-sonnet-4-5 | infinite: refused (…) | config BaseAgentSettings: ConfigurationError: Unrecognized model … | BaseAgent: built, runner TextModelRunner
  openrouter/anthropic/claude-sonnet-4-5 | infinite: refused (…) | config BaseAgentSettings: ConfigurationError: Unrecognized model … | BaseAgent: ConfigurationError: Missing API key for provider openrouter. …
  openai/my-finetune-xyz | infinite: refused (…) | config BaseAgentSettings: ConfigurationError: Unrecognized model … | BaseAgent: ConfigurationError: No runner mapping …
  with STRICT_MODEL_VALIDATION=False: gpt-4.1-2025-04-14 accepted
  ```
- **R-7's original confirmation was right.**
  - C012 is blocking.
  - The rule's header (`lint/rules/c012_provider_model_registry_validation.py:5`) accepts only four proofs for a model field, each in a method that runs at construction: a `ProviderModelRegistry` validation call, a catalog-membership test, or a hand-off to a configuration class or same-module helper that holds one.
  - Before the fix the PR raised C012 from main's 23 to 24, inside stale baseline headroom. lint/README forbids any count increase.
- **The strictness is the SDK's own policy.** The declarative `BaseAgentSettings` (`vidbyte/lib/dataclasses/config.py:505-517`, the `vidbyte/config` path) refuses exactly the same names. Only the programmatic `BaseAgent(...)` constructor skips the catalog.
- **Correction to the briefing.** `JevAgentSettings` does not call `ProviderModelRegistry`; `grep -n ProviderModelRegistry vidbyte/agents/jev/settings.py` finds nothing. The R-7 repair cited `JevRunBriefSettings._validate_model` only for the shape of the helper.
- **No spec ID is at stake.**
  - "All SDK agents" answered "Which executor?", meaning SDK agents rather than Codex threads (request.md:159, 171, 186). It is not about the range of models.
  - AC-2 lists the construction refusals it requires and does not forbid others.
  - The §4 snippet's model passes.
  - What remains is documentation: §9.3 and the README should name the catalog check and `STRICT_MODEL_VALIDATION`. That is folded into R-28.

## Disagreements adjudicated

- **The reviewer filed R-C2 as one Major. The verifier split it.** The encode cases are model-reachable on every OS and have a 4-line fix, so they stay Major as R-27. The Windows-lock case has a narrow trigger and a benign effect, so it is a Minor follow-up (R-29). Their fixes differ: a pre-encode check against a rollback or a spec edit.
- **The verifier's fix for R-27 is smaller than the reviewer's.** One encode check in `_entry_rules` covers both the root supersede and staging. One check in `write_note` covers the description. The reviewer also encoded inside `commit_entry`, which the `_entry_rules` check already makes redundant. The reviewer's version stays as the alternative.
- **The R-C1 fix was confirmed as proposed:** one `chmod`, with no lint change.
- **The briefing's claim that the strictness "matches `JevAgentSettings._validate_model`" was corrected.** The real precedent is `vidbyte/lib/dataclasses/config.py`'s `AgentSettings._validated_model`.

## Interactions for the repair agent

- R-26 and R-27 both edit `vidbyte/agents/infinite/workspace.py`, in different functions (`__init__`; `_entry_rules` and `write_note`). They do not conflict, and the trial applied them together.
- The R-26 fix must also delete the seed sentence from the KNOWN EDGE CASES header (`workspace.py:9`).
- R-28's §17 list should leave out "seed copies keep mode bits" once R-26 lands. If R-27 lands, it should add "entry text, refs, and descriptions must be UTF-8-encodable".
- Keep every new comment line at 72 columns or less (field guide `comment-format.md`; R-9).

## Commands run (final lines)

- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider`:
  - worktree: `107 passed in 3.19s`
  - `$V/fix` with both trial fixes: `107 passed in 3.10s`
- `python lint/run.py` in `$V/fix` (export of HEAD), baseline: `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS`, with C012 23/24, S061 5/6, S062 889/889, S008 19/19, S051 259/259, and A001 642/642.
- `python lint/run.py` in `$V/fix` with both trial fixes: `SDK-LINT: PASS`. `diff counts_base.txt counts_fix.txt` over all 90 rule rows gives `COUNTS IDENTICAL`.
- `awk 'length($0) > 72' $V/fix/vidbyte/agents/infinite/workspace.py | grep -E '^\s*#'` finds one line, the trial's own comment (see R-27).
- Probes at the worktree: `c1_ro_seed.py`, `c2_partial.py`, `c2_lock.py`, `obs_b_models.py`, `rr/ro_seed.py`, `rr/partial.py`, `rr/r1_guard.py`, and `rr/r1_finish_fault.py before-write|after-write`. Outputs are quoted above.
- Probes at `$V/fix`: `c1_ro_seed.py`, `c2_partial.py`, `c2_lock.py`, `rr/ro_seed.py`, `rr/partial.py`, and `rr/r1_guard.py`. Outputs are quoted above.
- `git diff origin/main...HEAD -- vidbyte/lib/registries/runtimes.py` shows 2 insertions: the import and the registry row.
- `git show def85360:vidbyte/agents/infinite/workspace.py` shows lines 78-79 `(… / INFINITE_SEED_DIRNAME).mkdir(exist_ok=True)` / `shutil.copyfile(seed, …)`.
- `git status --porcelain` in the worktree shows only `review.md` and this report, both modified or added.
