# S5 repair 2: infinite-memory-events

Branch `feat/infinite-memory-events`, start `5bf5bfc7`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1159 (stacked on #1084 at `7efceb55`). Input: the three Minors from `reports/S5-rereview-1.md` (R-C1..R-C3), with no failing gate. `SCRATCH` below is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/3e21357e-da06-45b9-8218-c0b25aec2a6d/scratchpad`. This iteration's probes are in `SCRATCH/s5r2/`. `SCRATCH/mut` was not touched.

## Gate matrix

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new test (1 function) | `python SCRATCH/s5r2/rc1_kill.py`, plus `validation.py` from `5bf5bfc7` swapped into the worktree and then restored | PASS at head; red before the fix | head `PASS []`; `pre_m5`, `m5_at_5bf5bfc7`, `reviewer_fix`, `refuse_every_partial_subclass` each `KILLED` by `test_require_callable_refuses_a_partial_subclass_whose_own_call_is_async`; at `5bf5bfc7`: `1 failed, 4 passed in 0.87s` |
| focused tests @ `6c7e0bd1` | `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider` | PASS | `193 passed in 6.03s` (192 + 1) |
| lint @ `2073421b` | `PYTHONPATH=$(pwd) python lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS`; no rule REGRESSED; IMPROVED set unchanged from iteration 1; `lint/baseline.json` untouched |
| full gate, source stage @ `2073421b` | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | FAIL, inherited only | `SDK-LINT: PASS`, `context write-path integrity: ok`, `context primitive introductions: ok`, `reasoning trace contracts: ok (182 tools, 55 shapes)`, then `FAILED …test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, `::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `3 failed, 6123 passed, 16 skipped in 104.75s (0:01:44)` / `CI failed: Command failed with exit code 1: … -m pytest`. These are the same 3 tests that iteration 1 showed failing at base `7efceb55`. |
| full gate, package stage @ `6c7e0bd1` | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| semgrep static policy @ `6c7e0bd1` | `PATH="<SCRATCH>/semgrep-venv/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (1.170.1) | PASS | `Ran 1 rule on 982 files: 0 findings.` |
| public-API contract @ `6c7e0bd1` | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 52249854c2da0ca5961a743e961d5b8972fa35ce (vidbyte-sdk 0.3.0, 647 exports).` |
| remote checks @ `4013eeb2` | `gh workflow run CI` (run 39011569724) and `gh workflow run "Static policy"` (run 39011571065), then `gh api …/commits/4013eeb2…/check-runs` | 4/4 green | `CI exit=0` / `Static exit=0` (`gh run watch --exit-status`) / `Package completed success 4013eeb2` / `Static policy completed success 4013eeb2` / `Source / Python 3.12 completed success 4013eeb2` / `Source / Python 3.11 completed success 4013eeb2`. No rerun was needed. The final head, which adds this report and the verify-log record to `4013eeb2` and changes only docs, was dispatched again; its run ids and check-runs are in the STATUS message |

`vidbyte/`, `tests/`, `contracts/` and CI config are byte-identical from `2073421b` through the final head. Every later commit changes only `docs/spec/infinite-memory-events/`.

## Per finding

| ID | What I did | Evidence |
|---|---|---|
| R-C1 | In `RecordFieldValidator.require_callable`, the old unwrap loop is replaced by a list holding the value and every partial it wraps. With `synchronous`, a layer is refused when it is an async function, or when `__call__` on its type is async. The code is still 3 lines, the `@intent` block grows by 1 line, and the header KNOWN EDGE CASES line is updated. One new test function, `test_require_callable_refuses_a_partial_subclass_whose_own_call_is_async`, comes with two sink classes, `_AsyncPartial` and `_PlainPartial`. It refuses `_AsyncPartial(print)` both alone and inside `functools.partial`, and it accepts a `_PlainPartial`. No existing assertion changed. | `rc1_repro.py`, 22 inputs, each verdict compared with whether calling the input makes a coroutine: at `5bf5bfc7`, `4 wrong verdicts of 22`; at head, `0 wrong verdicts of 22`. Every input that m-5 refused is still refused (`partial(AsyncCall())`, `partial(partial(AsyncCall()))`, `partial(async def)`, a bound async method and a partial of one). Every sync partial and plain sync callable is still accepted. `d913802b` |
| R-C2 | I re-measured before rewording. `vidbyte/lib/constants/infinite.py:147-149` now says that the envelope adds at most 4,078, that a whole event is at most 31,093, and that generator_finished's envelope, 4,079, is the largest but wraps a smaller record. Comment only; the lines stay within 72 columns. | `rc2_measure.py` uses the AC-30 builders with 5 fills, 5 summary fills, every role, 3 `at` precisions, and the 4 `json.dumps` settings. Results: `largest details: (27015, InfiniteSubagentFinishedDetails …)`, `largest whole event: (31093, InfiniteSubagentFinishedDetails … role=generator …)`, `overhead 4079 InfiniteGeneratorFinishedDetails`, `overhead 4078 InfiniteSubagentFinishedDetails`. `3bd374c3` |
| R-C3 | `vidbyte/lib/util/text.py:19-23` now says that `truncate_chars` is the cut `OutputText.truncate` and the infinite handoff share, and that other SDK cuts (`context/primitives/base.py`, `agents/aggregation.py`) behave differently and do not use it. `vidbyte/context/handoff/infinite.py:106` now says "the cut OutputText.truncate shares". Comments only. | `git grep -nE "\[: ?[a-z_]+ - len\(" vidbyte` finds 4 rstrip-plus-suffix cuts in `vidbyte/context` (`primitives/base.py:110`, `algorithms/error_correction.py:313`, `problem_space_search.py:269`, `trajectory_checkpoints.py:262`). `agents/aggregation.py:170` adds its marker after the limit. None of them calls `truncate_chars`. `2073421b` |

## Decisions and why

- **R-C1 does not take the re-review's one-clause fix.** That fix adds `inspect.iscoroutinefunction(type(value).__call__)`, which closes `AsyncPartial(print)`. But `SCRATCH/s5r2/rc1_candidates.py` shows that on 3.11 it still accepts `partial(AsyncPartial(print))` and `partial(partial(AsyncPartial(print)))`. Calling either one makes a coroutine, because the unwrap loop skips the middle layer. Checking every layer costs the same 3 lines and leaves 0 wrong verdicts. This would flip only if `functools.partial` merged partial subclasses on every supported Python, which would make the middle layer impossible. CPython 3.13 merges a subclass that has no instance `__dict__`. CPython 3.11, and 3.12 by its `_functoolsmodule.c`, merge only when `tp_call == partial_call`, so on the CI matrix the hole is real.
- **The nested test case gives the inner partial an attribute.** Without one, 3.13 would merge `partial(_AsyncPartial(print))` into a sync `partial(print)`, which the validator then rightly accepts, and the test would fail there. A partial with a `__dict__` is not merged on 3.11, 3.12 or 3.13: a probe printed `with dict: AP coroutine` on both 3.11.0 and 3.13.1. The test file's KNOWN EDGE CASES says why the attribute is there.
- **The test is a new sibling function.** I did not add an item to the m-5 test's tuple, so no existing assertion changed.
- **R-C2 states all three measured figures.** With only "4,079 over every kind", a reader would add it to 27,015 and get 31,094, which is not a real bound.
- **The R-C3 commit was first written as `docs(text): …`.** I amended it to `fix(text): …` before any push, to follow the one-commit-per-defect `fix(<scope>)` rule.

## Not done (out of scope by the briefing)

- `vidbyte/agents/infinite/README.md:101` and `vidbyte/agents/infinite/settings.py:9` list the refused async forms as "an async function, a partial of one, or an object with an async `__call__`". That is still true, but it does not name the partial-subclass case. Neither file is named by the findings, so I left both unchanged.
- The spec still says 31,091 in §9.1, §9.2 and INV-33. That forward to the siblings belongs to the orchestrator (iteration 1).
- Python 3.13 cannot import the SDK locally (`No module named 'yaml'`), so the new test was run on 3.11 only. The 3.13 behavior was checked with SDK-free probes.

## Commands run

- `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python SCRATCH/s5r2/rc1_repro.py`: at `5bf5bfc7`, `4 wrong verdicts of 22`; after the fix, `0 wrong verdicts of 22`.
- `python SCRATCH/s5r2/rc1_candidates.py` (3.11): `reviewer wrong: 2 ['partial(AsyncPartial(print))', 'partial(partial(AsyncPartial(print)))']` / `layered wrong: 0 []`. The same with `py -3.13 -I`: `reviewer wrong: 0 []` / `layered wrong: 0 []`.
- `py -3.11 -I` and `py -3.13 -I` flattening probes: without a dict, `3.11 AP … <coroutine …>` and `3.13 builtin_function_or_method … None`; with a dict, `AP coroutine` on both.
- `curl …/cpython/3.12/Modules/_functoolsmodule.c | grep -A12 'func = PyTuple_GET_ITEM(args, 0);'` gives `if (Py_TYPE(func)->tp_call == (ternaryfunc)partial_call) {`.
- `PYTHONPATH=$(pwd) python SCRATCH/s5r2/rc1_kill.py`: the results quoted in the gate matrix.
- `PYTHONIOENCODING=ascii:backslashreplace PYTHONPATH=$(pwd) python SCRATCH/s5r2/rc2_measure.py`: the results quoted under R-C2.
- `git grep -n "require_callable(" vidbyte`: only `settings.py:209` and the definition. `git grep -ln require_callable tests`: only `tests/test_record_field_validation_event_options.py`. The focused pack together with `tests/test_record_field_validation.py` gives `212 passed in 6.37s`.
- `awk 'length($0) > 72' <file> | grep -E '^\s*#'`: no output for `validation.py`, `constants/infinite.py` and `handoff/infinite.py`.
- The budget test's `_lines_after_header`: `constants/infinite.py` is at 304 of 400 and `handoff/infinite.py` at 99 of 400 before the edits (+2 and +0). `events.py` is untouched.
- The gate commands in the matrix above.
