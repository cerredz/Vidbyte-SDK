# S5 repair, iteration 2 of 8: native-thread-compose

- **Status:** DONE. R-32 is fixed. Every local gate is green at code HEAD bc351671, and both remote workflows are green there.
- **Branch:** `feat/native-thread-compose`, in the worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`.
- **PR:** draft https://github.com/cerredz/Vidbyte-SDK/pull/1186, stacked on `feat/native-grok-opencode-meta-hosts`. Its title, body and draft state are unchanged.
- **History:**
  - The iteration started at 43bd0024.
  - The orchestrator's docs commit 74d770da (`pipeline.md` only) landed on the branch just after launch, and was not pushed then. This iteration's commits sit on it, and the first push carried it.
  - The code HEAD is bc351671 (pushed). The records commit, which touches only `docs/spec`, sits on top.
- **Scope:**
  - Only three source files changed: `vidbyte/harnesses/native/compose/chain.py`, `stages.py` and `texts.py`.
  - `git diff d9cc9ff6..HEAD --stat -- tests` is empty.
  - Nothing changed under `lint`, `.semgrep`, `.github`, `scripts`, `contracts`, `pyproject.toml` or `spec.md`.
  - Nothing was pip-installed.
- **Scratch:** every saved output and script is under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s5-2/`, called `s5-2/` below. The final gate run is in `s5-2/final/`.

## 1. Gate matrix

Gates 1–9 ran in this worktree, in this iteration, at bc351671, after the last source commit. The final lines are quoted from the saved outputs in `s5-2/final/` (`g1-lint.txt` to `g8-wheel.txt`).

| # | Gate | Result | Final lines |
|---|---|---|---|
| 1 | `python lint/run.py` | PASS. The count table matches iteration 1's line for line (`diff` against `s5-1/grant-lint.txt` is empty). | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline` / `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| 2a | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS: 223, not risen | `Found 223 errors.` / ``[*] 223 fixable with the `--fix` option.`` |
| 2b | `python -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache` | PASS: exactly 5 | `Found 5 errors.` |
| 3a | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` | PASS, exit 0 | `1/1: ✓ All tests passed` / `No tests for fixes found.` |
| 3b | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS, exit 0 | ` • Findings: 0 (0 blocking)` / `Ran 1 rule on 977 files: 0 findings.` |
| 4 | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` | PASS. At 43bd0024 it was `2 failed, 361 passed`. | `...  [100%]` / `363 passed in 89.59s (0:01:29)` |
| 5 | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` | PASS | `......  [100%]` / `436 passed, 2 skipped in 50.92s` |
| 6 | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS. The inherited MCP stdio flake did not occur. | `tests\test_workflow_agent_forks.py ......  [100%]` / `================ 6004 passed, 16 skipped in 184.31s (0:03:04) =================` / `CI passed.` |
| 7 | `env -u PYTHONPATH python scripts/run_ci.py --stage package --dist-dir s5-2/final/dist-3` (a new empty folder) | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| 8 | AC-21 wheel half: `s5-2/final/wheel-venv-3/Scripts/python.exe -I s3/check_wheel_prompts.py <worktree>`, run from `s5-2/final/wheel-run-3` | PASS | `installed vidbyte: ...\s5-2\final\wheel-venv-3\Lib\site-packages\vidbyte\__init__.py (outside the checkout: True)` / `fixed combinations: 17, longest planner = 8304 chars, over 12000: {}` / `AC-21 WHEEL HALF: PASS` |
| 9 | `awk 'length($0) > 72' <file> \| grep -E '^[[:space:]]*#'` | PASS | `chain.py over72=0`, `stages.py over72=0`, `texts.py over72=0` (the three files this iteration changed) |
| — | `git diff d9cc9ff6..HEAD --stat -- tests` | PASS | empty |
| 10a | Remote: Static policy, run 39163919767 at bc351671 | PASS, watch exit 0 | `1/1: ✓ All tests passed` / `Ran 1 rule on 977 files: 0 findings.` |
| 10b | Remote: CI, run 39163918203 at bc351671 | PASS: Source / Python 3.11, Source / Python 3.12 and Package; watch exit 0 | 3.12: `========== 5964 passed, 56 skipped, 19 warnings in 141.19s (0:02:21) ===========`, `CI passed.` / 3.11: `================= 5964 passed, 56 skipped in 135.85s (0:02:15) =================`, `CI passed.` / Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, `CI passed.` |
| 10c | Remote, intermediate: CI 39162945987 and Static policy 39162947311 at 3600d47b | PASS, watch exit 0 for both | 3.11: `================= 5964 passed, 56 skipped in 136.17s (0:02:16) =================`, `CI passed.` / 3.12: `========== 5964 passed, 56 skipped, 19 warnings in 139.17s (0:02:19) ===========`, `CI passed.` / Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, `CI passed.` / Static policy: `Ran 1 rule on 977 files: 0 findings.` |

**Wheel check recipe.** The briefing's recipe worked unchanged:
1. Copy `s5-1/wheel-venv-1` to `s5-2/final/wheel-venv-3`.
2. Delete `Lib/site-packages/vidbyte` and `vidbyte_sdk-0.3.0.dist-info` in the copy.
3. `python -m zipfile -e s5-2/final/dist-3/vidbyte_sdk-0.3.0-py3-none-any.whl <copy>/Lib/site-packages/`.
4. Run the check with `-I` from `s5-2/final/wheel-run-3`.

A source check in that venv, `'**empty' in src and 'whole=whole' in src` on `ThreadChains._fit`, printed `True`. So the wheel under test holds bc351671's code.

**Processes.** Afterwards, `python s4-verifier/procs.py` printed `stand-in or grandchild processes: []`.

## 2. R-32: the blank check refused chain templates that hold `{prompt}`

**The defect.** The R-13 fix (9cbd47d6) refused chain templates that hold `{prompt}`, such as `{prompt}{previous}`. The message was "template must hold text besides its placeholders, or steps[1] can be sent a blank prompt…", which is false: the caller's prompt is checked non-blank before any step runs. `require_text` refuses `not value.strip()` unless `allow_blank` is set, and `chain_threads` calls it on `prompt` first. A developer's natural template, `"{prompt}\n\n{previous}"`, was refused. INV-5, INV-18 and EC-79 r5 all say such a template runs.

**Root cause.** `ThreadChains._fit` checks each later step's template twice:
- first with `{prompt}` rendered as `""`, naming `template`, so that a template too long by itself is blamed on the template;
- then with the caller's prompt, naming `prompt`.

`PromptFitter.check` ran the blank check on whichever frame it was given. In the first pass the only fixed text of `{prompt}{previous}` is `""`, so it refused. The traceback at 43bd0024 shows the frame `(PromptSegment(text='', spliced=False), PromptSegment(text='', spliced=True))`, raised at `texts.py:103` from `chain.py:132`.

**Reproduction before the fix.**
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose/test_harness_compose_validation.py -k holds_prompt` gave `2 failed, 98 deselected in 0.93s`, with the false message.
- The independent probe `s5-2/probe_r32.py` gave `PROBE R-32: 13/21 as the spec states` (`s5-2/probe-before.txt`). It runs only the up-front checks of `chain_threads` and `run_staged_threads` (`_steps`, `_template`, `_fit`) and never awaits a step, because grok and opencode are installed on this machine.
  - All 7 templates that hold `{prompt}` were refused as blank, `"{prompt}\n\n{previous}"` included.
  - A second effect the pack does not show: a 23,990-character prompt in `{prompt}{previous}` was refused as a blank `template`, not as a too-long `prompt`. So the false refusal also hid the true cause and named the wrong argument.

**The fix (dc631222).**
- `PromptFitter.check` gains a keyword-only `whole: Sequence[PromptSegment] | None = None`, the prompt the step receives. Only the blank check reads it: `(frame if whole is None else whole)`.
- The encoding and length checks still measure `frame`.
- `ThreadChains._fit` renders the template twice before its step loop: `alone`, with `{prompt}` as `""`, and `whole`, with the caller's prompt. Both have the answer and the diff spliced and empty.
- For each later step it calls `check(alone, …, argument=template, whole=whole)`, then `check(whole, …, argument=prompt)`.
- A truly blank template is still refused naming `template` and `steps[1]`. A template too long by itself is still blamed on `template`. A too-long prompt is blamed on `prompt`.
- No git call was added. `_gits` is untouched, so git still runs only for a template with `{diff}`.

**Evidence after the fix.**
- `-k holds_prompt`: `2 passed, 361 deselected in 1.02s`.
- `-k blank_without`, the five EC-79 refusals with their pinned fields and step names: `5 passed, 358 deselected`.
- `-k surrogate_in_caller`, the 27 EC-81 cases with their pinned fields: `27 passed, 336 deselected`.
- `s5-2/probe_r32.py`: `PROBE R-32: 21/21 as the spec states` (`s5-2/probe-after.txt`), at dc631222 and again at bc351671. That includes the long-prompt case, now `REFUSED field=prompt | prompt is too long for steps[1] …`.
- `s5-2/test_s52_natural_template.py` is a scratch test, not in the frozen tree, run with `-p tests.features.harness_compose.conftest`. It runs `"{prompt}\n\n{previous}"`, `"{previous}\n\n{prompt}"` and a labelled control end to end into a Grok, Muse or opencode second step. It asserts the exact prompt that step receives.
  - At bc351671: `9 passed`.
  - Against a `git archive` of 43bd0024: `6 failed, 3 passed`. The 3 that pass are the control, whose fixed text was never blank. So the check tells the two versions apart.
- Remote: at 3600d47b, CI 39162945987 ran the two R-32 cases on Ubuntu (git 2.55) and passed, with `5964 passed` on both source legs against the failing run's `5962 passed`.

## 3. Briefing item 2: the stale comments and docs at the same spot

Each change below is in dc631222 when the R-32 fix itself made the text wrong, and in 3600d47b otherwise. 3600d47b changes comments and docstrings only.

| Where | Before | After | Commit |
|---|---|---|---|
| `texts.py` comment in `check` (was :97–100) | "A template of placeholders alone gives a blank prompt …" (INV-18, EC-37) | A template blank once its spliced values are empty is refused. The caller's prompt stays in that form and is never blank, so a template that holds `{prompt}` is never refused (INV-18, EC-79). | dc631222 |
| `texts.py` `check` docstring, ARCHITECTURE NOTE, FUNCTION INVENTORY | did not say what the blank check reads | name `whole` and "the caller's prompt kept (EC-79)" | dc631222 |
| `chain.py:9` KNOWN EDGE CASES | "A template made only of placeholders is refused …" (EC-37), which is false after the fix | a template blank once the answer and the diff are empty, such as `{previous}` alone, is refused; `{prompt}` counts as the caller's prompt (EC-79) | dc631222 |
| `stages.py:9` KNOWN EDGE CASES | "… made only of {previous} …" (EC-37) | "… blank once the previous answer is empty, such as {previous} alone, …" (EC-79), which also covers whitespace around it | dc631222 |
| `chain.py` `_fit` comment | measured "first without the prompt" only | adds that the blank check reads the whole prompt (EC-79) | dc631222 |
| `texts.py` PURPOSE | "removes NULs and bound keys" | "removes NULs …, repairs their surrogate halves and replaces their bound keys, in that order" (INV-18, EC-80 r5) | 3600d47b |
| `texts.py` KNOWN EDGE CASES | omitted count "after NUL removal and key replacement" | "after NUL removal, surrogate repair and key replacement" | 3600d47b |
| `PromptFitter` docstring | "an up-front check of its longest form" | "of its shortest and longest forms" | 3600d47b |
| `fit` docstring and narration | NULs and keys only | NULs, surrogate halves, keys, in the code's order | 3600d47b |

`vidbyte/lib/dataclasses/native_compose.py:150` still cites EC-37 on purpose: it is about a NUL in a spliced value, which is EC-37.

## 4. Self-review fix (bc351671)

dc631222's two render lines in `_fit` each repeated the empty answer and diff. So a new spliced template value would have needed two entries in `_fit`. That made the `chain.py` header's COMMON MODIFICATION PATTERNS ("one entry in _values and in _fit") untrue. Both frames now take one annotated dict:

```python
empty: dict[ComposeField, str | tuple[PromptSegment, ...]] = {ComposeField.PREVIOUS: ComposeTexts.spliced(""), ComposeField.DIFF: ComposeTexts.spliced("")}
alone = ComposeTexts.render(template, {ComposeField.PROMPT: "", **empty})
whole = ComposeTexts.render(template, {ComposeField.PROMPT: prompt, **empty})
```

This is written as `ensemble.py:178` writes its values dict. The behaviour is unchanged. The full gate was re-run from the top at bc351671 (section 1).

## 5. Decision record: why an optional `whole` on `check`

All options were weighed before any code was written. None was coded and then dropped.

1. **Chosen: `whole` on `PromptFitter.check`.**
   - It keeps the blank check inside `check`, where spec r5 puts it. Row 13 says "`PromptFitter.check` is the up-front check: it refuses a blank shortest form (`COMPOSE_BLANK_PROMPT`, EC-79)", and the §5 list says the same.
   - The refusal still names `template` (EC-79), and every other caller is unchanged.
   - It is the strict-config field guide's shape: "When an option is missing …, add it as a keyword with a backward-compatible default."
   - Cost: the keyword has one caller, `ThreadChains._fit`. A stage template cannot hold `{prompt}`, so stages never need it.
2. **Runner-up: a separate `PromptFitter` method for the blank check, called from the chain and stages `_fit`.**
   - It needs no keyword.
   - But it contradicts row 13 and §5, so the spec author would have to edit them, and this iteration may not edit the spec.
   - It also moves R-13's code across three files.
   - **Flip condition:** the reviewer rules that a one-caller keyword costs more than that spec edit.
3. **Rejected: the blank check in the prompt pass.** Its refusal names `prompt`, which breaks EC-79 and the five pinned refusals.
4. **Rejected: render the template pass with the caller's prompt and still blame `template`.**
   - A too-long caller prompt would then be blamed on `template`.
   - That breaks the AC-14 case "prompt too long for a later grok step" (field `prompt`) and INV-18's "naming the argument that makes it too long".
5. **Rejected: render `{prompt}` as a spliced segment in the template pass.**
   - The blank check reads only fixed segments, so it still refuses.
   - The length check would count the prompt as a truncation note.

**Pre-mortem of the chosen fix.**
- Could any other caller of `check` hit the same trap? No. Its other callers are answers.py:65–68, ensemble.py:191–194, selection.py:120 and verify.py:139–141, and each of their frames holds a prompt file's text or the caller's prompt. So none can be blank, as INV-18 r5 says ("Only a template can make the shortest form blank").
- The second `check` call per later step, on `whole`, repeats the blank check, which cannot fire there. It costs one string join.

## 6. Test changes proposed

None. The test tree is unchanged since d9cc9ff6.

## 7. Confirmed findings I believe are wrong

None. R-32 is a defect, as ruled. Its row is in review.md's confirmed table, after R-15, the last repairable Major, with status `fixed @dc631222 (comments @3600d47b)`. The heading count is now 18, and the tier sentence names R-32's origin.

## 8. What remains open

- No confirmed finding is open. The follow-ups R-24 to R-31 stay outside this loop.
- **For the conformance re-review:**
  - The one judgement call in this iteration is the one-caller `whole` keyword (section 5).
  - The spec needs no edit for R-32. Row 13, §5 and INV-18 describe the code as it now is, and no spec text pins `check`'s signature.
- **For S6:** the PR can say that `chain_threads` accepts any template that holds `{prompt}` and `{previous}`, such as `"{prompt}\n\n{previous}"`, and refuses only templates that are blank once the answer and the diff are empty (EC-79).

## 9. Notes for a next iteration, if there is one

- **Line endings.** Git Bash's `grep -c $'\r$'` misreports line endings in this worktree. It showed CRLF for LF files and 0 for a CRLF file. Count bytes with Python instead.
  - The compose sources and verify-log.md are LF in the working tree; review.md is CRLF.
  - `s5-2/apply_edits.py <checkout> <edits.py>` applies exact edits, keeps each file's own ending, and refuses any edit whose old text does not occur exactly once.
- **The probe is safe on this machine.** `s5-2/probe_r32.py` runs only up-front checks, never a step. Use it to test a change to prompt fit without launching grok or opencode.
- **Before/after runs need no stash.** `git archive <rev> vidbyte tests pyproject.toml` unpacked in scratch, with `PYTHONPATH` set to that folder and `-p tests.features.harness_compose.conftest`, runs any scratch test against an older revision.
- **If a reviewer rejects the `whole` keyword,** take section 5's runner-up and route the row 13 and §5 edit to the spec author.
