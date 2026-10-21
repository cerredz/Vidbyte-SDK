STAGE: S5 findings verifier (re-review round 1, scoped to R-RC1)
VERDICT: R-RC1 CONFIRMED, Blocker. Recorded in review.md as R-33 (status `open`), with the verifier's class sweep folded in.
HEAD: `5122dce2` (code identical to `b95e11c1`). This stage made no commits and edited only review.md and this report.

Paths used below:
- `$W` is the worktree root, `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`.
- `$V` is this stage's scratch folder, `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s5-verifier-rr1`.
- `$R` is the re-review's sibling folder `s5-rereview-1`, and `$S` is the sibling `s4-verifier`.

## 1. The finding as filed

R-RC1 (reports/S5-rereview-1-conformance.md:39-82) says this. A `ThreadStep` that a caller builds directly or through `dataclasses.replace`, and `StageSpec.retries`, quote a misplaced short key in compose's own `ConfigurationError`. R-3's repair (4b153b94) hid the value only in the binders, through `ThreadBinder._withheld` (steps.py:75-81, :89-95, :155-166).

## 2. Spec basis (decided on the spec's own words)

- request.md:166, §D Weighted words, ledger 3: "The key is still passed only to the nine functions and still never reaches argv, files, `os.environ`, error messages or logs."
- spec.md:249-255, INV-4: "It never appears in any text compose itself produces: … any `ConfigurationError` compose raises;"
- spec.md:269, INV-5: "A refusal is a `ConfigurationError` whose `details["field"]` names the argument path and whose message never quotes a key."
- spec.md:496, AC-15: "No key appears in: … any `ConfigurationError` message;"
- spec.md:1488, §14 Never: "Put a key in argv, a file, `os.environ`, an error, a log or a `repr` …"
- spec.md:589, EC-78: a `ThreadStep` "built directly instead of through a binder", or changed "with `dataclasses.replace`", is a supported input.
- spec.md:213, INV-1: the 42 names of `compose.__all__`. They include 18 records, so every record is a public constructor.
- spec.md:94, NG-1: the nine functions, `NativeThreadRequest`, the three config records and the rest of the base stay unchanged.
- spec.md:1626, §17 grant (c): "the binders raise the record's model refusal again with the model named by its type only". The repair agent wrote this sentence to record what it built. It is not an owner decision that narrows INV-4, and nothing in the spec exempts a misplaced key.

Decision: "never" in ledger 3 is a §D weighted word. INV-4 names exactly this kind of error, a `ConfigurationError` that compose raises, and none of the clauses has a carve-out for a key in the wrong field.

The orchestrator already ruled R-3's binder model refusal in scope. That is the same key, the same mistake and the same `_received` mechanism, reached through a different supported entry, so it must hold here too.

Defences considered:
- The key has to be misplaced. R-3 had the same character.
- Some misplaced keys are accepted rather than refused. That is a different class (section 5, item 7).
- No test pins the wording. That shows the gap rather than a permission.

Severity: Blocker.

## 3. Reproduction

### 3.1 The reviewer's probes, re-run at HEAD from `$W`

- `PYTHONPATH=$(pwd) python $R/probe_keys_direct.py` prints:
  - `ThreadStep() opencode model: ConfigurationError key-in-message=True key-in-details=False field=model`
  - `ThreadStep() continue thread_id: ConfigurationError key-in-message=True key-in-details=False field=thread_id`
  - the binder lines, which stay `key-in-message=False`
- `PYTHONPATH=$(pwd) python $R/probe_keys_direct_msg.py` prints:
  - `"model must match ^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9]\S*$; got 'vbk-probe7a1c0e2f'."`
  - `"thread_id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; got 'vbk-probe7a1c0e2f\x00'."`
  - `"... got 'vbk-probe7a1c0e2f x'."`
- `PYTHONPATH=$(pwd) python $R/probe_keys_direct2.py` prints `key-in-message=True` for `harness`, `verb` and `dataclasses.replace(bound opencode step, model=key)`.
- `PYTHONPATH=$(pwd) python $R/probe_keys_records.py` prints `StageSpec(step, template, retries=key) [3rd positional]: key-in-message=True | "StageSpec.retries must be an integer from 0 to 3; got 'vbk-probe7a1c0e2f'."`.

### 3.2 The verifier's own test: one row per site

The test is `$V/test_s5v_rr1_record_keys.py`. Each row puts the pack's `short_key()` shape (16 characters) into one field. It then asserts three things:
- `details["field"]` names that field;
- no 12-character fragment of the key appears in the message, the args, `vars()`, or anywhere in the `__context__`/`__cause__` chain;
- `sandbox.launches() == []`.

`PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -p tests.features.harness_compose.conftest "$V/test_s5v_rr1_record_keys.py"` gives `18 failed in 14.42s` at HEAD. The quoted messages are kept in `$V/red_at_head.txt`. Examples:
- `ThreadStep.harness must be one of grok, opencode, muse; got 'vbk-835e5b6db7bf'.`
- `ThreadStep.verb must be one of run, continue, fork; got 'vbk-9273c6b54435'.`
- `model must match ^[A-Za-z0-9]\S*$; got 'vbk-ad7294688d43\n'.` This is a grok step whose model ends in a newline.
- `thread_id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; got 'vbk-350bffaccd90 x'.` This is an opencode fork step.
- `StageSpec.retries must be an integer from 0 to 3; got 'vbk-864ce19c744d'.` This is the `dataclasses.replace` path.
- `ThreadVerdict.decision must be one of approve, reject; got 'vbk-3503857e8df9'.`
- `StageAttempt.rung must be an integer from 0 to 4; got 'vbk-17361cedb90b'.`
- `StageAttempt.decision must be one of retry, raise_effort, abort; got 'vbk-45a5caa371c0'.`
- `EnsembleSelection.proposal must be an integer from 1 to 10; got 'vbk-775ce3f98b8e'.`
- `EnsembleRole.name must match [^\x00]+; got 'vbk-35d5a570e67a\x00'.`
- `WorkspaceDiff.truncated must be True or False; got 'vbk-96f953449db5'.`

### 3.3 A step's answer reaches three of the sites with no caller mistake

`PYTHONPATH=$(pwd) python "$V/probe_answers.py"` passes a step's JSON answer through `AnswerDecoders.read`, using the composites' own decoders. In each answer, one member holds a short key. At HEAD it prints:
- `ANSWER verdict decision: key-in-problem=True problem="ThreadVerdict.decision must be one of approve, reject; got '<KEY>'."`
- `ANSWER selection proposal: key-in-problem=True problem="EnsembleSelection.proposal must be an integer from 1 to 10; got '<KEY>'."`
- `ANSWER plan role name (NUL): key-in-problem=True problem="EnsembleRole.name must match [^\\x00]+; got '<KEY>\\x00'."`
- `ANSWER round kept: key-in-problem=False`, because `to_tuple` names only the type.

The repair prompt scrubs keys at send time. `JsonAnswer.problem`, however, keeps the raw problem by design (answers.py:9). So compose's own refusal text, with the key in it, lands in a returned record. Any step whose answer echoes a key into one of these members reaches this path, and AC-15's stand-ins already echo keys into their answers.

## 4. Class sweep

### 4.1 Method

The sweep is `$V/probe_sweep.py`, run from a tree root with `PYTHONPATH=$(pwd)`. It starts no process. It builds every record in `compose.__all__` (18 records) plus the compose-owned `PromptSegment` from a valid baseline, then puts a key into one field at a time.

- Keys: 16 characters (the pack's `short_key` shape), 49 characters (Zhipu-shaped, `hex32.hex16`) and 70 characters (repr 72, inside the 80-character quote limit). Each is used bare and with a NUL, `" x"` or `"\n"` appended.
- Entries:
  - direct construction, with every harness and verb shape of `ThreadStep`;
  - `dataclasses.replace` on bound grok run, opencode run and grok continue steps, and on a `StageSpec`;
  - both binders, on every argument;
  - the three derived-step helpers `ThreadBinder.anchor`, `relocate` and `rung`;
  - the standard-library constructors of compose's 4 enums.
- Leak check: a leak means a 12-character fragment of the key appears in `str()`, `args`, `details` or `__dict__` of the error or of anything reachable through `__context__` and `__cause__`.

### 4.2 Results

| Tree | Entries | Leaking entries | Attempts that raised `ConfigurationError` | Their `__context__` |
|---|---|---|---|---|
| HEAD `5122dce2` | 183 | 44: 40 record entries plus 4 stdlib `Enum(value)` | 1,796: 430 quote the key, 1,366 do not | None on all 1,796 |
| Proof copy (section 7) | 183 | 4: the stdlib `Enum(value)` only | 1,796, none quoting the key | None on all 1,796 |

In both trees, 352 attempts were accepted (no refusal). `$V/ctx_count.py` produced the context counts.

Collapsed to (record, field), the sweep finds **64 pairs. 12 quote a short key at HEAD and 52 never do.** The 8 binder pairs and the 3 derived-path pairs are clean. On the proof copy, none of the 64 pairs quote a key. The full side-by-side table is `$V/sweep_table.txt`.

| Record (public?) | Fields that quote at HEAD, and the validator that quotes | Fields that never quote |
|---|---|---|
| ThreadStep (yes) | `harness` and `verb`, through `to_enum` (:96-97). `model`, through the probe `NativeThreadRequest`: `native_threads.py:127` (opencode, needs `/`) and `:129` (grok and muse, refuses whitespace). `thread_id`, through the probe at `native_threads.py:136`: NUL, space, newline or a dot is refused, but a bare `vbk-…` passes. Each quotes both directly and through `replace`. | `function` and `invoker` (the callable check names the type). `api_key` (a credential field name is never quoted). `workspace` (`to_path`, `require_directory`). `skills` (paths). `config` (`require_instance`). |
| StageSpec (yes) | `retries`, through `require_int` (:325), both directly and through `replace` | `step`, `template` (`require_template` names only), `ladder` |
| StageAttempt (yes) | `rung`, through `require_int` (:338), and `decision`, through `to_enum` (:341) | `outcome` |
| ThreadVerdict (yes) | `decision`, through `to_enum` (:243) | `summary`, `findings` (free text, cap 100,000) |
| WorkspaceDiff (yes) | `truncated`, through `require_bool` (:169) | `files` (already `quote=False`), `text` |
| EnsembleRole (yes) | `name`, through `require_text` with `[^\x00]+` and cap 64 (native_ensemble.py:70): a NUL, or more than 64 characters | `identity`, `personality`, `expertise`, `knowledge`, `skills`, `goal` |
| EnsembleSelection (yes) | `proposal`, through `require_int` (native_ensemble.py:123) | `approach`, `rationale`, `guidance` |
| PromptSegment (no, internal) | `spliced`, through `require_bool` (:152). Compose only ever passes a literal bool (texts.py:55, 59, 65, 70, 78, 138), so this one matters only for uniformity. | `text` |
| ChainResult, VerifyResult, HandoffResult, StagedResult, StageOutcome, StepOutcome, JsonAnswer, EnsemblePlan, EnsembleRound, EnsembleRoster, EnsembleResult (yes) | none | all 28 fields |

Why the clean fields are clean: a field can quote a key only if its check can refuse a short, non-blank str. Several kinds of check never do that:
- Checks that name only the type or a count: `require_instance`, `to_tuple`, `to_mapping`, `to_path`, `require_directory`, `require_template`, `require_command_line_units`.
- Free text with a cap of 2,000 or more and no pattern, which never refuses a short non-blank str.
- `api_key`, whose credential-like name `_received` never quotes.

The binders are clean because of R-3:
- `ThreadBinder._withheld` rewrites a quoted model.
- `bind_continue` checks its thread id first with `quote=False` (steps.py:88).

The derived paths are clean for their own reasons:
- `anchor` checks the thread id with `quote=False`.
- `relocate` uses `to_path` and `require_directory`.
- `rung` uses `require_instance`.
- `_derived` builds through `object.__new__` and never re-runs `__post_init__`.

## 5. Out of scope

Each of these was examined and left out of R-33 on purpose.

1. **The base functions' own refusals** (R-29, NG-1). For example, calling `run_opencode_thread(model=key)` directly quotes the key from `NativeThreadRequest`. Compose does not raise that error, and NG-1 freezes the record.
2. **The three base config records** that a caller builds (NG-1). `GrokThreadConfig.reasoning_effort` and `.permission_mode` and `MuseThreadConfig.reasoning_effort` go through `to_enum` (native_threads.py:168, :169, :204), every `timeout_seconds` goes through `require_number`, and `OpencodeThreadConfig.agent` and `.variant` and `MuseThreadConfig.wsl_distro` and `.muse_path` go through the patterned text validators. All of them quote a short str. Once `to_enum` gains `quote`, a later PR could pass `quote=False` there.
3. **`api_key` itself.** Its name is credential-like, so it is never quoted: `api_key must match ^[!-z|~]+$; got a value of type str.` (re-review inline probe, `ctx=None`).
4. **The standard library's `Enum(value)` `ValueError`** for `VerdictDecision`, `StageDecision`, `EnsembleStage` and `ThreadComposeProblem` (`"'vbk-…' is not a valid VerdictDecision"`). This is not a `ConfigurationError` and not compose code. Compose never calls these constructors on input: the only enum call in compose is `ComposeField(name)` at texts.py:58, on template names that `require_template` has already checked.
5. **`ThreadComposeError`.** It does no validation, and `ComposeFailures.error` scrubs keys from it (grant (b)).
6. **The skill folder-name quote** (native_threads.py:150). It is base code, and it needs a folder that the caller created, named like a key and holding `SKILL.md`.
7. **A misplaced key that validation accepts.** Examples are a bare key as a grok or muse `model` (`^[A-Za-z0-9]\S*$` accepts it, NUL included) and a bare key as a `thread_id`. These are not refusals, so this class is not R-RC1. Such a key shows in `repr(ThreadStep)` through `model` or `thread_id`, and it reaches the base's argv. Compose cannot tell a key from a model id. INV-4's repr bullet is satisfied as written ("`ThreadStep.api_key` is `field(repr=False)`"). A `model != api_key` check would add scope, so it is a possible follow-up for the orchestrator, not part of this fix.
8. **The raw `JsonAnswer.problem`** keeps a decoder's own `ValueError` text, such as an extra member name the model chose (answers.py:9). That text is the step's own answer text, already raw in `turns` (EC-71). After the fix, only the record refusals inside it stop quoting.

## 6. Classification

**CONFIRMED, Blocker.** It is one root cause:
- `RecordFieldValidator._received` (validation.py:161-170) quotes a short non-secret str, and compose's records still call `to_enum`, `require_int`, `require_bool` and one `require_text` with quoting on.
- The probe's model and thread-id refusals are rewritten only in the binders.

It covers 12 (record, field) pairs:
- 11 that a caller reaches through compose's public records;
- 3 of those 11 that a step's answer also reaches;
- `PromptSegment.spliced`, for uniformity only.

The reviewer's five pairs are a subset of the 12. Without the verifier's six extra sites, the reviewer's fix would leave R-33 half open.

## 7. Smallest complete fix (proved on a full copy of HEAD)

The proof copy is `$V/lint_patched`. It is `git archive HEAD` with `core.autocrlf=false`, patched by `python $V/apply_fix.py $V/lint_patched`. The diff is `$V/proposed_fix.diff`: 4 files, 50 lines added and 54 removed. `git -C $W apply --check --verbose $V/proposed_fix.diff` reports that the diff applies cleanly to HEAD; it was only checked, never applied.

1. **validation.py: three new `quote` keywords**, in the same shape grant (c) gave `require_text`. Each defaults to the old behaviour and is passed on as `_received(value, field_name, quote=quote)`:
   - `RecordFieldValidator.require_int(value, field_name, *, minimum, maximum, quote: bool = True)`
   - `RecordFieldValidator.require_bool(value, field_name, *, quote: bool = True)`
   - `RecordFieldConverter.to_enum(value, enum_type, field_name, *, quote: bool = True)`

   This follows field-guide/vidbyte-sdk/strict-config-dataclasses.md:61-64: "When an option is missing … add it as a keyword with a backward-compatible default. Check its callers in `vidbyte/harnesses/native/*` first."
2. **No base caller changes.** These 11 calls keep the default, so no base message changes (NG-1):
   - native_threads.py:86, :87, :168, :169, :204, :222 (`to_enum`)
   - native_threads.py:225 (`require_bool`)
   - process.py:66 (`require_int`)
   - process.py:88, :89, :90 (`require_bool`)

   A grep of `vidbyte/` finds no other caller of the three.
3. **`quote=False` at the record sites:**
   - native_compose.py:96 and :97 (`ThreadStep.harness`, `verb`)
   - native_compose.py:169 (`WorkspaceDiff.truncated`)
   - native_compose.py:243 (`ThreadVerdict.decision`)
   - native_compose.py:325 (`StageSpec.retries`)
   - native_compose.py:338 (`StageAttempt.rung`)
   - native_compose.py:341 (`StageAttempt.decision`)
   - native_ensemble.py:70 (`EnsembleRole.name`, the existing `require_text` keyword)
   - native_ensemble.py:123 (`EnsembleSelection.proposal`)
   - native_compose.py:152 (`PromptSegment.spliced`), for uniformity
4. **The rewrite moves into `ThreadStep`.** `__post_init__` keeps its narrated steps. Where it built the probe inline (:104-116), it now does this:
   ```python
   # Check the key, workspace, model, skills and thread id with the
   # record the nine functions use, built with a probe prompt that
   # is never sent, and keep its resolved paths. Its refusal of a
   # model or thread id is raised again without the value, outside
   # any handler, so no context keeps the quoted original.
   probe = self._probe()
   if isinstance(probe, ConfigurationError):
       raise self._withheld(probe)
   ```
   It uses two flat helpers, each of which calls none of its siblings, which keeps AGENTS.md principle 1:
   ```python
   def _probe(self) -> NativeThreadRequest | ConfigurationError:
       # The record the nine functions use, or the refusal it raised.
       try:
           return NativeThreadRequest(harness=self.harness, verb=NativeThreadVerb.RUN if self.thread_id is None else self.verb, prompt=COMPOSE_PROBE_PROMPT, api_key=self.api_key, workspace=self.workspace, model=self.model, skills=self.skills, thread_id=self.thread_id)
       except ConfigurationError as error:
           return error

   def _withheld(self, error: ConfigurationError) -> ConfigurationError:
       # That record quotes a short bad value, and a model or thread
       # id is caller text that can hold a key, so a refusal quoting
       # either is made again naming it by its type only, with the
       # same field (spec INV-4, INV-5).
       for value in (self.model, self.thread_id):
           head, quoted, tail = str(error).rpartition(repr(value)) if isinstance(value, str) else ("", "", "")
           if quoted:
               return ConfigurationError(head + COMPOSE_WITHHELD_VALUE.format(type_name=type(value).__name__) + tail, details=error.details)
       return error
   ```
   `COMPOSE_WITHHELD_VALUE` (lib/constants/native_compose.py:329) joins the existing constants import. **Lint trap:** put it after `COMPOSE_VERDICT_MAX_FINDINGS`. The first proof copy placed it after `COMPOSE_ANSWER_TEXT_MAX_CHARS`, and `lint/run.py` failed with `S051 REGRESSED: 260 finding(s), allowance 259`, which is I001 at native_compose.py:14.
5. **steps.py.** Each binder becomes a plain `return ThreadStep(...)`, which deletes :75-81 and :89-95. Delete `ThreadBinder._withheld` (:154-166). `ConfigurationError` is still raised at steps.py :106, :117, :120 and later, so its import stays.
6. **Header updates.** These are proposed wording; the proof copy leaves the headers unchanged.
   - validation.py line 5 (ARCHITECTURE NOTE): change "and, for require_text, the caller did not pass quote=False" to "and the caller did not pass quote=False (require_text, require_int, require_bool and to_enum take it)".
   - validation.py line 6 (FUNCTION INVENTORY): mark `require_int`, `require_bool` and `to_enum` "(each with quote)".
   - validation.py line 9 (KNOWN EDGE CASES): change "Caller text that can hold a key, such as a compose prompt or template, is checked with quote=False" to "Caller text or a record field that can hold a misplaced key, such as a compose prompt, template, harness, verb, retries count or verdict decision, is checked with quote=False".
   - native_compose.py FUNCTION INVENTORY: add "_probe builds the NativeThreadRequest the nine functions use or returns its refusal, _withheld makes a refusal that quotes the model or thread id again without it".
   - native_compose.py KNOWN EDGE CASES: add "A record never quotes a refused value a caller could have filled with a key: the closed sets, counts and flags are checked with quote=False, and a model or thread id the probe refuses is named by its type only, whether the step came from a binder, a direct build or dataclasses.replace (INV-4)."
   - steps.py line 6: remove the `_withheld` clause.
   - steps.py line 9: change "A refused model is named by its type only: the record the nine functions use would quote a short one, key and all (INV-4)." to "ThreadStep names a refused model or thread id by its type only, so the binders pass its refusal on unchanged (INV-4)."
7. **Should `_withheld` move into the record? Yes.**
   - All three supported entries (binder, direct build, `dataclasses.replace`) pass through `ThreadStep.__post_init__`, and the binders are the only one of them with the rewrite today.
   - The lib layer can own the rewrite: `COMPOSE_WITHHELD_VALUE` lives in lib/constants, so nothing imports upward.
   - Keeping a binder copy as well would write the same logic twice, against AGENTS.md principle 5.
   - The record version also covers `thread_id`. The binder never needed that, because `bind_continue` pre-checks the thread id with `quote=False`.
8. **What the orchestrator owns.** The pipeline does not let this stage edit the spec.
   - spec.md:1626, §17 grant (c): `quote` also goes on `require_int`, `require_bool` and `to_enum`, and compose passes `quote=False` for every record field whose refusal could quote a str (R-33). "the binders raise the record's model refusal again" becomes "`ThreadStep` raises the probe's model or thread-id refusal again with the value named by its type only".
   - spec.md:731, :1103 and §12.3 row 4 (:1308): "two keywords" becomes five (`quote` on four validators, `min_items` on `to_tuple`).
   - spec.md:1588: "`ThreadBinder._derived` (R-15) and `_withheld` (R-3)" becomes "`ThreadBinder._derived` (R-15); `ThreadStep._probe` and `_withheld` (R-3, R-33)".
9. **The alternative: the reviewer's fix** (R-RC1 steps 1-6). It wraps the probe in try/except inside `__post_init__`, adds `quote` to `to_enum` and `require_int`, and deletes the binders' `_withheld`.
   - It is the same mechanism, but it misses the verifier's six sites: `ThreadVerdict.decision`, `StageAttempt.rung`, `StageAttempt.decision`, `WorkspaceDiff.truncated`, `EnsembleRole.name` and `EnsembleSelection.proposal`.
   - An inline try/except also puts a handler and a rewrite into the narrated main function. A `_probe` helper keeps it flat, as `_checked_config` already does.
   - Another acceptable variant chooses the value by `error.details["field"]` (`"model"` or `"thread_id"`) instead of scanning both values. It is tighter, but it ties the record to the base's field names. Scanning can only hide a value, never show one.
10. **Why not flip `_received`, so that it never quotes a str anywhere?** That would close R-29 SDK-wide, but it changes base messages (NG-1). It is the larger move for its own PR (section 11).

## 8. Test assertions for the test author

Add these 18 rows to `tests/features/harness_compose/test_harness_compose_keys.py` beside `CALLER_TEXT_SITES`. They use the pack's `compose_api`, `sandbox`, `steps` and `pack` fixtures and `key = short_key()`. The verified source is `$V/test_s5v_rr1_record_keys.py`, with its `RecordText` helper and `reachable()`.

Every row asserts all of the following:

```python
with pytest.raises(api.ConfigurationError) as refused:
    build(text)
error = refused.value
assert error.details.get("field") == field, f"{site}: {error} {error.details}"
shown = " ".join(" ".join([str(item), repr(item.args), *(repr(value) for value in vars(item).values())]) for item in reachable(error))
assert pack.leaks(shown, [text.key]) == [], f"INV-4: the {site} refusal quotes the key: {str(error)!r}"
assert sandbox.launches() == [], "refused before any process starts"
```

Here `reachable(error)` is the error plus everything reachable through `__context__` and `__cause__`, so a quoted original kept as context also fails the row.

| # | Site | Call (`ws` is the sandbox workspace, `fn` the matching nine function) | `details["field"]` |
|---|---|---|---|
| 1 | ThreadStep() harness | `ThreadStep(function=fn[grok, run], harness=key, verb="run", api_key=key, workspace=ws)` | `ThreadStep.harness` |
| 2 | ThreadStep() verb | `ThreadStep(function=fn[grok, run], harness="grok", verb=key, api_key=key, workspace=ws)` | `ThreadStep.verb` |
| 3 | ThreadStep() opencode model | `ThreadStep(function=fn[opencode, run], harness="opencode", verb="run", api_key=key, workspace=ws, model=key)` | `model` |
| 4 | ThreadStep() grok model with a newline | `ThreadStep(function=fn[grok, run], harness="grok", verb="run", api_key=key, workspace=ws, model=key + "\n")` | `model` |
| 5 | ThreadStep() continue thread_id | `ThreadStep(function=fn[grok, continue], harness="grok", verb="continue", api_key=key, workspace=ws, thread_id=key + "\x00")` | `thread_id` |
| 6 | ThreadStep() fork thread_id | `ThreadStep(function=fn[opencode, fork], harness="opencode", verb="fork", api_key=key, workspace=ws, model=pack.OPENCODE_MODEL, thread_id=key + " x")` | `thread_id` |
| 7 | replace() harness | `dataclasses.replace(steps.bind("grok", "run", None, key=key), harness=key)` | `ThreadStep.harness` |
| 8 | replace() verb | `dataclasses.replace(steps.bind("grok", "run", None, key=key), verb=key)` | `ThreadStep.verb` |
| 9 | replace() opencode model | `dataclasses.replace(steps.bind("opencode", "run", None, key=key), model=key)` | `model` |
| 10 | replace() continue thread_id | `dataclasses.replace(steps.bind("grok", "continue", THREAD_ID, key=key), thread_id=key + "\x00")` | `thread_id` |
| 11 | StageSpec retries | `StageSpec(steps.bind("grok", "run", None, key=key), "Start.", key)` | `StageSpec.retries` |
| 12 | replace() StageSpec retries | `dataclasses.replace(StageSpec(step=steps.bind("grok", "run", None, key=key), template="Start."), retries=key)` | `StageSpec.retries` |
| 13 | ThreadVerdict decision | `ThreadVerdict(decision=key, summary="s")` | `ThreadVerdict.decision` |
| 14 | StageAttempt rung | `StageAttempt(rung=key, outcome=StepOutcome(result=NativeThreadResult(harness=NativeHarness.GROK, thread_id=THREAD_ID, text="x", text_truncated=False)))` | `StageAttempt.rung` |
| 15 | StageAttempt decision | `StageAttempt(rung=0, outcome=<as row 14>, decision=key)` | `StageAttempt.decision` |
| 16 | EnsembleSelection proposal | `EnsembleSelection(proposal=key, approach="a", rationale="r", guidance="g")` | `EnsembleSelection.proposal` |
| 17 | EnsembleRole name | `EnsembleRole(name=key + "\x00", identity="i", personality="p", expertise="e", knowledge="k", skills="s", goal="g")` | `EnsembleRole.name` |
| 18 | WorkspaceDiff truncated | `WorkspaceDiff(files=(), text="", truncated=key)` | `WorkspaceDiff.truncated` |

All 18 are red at HEAD (`18 failed in 14.42s`) and green on the proof copy (`18 passed in 1.12s`).

There are also three optional rows for the answer path in 3.3. Each builds `NativeThreadResult(harness=NativeHarness.GROK, thread_id=THREAD_ID, text=json.dumps(answer), text_truncated=False)` and calls `value, problem = AnswerDecoders.read(result, parse)`. It then asserts `value is None`, `field in problem` (EC-28: the problem names the field) and `pack.leaks(problem, [key]) == []`. The cases are:
- `AnswerDecoders.verdict` with `{"decision": key, "summary": "s", "findings": []}`, field `ThreadVerdict.decision`;
- `functools.partial(AnswerDecoders.selection, offered=[1, 2])` with `{"proposal": key, "approach": "a", "rationale": "r", "guidance": "g"}`, field `EnsembleSelection.proposal`;
- `functools.partial(AnswerDecoders.plan, roles=1)` with one role whose `name` is `key + "\x00"`, field `EnsembleRole.name`.

The black-box form is a `verify_with` whose verifier stand-in answers `{"decision": key, …}` on every turn, then asserts that the verdict answer's `problem` holds no fragment of the key.

## 9. Gates on the proof copy

| Gate | Proof copy (`$V/lint_patched`) | Unpatched copy |
|---|---|---|
| R-33 rows (`$V/test_s5v_rr1_record_keys.py`) | `18 passed in 1.12s` | `18 failed in 14.42s` (HEAD worktree) |
| compose pack `tests/features/harness_compose` | `363 passed in 48.67s` | `363 passed in 48.15s` (`$V/control`) |
| base pack `tests/features/harness_threads` | `435 passed, 3 skipped in 42.71s` | re-review: `436 passed, 2 skipped` |
| `python lint/run.py` | `SDK-LINT: PASS`, output identical to the unpatched copy | `SDK-LINT: PASS` (`$V/lint_control`) |
| `ruff check --no-cache --isolated --select F,E9,I` on the 4 changed files | `All checks passed!` | `All checks passed!` |
| class sweep | `183; leaking: 4; clean: 179` (stdlib `Enum` only) | `183; leaking: 44; clean: 139` |
| answer probe | `key-in-problem=False` x4, field named | `True` x3 |
| reviewer's four probes | every line `key-in-message=False` | `True` on every R-RC1 line |

Notes on the gates:
- **The third harness_threads skip** is `origin/main is not available in this checkout`, because an archive copy has no git refs.
- **The concurrent runs.** An earlier pair of compose-pack runs, made at the same time as each other (about 166 s each), failed the same two environment tests in both the patched and the unpatched copy: a worktree removal test (`fatal: failed to read .git/worktrees/…/commondir: No error`) and `test_compose_and_new_lib_modules_respect_the_layers`. Run alone, both copies give 363 passed, so the patch does not cause them.
- **How lint was run.** `lint/run.py` enumerates files with `git ls-files`, so it was run on the archive copies with `GIT_DIR` set to the worktree's git dir, `GIT_WORK_TREE` set to the copy, and `GIT_INDEX_FILE` set to a scratch copy of the worktree index. That is read-only use of git.

## 10. Commands run (final output lines)

From `$W` (HEAD) unless noted. Every Python run used `PYTHONDONTWRITEBYTECODE=1`.

- `PYTHONPATH=$(pwd) python $R/probe_keys_direct.py` and the other three `$R/probe_keys_*.py` probes print the lines in 3.1. From `$V/lint_patched`, every line is `key-in-message=False`, and messages end `got a value of type str.`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -p tests.features.harness_compose.conftest "$V/test_s5v_rr1_record_keys.py"` → `18 failed in 14.42s`. From `$V/lint_patched`: `18 passed in 1.12s`.
- `PYTHONPATH=$(pwd) python "$V/probe_sweep.py" > "$V/probe_sweep.out"` → `TOTAL (entry, record, field) pairs: 183; leaking: 44; clean: 139`. From `$V/lint_patched`: `… leaking: 4; clean: 179` (`$V/probe_sweep_proof.out`).
- `python "$V/aggregate.py" probe_sweep.out probe_sweep_proof.out` → `$V/sweep_table.txt`.
- `PYTHONPATH=$(pwd) python "$V/ctx_count.py" "$V"` → `430 ('LEAK', 'None')`, `1366 ('clean', 'None')`, `352 ('ACCEPTED', '-')`, `4 ('OTHER-LEAK', '-')`. From `$V/lint_patched`: `1796 ('clean', 'None')`.
- `PYTHONPATH=$(pwd) python "$V/probe_answers.py"` → `key-in-problem=True` x3 and `False` x1. From `$V/lint_patched`: `False` x4.
- `git -c core.autocrlf=false -C $W archive --format=tar HEAD | tar -x -C $V/lint_control` (and the same into `$V/lint_patched`), then `python $V/apply_fix.py $V/lint_patched` → `patched …validation.py: 4 replacement(s)`, `native_compose.py: 10`, `native_ensemble.py: 2`, `steps.py: 3`, `done`.
- `GIT_DIR=<worktree git dir> GIT_WORK_TREE=<copy> GIT_INDEX_FILE=$V/index.copy python lint/run.py` → `SDK-LINT: PASS` in both copies, and `diff` of the two outputs is empty.
- `python -m ruff check --no-cache --isolated --select F,E9,I <4 files>` → `All checks passed!` in both copies.
- From `$V/lint_patched`: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=short -rf tests/features/harness_compose` → `363 passed in 48.67s`. From `$V/control`: `363 passed in 48.15s`.
- From `$V/lint_patched`: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -rs tests/features/harness_threads` → `435 passed, 3 skipped in 42.71s`.
- `git -C $W apply --check --verbose $V/proposed_fix.diff` → four `Checking patch …` lines, exit 0. Nothing was applied.
- `python $S/procs.py --kill`, after each probe batch and at the end → `stand-in or grandchild processes: []`.
- `git -C $W status --short` → only `M docs/spec/native-thread-compose/review.md` (this stage's row). The report is new.

## 11. The larger move

The deeper fix is in `_received` itself. A str is the only quotable type that can hold a credential, and the record cannot know that a field will never hold a misplaced key. If `_received` never quoted a str, the class would close for every record in the SDK, R-29's base refusals included. Base messages would then say "got a value of type str" for bad enum strings.

That change touches NG-1 territory and messages that existing tests may pin, so it belongs in its own PR, after an audit of the base tests that read `got '…'` text. Within this PR, the `quote` keywords added here are the reversible half of that move.

## 12. Open items

- **Orchestrator:**
  - Apply the spec edits in 7.8 (§17 grant (c), the keyword lists at spec.md:731, :1103 and :1308, and the as-built list at :1588), so that the repair stays inside a granted file set.
  - review.md's Verdict paragraph (line 6) still says "10 repairable Blockers and 4 repairable Majors". The table now has 11 repairable Blockers and 5 repairable Majors. This stage changed only the count line and its breakdown sentence, as instructed.
- **Test author:** add the 18 rows in section 8, and optionally the three answer rows.
- **Repair agent:** apply section 7 with `$V/proposed_fix.diff` as the reference, then do the header edits in 7.6, which the proof diff does not contain.
