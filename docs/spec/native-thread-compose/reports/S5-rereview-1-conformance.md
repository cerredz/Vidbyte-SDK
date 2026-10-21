LENS: conformance (post-repair re-review, round 1)
VERDICT: MERGEABLE AFTER FIXES — all 24 repairs hold and AC-1 runs as written, but a `ThreadStep` built directly or through `dataclasses.replace`, and `StageSpec.retries`, still quote a misplaced short key in compose's own `ConfigurationError`, so ledger 3 ("still never reaches … error messages") and INV-4 fail on record paths that the R-3 repair did not reach.

Reviewed: `git diff origin/feat/native-grok-opencode-meta-hosts...b95e11c1`, with the most attention on `git diff e1bf20d8..b95e11c1 -- vidbyte`. HEAD is `5032164e`. It adds one line to `docs/.../pipeline.md`, so its code is identical to `bc351671` and `b95e11c1`. Checked against spec r5.

FIX CONFIRMATIONS (one line per fixed finding: R-id — holds | does not hold — evidence)
R-1 — holds — `COMPOSE_TRUNCATED_PROBLEM` now reads only "The answer was cut at the length limit, so it was not read." `json_repair.md` asks "Reply again with exactly one JSON object…". `grep -rn 'Answer again' vidbyte` finds 0.
R-2 — holds — Every floor is a named constant: `COMPOSE_MIN_CHAIN_OUTCOMES`, `COMPOSE_MIN_VERIFIERS`, `COMPOSE_MIN_STAGES`, `STAGE_MIN_RETRIES`, `STAGE_MIN_RUNG`, `ENSEMBLE_MIN_PROPOSAL_NUMBER` and `COMPOSE_MIN_JSON_TURNS`. `grep -rnE 'minimum=[01]\b|min\(kept\) < 1|must hold 1 to'` over compose and the six lib modules finds 0.
R-3 — holds for every site R-3 names — The S4 probe `-k "key_in or bind_refus"`, re-run at HEAD, prints `key-in-message=False` on all 14 compose lines at both key lengths: chain prompt and template, verify prompt, staged template, ensemble task, `parse_json_answer` prompt and schema, the `bind_continue` thread id and the binder model. Its only `True` lines are `BASE run_opencode_thread` (R-29, a follow-up). Record-level sites that R-3 never listed still leak; see R-RC1.
R-4 — holds — `ComposeGit.add_worktree` has no except path (awk finds 0). The half-way cleanup is in `DisposableWorktree.__aenter__` (workspace.py:126-142) and runs through `_settled`.
R-5 — holds — `def _replace` occurs 0 times in compose. Four compose modules call `SecretText.replace_all`, which lives in `vidbyte/lib/util/secret_text.py`, replaces the longest secret first and is exported from `vidbyte.lib.util`.
R-6 — holds — No comment line runs past 72 columns in the compose modules or the six lib modules (awk finds 0).
R-7 — holds — `to_tuple(min_items=)` checks the six counts. `counted`, `COMPOSE_COUNT_RULE` and the hand-written floors are gone. The only remaining `if not outcomes:` is in `ThreadStages._values` and gives stage 1 its empty values; it is not a count check. Each `WorkspaceDiff.files` item goes through `require_text(quote=False)`.
R-8 — holds — Probe `-k ec16`: EC16-1 prints `verdicts=1 session-in-record=True`, EC16-2 prints `verdicts=2` with both sessions, and EC16-P prints `plan-kept=True proposals=2`. HEAD's removal tests run against e1bf20d8's code give `2 failed` (`assert [] == [...]`).
R-9 — holds — `tuple[str, bool]` occurs 0 times. Segments travel as `PromptSegment(text, spliced)`.
R-10 — holds — Probe `-k "double_cancel or anyio or two_failing or orphan_removal"`: every case prints `worktrees=1 leftovers=0 pending=0 live_leaders=0 live_grandchildren=0`. The anyio case prints `anyio caught=True`, and SHUTDOWN prints `admin=[]`. 7 passed.
R-11 — holds — No comment line runs past 72 columns in `tests/features/harness_compose` (awk finds 0).
R-12 — holds — Probe: with Grok, Muse or opencode as the next step, the chain prints `RETURNED failed_step=None`; the second step launched once, and nothing was still alive 2 s later. A lone surrogate in the caller's prompt gives `ConfigurationError | launches=0`.
R-13 — holds — HEAD's blank-template tests run against e1bf20d8's code give `5 failed` (`DID NOT RAISE … ConfigurationError`). They pass at HEAD.
R-14 — holds — `probe_locked_head.py` uses HEAD's API and sends two cancels 0.5 s apart. The hook saw `…/worktrees/vidbyte-compose-worktree-7_q2okas/locked: initializing`. The CancelledError reached the caller 2.84 s after the first cancel. Admin entries are `[]` and leftover TMP folders are `[]`.
R-15 — holds — Probe: an opencode verifier whose skill folder the writer deleted gives `RETURNED writer.ok=True failed_verifiers=(0,) error=FailureCode.CONFIGURATION_INVALID_ARGUMENT` with `worktrees=1 leftovers=0`. A Grok verifier gives the same.
R-16 — holds — The gather mutation (`-p s4v_mut_gather`) gives `2 failed` with "INV-14: tasks still pending when the error propagated: ['CliRunner._drain', 'CliRunner._drain', 'ThreadVerifiers._review']". The no-cancel mutation (`-p s4v_mut_nocancel`) gives `1 failed` with "the error propagated 30.0 s after the add failed: the sibling was not cancelled".
R-17 — holds — `CALLER_TEXT_SITES` has 21 sites, each driven with `short_key()` and `"{previous} " + key + NUL`. All 25 key tests are collected and pass.
R-18 — holds — verify.py:8 says the backstop is skipped "only on a cancellation, a defect or a compose failure, which goes on alone (INV-14)". ensemble.py:8 uses the same phrase.
R-19 — holds — spec.md:1587 records `JSON_KIND_NAMES` as "a module constant in `vidbyte/lib/util/json_text.py` beside `JSON_FENCE` …".
R-20 — holds — stages.py has 0 occurrences of `tried` and 8 of `attempts`.
R-21 — holds — REPO_MAP.md:161 reads: "…stage and ensemble these thread calls; no two of their steps ever write to the workspace at the same time."
R-22 — holds — Item 2 at compose/__init__.py:8 lists all 22 compose classes, JsonAnswers, DiffCapture and DisposableWorktree included. `_replace` is gone (R-5), so the git.py inventory no longer needs it. `DiffCapture.__aenter__` and `__aexit__` have step comments (workspace.py:53-74).
R-23 — holds — verdict_schema.md says "The number of findings is limited, so list the most important problems first." It gives no number.
R-32 — holds — `probe_r32.py` prints `PROBE R-32: 21/21 as the spec states`. chain.py `_fit` passes `whole`, so step i's blank check reads the caller's prompt while the refusal names the template. That is the review's smallest fix.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- `ComposeCalls.settle` waits through any number of cancels with `suppress(CancelledError)` and raises the first cancel again once the work ends. It has no sleep and no deadline of its own; each git step stays bounded by `COMPOSE_GIT_TIMEOUT_SECONDS`. This keeps ledger 8 ("no composite invents a second timeout system") on the cancel path. The R-10 and R-14 probes leave 0 worktrees, 0 pending tasks and 0 live processes. Do not add a deadline to `settle`.
- `PromptFitter.check` runs its checks in the order blank, then encodable, then length. Its `whole` keyword lets chain step i refuse a template made only of placeholders, naming the template, while it judges blankness on the caller's prompt (R-13 + R-32, 21/21). Do not drop `whole` or reorder the checks.
- The positional `kept` lists in verify.py and ensemble.py attach every finished verdict and proposal to `ThreadComposeError.result`, even when a sibling's worktree cannot be removed (ledger 7, EC-16). This is red at e1bf20d8 and green at HEAD.
- The binders raise their refusal after the `except` block, so `__context__` and `__cause__` never carry the quoted original. The `api_key` field itself is never quoted on any path (`api_key must match ^[!-z|~]+$; got a value of type str.`, `ctx=None`). R-RC1's fix must keep both properties.

FINDINGS (ranked, most severe first, max 15)
R-RC1 [Blocker] [weighted word / key hygiene] vidbyte/lib/dataclasses/native_compose.py:96-116 (also :325; vidbyte/harnesses/native/compose/steps.py:75-81, :89-95, :155-166) — A caller-built `ThreadStep`, made directly or through `dataclasses.replace`, and `StageSpec.retries` quote a misplaced short key in compose's own `ConfigurationError`
  Evidence:
    The record checks quote a short bad str:
      native_compose.py:96-97: `object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "ThreadStep.harness"))`, and the same for `verb`.
      native_compose.py:107-116: `probe = NativeThreadRequest(... model=self.model, ... thread_id=self.thread_id)`. The base record quotes a short bad str.
      native_compose.py:325: `RecordFieldValidator.require_int(self.retries, "StageSpec.retries", minimum=STAGE_MIN_RETRIES, maximum=STAGE_MAX_RETRIES)`. `require_int` quotes a short str.
    The R-3 repair hides the value only in the binders:
      steps.py:78 and :92: `refusal = ThreadBinder._withheld(error, model)`.
      The `_withheld` comment at steps.py:156-160 says: "The record the nine functions use quotes a short bad value, and a model is caller text that can hold a key".
      §17 grant (c), spec.md:1626, records exactly that scope: "the binders raise the record's model refusal again with the model named by its type only".
    `PYTHONPATH=$(pwd) python $R/probe_keys_direct.py`, key `vbk-probe7a1c0e2f`:
      `bind_thread opencode model: ConfigurationError key-in-message=False …`
      `ThreadStep() opencode model: ConfigurationError key-in-message=True key-in-details=False field=model`
      `ThreadStep() continue thread_id: ConfigurationError key-in-message=True key-in-details=False field=thread_id`
    `probe_keys_direct_msg.py`:
      `model must match ^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9]\S*$; got 'vbk-probe7a1c0e2f'.`
      `thread_id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; got 'vbk-probe7a1c0e2f\x00'.`
      `thread_id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; got 'vbk-probe7a1c0e2f x'.` (an opencode fork step)
    `probe_keys_direct2.py`:
      `ThreadStep.harness must be one of grok, opencode, muse; got 'vbk-probe7a1c0e2f'.`
      `ThreadStep.verb must be one of run, continue, fork; got 'vbk-probe7a1c0e2f'.`
      `dataclasses.replace(bound opencode step, model=key)` gives `model must match …; got 'vbk-probe7a1c0e2f'.`
    `probe_keys_records.py`:
      `StageSpec.retries must be an integer from 0 to 3; got 'vbk-probe7a1c0e2f'.`
      `StageSpec.ladder`, `EnsembleRoster.planner`, `in_worktree` and `capture_diff` name the type only.
    tests/features/harness_compose/test_harness_compose_keys.py:72-94: the 21 `CALLER_TEXT_SITES` have no row for a directly built `ThreadStep`, for `dataclasses.replace` or for `StageSpec.retries`, so the pack (363 passed) cannot see this.
  Failure:
    Input: a caller builds a step directly, which EC-78 lists as a supported input along with `dataclasses.replace`, and swaps two str arguments. Examples are `ThreadStep(function=run_opencode_thread, harness="opencode", verb="run", api_key="zhipuai/glm-4.6", workspace=ws, model=<a 12- to 49-character key>)` and `dataclasses.replace(step, thread_id=<key>)`.
    Outcome: the caller gets a `ConfigurationError` whose `str()` holds the whole key. That text reaches tracebacks, logs and CI output.
    The same mistake made through `bind_thread` or `bind_continue` is withheld, so the guarantee depends on which supported entry the caller used.
    Defence considered: the key has to be misplaced, and the `api_key` field itself is never quoted. R-3 has the same character and was rated Blocker, and the ruling put the binder's misplaced-key model refusals in scope, so the same mistake on the record path must hold too. Ties go to the prosecution.
  Smallest fix:
    1. In `ThreadStep.__post_init__` (lib layer, using `COMPOSE_WITHHELD_VALUE` from lib/constants), build the probe inside `try/except ConfigurationError`. Rewrite a quoted str `model` or `thread_id` to "a value of type str". Raise after the handler, so `__context__` stays `None`.
    2. Refuse a bad str `harness` or `verb` without quoting the value. One way is a `quote` keyword on `to_enum` that defaults to True, as grant (c) did for `require_text`.
    3. Add `quote: bool = True` to `require_int` and pass `quote=False` for `StageSpec.retries`.
    4. The binders' `_withheld` is then no longer needed.
    5. The test author adds `CALLER_TEXT_SITES` rows for a directly built `ThreadStep` (model, thread_id, harness and verb), for `dataclasses.replace(step, model=…)` and for `StageSpec.retries`.
    6. The orchestrator updates the "binders raise …" sentence of §17 grant (c).
  Spec IDs: request.md §D ledger 3 (weighted: "still never reaches argv, files, `os.environ`, error messages or logs"); INV-4 ("any `ConfigurationError` compose raises"); AC-15 ("No key appears in: … any `ConfigurationError` message"); §14 Never ("Put a key in … an error"); EC-78.

VERIFIED CLAIMS:
- AC-1 — held. The acceptance test's `SNIPPET` equals the only python block in spec §4 (1,565 characters each, identical). It runs as written against stand-ins on PATH: 1 passed.
- §5 diagrams match the code — held. `verify_with` (verify.py:49-96) checks the steps and the prompt fit before any git command. It then runs locate, toplevel and has_commit; snapshot S0; the writer; snapshot S1 and the diff; the readers through `fan_out`, Muse and opencode in `from_tree(after, before)` worktrees; and the S2 backstop. That is the order of the sequence diagram.
- Budget — held. 41 new files: 13 compose `.py`, 6 lib `.py` and 22 prompts. 9 modified files. 51 classes: 50 in the new modules plus `ThreadComposeError` in `errors/base.py`. This matches the spec's 51-class row (spec.md:725).
- Files outside §12.3 — held. The 9 modified files are §12.3 rows 2, 4, 6, 9, 10, 18, 26, 27 and 28. The diff has 0 lines under lint/, .semgrep/, contracts/, .github/ and scripts/, and `lint/baseline.json` is untouched.
- `python lint/run.py` — held. It prints `SDK-LINT: PASS`, no baseline is raised, and S061 (6→5) and S063 (4→3) improved.
- Test tree — held. Exactly 12 commits in e1bf20d8..b95e11c1 touch tests/. All are `test(compose)` commits by the test author, including 3a21352b (whose `"aborted by"` wording is granted), and none touches a code file. No repair commit touches a test.
- bc351671..b95e11c1 and b95e11c1..5032164e change no code — held. Both are docs only.
- Packs — held. compose: 363 passed. Base harness_threads: 436 passed, 2 skipped; both skips depend on the environment.
- Exports — held. `compose.__all__` has 42 names and exports neither `PromptSegment` nor `SecretText`. The native `__all__` keeps its 17 names unchanged. `vidbyte.lib.util` exports `JsonText` and `SecretText`.
- Ledger 6, "text_truncated=True must fail the parse" — held. `answers.py` returns `COMPOSE_TRUNCATED_PROBLEM` before decoding whenever `text_truncated` is set.
- Ledger 8, no second timeout system — held. `settle` and `fan_out` have no sleep and no deadline. The only bounds are the git step's `COMPOSE_GIT_TIMEOUT_SECONDS` and the base's own timeouts.
- Ledger 4, "Exactly one writer" — held. Readers run in worktrees or as Grok PLAN steps, and the REPO_MAP sentence (R-21) states it.
- Ledger 7, "every step's … which step failed. Only an empty result aborts" — held. In the R-8, R-12 and R-15 probes, every failure after I/O is recorded and none is raised.
- Ledger 3, keys never reach error messages — held at the 21 caller-text sites, the binders, every `ThreadComposeError` probe line and the `api_key` field (never quoted, `ctx=None`). It does NOT hold for a directly built `ThreadStep`, for `dataclasses.replace` or for `StageSpec.retries` (R-RC1).
- S5-repair-1 R-3, "`require_text(quote=False)` … at every caller-text site" — does NOT hold. The `ThreadStep` and `StageSpec` constructors still quote (R-RC1).
- S5-repair-1 R-3, "all 25 keys tests pass" — held: 25 are collected and all pass. The site table has no rows for the record constructors.
- EC-79..81 tests are collected: EC-79 5+2, EC-80 15+2, EC-81 27 — held.
- Compose has no logging, and every other compose `raise ConfigurationError` formats only argument names, enum values or type names — held.
- The R-32 `whole` keyword is internal plumbing — held. Spec §8 lists only `PromptFitter: check, fit` (spec.md:923), so the keyword contradicts nothing.

COMMANDS RUN: (`$R` = scratchpad/s5-rereview-1, `$S` = scratchpad/s4-verifier, run from the worktree root)
- `python $S/procs.py --kill` (at resume, after the probes and at the end) → `stand-in or grandchild processes: []`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose` → `363 passed in 84.32s (0:01:24)`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `436 passed, 2 skipped in 41.41s`
- `python lint/run.py` → `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose/test_harness_compose_acceptance.py -k developer_snippet -rA` → `PASSED …::test_developer_snippet_runs_as_written_against_stand_ins_on_path` / `1 passed in 2.45s`
- `python -I -` (an ast comparison of spec §4 with `SNIPPET`) → `python blocks in §4: 1 | identical: True | lengths: [1565] 1565`
- `python -m pytest -q -s -p no:cacheprovider -p tests.features.harness_compose.conftest $S/test_s4v_probes.py -k "key_in or bind_refus"` → 14× `key-in-message=False`, 2× `BASE run_opencode_thread: NativeThreadError key-in-message=True` / `3 passed, 21 deselected in 24.74s`
- the same file with `-k "double_cancel or anyio or two_failing or orphan_removal"` → `SHUTDOWN pending at raise=[] -> after cancel: worktrees=1 leftovers=[] admin=[]` / `7 passed, 17 deselected in 50.83s`
- the same file with `-k ec16` → `EC16-P problem=worktree_failed plan-kept=True proposals=2` / `3 passed, 21 deselected in 17.03s`
- the same file with `-k "writer_deletes_reader_skill or lone_surrogate or caller_prompt or opencode_orphan"` → `CALLER-LONE chain(grok first) on win32: ConfigurationError | launches=0 …` / `7 passed, 17 deselected in 26.87s`
- `PYTHONPATH=$(pwd) python -W ignore $R/probe_locked_head.py $R` → `[after] admin entries (name, lock reason): []` / `[after] leftover folders in TMP: []`
- `python -I scratchpad/s5-2/probe_r32.py "$(pwd)"` → `PROBE R-32: 21/21 as the spec states`
- HEAD's `test_harness_compose_removal.py` against e1bf20d8's vidbyte (scratch copy `$R/old`) → `2 failed, 1 deselected in 2.41s`
- HEAD's blank-template validation tests against e1bf20d8's vidbyte (`$R/old`) → `5 failed, 95 deselected in 3.35s`
- concurrency tests with `-p s4v_mut_gather` (`$S` on PYTHONPATH) → `2 failed, 6 deselected in 1.49s`; with `-p s4v_mut_nocancel` → `1 failed, 1 passed, 6 deselected in 32.11s`
- `PYTHONPATH=$(pwd) python $R/probe_keys_direct.py` → `ThreadStep() opencode model: ConfigurationError key-in-message=True …` / `ThreadStep() continue thread_id: ConfigurationError key-in-message=True …` / `StageSpec template: ConfigurationError key-in-message=False …`
- `PYTHONPATH=$(pwd) python $R/probe_keys_direct_msg.py` → the three quoted messages under R-RC1
- `PYTHONPATH=$(pwd) python $R/probe_keys_direct2.py` → harness, verb and `dataclasses.replace` lines each `key-in-message=True`
- `PYTHONPATH=$(pwd) python $R/probe_keys_records.py` → `StageSpec(step, template, retries=key) … key-in-message=True`; the ladder, roster, in_worktree and capture_diff lines `False`
- an inline `api_key` probe (bind_thread and ThreadStep with key+NUL or key+' x') → 3× `api_key must match ^[!-z|~]+$; got a value of type str.`, `key-in-message=False ctx=None`
- `git diff --name-status origin/feat/native-grok-opencode-meta-hosts...b95e11c1 -- vidbyte pyproject.toml REPO_MAP.md | … | uniq -c` → `41 A` / `9 M`. Counting `+class` gives `51`. `git diff … -- lint .semgrep contracts .github scripts | wc -l` gives `0`.
- `git log e1bf20d8..b95e11c1 -- tests` → 12 commits, all `test(compose)`, the newest `b846925e … [AC-22]`
- the grep and awk checks for R-1, R-2, R-4, R-5, R-6, R-7, R-9, R-11, R-18, R-19, R-20, R-21, R-22 and R-23 → each returns 0 or the expected text. R-7's only hit is `ThreadStages._values`.
- `pytest --collect-only` over the compose pack → EC-79 5+2, EC-80 15+2, EC-81 27, derived_steps 6, removal 3, concurrency 8, keys 25
