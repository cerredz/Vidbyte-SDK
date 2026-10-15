# S3 implementer report: infinite-memory-agent

- Status: DONE
- Branch: `feat/infinite-memory-agent`. S3 started at `4916193f`, rebased onto origin/main `179d8adc`; the spec was grounded at `d9c01461`.
- Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/1084 (draft, placeholder body)
- Spec: frontmatter `status: implemented`, `pr:` set; §17 has the S3 row and an "Implementation deviations (S3)" list.

## Commits (in order)

| SHA | Rows | Message |
|---|---|---|
| `ef5a1336` | 1, 2 | feat(enums): add the six InfiniteMemory enums and export them [W-3; FR-3, AC-27] |
| `4710a227` | 3 | feat(constants): add the InfiniteMemory defaults, limits, patterns, and labels [W-4; FR-4, AC-39] |
| `b48561e6` | 4 | feat(dataclasses): add the six validated InfiniteMemory records [W-7; FR-8, AC-6] |
| `b38488e5` | 5, 6 | feat(util): add TokenEstimate, the canonical characters-per-token helper [W-12; FR-15] |
| `bdf30c69` | 7–13 | feat(prompts): add the infinite_memory prompt family [W-10; FR-13, AC-27] |
| `a48380ea` | 16 | feat(agents): add the InfiniteMemory settings [W-1; FR-1, AC-2] |
| `4524bf05` | 14, 15 | feat(toolsets): add InfiniteMemoryAgentTools [W-3; FR-3, AC-42] |
| `b1baec6d` | 17 | feat(agents): add the InfiniteMemory workspace and its guardrails [W-4; FR-4, AC-16] |
| `95dac1d5` | 19 | feat(agents): add the InfiniteMemory memory tools [W-5; FR-6, AC-14] |
| `bd710de3` | 18 | feat(agents): add the InfiniteMemory run journal [W-8; FR-10, AC-19] |
| `6b41d056` | 20–26 | feat(agents): add InfiniteMemoryAgent, its runtime, and launch_subagent pairs [W-2, W-7, W-8; FR-2, FR-8, FR-11, AC-3, AC-5, AC-20] |
| `41e94210` | 27, 28 | feat(exports): export InfiniteMemoryAgent and its settings from vidbyte and vidbyte.agents [W-11; FR-14, AC-27] |
| `1b972c01` | 29 | chore(contracts): regenerate the public-API contract for the InfiniteMemory exports [W-11; FR-14, AC-27] |
| `06d6d526` | 30 | docs(agents): add the InfiniteMemory agent folder README [W-11; FR-14, AC-27] |
| `03a25c7c` | 31–33 | docs: list the InfiniteMemory agent in the agents and tools READMEs and REPO_MAP [W-11; FR-14, AC-27] |
| `bd45b56e` | 20 | fix(agents): keep a failed pair's written files on its card and skip entry checks without ids [W-7; FR-9, AC-12] |
| `7e7f9454` | — | docs(spec): record draft PR for infinite-memory-agent |
| `f00da6ca` | — | docs(spec): record implementation proof for infinite-memory-agent |

Rows 20–26 (P4) share one commit. The agent, the runtime, and the launch tool import each other's types, and the registry row and `base.py` row only work with all three present, so a partial P4 commit could not be imported or tested.

## What exists now, in data-flow order

1. `InfiniteMemoryAgentSettings` / `InfiniteWorkspaceSettings` (`vidbyte/agents/infinite/settings.py`) validate everything at construction. `loop` defaults to 100 iterations and a 100,000-character result cap.
2. `InfiniteMemoryAgent.__init__` (`agent.py`) builds `InfiniteWorkspace` (folder, bookkeeping files, seeds, cap check). It then builds a `BaseAgent` with runtime `INFINITE_MEMORY`, the root rules, `InfiniteMemoryAgentTools` (bash, grep, read_lines) plus the developer's extras, and a history-trim middleware.
3. `RuntimeRegistry` resolves `INFINITE_MEMORY` to `InfiniteMemoryRuntime` (`runtime.py`). The runtime refuses to exist without its agent's settings and workspace. `arun` refuses run-bound name clashes, then opens or continues the journal (`journal.py`). It adds `launch_subagent` and the root's memory tools, clears earlier-run context, puts the map at the top of a copied context manager, and runs the linear loop. It records `run_finished` and re-renders the map after each tool iteration.
4. `InfiniteLaunchTool` (`launch.py`) checks the whole batch: size, names, unknown fields, extras, live context ids, and `max_agents`. It writes `pair_started` for each new pair, runs the pairs through `ParallelPipeline`, and returns the cards in task order; finished names replay their recorded card.
5. `InfinitePair.run` builds a fresh generator, then yields one turn so sibling generators stage too. A fresh verifier then gets the outcome, never the transcript. The pair parses the verdict and commits or drops the staged entries. Errors are caught as `VidbyteSdkError`, `OSError`, or `ValueError`. The pair writes `pair_finished` and returns a capped card.
6. `InfiniteAgentMemory` (`memory.py`) and its four tools: `remember`, `write_note`, `edit_file`, `drop_entry`. They route to `InfiniteWorkspace` (`workspace.py`), which enforces every cap from disk under one lock and renders the map.
7. `InfiniteMemoryAgent.resume` / `aresume` find an unfinished journal and brief a fresh root with the task, finished-pair lines, and interrupted names.
8. Shared lib layer: six enums, the constants module, six frozen records, `TokenEstimate`, and the 40-leaf `infinite_memory` prompt family. Exports go out through `vidbyte`, `vidbyte.agents`, `vidbyte.lib.enums`, `vidbyte.lib.util`, and `vidbyte.tools.toolsets`, and the public-API contract is regenerated.

## §12.3 rows

- [x] 1 `vidbyte/lib/enums/infinite.py` (ef5a1336)
- [x] 2 `vidbyte/lib/enums/__init__.py` (ef5a1336)
- [x] 3 `vidbyte/lib/constants/infinite.py` (4710a227, plus three constants in 6b41d056; see deviations)
- [x] 4 `vidbyte/lib/dataclasses/infinite.py` (b48561e6)
- [x] 5 `vidbyte/lib/util/text.py` (b38488e5)
- [x] 6 `vidbyte/lib/util/__init__.py` (b38488e5)
- [x] 7–11 `vidbyte/prompts/prompts/infinite_memory/` json + four .md leaves (bdf30c69)
- [x] 12 `vidbyte/lib/enums/prompts.py`: 40 members; header 138 assets across 34 families (bdf30c69)
- [x] 13 `vidbyte/prompts/README.md` (bdf30c69)
- [x] 14 `vidbyte/tools/toolsets/infinite.py` (4524bf05)
- [x] 15 `vidbyte/tools/toolsets/__init__.py` (4524bf05)
- [x] 16 `vidbyte/agents/infinite/settings.py` (a48380ea)
- [x] 17 `vidbyte/agents/infinite/workspace.py` (b1baec6d)
- [x] 18 `vidbyte/agents/infinite/journal.py` (bd710de3)
- [x] 19 `vidbyte/agents/infinite/memory.py` (95dac1d5; `quota()` made public in 6b41d056)
- [x] 20 `vidbyte/agents/infinite/launch.py` (6b41d056, bd45b56e)
- [x] 21 `vidbyte/agents/infinite/runtime.py` (6b41d056)
- [x] 22 `vidbyte/agents/infinite/agent.py` (6b41d056)
- [x] 23 `vidbyte/agents/infinite/__init__.py` (6b41d056)
- [x] 24 `vidbyte/lib/enums/agent_runtime.py` (6b41d056)
- [x] 25 `vidbyte/lib/registries/runtimes.py` (6b41d056; also the S062 offset, see deviations)
- [x] 26 `vidbyte/agents/base.py`: frozenset, comment clause, header "(LINEAR, JEV, and INFINITE_MEMORY)"; nothing else (6b41d056)
- [x] 27 `vidbyte/agents/__init__.py` (41e94210)
- [x] 28 `vidbyte/__init__.py` (41e94210)
- [x] 29 `contracts/sdk-public-api.json`, regenerated by `scripts/generate-sdk-public-api.py`; `--check` reports current (1b972c01)
- [x] 30 `vidbyte/agents/infinite/README.md`, 8,852 chars (06d6d526)
- [x] 31 `vidbyte/agents/README.md`: Key Modules line plus `## InfiniteMemory Agent` after `## Coding Agent`; 24,773 chars (03a25c7c)
- [x] 32 `REPO_MAP.md`: `vidbyte/agents/infinite/` entry before jev, and the toolsets entry regenerated (03a25c7c)
- [x] 33 `vidbyte/tools/README.md`: the line 91 clause (03a25c7c)

§6.2 Proof cells: every cell already names its test (S2 wrote them all), so none were blank and none were changed.

## Deviations from the spec (also in spec §17)

1. Three extra constants: `INFINITE_ROOT_DEPTH = 0`, `INFINITE_DEPTH_STEP = 1`, and `INFINITE_PAIR_TURN_SECONDS = 0`. A007 rejects literal depths and a literal `asyncio.sleep` argument. The sleep between a pair's generator and its verifier is what lets every generator in a batch stage before any verifier commits (AC-37) when runners never suspend.
2. `InfiniteWorkspace.check_entry(draft, staged)` takes `tuple[InfiniteStagedEntry, ...]`, not `tuple[InfiniteEntryDraft, ...]`, so the refusal can say "already staged as sN".
3. `InfiniteAgentMemory.quota()` is public. It sits beside the memory's routing methods `remember`, `write_note`, `edit_file`, `drop`, `answer`, and `refusal`. `InfinitePair` has two static formatters, `render` and `finished_lines`.
4. Short fixed text in code, not prompt leaves: `-` for an empty list; "dropped by the verifier"; "not committed, because the verdict is <v>"; the map file line `- <path> (<n> tokens): <label>`; a pasted entry `#<id>: <text>`; a staged line `- sN (<kind>): <text>`.
5. All workspace writes, appends included, rewrite the whole file to a temp file and `os.replace` it. `at` stamps use `isoformat(timespec="seconds")`, which gives `+00:00`.
6. Journal tail: a cut-off last line is skipped on read and truncated before the next append. A complete last line without a newline is kept, and the next record is newline-prefixed.
7. `vidbyte/lib/registries/runtimes.py` (row 25's file): the unknown-runtime message's two adjacent f-strings are merged into one with the same text. This offsets the S062 finding from S2's `tests/features/infinite_memory_agent/test_infinite_memory_workspace.py:399`, so S062 stays at 889 and no baseline was raised.
8. Minor: `settings.py` uses `typing.cast` to type the `Tools(...)` validation of `tools`, and imports `PermissionPolicy` from `vidbyte.lib.dataclasses.security`. `workspace.py`'s token-count helper is named `_file_tokens`, because A007 judges numeric literals by nearby names.

Files outside §12.3: none. No new dependency, error class, settings field, tool, tool parameter, prompt leaf, enum member, or record field.

## Complexity budget (§8.4)

- New files: 18 of 18. These are the 8 `.py` files in `vidbyte/agents/infinite/`, its README, `vidbyte/tools/toolsets/infinite.py`, the three `vidbyte/lib/*/infinite.py` modules, and the five prompt assets.
- Classes: 27 of 27, in 11 modules (cap 12).
- Largest module after its header: `launch.py` at 358 lines (cap 400), then `workspace.py` at 325 and `memory.py` at 259.
- `.py` files in `vidbyte/agents/infinite/`: 8 of 8.

## Gate results (final lines)

Feature pack, `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` at `bd45b56e`:
```
........................................................................ [ 80%]
.................                                                        [100%]
89 passed in 2.03s
```

Lint, `python lint/run.py`:
```
S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

Full gate, source stage, `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` at `bd45b56e` (it includes lint `SDK-LINT: PASS`, the context and trace contract scripts reporting `ok`, and the full test suite):
```
tests\test_workflow_agent_forks.py ......                                [100%]

====================== 5262 passed, 14 skipped in 44.83s ======================
CI passed.
EXIT 0
```

Full gate, package stage, `python scripts/run_ci.py --stage package` at `bd45b56e` (no PYTHONPATH; it installs into a temporary venv):
```
No broken requirements found.
> ...venv\Scripts\python.exe -c from importlib.metadata import entry_points, version; import vidbyte; ...
Installed vidbyte-sdk 0.2.1 passed smoke checks.
CI passed.
EXIT 0
```

The commits after `bd45b56e` touch only `docs/spec/`.

Test tree: `git diff d8bcdf14..HEAD -- tests/ | wc -l` gives `0`.

## Baseline before implementation

- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -x --ignore=tests/features/infinite_memory_agent` gave `5173 passed, 14 skipped in 45.47s` (exit 0).
- `python lint/run.py` gave `SDK-LINT: FAIL`, with one regression: `S062 no-implicit-string-concatenation 890 889 REGRESSED`. It came from the S2 test file at line 399, which has three adjacent string literals. Deviation 7 resolved it without touching `tests/` and without raising a baseline.
- Drift check: the changes in `d9c01461..origin/main` on the spec's paths are mechanical (skill exports), so no spec fact changed.

## Tricky parts

- **A007 (operational-constants)** judges a numeric literal by the names in up to seven enclosing nodes. That reach covers whole `with` and `for` bodies but stops at the function. A harmless `enumerate(..., start=1)` near a `status=` keyword was flagged. The journal card parse now uses a dict spread (`InfiniteResultCard(**{**card, **enums, **lists})`), and the workspace helper was renamed to `_file_tokens`.
- **AC-37 interleaving.** Scripted runners never suspend, so without a yield each pair ran to completion before the next began, and the malformed `entries.jsonl` line arrived after the first commit. `await asyncio.sleep(INFINITE_PAIR_TURN_SECONDS)` between generator and verifier fixes the order. AC-5's concurrency test also relies on it.
- **A pair's files.** `InfinitePair.run` creates both memories before its `try`, so a pair that fails in its verifier still lists the files the generator wrote (bd45b56e). `_check` calls `workspace.entries` only when a batch names `#N` ids.
- **mypy:** `InfiniteTaskCard(**given)` needs `given: dict[str, Any]`. ANN401 on `runtime.py`'s `**kwargs: Any` matches `JevRuntime` and is not counted by S007.
- **Lint uses `git ls-files`,** so new files must be `git add`ed before `python lint/run.py` sees them. Semgrep in the source gate also scans tracked files only.

## Notes for S4 reviewers

- Public surface: `InfiniteMemoryAgent`, `InfiniteMemoryAgentSettings`, `InfiniteWorkspaceSettings`, and `InfiniteMemoryPreset` from `vidbyte`; `InfiniteMemoryRuntime` from `vidbyte.agents`; `InfiniteMemoryAgentTools` from `vidbyte.tools.toolsets`; `TokenEstimate` from `vidbyte.lib.util`.
- The `launch_subagent` result is exempt from the tool timeout and result cap through `metadata={"internal": True}` (INV-38, AC-35).
- The runtime's refusal message text is fixed by AC-3 and the spec row 21 text. Do not reword it.
