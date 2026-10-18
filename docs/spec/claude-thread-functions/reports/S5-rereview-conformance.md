LENS: conformance
VERDICT: SOUND — every confirmed S4 finding (R-1 to R-4) and every trivial Minor (R-5 comment move, R-7, R-8, R-9, R-15) is fixed as spec r4 says, the merge disturbed nothing, and the only new defects are three comment-level Minors.

Scope: `git diff origin/main...73252faf` (merge base 845a4d9b = origin/main), with the focused diffs `git diff be18994a 821af103 -- . ':!docs'`, `git show --cc be18994a`, `git show cabf0f80` and `git show 2c1e233c`. Review is post-repair (round 1 of 2). The code head is 821af103; 2e6049b9 and 73252faf are docs only.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **AC-1 still holds exactly, in a hostile environment.** The §4 snippet ran against the independent S4 stand-in, reached through PATH, with a fresh HOME. It printed `claude True True`, then `answer to: Try it with argparse instead.` The parent shell held 12 real `ANTHROPIC_*`/`CLAUDE*` names, among them a real `ANTHROPIC_API_KEY`, `CLAUDECODE`, `CLAUDE_CONFIG_DIR` and the messaging socket and token. Each child saw only three of them: `ANTHROPIC_API_KEY` (sha256 prefix `5eaf12c29df2`, the caller's fake key), the private `CLAUDE_CONFIG_DIR` (`…\.vidbyte\claude-configs\e3a70a5a2403e685`, equal to `sha256(normcase(resolved ws))[:16]`) and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, plus `DISABLE_AUTOUPDATER=1`. argv was the exact AC-5 form for each of the three verbs, the prompt arrived only on stdin, and the workspace stayed empty.
- **R-1 and R-3: `ClaudeWire.read` now mirrors `opencode/wire.py:53-64` line for line.** It reads the answer first. `TIMED_OUT` and `OUTPUT_TOO_LARGE` both pass `thread_id=newest, vendor_text=outcome.stderr`, and the INV-7 order and `subtype` handling are unchanged. C901 for `read` is still 8 (`8 > 7` at max 7). An independent red run proves the five S2 regression tests can fail: run on 2c1e233c's pre-repair code, they give `5 failed, 6 passed`, and they pass at HEAD.
- **R-2 is Claude-only and exact.**
  - A differential probe over 17 prompts gives identical accept and refuse results for Grok, opencode and Muse on origin/main and HEAD (`sibling differences main vs head: none`), which supports INV-20.
  - Claude refuses only NUL and U+D800–U+DFFF. Emoji, ZWJ sequences, CJK, CJK Extension B (astral), U+FEFF, U+FFFE, U+FFFF and U+10FFFF are all accepted.
  - The refusal comes before launcher lookup, as INV-5 requires: with a nonexistent `claude_command`, the call still gives `configuration.invalid_argument`. No private folder is created, and the message is UTF-8-encodable, because `_received` quotes with `repr`.
- **The merge and the scope are clean.**
  - `git show --cc be18994a` shows only the `validation.py` `ROLE IN CODEBASE` line, with `ClaudeWire` inserted.
  - 25 of the PR's 38 changed files have byte-identical patches against their base before and after the merge. The 13 that differ are exactly the repair files, S2's test files and `validation.py`.
  - `lint/`, `contracts/`, `pyproject.toml`, `vidbyte/tools`, `vidbyte/lib/errors/__init__.py`, `vidbyte/lib/configs` and root `vidbyte/__init__.py` show no diff against main.
  - The §8.4 budget holds: 4 new files, 8 classes and 0 dependencies. `claude/*.py` is 364 lines (NFR-3 ≤ 400), and the constants module is 521 lines (NFR-7 ≤ 600).

FINDINGS (ranked, most severe first, max 15)
R-C1 [Minor] [weighted words / spec text] vidbyte/harnesses/native/claude/threads.py:9 (also wire.py:9; spec row 20 r4) — The header says "only" two kinds of run carry no new id, but at least two other paths carry none
  Evidence: threads.py:9 now reads "The thread id is read only from Claude Code's JSON answer, so only a run that times out before printing it, or whose stdout is cut at the cap, carries no new id". wire.py:9 lists the same two cases in its parenthetical: "only a run whose whole answer the SDK never read (a timeout before Claude Code printed it, or stdout cut at the cap) carries no new id". Probe through `ClaudeWire.read` for a run:
    `bare non-zero exit, stderr only -> claude.run_failed thread_id = None | timed_out: False truncated: False`
    `exit 0, not JSON -> claude.protocol_mismatch thread_id = None | timed_out: False truncated: False`
    A launch failure (`from_launch_failure`) also carries None for a run. Spec row 20 r4 prescribes the same overbroad wording: "the headers of wire.py and threads.py say that only a run that times out before printing its answer carries no new id".
  Failure: An agent reads the module header, as AGENTS.md says to, and concludes that a `run_failed` from a crash or a `protocol_mismatch` at exit 0 carries a resumable id. It then tries `continue_claude_thread(error.thread_id, …)` with `None`.
  Smallest fix: In both headers, replace the "only" sentence with "a run that printed no valid answer carries no new id, whether it timed out, was cut at the cap or failed; one that printed its answer and then hung reports that id (D-9, EC-14, EC-15)". The orchestrator mirrors that wording in spec row 20.
  Spec IDs: INV-6, D-9, EC-14, FR-15; AGENTS.md principle 2 (comments never describe behaviour that does not exist)

R-C2 [Minor] [deviations / R-9 regression] vidbyte/lib/constants/native_threads.py:9; vidbyte/lib/dataclasses/native_threads.py:9 — The R-2 commit cites "(spec EC-38)" unqualified in two shared headers whose other unqualified citations mean #1036's spec, which has its own EC-38
  Evidence: `git show 9398d9ee` adds "…opencode's stdin prompt still uses NATIVE_PROMPT_PATTERN (spec EC-38)" to the constants header and "…opencode's prompt is not checked for one (spec EC-38)" to the dataclass header. In the same files, the unqualified citations name the harness-thread-functions spec. In the constants header these are `(spec INV-15)` at :5 and `(lint A007, spec INV-15)` at :7, and INV-15 there is #1036's literal policy, while this spec's INV-15 is the batch-launcher rule. In the dataclass module it is `(spec §9.1, EC-3)` at :108, which is on origin/main. #1036's spec numbers its edge cases at least to EC-44: the README cites its EC-39, EC-43 and EC-44, and its own new last sentence assigns them to "the harness-thread-functions spec". So "(spec EC-38)" resolves to an unrelated row. This is the defect R-9 fixed in `folders.py`, which now writes "(claude-thread-functions spec EC-31)".
  Failure: An agent that follows "spec EC-38" from the constants header into #1036's spec lands on the wrong edge case, and the cited reason for the Claude-only pattern is lost.
  Smallest fix: Write "(claude-thread-functions spec EC-38)" in both headers, as `hostkit/folders.py:9` does.
  Spec IDs: EC-38, INV-5 rule 5; R-9 (`review.md`)

R-C3 [Minor] [deviations / unreported edit] vidbyte/harnesses/native/claude/wire.py:91; vidbyte/lib/dataclasses/native_threads.py:147 — Two "comment-only" repair commits also deleted the space after `=` in a code line
  Evidence: In `git show --format= 687141f7` (R-8), the line `-        thread_id = request.thread_id if …` becomes `+        thread_id =request.thread_id if …`. In `git show --format= 821af103` (R-5 comment move), `-            pattern = CLAUDE_THREAD_ID_PATTERN if …` becomes `+            pattern =CLAUDE_THREAD_ID_PATTERN if …`. `git log -S'thread_id =request'` and `-S'pattern =CLAUDE'` name exactly those two commits. Neither commit message, nor the repair report ("both are comment text only"), mentions the edit. Lint does not catch it: across `vidbyte/` the only other such assignment is `vidbyte/tools/toolsets/coding.py:134`. Behaviour is unchanged.
  Failure: There is no runtime effect. A human reviewer sees PEP 8 E225 spacing introduced in a PR that otherwise keeps the sibling style. The claim that R-8 and R-5 changed only comments and a parameter does not quite hold.
  Smallest fix: Restore the single space at both sites: `thread_id = request.thread_id …` and `pattern = CLAUDE_THREAD_ID_PATTERN …`.
  Spec IDs: n/a (house style; §12.4 S008 and S009 are unaffected)

VERIFIED CLAIMS:
1. R-1 fixed (bb624cc9): HELD. `wire.py:54` passes `vendor_text=outcome.stderr`. `test_stdout_past_the_cap_carries_claudes_stderr_as_the_vendor_text` passes at HEAD and fails on 2c1e233c (`where None = NativeThreadError('… claude.output_too_large …')`). `check_error(vendor=)` asserts `vendor in error.vendor_message` (conftest.py:374-376). Spec §17 deviation 3 is struck through.
2. R-3 fixed (b65590a4): HELD. The reading moved above both bound checks, and both checks pass `thread_id=newest`. Every interaction the briefing asked about matches r4, probed through `ClaudeWire.read`:
   - A run that timed out after printing a 401 answer gives `claude.timed_out` with the printed session id. The timeout keeps priority over `key_rejected` (INV-7 order), and INV-6 says a failed run's answer id is kept.
   - A fork that timed out after printing its source id gives `claude.timed_out` with the source id, the same as the fallback.
   - A continue that timed out after printing another id gives `claude.timed_out` with the caller's id.
   - The narration and headers moved with the code: wire.py:5 says the answer is read first, wire.py:8 item 3 now reads "only its thread id is ever used", and the wording issue in wire.py:9 and threads.py:9 is R-C1.
   - The INV-7 order is unchanged, and `subtype` is still used only as reason text in `_error_text`.
   - Reading first changes one more outcome. A pathological stdout nested deeper than about 1,000 levels (`"[" * 200000`) on a timed-out or truncated run now raises `RecursionError` from `json.loads`, which `_call` turns into `runtime.error` instead of `claude.timed_out`/`output_too_large`. The process tree is already stopped. The same happens on opencode's timed-out path on main (`opencode run timed-out, deep-nesting stdout -> RecursionError`) and on Claude's exit-0 path since S3. Claude Code never prints such output, and the behaviour matches the sibling the spec told row 20 to copy, so it is not filed. A 64 MiB truncated prefix parses in 0.03 s and gives `output_too_large` with thread_id None.
3. R-2 fixed (9398d9ee): HELD. The pattern and the conditional expression match spec row 16, row 17 and §8.5 exactly, and the switch is never keyed on `NATIVE_STDIN_PROMPT_HARNESSES`. The differential probe of origin/main against HEAD finds no sibling difference, and Grok and Muse raise the same pre-existing `UnicodeEncodeError` for a lone surrogate on both trees. Astral characters pass, because Python stores them as single code points; only an explicit surrogate pair written as two code points (`"😀"`) is refused, and UTF-8 cannot encode that either. The refusal comes before lookup, and no folder is created (see above). `test_invalid_prompt_is_refused[lone-surrogate]` fails on 2c1e233c (`expected configuration.invalid_argument, got runtime.error`) and passes at HEAD.
4. R-4 fixed (0fd70984): HELD.
   - The REPO_MAP native section contains `Claude Code` and none of the six forbidden substrings.
   - Its only backticks are the heading, `hostkit` and `vidbyte/lib/process/`, as on main.
   - It reads correctly for all four harnesses.
   - `git diff origin/main...73252faf -- REPO_MAP.md` is one hunk, that paragraph only.
   - The README holds all six AC-23 r4 tokens and is 13,961 characters (A009 ≤ 40,000).
   - The AC-23 test fails on 2c1e233c and passes at HEAD.
5. R-8 (687141f7): HELD for behaviour. `_missing_member(answer, session)`, ruff `ARG` is clean, and the mypy-narrowing comment is true: `_checked_thread_id` requires text for every non-run verb. Spec §17 deviation 5 records it. The stray whitespace edit is R-C3.
6. R-9 (5d449187): HELD for the two sites R-9 named. The README's IDs match this spec's rows (EC-9, EC-10, EC-30, EC-20, EC-21, EC-22, EC-28, EC-37 and T-4 are all the rows the sentences describe), and `folders.py` uses `(spec INV-15)` like its siblings and qualifies EC-31 and EC-21. The R-2 commit reintroduced the pattern elsewhere (R-C2).
7. R-15 (8d28e7f5) and the R-5 comment move (821af103): HELD. The comment text is correct and sits directly above its line. R-C3 covers the whitespace.
8. R-7 (cabf0f80): HELD. INV-11 r4 excepts `taskkill` (`runner.py:118`).
9. Spec r4 and the S2 tests agree. The tests match INV-5 rule 5, INV-6, INV-7 items 4–5, EC-14, EC-15, EC-38 and AC-23 r4 one for one (`README_TOKENS` and `MAP_FORBIDDEN` equal AC-23's lists). The test-plan coverage-map rows 34–37 name the five tests.
10. Merge resolution: HELD. Exactly one `--cc` hunk. Main's 60 commits touched no native-thread code: `git diff --stat b28c3027 845a4d9b` over the harness, process, native_threads, failure and errors paths lists only `validation.py` (new optional parameters, backward-compatible for every Claude call), `enums/__init__.py` and `errors/base.py`, whose change is in `CodexAgentError`, not `NativeThreadError`.
11. Ratchets: HELD. S008 19/19, S009 346/350, A002 566/703, and `lint/` is unchanged. Every comment line added since S3_HEAD is ≤ 70 columns.
12. Test discipline: HELD. Both briefing commands print nothing. The diff adds no `noqa`, `type: ignore`, `cast`, skip or xfail under `vidbyte/`. The `bypassPermissions`, `dangerously`, `subprocess` and `skipif` hits are all test guards or the stand-in's own code.
13. Remote CI 4/4 green on 821af103: HELD (check-runs API). GitHub's PR head is 2e6049b9. 73252faf, docs only, is local.
14. ID walk for the code changed since 0a2752dd: INV-5 (rule 5), INV-6, INV-7, INV-9, INV-11, INV-16 (no new literal; static-policy test passes), INV-20, AC-1, AC-8, AC-10, AC-15, AC-23, EC-14, EC-15, EC-38, D-9, Q-3, FR-6, FR-11, FR-15, NFR-3, NFR-4, NFR-7, and rows 16, 17, 19, 20, 29, 30 and 32 (header) all hold, apart from R-C1 to R-C3. Every other ID covers code whose patch is byte-identical to the S3_HEAD patch S4 reviewed, and the whole pack passes (635 passed, 2 skipped).
15. request.md §A–§C: nothing in the repair adds scope or reverses a decision. The README's R-9 sentence names spec slugs, not `docs/` paths.

COMMANDS RUN:
- `git show --cc --format='%H %P%n%s' be18994a` → one hunk, `vidbyte/lib/dataclasses/validation.py` ROLE line with `ClaudeWire` inserted
- `git diff be18994a 821af103 -- . ':!docs'` → `7 files changed, 43 insertions(+), 32 deletions(-)`
- `git diff --stat origin/main...73252faf -- lint/ contracts/ pyproject.toml vidbyte/tools vidbyte/lib/errors/__init__.py vidbyte/lib/configs vidbyte/__init__.py` → empty
- `git log --no-merges --oneline 4806c697..73252faf --not origin/main -- tests` and `git show --cc --format= be18994a -- tests` → both empty
- `git log -S'thread_id =request' …` and `git log -S'pattern =CLAUDE' …` → `687141f7 …[R-8]`, `821af103 …[R-5]`
- AC-1: the S4 `snippet.py` with HOME and USERPROFILE set to `s5conf/home`, `S4_LOG=s5conf/log`, PATH = stand-in bin, Python and System32 only, and a fake `MY_ANTHROPIC_KEY` → `claude True True` / `answer to: Try it with argparse instead.` / `exit=0`; 3 start records decoded as above
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ < /dev/null` at 73252faf → `635 passed, 2 skipped in 67.63s`
- Red run on `git archive 2c1e233c` (scratch `s5conf/red_tree`) of the 4 test functions → `5 failed, 6 passed in 11.64s` (the five regression ids fail)
- R-2 differential probe (`git archive 845a4d9b vidbyte` to `s5conf/main_tree` against the worktree) → `sibling differences main vs head: none`; Claude refuses lone-high, lone-low, pair-as-two and nul, and accepts the rest
- R-2 through the public functions with a missing `claude_command` → `run_claude_thread configuration.invalid_argument`, `fork_claude_thread configuration.invalid_argument`, `home2 contents … []`
- ClaudeWire and OpencodeWire probes (bound paths, deep nesting, 64 MiB prefix) → results quoted in claims 2 and R-C1
- `PYTHONPATH=$(pwd) python lint/run.py --rule S008` → `S008 RATCHETED: 19 known finding(s)` / `SDK-LINT: PASS`; `--rule S009` → `S009 IMPROVED 350 -> 346` / `SDK-LINT: PASS`; `--rule A002` → `A002 IMPROVED 703 -> 566` / `SDK-LINT: PASS`
- `python -m ruff check vidbyte/harnesses/native/claude --isolated --select C901 --config 'lint.mccabe.max-complexity=7'` → `C901 \`read\` is too complex (8 > 7)`; `--select C901,PLR0912,PLR0915` over native and the dataclass → `All checks passed!`; `--select ARG` over claude → `All checks passed!`
- `wc -l` → claude `22 + 190 + 152 = 364`, constants 521, dataclasses 258, folders 50
- `gh api repos/cerredz/Vidbyte-SDK/commits/821af103…/check-runs` → `Package`, `Static policy`, `Source / Python 3.11` and `Source / Python 3.12`, each `completed success`
