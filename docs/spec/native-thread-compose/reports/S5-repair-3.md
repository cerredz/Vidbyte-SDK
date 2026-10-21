STAGE: S5 repair, iteration 3 of 8
FINDING: R-33 (Blocker), fixed @0e4321a4; spec record @7aad13ba
HEAD: see the STATUS block (records commit on top of 7aad13ba)
STATUS: DONE

Paths used below:
- `$W` is the worktree root, `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`.
- `$S` is the session scratch folder, `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad`.
- `$S/s5-3` is this iteration's folder. Gate outputs are in `$S/s5-3/final/`, and probe outputs are in `$S/s5-3/probes/`.

## 1. Gate matrix

Gates 1 to 9 ran at 7aad13ba, whose code is 0e4321a4. Every one ran in this worktree in this iteration. 7aad13ba changes only spec.md.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| 1 lint | `python lint/run.py` | PASS. The count table is identical to iteration 2's (`diff` of the rule rows is empty), with S009 at 350/350. | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline`<br>`S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`<br>`SDK-LINT: PASS` |
| 2 ratchets | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`; `python -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache` | PASS (223 / 5) | `Found 223 errors.`<br>``[*] 223 fixable with the `--fix` option.``<br>`Found 5 errors.` |
| 3 semgrep | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`; `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS (exit 0 for both) | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` |
| 4 new tests | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` | PASS (21 failed at ad6ec58e) | `385 passed in 55.26s` |
| 5 base pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` | PASS | `436 passed, 2 skipped in 45.46s` |
| 6 source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS. That is iteration 2's 6004 plus the 22 R-33 cases; the MCP flake did not occur. | `================ 6026 passed, 16 skipped in 156.80s (0:02:36) =================`<br>`CI passed.` |
| 7 package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package --dist-dir $S/s5-3/final/dist-4` | PASS | `No broken requirements found.`<br>`Installed vidbyte-sdk 0.3.0 passed smoke checks.`<br>`CI passed.` |
| 8 AC-21 wheel half | the briefing's copy recipe: `wheel-venv-4` is a copy of `s5-1/wheel-venv-1` holding the dist-4 wheel. The command is `wheel-venv-4/Scripts/python.exe -I $S/s3/check_wheel_prompts.py $W`, run from `$S/s5-3/final/wheel-run-4` | PASS | `installed vidbyte: ...\s5-3\final\wheel-venv-4\Lib\site-packages\vidbyte\__init__.py (outside the checkout: True)`<br>`fixed combinations: 17, longest planner = 8304 chars, over 12000: {}`<br>`AC-21 WHEEL HALF: PASS` |
| 9 comment width | `awk 'length($0) > 72' <file> \| grep -E '^[[:space:]]*#'` on each changed `.py` file | PASS | `over72=0` for steps.py, native_compose.py, native_ensemble.py and validation.py |
| frozen tests | `git diff 1d7bfbec..HEAD --stat -- tests` | PASS | empty |
| scope | `git diff --stat 0fda73fb..HEAD -- vidbyte/lib/dataclasses/native_threads.py vidbyte/lib/dataclasses/process.py lint .semgrep .github scripts pyproject.toml docs/spec/native-thread-compose/request.md docs/spec/native-thread-compose/test-plan.md` | PASS | empty |
| 10 remote: Static policy | `gh workflow run static-policy.yml --ref feat/native-thread-compose`, run 39372992819 at 7aad13ba | PASS; watch exit 0 | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` |
| 10 remote: CI | `gh workflow run ci.yml --ref feat/native-thread-compose`, run 39372990529 at 7aad13ba | PASS: Source / Python 3.11, Source / Python 3.12 and Package; watch exit 0 | 3.11: `================= 5986 passed, 56 skipped in 109.14s (0:01:49) =================`, then `CI passed.`<br>3.12: `========== 5986 passed, 56 skipped, 19 warnings in 113.19s (0:01:53) ===========`, then `CI passed.`<br>Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, then `CI passed.` |

`python $S/s4-verifier/procs.py --kill` after the process-starting runs: `stand-in or grandchild processes: []`.

## 2. R-33: what I did, with evidence

### 2.1 Reproduction

At ad6ec58e, before any change, `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose/test_harness_compose_keys.py` gave `21 failed, 26 passed in 7.88s`. All 21 were the test author's R-33 rows: 18 `test_a_record_refusal_never_quotes_the_key_it_was_given` cases and 3 `test_an_answer_member_refusal_never_quotes_the_key_in_its_problem` cases. Each failed on its INV-4 assertion, for example `AssertionError: INV-4: the verify_with verdict decision problem quotes the key: "ThreadVerdict.decision must be one of approve, reject; got 'vbk-6c6dd1f1c36b'."`. This is the briefing's red run exactly.

### 2.2 Root cause

The root cause has two parts.

- **The validators.** `RecordFieldValidator._received` (validation.py) quotes a short, non-secret str, and compose's records called `to_enum`, `require_int` and `require_bool`, which had no way to turn the quote off. They also called `require_text` without `quote=False` for `EnsembleRole.name`.
- **The probe.** `ThreadStep.__post_init__` builds the base `NativeThreadRequest` as a probe, and that record quotes a short bad `model` or `thread_id`. Only the two binders rewrote that refusal (`ThreadBinder._withheld`). A step built directly or through `dataclasses.replace` never passed through them.

### 2.3 What changed (0e4321a4)

The fix touches 4 files, adds 72 lines and removes 66. It adds no file, no class and no dependency, so §8.4 holds.

1. **`vidbyte/lib/dataclasses/validation.py`.** `require_int(..., quote: bool = True)`, `require_bool(..., *, quote: bool = True)` and `to_enum(..., *, quote: bool = True)` pass `quote` on to `_received`, in the shape grant (c) gave `require_text`.
   - Each default keeps the old behaviour, so the 11 base calls are untouched: `native_threads.py:86, :87, :168, :169, :204, :222, :225` and `process.py:66, :88, :89, :90`. No base message changes (NG-1).
   - The header ARCHITECTURE NOTE, FUNCTION INVENTORY and KNOWN EDGE CASES say so, with the §7.6 wording. Each method's comment gains "With quote False a refusal names the value by its type only", as `require_text`'s comment already says.
2. **`vidbyte/lib/dataclasses/native_compose.py`.**
   - `quote=False` at `ThreadStep.harness` and `.verb`, `PromptSegment.spliced` (for uniformity), `WorkspaceDiff.truncated`, `ThreadVerdict.decision`, `StageSpec.retries`, and `StageAttempt.rung` and `.decision`.
   - `ThreadStep` now owns the model and thread-id rewrite, so the binder, direct and `dataclasses.replace` entries share one rule. The narrated probe step reads:
     ```python
     probe = self._probe()
     if isinstance(probe, ConfigurationError):
         raise self._withheld(probe)
     ```
   - `_probe` returns the `NativeThreadRequest`, or the `ConfigurationError` it raised, from inside its handler. The raise happens in `__post_init__`, outside any handler, so neither `__context__` nor `__cause__` holds the quoted original.
   - `_withheld` carries `# @intent step-refusals-withhold-a-misplaced-key`. It picks the value by the field the refusal names: `{"model": self.model, "thread_id": self.thread_id}.get(error.details.get("field", ""))`. It rebuilds the message with `COMPOSE_WITHHELD_VALUE` and the same `details`. Any other refusal is returned unchanged and raised as the same object.
   - Neither helper calls a sibling (AGENTS.md principle 1). `COMPOSE_WITHHELD_VALUE` joins the constants import right after `COMPOSE_VERDICT_MAX_FINDINGS`, the I001 position the verifier proved.
   - The header FUNCTION INVENTORY names `_probe` and `_withheld`. KNOWN EDGE CASES gains the §7.6 sentence, extended to "a caller or a step's answer".
3. **`vidbyte/lib/dataclasses/native_ensemble.py`.** `quote=False` at `EnsembleRole.name`, through the existing `require_text` keyword, and at `EnsembleSelection.proposal`.
   - One KNOWN EDGE CASES sentence says why: a step's answer can echo a key into either field, and the refusal is kept as that answer's problem. Without it, a later reader could "simplify" the keyword away.
4. **`vidbyte/harnesses/native/compose/steps.py`.**
   - Each binder is a plain `return ThreadStep(...)`, and `ThreadBinder._withheld` is deleted.
   - Header line 6 loses the `_withheld` clause, and line 9 now reads "ThreadStep names a refused model or thread id by its type only, so the binders pass its refusal on unchanged (INV-4)."
   - The `quote=False` thread-id pre-check in `bind_continue` stays, because it is what makes a fork bound there anchored.

### 2.4 Hypotheses, including the ones that failed

- **The reference fix as written leaves a key in a refusal. I found this, proved it and did not use it.**
  - The verifier's `_withheld` scans `(self.model, self.thread_id)` and rewrites the first repr found in the message. That fails when one value's repr sits inside the other's quote.
  - The test case is an accepted grok model `"grok-4"` with a refused `thread_id="<key> 'grok-4'"`. The thread id's repr is double-quoted and contains `'grok-4'`.
  - The scan rewrites only the model's repr and leaves the key. `$S/s5-3/probes/probe_withheld_exact.py`, run with `PYTHONPATH=$S/s5-verifier-rr1/lint_patched` (the verifier's proof copy), prints:
    - `direct grok continue, model accepted, thread_id holds key and quoted model: field=thread_id key-shown=True context=None cause=None | 'thread_id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; got "vbk-7c3a91e0d24f a value of type str".'`
    - the same line for `replace() of a bound continue step`.
  - On this tree, all 8 cases of that probe print `key-shown=False context=None cause=None`. Those are the two above, a model holding a key and a quoted word, both binders, the `bind_continue` pre-check, a relative workspace (nothing to withhold) and a model too long to be quoted.
  - `$S/s5-3/probes/probe_scan_order.py` shows the same thing at the base-record level, comparing the scan with the field-keyed rewrite side by side.
  - The input is contrived. I closed it anyway, because re-review round 2 is the last one and the brief is to close the class by construction.
- **Choosing by field is exact.** `_received` quotes exactly the value of the field the refusal names, and the quote ends the message, so `rpartition(repr(value))` removes all of it.
  - The verifier called this variant "tighter, but it ties the record to the base's field names". The tie is guarded: a base rename of `details["field"]` turns the six model and thread-id record rows red on their field assertion.
  - Runner-up: a scan with the longest repr first, which is also exact. The flip condition: switch if the base ever quotes a value other than the one its field names.
- **The first field-keyed version failed lint (S009), and the fix was a default.**
  - `python lint/run.py` printed `S009 REGRESSED: 351 finding(s), allowance 350`. S009 runs `python -m mypy --config-file lint/mypy.ini vidbyte` over the whole package.
  - The new finding was `vidbyte\lib\dataclasses\native_compose.py:147:72: error: Argument 1 to "get" of "dict" has incompatible type "Any | None"; expected "str"  [arg-type]`.
  - I fixed it with a default, `error.details.get("field", "")`, which behaves the same way: no field means nothing is withheld. No `Any`, no ignore and no baseline change. S009 is back at 350, and the whole count table matches iteration 2's.
- **Considered and not coded:**
  - `raise ... from None` inside the handler. Known-failed: it still sets `__context__`, and the rows walk it.
  - A deferred raise after an inline handler. It works, but it puts a handler and a sentinel into the narrated main function.
  - Pre-checking the model and thread id in `ThreadStep` with `quote=False`. That duplicates the base's per-harness rules, and `require_optional_text` has no `quote` keyword, so it is outside the grant.
  - Flipping `_received` SDK-wide (NG-1).
- **A trade-off, recorded.** `quote=False` hides every refused value, not only a str. `StageSpec(retries=4)` now ends `got a value of type int.` where it used to end `got 4.`.
  - The bound stays in the message, and no test pins the old text: the pack and the base pack are green.
  - The flip condition: if reviewers want ints quoted, `_received` should withhold only a str under `quote=False`. That belongs to the SDK-wide `_received` move.

### 2.5 Evidence beyond the frozen pack (this tree, after 0e4321a4)

| Probe (from `$W`, `PYTHONPATH=$(pwd)`) | Output |
|---|---|
| `$S/s5-verifier-rr1/probe_sweep.py` (183 entries, 16-, 49- and 70-character keys, bare or with NUL, " x" or "\n") | `TOTAL (entry, record, field) pairs: 183; leaking: 4; clean: 179`. The 4 are the stdlib `VerdictDecision`, `StageDecision`, `EnsembleStage` and `ThreadComposeProblem` `(value)` constructors: out of scope, verifier §5 item 4. This is the same result as the proof copy. |
| `$S/s5-verifier-rr1/ctx_count.py $S/s5-verifier-rr1` | `1796 ('clean', 'None')`, `352 ('ACCEPTED', '-')`, `4 ('OTHER-LEAK', '-')`. No refusal quotes the key, and none has a `__context__`. |
| `$S/s5-verifier-rr1/probe_answers.py` | `key-in-problem=False` for all 4 answers. The problem still names the field, e.g. `'ThreadVerdict.decision must be one of approve, reject; got a value of type str.'` (EC-28). |
| `$S/s5-rereview-1/probe_keys_direct.py`, `probe_keys_direct_msg.py`, `probe_keys_direct2.py`, `probe_keys_records.py` | `key-in-message=False` on every refused line. The bare grok model is `ACCEPTED`, which is out-of-scope item 7. |
| `python -m pytest -q -p no:cacheprovider -p tests.features.harness_compose.conftest $S/s5-verifier-rr1/test_s5v_rr1_record_keys.py` | `18 passed in 29.17s` |
| `$S/s5-3/probes/probe_withheld_exact.py $W` | 8 of 8 `key-shown=False context=None cause=None`. On the proof copy, 2 of 8 are `key-shown=True` (section 2.4). |

Before and after on the frozen pack: `21 failed, 26 passed` at ad6ec58e, and `47 passed in 4.98s` after the fix. The whole compose pack gives `385 passed`. The "gets right" list holds:
- the 21 caller-text cases, the binder model cases included, are green and now read every error surface;
- the `kept` guard is green;
- AC-14's 58 cases and the binding tests are green.

### 2.6 The spec record edits (7aad13ba)

These are the five lines the briefing authorized, and no others. spec.md stays CRLF (1627 CRLF, 1627 LF, 1627 CR before and after), and only lines 731, 1103, 1308, 1588 and 1626 differ.

- **:731.** Before: "S5 grant (c) adds two keywords whose defaults keep every existing caller unchanged: `min_items` on `RecordFieldConverter.to_tuple` and `quote` on `RecordFieldValidator.require_text` (§17)." After: "S5 grant (c) adds five keywords whose defaults keep every existing caller unchanged: `min_items` on `RecordFieldConverter.to_tuple` and `quote` on `RecordFieldValidator.require_text`, `RecordFieldValidator.require_int`, `RecordFieldValidator.require_bool` and `RecordFieldConverter.to_enum` (§17)."
- **:1103.** Before: "- two keywords whose defaults keep every existing caller unchanged, `quote` on `RecordFieldValidator.require_text` and `min_items` on `RecordFieldConverter.to_tuple` (S5 grant (c));" After: "- five keywords whose defaults keep every existing caller unchanged, `quote` on `RecordFieldValidator.require_text`, `RecordFieldValidator.require_int`, `RecordFieldValidator.require_bool` and `RecordFieldConverter.to_enum`, and `min_items` on `RecordFieldConverter.to_tuple` (S5 grant (c));"
- **:1308, §12.3 row 4 cell.** Before: "S5 grant (c) (§17) also adds two keywords whose defaults keep every existing caller unchanged: `quote` on `RecordFieldValidator.require_text` and `min_items` on `RecordFieldConverter.to_tuple`". After: "S5 grant (c) (§17) also adds five keywords whose defaults keep every existing caller unchanged: `quote` on `RecordFieldValidator.require_text`, `RecordFieldValidator.require_int`, `RecordFieldValidator.require_bool` and `RecordFieldConverter.to_enum`, and `min_items` on `RecordFieldConverter.to_tuple`".
- **:1588.** Before: "`ThreadBinder._derived` (R-15) and `_withheld` (R-3);" After: "`ThreadBinder._derived` (R-15); `ThreadStep._probe` and `_withheld` (R-3, R-33);"
- **:1626, §17 grant (c).**
  - Before: "  - Grant (c), R-7 and R-3. `RecordFieldConverter.to_tuple` gains `min_items`, which replaces `StepRoles.counted` and `COMPOSE_COUNT_RULE`. `RecordFieldValidator.require_text` gains `quote`: compose passes `quote=False` for caller text and for each `WorkspaceDiff.files` name, and the binders raise the record's model refusal again with the model named by its type only. Both keywords default to the old behaviour."
  - After: "  - Grant (c), R-7, R-3 and R-33. `RecordFieldConverter.to_tuple` gains `min_items`, which replaces `StepRoles.counted` and `COMPOSE_COUNT_RULE`. `RecordFieldValidator.require_text` gains `quote`, and so do `RecordFieldValidator.require_int`, `RecordFieldValidator.require_bool` and `RecordFieldConverter.to_enum` (R-33): compose passes `quote=False` for caller text, for each `WorkspaceDiff.files` name and for every record field whose refusal could quote a str (R-33), and `ThreadStep` raises the probe's model or thread-id refusal again with the value named by its type only, outside any handler, for the binder, direct and `dataclasses.replace` paths (R-3, R-33). All five keywords default to the old behaviour."
  - One wording choice goes slightly past the literal brief: the row's lead names R-33 beside R-7 and R-3, because the row now records that grant too.

## 3. Test changes proposed

None. The test tree is unchanged since 1d7bfbec (`git diff 1d7bfbec..HEAD --stat -- tests` is empty).

## 4. Findings I believe are wrong

None. R-33 is right as filed. My one departure is from the reference fix, not from the finding: `_withheld` picks the value by the refusal's field instead of scanning for each value, because the scan leaves a key in the case shown in section 2.4.

## 5. What remains open, and what I would try next

Nothing is open. R-33 is fixed, and every gate in section 1 is green: locally at 7aad13ba, and remotely at 7aad13ba (CI 39372990529 and Static policy 39372992819, both watch exit 0). The test tree is unchanged, and no confirmed finding is open. The follow-ups R-24 to R-31 and the verifier's out-of-scope items are outside this loop by ruling.

Watch items for re-review round 2. None of them is a defect I know of.
- The only `ConfigurationError` text compose's own records can still show from a misplaced key is the stdlib `Enum(value)` `ValueError`. It is not a `ConfigurationError`, compose never calls it on input, and it is out of scope (§5 item 4).
- A key that validation accepts, such as a bare key as a grok or muse model or as a thread id, is not a refusal. It is the follow-up the orchestrator ruled out of scope (§5 item 7).
- Base refusals stay as they were (NG-1, R-29).

The larger move this opens: now that `require_int`, `require_bool` and `to_enum` take `quote`, a separate PR can make `_received` never quote a str SDK-wide. It would audit the base tests that read `got '…'` first. That closes R-29's base refusals, and the base config records' `to_enum` and `require_*` refusals, for every record in the SDK. That PR is also where to decide whether `quote=False` should still quote non-str values (section 2.4, trade-off).
