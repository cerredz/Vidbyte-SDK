# S4 findings verifier — infinite-memory-events

Inputs:
- The three lens reports: `S4-review-conformance.md`, `S4-review-conventions.md`, `S4-review-engineering.md`.
- spec.md r3, test-plan.md, AGENTS.md, and the field guide (`comment-format.md`, `class-bound-helpers.md`, `strict-config-dataclasses.md`).
- The diff `origin/feat/infinite-memory-agent...24297ccf`.

Output: `docs/spec/infinite-memory-events/review.md`. No source, test, or spec file was edited, and no git state was changed.

`SCRATCH` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/3e21357e-da06-45b9-8218-c0b25aec2a6d/scratchpad`.

## Result

**MERGEABLE AFTER FIXES.**

| Count | What |
|---|---|
| 0 | confirmed Blockers |
| 7 | confirmed Majors (one is `needs-decision`) |
| 10 | Minors (one is the verifier's own) |
| 1 | finding downgraded (R-V1) |
| 1 | reviewer fix refuted (R-E4's source fix) |
| 0 | findings refuted outright |

## Merge map (original ID → merged ID)

| Original | Lens | Merged | Disposition |
|---|---|---|---|
| R-V3 | conventions | R-1 | confirmed Major |
| R-E1 | engineering | R-2 | confirmed Major |
| R-E3 | engineering | R-3 | confirmed Major |
| R-E4 | engineering (conformance V-12 disagreed) | R-4 | confirmed Major; the reviewer's fix was refuted and replaced by a test-only fix |
| R-E2 | engineering | R-5 | confirmed Major |
| R-E5 | engineering | R-6 | confirmed Major |
| R-V2 + R-C1 | conventions + conformance | R-7 | confirmed Major, `needs-decision`. Same root cause and lines (`context/handoff/infinite.py:106-108`, README:135), so the higher severity is kept. |
| R-V1 | conventions (conformance V-6 accepted the packing) | m-1 | downgraded Major → Minor |
| R-E6 | engineering | m-2 | Minor, follow-up |
| R-E7 | engineering | m-3 | Minor, follow-up |
| R-E8 | engineering | m-4 | Minor, follow-up (cross-referenced to R-2) |
| R-E9 | engineering | m-5 | Minor, trivial |
| R-V5 | conventions | m-6 | Minor, trivial |
| R-V6 | conventions | m-7 | Minor, trivial |
| — | verifier | m-8 | Minor, trivial: README:122 says 31,091; the measured figure is 31,093 |
| R-V4 | conventions | m-9 | Minor, follow-up (outside §12.3) |
| R-V7 + conformance V-13 | conventions + conformance | m-10 | Minor, follow-up (S6 PR body) |

The engineering report's own dismissals stay dismissed. Those are `finished_files_writer_only`, `staged_before_append`, `dropped_before_remove`, `handoff_atomic_off`, `relative_no_resolve_fallback`, EC-9, and D-9. The verifier saw nothing that reopens them.

## Method

Every Blocker and Major was re-established with the verifier's own commands. No reviewer's output is quoted as evidence.

- **Own mutation runner.** `SCRATCH/v_mut.py`:
  - It applies the reviewer's named mutations to the scratch copy `SCRATCH/mut`. Each pattern was read and judged to be a faithful, plausible one-line regression.
  - It runs the briefing's exact focused command, without `-x` and without overriding addopts.
  - It restores each file byte for byte. `git -C SCRATCH/mut status --short -- '*.py'` was empty after every batch.
  - Before use, the scratch copy was checked equal to the worktree (`diff --strip-trailing-cr`: same apart from CRLF). Its baseline was `186 passed in 5.80s`.
- **Behaviour probes.** Each probe is a real scripted run or uses real objects. Only the model runner is fake, as §13 allows.
  - `SCRATCH/v_probe_r_e1.py`
  - `SCRATCH/v_probe_r_e2.py`
  - `SCRATCH/v_probe_r_e3.py`
- **Fix-feasibility tests.** These scratch tests prove the proposed new-test fixes can be written without mocks of real seams, and that they kill the surviving mutants. Neither is committed.
  - `SCRATCH/vtests/test_v_no_sink.py`
  - `SCRATCH/vtests/test_v_all_depths.py`

Baseline at the worktree:
```
$ PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider
........................................................................ [ 77%]
..........................................                               [100%]
186 passed in 5.90s
```
`git status --porcelain` was empty before this report and review.md were written. Python is 3.11.0.

## Verifications

### R-1 (R-V3): lib headers send routine edits into `docs/spec`. CONFIRMED, Major.

The three sentences, read at 24297ccf:
- `vidbyte/lib/constants/infinite.py:7`: "… a new details field adds its cap here and its worst case to the table in docs/spec/infinite-memory-events/spec.md section 9.1".
- `vidbyte/lib/dataclasses/infinite.py:7`: "… a new details field adds its cap and its worst case to docs/spec/infinite-memory-events/spec.md section 9.1".
- `vidbyte/lib/dataclasses/infinite.py:9`: "The worst-case size of every details record lives in docs/spec/infinite-memory-events/spec.md section 9.1".

Counts:
```
origin/main: MODIFICATION->docs 0, EDGE CASES->docs 0, RELATED DOCS->docs 393
origin/feat/infinite-memory-agent: MODIFICATION->docs 0, EDGE CASES->docs 0, RELATED DOCS->docs 402
24297ccf: MODIFICATION->docs 2, EDGE CASES->docs 1, RELATED DOCS->docs 404
```

How the rules apply:
- **The rule broken.** AGENTS.md lists this as one of two rules for every change: "Do not grep, glob, or read files under `docs/` as part of ordinary work: those design documents are large and not kept in sync with the implementation."
- **Where the wording came from.** Spec §12.3 rows 3 and 4 asked for this wording. House style says the repo wins over pipeline documents, and AGENTS.md is the repo.
- **What is not a problem.** RELATED DOCS pointers into `docs/` are normal: there are 393 on main.
- **The enforced source.** The figures that are actually enforced are `_FIGURES` (`test_infinite_memory_events_records.py:53`) and `_FIELDS` (`:87`).

**Severity:** Major, not Blocker. The literal calibration ("contradicts AGENTS.md") would allow Blocker. It stays Major because the sentences are header prose that would misdirect later maintenance; they change no runtime behaviour, and the implementer followed an approved spec row.

### R-2 (R-E1): `relative` lets `RuntimeError` escape. CONFIRMED, Major.

The code at `workspace.py:249-252` is `try: return FileSystemPermissions.resolve_scoped_path(...)...` with `except (ToolExecutionError, ValueError, OSError): return path`. `resolve_scoped_path` (`vidbyte/lib/tools/filesystem/permissions.py:14-22`) calls `(root / Path(path)).expanduser().resolve()`. On Python 3.11, that call raises `RuntimeError` on a symlink loop. The spec says the method never raises: FR-14 ("never raising"), D-23 ("It never raises"), and EC-35. The probe scenario is realistic: run 1's root creates `notes/a.md` through `write_note`, run 2 never touches it, and then a two-link loop replaces the note.

At the worktree:
```
LOG vidbyte.agents.infinite.events WARNING infinite_event_failed run_id=20261016T193108Z-de45fe91 kind=file_written error_type=RuntimeError
files.jsonl: {"path": "notes/a.md", "description": "Root note", "by": "root", "run": "20261016T193108Z-3e698c14", ...}
relative('notes/a.md') -> RAISED RuntimeError Symlink loop from 'C:\\Users\\...\\memory\\n
run_handoff(run 1, wrote the note) -> RAISED RuntimeError Symlink loop from ...
run_handoff(run 2, never touched it) -> RAISED RuntimeError Symlink loop from ...
file_written events delivered: 0
```

With the fix applied in `SCRATCH/mut` (`except (ToolExecutionError, ValueError, OSError, RuntimeError):`), then restored:
```
relative('notes/a.md') -> OK 'notes/a.md'
run_handoff(run 1, wrote the note) -> OK '- notes/a.md: Root note'
run_handoff(run 2, never touched it) -> OK '(none)'
file_written events delivered: 1
186 passed in 6.02s
```

The fix keeps the line count. The engineering reviewer reported 182 passed after the fix; the verifier's run gives 186.

On the test: the test plan skipped EC-35 because "symlinks need elevated rights on Windows". Symlinks work on this machine. A test can call `pytest.skip` when `os.symlink` raises `OSError`. That keeps the filesystem seam real, as §13 asks, instead of monkeypatching `FileSystemPermissions`.

### R-3 (R-E3): the handoff surrogate scrub has no test. CONFIRMED, Major.

```
handoff_no_surrogate_fix: SURVIVED :: 186 passed in 5.80s :: []
```
Probe: a scripted root replies `"Prices checked \ud800 done."`, then `run_handoff` is called.
```
== baseline (worktree)
journal last line: {"event": "run_finished", ..., "answer": "Prices checked
run_handoff OK; Outcome: 'Task: Compare prices.\nStop reason: final_response\n\nPrices checked ? done.' ; file decodes: ...
== mutation handoff_no_surrogate_fix (scratch copy)
run_handoff RAISED UnicodeEncodeError 'utf-8' codec can't encode character '\ud800' in position 132: surrogates not allowed
```
EC-17 and INV-23 require `?` in the handoff, and that the write cannot raise. AC-35 tests events only.

### R-4 (R-E4): NFR-2's "0 InfiniteEvent instances" is not measured. CONFIRMED, Major; the reviewer's fix is REFUTED.

```
no_sink_still_builds: SURVIVED :: 186 passed in 6.07s :: []
deliver_guard_removed: SURVIVED :: 186 passed in 5.74s :: []
no_sink_still_builds+deliver_guard_removed: KILLED :: 1 failed, 185 passed in 6.05s :: [...test_without_a_sink_the_journal_gains_only_answer_and_files_and_nothing_is_logged]
```

What the spec requires:
- NFR-2 (P0) has the target "0 `InfiniteEvent` instances and 0 log records … (AC-20)". AC-20's test checks journal keys and logs only.
- The test plan declined only "Overhead with no sink (performance)" because "no benchmark harness". Counting instances needs no benchmark.

Reviewer fix, checked with mypy (pinned config, scratch copy, guard removed, then restored):
```
== baseline
== guard removed
vidbyte\agents\infinite\events.py:341:20: error: "None" not callable  [misc]
```
That regresses the S009 ratchet. §14 forbids `type: ignore`, and `events.py` is at 400 of 400 lines, so any line-adding source fix fails the budget test. The fix is therefore test-only.

Scratch test `vtests/test_v_no_sink.py`:
- It calls all 14 public methods on `InfiniteEvents(None, run_id)` with `object()` arguments.
- It counts `InfiniteEvent.__post_init__` through `monkeypatch`, which instruments without replacing behaviour.
- It asserts 0 built and no events-logger records.

```
== baseline (worktree code)
1 passed in 0.71s
no_sink_still_builds: KILLED :: 1 failed, 186 passed in 5.96s :: ['FAILED ::test_without_a_sink_no_public_method_builds_an_event_or_logs - asser...']
```

**Adjudication with conformance V-12.** Conformance said "NFR-2's measurable checks pass: 0 InfiniteEvent objects". That is true of the code today: the scratch test passes at head. But no committed test measures it, so the finding is about the test pack, and it stands.

### R-5 (R-E2): D-18 has no test for several parts or for none. CONFIRMED, Major.

```
cost_any_not_all: SURVIVED :: 186 passed in 5.57s :: []
cost_empty_rollups_known: SURVIVED :: 186 passed in 5.67s :: []
cost_ignores_complete: KILLED :: 1 failed, 185 passed ... [cost-incomplete]   (control: the runner kills)
```
Probe: a real `InfiniteLaunchTool` and `InfinitePair`, with `pair.replies` set, then `events.subagent_finished`.
```
== baseline (worktree)
gen complete 0.02 + ver incomplete 0.01 -> (8, None)
no replies (generator raised) -> (0, None)
== mutation cost_any_not_all
gen complete 0.02 + ver incomplete 0.01 -> (8, 0.03)
== mutation cost_empty_rollups_known
no replies (generator raised) -> (0, 0)
```

Why it matters:
- D-18 says "'Unknown' is never shown as 0 dollars." The `(0, 0)` case is a generator that raised, which may have been billed.
- `test-plan.md:81` routes EC-14's usage sum to "AC-23's code path". The AC-23 test (`test_infinite_memory_events_stream.py:418`) asserts only `.tokens`.

### R-6 (R-E5): counts over every depth are tested only at the root. CONFIRMED, Major.

```
resumed_root_only_finished: SURVIVED :: 186 passed in 6.16s :: []
resumed_root_only_interrupted: SURVIVED :: 186 passed in 5.75s :: []
run_finished_root_pairs: SURVIVED :: 186 passed in 6.15s :: []
```

What the spec requires: §9.1 `run_resumed` says "`finished` = `len(journal.cards)`; `interrupted` = `journal.interrupted` (pair keys, all depths)". `run_finished` says "`pairs` = `len(journal.cards)`".

Why the regression is plausible: the root-only twins `finished_children(INFINITE_ROOT_KEY)` and `interrupted_children(...)` are what `_resume_prompt` uses (`agent.py`).

Scratch test `vtests/test_v_all_depths.py` uses a hand-written journal, an approved §13 seam. The root pair `root/a` is started, the nested `root/a/gen/b` is finished, and the nested `root/a/gen/c` is started. Then `agent.resume()` runs with a list sink.
```
== baseline (worktree code)   1 passed in 0.72s
resumed_root_only_finished: KILLED :: 1 failed, 186 passed in 5.61s
resumed_root_only_interrupted: KILLED :: 1 failed, 186 passed in 5.68s
run_finished_root_pairs: KILLED :: 1 failed, 186 passed in 5.72s
```

### R-7 (R-V2 + R-C1): the handoff repeats `OutputText.truncate` inline. CONFIRMED, Major, `needs-decision`.

**Import probe.** One line was inserted after `from vidbyte.context.handoff.base import Handoff` in `SCRATCH/mut`, then restored.
```
== from vidbyte.lib.outputs.text import OutputText
ImportError: cannot import name 'FileSystemToolConfig' from partially initialized module 'vidbyte.lib.dataclasses' (most likely due to a circular import)
== from vidbyte.lib.util.text import TokenEstimate
import vidbyte OK
```

**The lib home.** The `vidbyte/lib/util/text.py` header says:
- COMMON MODIFICATION PATTERNS: "Add another general text helper as a @staticmethod here."
- WHAT NOT TO DO 1: "Do not import any SDK feature package."

So a cycle-free canonical home exists. AGENTS.md style 5 says: "if one is close, add the option you need to it rather than copying it into a variant beside your feature … If none exists, create the helper in `vidbyte/lib/`". The field guide's `class-bound-helpers.md` says to search `vidbyte/lib` and extend what exists. Spec §17 deviation 3 records that fixing the façade import "cascades". It does not record that the `lib/util/text.py` route was checked.

**Behaviour is the same today.** An own differential check of `InfiniteHandoff._lines([t])` against `OutputText.truncate(" ".join(t.split()), 1000, marker=" … [cut]")` used lengths 0 to 5,000. The characters were whitespace, `\u2028`, `\x85`, emoji and CJK. Result: `cases 600 mismatches 0`.

**README:135 is false for list lines.** It says "`OutputText.truncate` (`vidbyte/lib/outputs/text.py`) cuts event and handoff text with the infinite marker", inside a paragraph that opens "rather than private copies".

**Severity.** Major, not Blocker. The output is not wrong, and the departure is documented in three places: spec §17, the handoff header, and README:163. AGENTS.md style 5 (one helper) also conflicts here with a pre-existing breach of style 3 (the upward import `lib/dataclasses/__init__.py:19` → `vidbyte.context.primitives`). It is not downgraded to Minor, because this owner's review history enforces canonical helpers (`class-bound-helpers.md`, the #1084 comment) and README:135 states something untrue. A human reviewer would comment.

**Why `needs-decision`.** The full fix adds a helper to `vidbyte/lib/util/text.py`, which is not a §12.3 row. §14 lists "Touching files outside §12.3" under "Ask first". No fix inside the §12.3 files is good:
- None of the in-scope lib files is a fitting home: they are constants, records, validators, and `outputs/text.py`, which hits the cycle.
- Moving the line cut into `run_handoff` would take INV-37's line bound out of the renderers.

**Options.**

| Option | What | Size and checks |
|---|---|---|
| A (recommended) | Add one `@staticmethod` character cut to `vidbyte/lib/util/text.py`, make `OutputText.truncate` delegate to it, and call it from `_lines`. Optionally host the surrogate scrub there too, but `events.py` stays ≤ 400 lines. | About 10 code lines plus header and README updates. Behaviour is pinned by `tests/test_output_text_truncate_marker.py`, AC-33, and `tests/features/agent_output_connectors/` (`"\n\n[truncated]"`). |
| B | Reword README:135 only, and file a follow-up to remove the upward import. | 1 line. |

**Adjudication.** Conformance rated this Minor, saying the defense wins because of the cycle. Conventions rated it Major, because the cycle-free lib home exists. The verifier sides with conventions on whether the issue is real (the cycle-free path is proven above) and with conformance on whether the output is correct (proven equal). Because the remedy crosses the spec's file boundary, the decision goes to the orchestrator.

## Downgraded

### R-V1: packed constructors. Major → Minor (m-1).

The orchestrator's constraint (d) was checked first: is any written rule broken?
- `lint/ruff.toml` has `target-version` and `[lint] select = ["TID251"]` only. It has no `[format]` section and no `line-length`.
- `grep -rn "ruff format\|line-length" lint/run.py scripts/run_ci.py .github/workflows/*.yml pyproject.toml` finds nothing.
- `python -m ruff format --check vidbyte/agents/infinite/ vidbyte/agents/jev/` reports `38 files would be reformatted, 10 files already formatted`. The formatter is not a gate in this repo, so "accepted formatter output" cannot be the test.
- AGENTS.md has no layout rule. `comment-format.md` covers `#` comments only. `awk 'length($0) > 72' events.py | grep -cE '^\s*#'` prints `0`.

The repo's grain, from AST counts over `vidbyte/**/*.py` (scripts `SCRATCH/v_pack.py` and `SCRATCH/v_widths.py`):

| Measure | Base `origin/feat/infinite-memory-agent` | Head `24297ccf` |
|---|---|---|
| Calls with ≥ 4 keywords, one keyword per line | 1,434 | 1,435 |
| Calls with ≥ 4 keywords, all on one line | 500 | 520 |
| Calls with ≥ 4 keywords, several per line over several lines | 0 | 4, all in `events.py` |
| Code lines over 160 / over 200 characters | 4,361 / 3,525 | — |

NFR-1 holds literally. `_lines_after_header` gives events 400 (cap 400), launch 398 (410), lib records 604 (620), and handoff 100 (400). Spec §17 deviation 4 records the packing.

**Conclusion.** No rule is broken, so the cap-and-reflow fix the reviewer proposed is not needed. What remains is a readability follow-up: the mixed layout is new to the repo, and the module has no headroom.

**Adjudication with conformance V-6,** which accepted the packing: agreed on conformance. The readability note stays as a Minor.

## Minors: verification notes

- **m-2 (R-E6) and m-3 (R-E7).** The verifier's runner re-ran all seven mutants, and each gave `SURVIVED :: 186 passed`: `batch_rejected_root_envelope`, `replayed_root_envelope`, `key_no_verifier_suffix`, `interrupted_not_shortened`, `handoff_drop_root_files`, `description_on_append`, `duration_seconds`. They are kept Minor, as the reviewer filed them. The paths are rarer (nested rejections and replays, keys over 508 characters, appends to existing notes by the root only), or the test plan declined exact durations on purpose. They are follow-ups, because each needs a new scenario.
- **m-4 (R-E8).** Measured here at `relative(): 193 us per call; 10,000 descriptions -> 1.93 s per run_handoff`. `INFINITE_DEFAULT_MAX_FILES = 2_000` bounds live notes. Recorded paths are already relative POSIX paths (`_note_path` returns `relative.as_posix()`, written at `workspace.py:184`, same as the base). It is not scope-adding in the sense of a new feature; it is a performance follow-up.
- **m-5 (R-E9).** Probe output:
  ```
  async def                                refused
  partial(async def)                       refused
  object with async __call__               refused
  partial(object with async __call__)      ACCEPTED
  partial(partial(async def))              refused
  ```
  The method's own `@intent` comment at `validation.py:155-159` claims every async form is refused.
- **m-6, m-7, m-10.** Confirmed by reading:
  - m-6: `agent.py:158`.
  - m-7: `memory.py:82-85` against the event calls at `:104`, `:112`, `:123`.
  - m-10: `git show --stat 8cd15dab` touches `workspace.py` only, and `72f1f56d` touches `context/handoff/infinite.py` only.
- **m-8 [verifier].** README:122 says "a whole event at most 31,091". Measured with the AC-30 `_worst` and `_build` builders:
  ```
  U+1F600 us=0 role=generator event max 31086 details max 27015
  U+1F600 us=789000 role=generator event max 31093 details max 27015
  ```
  The method used a 512-character `agent_key`, a 280-character U+1F600 summary, `depth` 2^63−1, and the AC-13 serializer `json.dumps(asdict(event), default=isoformat)` under the four settings. Every real event's `at` has milliseconds, so 31,093 is the true bound. All consumer bounds (32,768 and 65,536) are unaffected. The engineering report noted this and did not file it; it is filed here because product docs state the wrong figure.
- **m-9 (R-V4).** `grep -n "Infinite" llms.txt` finds nothing. `llms.txt` is hand-maintained; no generator references it. It is not a §12.3 row, so it is a follow-up.

## Severity blind spots checked

1. **The R-E4 fix crosses into the mypy ratchet.** The reviewer's fix would break S009, as shown above, so R-4 is test-only.
2. **The R-V2 fix crosses the spec's file boundary.** It lands in `lib/util/text.py`, outside §12.3, under §14's "Ask first". Hence `needs-decision`.
3. **The R-V3 fix departs from the spec's §12.3 row 3–4 wording.** The repo rule wins. The repair report must say so, so that the orchestrator updates spec §17.
4. **R-V4's fix touches `llms.txt`,** which is outside §12.3. Hence a follow-up.
5. **Budgets bound every fix.** `events.py` is at 400/400, so no confirmed fix may add a line there. Lib records are at 604/620: do not wrap the alias. `workspace.py` 353, `agent.py` 173, `memory.py` 277, constants 301 and handoff 100 have room.
6. **S2 tests may not be edited.** Every fix a reviewer phrased as "extend AC-xx" or "add a param" is rewritten in review.md as a new test function.
7. **Tools on worker threads (INV-5, A-2).** Not an issue. Every memory and launch tool is `async def execute` (`memory.py:164`, `:216`, `:250`, `:279`; `launch.py:122`), and there is no `to_thread` or `run_in_executor` on these paths.
8. **A deep copy of the settings would detach `on_event`.** Not an issue. Nothing in `vidbyte/agents/infinite/` deep-copies the settings or calls `asdict` on them, and `BaseAgent` passes `_runtime_extension_kwargs` unchanged.
9. **Other ways `relative` could raise.** `expanduser()` cannot fire, because the joined path starts with the absolute root. A NUL byte raises `ValueError`, which is caught. Only the symlink-loop `RuntimeError` escapes, which is R-2.

Nothing further reached Blocker class.

## Commands run (final lines)

- **Focused pack at the worktree:** `186 passed in 5.90s`. In `SCRATCH/mut`: `186 passed in 5.80s`.
- **`python SCRATCH/v_mut.py`:**
  - Major candidates: `cost_any_not_all`, `cost_empty_rollups_known`, `handoff_no_surrogate_fix`, `no_sink_still_builds`, `deliver_guard_removed`, `resumed_root_only_finished`, `resumed_root_only_interrupted`, `run_finished_root_pairs` → all `SURVIVED :: 186 passed`.
  - `no_sink_still_builds+deliver_guard_removed` → `KILLED :: 1 failed, 185 passed`.
  - Minor candidates (the seven listed for m-2 and m-3) → all `SURVIVED :: 186 passed`.
  - Control `cost_ignores_complete` → `KILLED :: 1 failed, 185 passed`.
- **Probes:**
  - `SCRATCH/v_probe_r_e1.py`, `SCRATCH/v_probe_r_e2.py` and `SCRATCH/v_probe_r_e3.py`: outputs quoted above.
  - The R-E1 fix in the scratch copy: `186 passed in 6.02s`.
- **Scratch tests against the worktree code:**
  - `vtests/test_v_no_sink.py` → `1 passed in 0.71s`.
  - `vtests/test_v_all_depths.py` → `1 passed in 0.72s`.
- **Scratch tests against mutants:** `no_sink_still_builds` and the three R-6 mutants → `KILLED :: 1 failed, 186 passed`.
- **mypy:** `python -m mypy --config-file <worktree>/lint/mypy.ini --cache-dir SCRATCH/v_mypy_cache vidbyte/agents/infinite/events.py` in the scratch copy. Baseline: no `events.py` errors. With the guard removed: `events.py:341:20: error: "None" not callable [misc]`.
- **Import probes:** quoted under R-7.
- **Differential check:** `cases 600 mismatches 0`.
- **Whole-event size:** quoted under m-8.
- **`git grep` header counts:** quoted under R-1.
- **`git show --stat`** of `8cd15dab`, `72f1f56d`, `5e5b845c` and `e8c5ef27`.
- **Budget counts:** `_lines_after_header` from the contract test → `events.py 400`, `launch.py 398`, `lib/dataclasses/infinite.py 604`, `context/handoff/infinite.py 100`, constants `301`, `memory.py 277`, `workspace.py 353`, `agent.py 173`.
- **Not run:**
  - `lint/run.py` in full. No finding's verification needed it, and the conventions lens already ran it (`SDK-LINT: PASS`). The S009 question was answered with the pinned mypy configuration directly.
  - semgrep, which crashes in the global Python.
  - The full source gate.
