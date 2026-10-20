# S1 spec author report: infinite-memory-derived-events

**Status:** DONE. The spec is `docs/spec/infinite-memory-derived-events/spec.md` at r1, committed as `09edbc4f` (`docs(spec): add infinite-memory-derived-events spec r1`).
- I wrote this report and did not commit it. The briefing's commit command names the spec only, so the orchestrator commits the report as it did the scout's.
- I edited no source, test, fixture, or other `docs/` file.
- I ran no gate, install, lint, or pytest. Every command I ran was read-only: `grep`, `sed`, `wc`, `awk`, `git status`/`log`, plus one import-path check.

## 1. What I read

**The pipeline inputs:**
- `request.md` (all of it);
- `context/code-map.md` (all of it);
- `reports/S0-scout.md`;
- the spec template, house style, the report formats, and the gates reference.

**Rules:** AGENTS.md (via CLAUDE.md) and `vidbyte/agents/infinite/README.md` (all of it).

**Field guide** (`field-guide/vidbyte-sdk/`):
- `comment-format.md`;
- `blocking-lint-invariants.md`;
- `runtime-boundaries.md`;
- `strict-config-dataclasses.md`;
- `local-ci-verification.md`;
- `review-scope.md`.

**Read in full:**
- `vidbyte/agents/infinite/{events,launch,runtime,memory,workspace,journal,agent}.py`;
- `vidbyte/lib/{enums,constants,dataclasses}/infinite.py`;
- `vidbyte/lib/enums/__init__.py` (the infinite block and `__all__`).

**Read in part:**
- `vidbyte/agents/runtime.py`:
  - `BaseAgentRuntimeLoopState` :160-183;
  - `_arun_once` :460-700;
  - `_middleware_denied_tool`/`_denied_tool_result` :1408-1419;
  - `_process_tool_call` :1770-1780;
  - `_runtime_metadata` :2111-2127.
- `vidbyte/agents/base.py`:
  - `_generate_reply` :986-1006;
  - `_run_direct` :1319;
  - `_run_with_tools` :1388;
  - `_runtime` :1408-1460.
- `vidbyte/middleware/builtins/delegation_limits.py` :1-70.
- `vidbyte/lib/errors/base.py` :72-90, :330.
- `vidbyte/lib/dataclasses/tools.py` :56-62, :342-372.
- `vidbyte/lib/dataclasses/validation.py`, the signatures of `require_*` and `to_tuple`.
- `vidbyte/lib/util/text.py` :128-135.
- `vidbyte/context/handoff/base.py` :29, plus `InfiniteHandoff` (title and default sections).
- `vidbyte/pipelines/parallel.py` :43.
- `vidbyte/agents/infinite/settings.py` (field list).
- `vidbyte/__init__.py` (exports).

**Tests I read to find the pins** (facts only, in spec §13):
- `test_infinite_memory_events_{stream,pairs,lifecycle,records}.py`;
- `test_infinite_memory_contract.py` :94-109, :474-489;
- `infinite_events_fixtures.py`;
- `infinite_memory_fixtures.py`.

**Not read:** PR #1159's `docs/spec/infinite-memory-events/spec.md`, per the briefing. Its constraints come from `request.md` §C and from the module headers.

**Measured, lines after the 12-line header:**

| Module | Lines |
|---|---|
| events | 400 |
| launch | 398 |
| lib dataclasses | 604 |
| workspace | 354 |
| constants | 306 |
| memory | 284 |
| settings | 205 |
| journal | 186 |
| agent | 174 |
| runtime | 131 |
| enums | 100 |
| handoff | 99 |
| `__init__` | 20 |

**Import path:** `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` printed the worktree's `vidbyte\__init__.py`.

## 2. Approaches weighed

| Question | Chosen | Runner-up | Why the choice |
|---|---|---|---|
| Where D1 comes from | DENIED `ToolCallContext`s: `state.call_contexts` for the root, `reply.metadata["tool_calls"]` for a generator | `self.middleware.events` (the request's hint) | Per call, carries the tool name, `limit`, and reason, and reaches the generator's reply. `middleware.events` mixes all middleware and never reaches a child's reply (D-2). |
| How a refusal names its rule | `VidbyteSdkError.details["rule"]` at each raise site, with a type fallback | 23 exception subclasses, or matching message text | Messages stay byte-identical. `details` is already the "safe structured details" channel, and the workspace uses it (D-5). |
| How abort is caught | Outer `try/except BaseException: announce; raise` around the pair body | A second `except BaseException` on the inner `try` | The outer wrap also catches an error raised by `_finish` inside the inner handler (EC-25). Nesting stays at exactly 3 (S024). |
| Batch id | `len(journal.started)` before the batch's first `pair_started` | `ToolCall.call_id` | Unique across launchers and resumes. `call_id` can be `None` (D-7). |
| Attempt | `journal.started.count(key)` | An in-memory counter | Survives resume with no format change (D-8). |
| Where C3's counts come from | A second `usage()` scan, only with a sink, plus `map_omitted` parsed from the map's closing line | Parsing the map header | The header is prompt text (D-12, D-13). |
| Line budget | Raise three caps: events 650, launch 460, lib records 850 | A new `vidbyte/lib/dataclasses/infinite_events.py` | Keeps the single writer whole, and the repo already has lib record modules of 828–1,205 lines. Left as Q-1, default no. |
| A8 | Verifier facts go on `verifier_finished`; `subagent_finished` gains only `error_type` | Duplicating them on both | No duplicate fields. `verdict_found` would be a status bool beside content (C002) (D-6). |

## 3. Where I disagree with the request or the scout (with evidence)

1. **D1's source.**
   - The request's hint was `middleware.events`.
   - The DENIED tool-call contexts are strictly better. `AgentRuntime._denied_tool_result` (`vidbyte/agents/runtime.py:1415-1419`) stores `{"error","reason",**decision.metadata}` on each context, and `DelegationLimitsMiddleware` puts `limit` in that metadata (`delegation_limits.py:55`, `:67`).
   - `BaseAgent._generate_reply` (`base.py:986-1006`) merges the loop's `tool_calls` into the child reply, so generator denials are reachable with no listener. `middleware.events` would not be.
2. **No room in the `events.py` budget.**
   - The file is at exactly 400/400 lines after its header today.
   - The idea list cannot fit without a cap change or a split. I chose the cap change (D-15) as an explicit §12.3 row 13 for the S2 test author, and estimated about 620 lines (cap 650).
   - `launch.py` needs about 444 (cap 460), and the lib records need about 827 (cap 850).
3. **The B5 path must be relative.**
   - `workspace.relative()` goes through `resolve_scoped_path` and can return an absolute path (`workspace.py:243-253`).
   - The spec uses `target.relative_to(workspace.root).as_posix()` instead. This is lexical: `workspace.root` is `Path(settings.root)`, unresolved (`workspace.py:66`), and `InfiniteRunJournal.find` builds the path from that same root (`journal.py:80`, `:95`).
4. **A8 collapses into B2,** and `verdict_found` is dropped (C002). `verifier_finished.verdict == unchecked` already says "no verdict".
5. **A6's "files created" is rendered as "distinct notes written".**
   - The source is card files plus `journal.root_files`, which needs no disk read in the shield.
   - Recorded as A-11. The alternative, `workspace.descriptions(run_id)`, is one line away if the user meant "created".
6. **The scout's suggested AC list for AC-36** (`run_started, batch_rejected, subagent_launched, …`) gains `batch_rejected` twice, plus `verifier_*` and `batch_finished`.
   - The root's max_parallel denial is announced at the end of the root's iteration, which comes before the next batch's launch.
   - The generator's max_depth denial is announced before `generator_finished`.
7. **Header rule 2 of `launch.py`** ("Do not catch CancelledError or BaseException") must be reworded to allow one catch-and-re-raise. S019 accepts it because it contains `raise`, and it matches `run_stopped` in `InfiniteMemoryRuntime.arun`.

## 4. Assumptions I am least sure of

- **A-2: one loop attempt per root run.** If any path gives the root a fallback attempt, `call_contexts` restarts and the `_announced` high-water mark must reset. I found no `fallback` or `algorithm` setting on `InfiniteMemoryAgentSettings`, but I did not trace every `AgentRuntime` retry path.
- **A-6: on cancel, `asyncio.gather` runs started children's handlers before the outer `CancelledError`.** I believe this holds for CPython 3.11+. If the order differs on some loop, AC-12's "precedes `run_stopped`" flips.
- **A-10: the line estimates.** They come from counting the per-method shape of the exemplar (about 9–20 lines per new method, plus enrichment). A 5 % miss on `events.py` is 30 lines. The implementer must stop BLOCKED rather than compress.
- **A-5: Ruff complexity defaults (C901 10, PLR0912 12, PLR0915 50).** These are unverified, because `lint/ruff.toml` sets none. `InfinitePair.run` grows by about 12 statements.
- **Q-1 (the split).** A reviewer may prefer a new `infinite_events.py` lib module to an 850-line cap. Either way is defensible. The spec defaults to the cap.

## 5. Self-check (Stage E)

- **Names.** §4, §8.5, and §12.3 match. I checked all 22 kind values, the 8 records, the 3 enums, `denials`, `map_omitted`, `started`, `_announce_denials`, `_rule`, `_quota`, and the `_commit`/`_finish` signatures by script.
- **Governing standards.** All 13 rows of §12.3 name one.
- **No test cases.** There are none. §13 holds facts, including expected pinned lists, marked for the test author to confirm.
- **File paths.** They appear only in §11 and §12, plus `path:symbol` in §8.2 and paths in §13, as the template's own guidance for those sections asks. Everywhere else uses module or symbol names, with the `path:line` evidence moved into §11.
- **Constants.** All 18 new constants are absent from the constants module today. Every existing constant the spec names exists, with the value it assumes.
- **N/A rows.** T-3 and T-4 each give a reason. No section is skipped.
- **Counts.**
  - 28 rule-tag sites: workspace 18 raises plus the `_entry_lines` details; memory 6; launch 3.
  - 22 kinds.
  - 30 records and 21 details records.
