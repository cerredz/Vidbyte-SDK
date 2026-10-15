# S2 test author: InfiniteMemory agent

STATUS: DONE. The pack in `tests/features/infinite_memory_agent/` binds to the spec r3 names and has 89 cases across 7 modules. Every case is red for a missing-feature reason. The rest of the suite is unchanged: 4767 passed and 13 skipped, the same as the baseline. `test-plan.md` maps all of AC-1 – AC-42, and spec §6.2's Proof column names the test for each AC.

## Inventory

| File | Cases | Spec IDs |
|---|---|---|
| `README.md` | — | boundary, File Index (S020 parity), run command |
| `FEATURE.md` | — | contract, invariants, failure inventory with the test for each, omitted strategies |
| `infinite_memory_fixtures.py` | — | `ScriptedTree` (the runner for every agent, routed by name, patched at `BaseAgent._runner_for_model`), `Gate`/`Signal`, builders, journal and entry writers in the §9.1 shape, template matchers |
| `test_infinite_memory_acceptance.py` | 4 | AC-1, AC-9, AC-24, AC-30 |
| `test_infinite_memory_contract.py` | 24 | AC-2 with INV-2 (9), AC-3, AC-4 (2), AC-25, AC-27 (3), AC-39, INV-21/EC-3 (2), INV-33, §9.1, §9.2 schema, FR-15, NFR-1 |
| `test_infinite_memory_delegation.py` | 21 | AC-5, AC-6 (9), AC-7, AC-8, AC-12 (2), AC-13, AC-26, AC-28/AC-36, AC-29, AC-31, AC-32, AC-35 |
| `test_infinite_memory_verification.py` | 12 | AC-10 (2), AC-11, AC-37, AC-38 (7), EC-17 |
| `test_infinite_memory_workspace.py` | 12 | AC-14, AC-15, AC-16 (3), AC-17, AC-18 (2), AC-34, AC-42, INV-22 labels and usage, D-15 |
| `test_infinite_memory_resume.py` | 14 | AC-19, AC-20, INV-28, AC-21 (5), AC-22 (2), AC-23, AC-41, NFR-3, T-3 |
| `test_infinite_memory_context.py` | 2 | AC-33, AC-40 |

The only fake is the model runner, as spec §13 requires. The filesystem (`tmp_path`), `InfiniteWorkspace`, `InfiniteRunJournal`, `ParallelPipeline`, the prompt catalog, and `bash` are real. Concurrency, ordering, and cancellation use asyncio events; nothing sleeps or reads the clock. Each guard timeout (20 s) only turns a hang into a failure. Every path comes from `tmp_path`, files are written with explicit `encoding="utf-8"` (and `newline="\n"` wherever token counts matter), and the bash case runs on Git for Windows bash as well as Linux bash.

## Pruning and changes made while writing

- **Dropped or kept out** (each is listed in the test plan's NOT-written table): EC-15 and EC-16 sibling races (they would need polling); per-record `__post_init__` tests (duplicates of the tool-boundary tests); the accepted limitations (EC-30/31/36/41/45/46/47/48/49); EC-14, EC-32 and EC-40 (allowed behavior); EC-37 (nondeterministic by design); EC-44 (existing permission tests own it); MCP servers (`add_tool` takes the same path, per §13); NFR-4 and stress tests; INV-34 and INV-37 parity (the existing suite and C016 own them); everything under NG and Q.
- **Assertions removed as over-specification:**
  - AC-32 had required that the generator's own prompt never reach the verifier. INV-12 lists what the verifier receives but forbids only the "transcript", so that went beyond the spec.
  - The map test had required that `.runs/` never appear in the map. The spec excludes `.runs/` only from usage, which the test still checks.
- **Added during review:** EC-17, the commit-time cap re-check. It is deterministic (the verifier's call fills the workspace before the commit), and it covers the cap half of INV-16 that AC-37 does not.
- **Fixed in the harness:** a callable step that returns another callable step (`after(...)` wrapping `observe(...)`) is now resolved in a loop. A plain-`BaseAgent` probe found this.
- **Harness validated without the feature.** Scratch probes against a plain `BaseAgent` confirmed four things. The tool-call and final-reply shapes drive the loop, and the error envelope begins with `[tool_error`. `Gate(2)` opens only with two agents inside a model call at once, and a lone waiter fails with a recorded problem. A runner `VidbyteSdkError` is not retried. The map item renders under `### [infinite_memory_map] Workspace map` with its content verbatim.

## Red run (exact)

Baseline at `1bc5c857`: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` → `4767 passed, 13 skipped in 38.37s`.

```
PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider
89 failed in 1.86s
(--tb=line reasons) 73 ModuleNotFoundError: No module named 'vidbyte.agents.infinite'
                     3 ModuleNotFoundError: No module named 'vidbyte.lib.constants.infinite'
                     3 ImportError: cannot import name 'InfiniteMemoryPreset' from 'vidbyte.lib.enums'
                     2 ImportError: cannot import name 'InfiniteMemoryAgent' from 'vidbyte'
                     1 ImportError: cannot import name 'TokenEstimate' from 'vidbyte.lib.util'
                     1 ImportError: cannot import name 'InfiniteMemoryRuntime' from 'vidbyte.agents'
                     1 ImportError: cannot import name 'InfiniteEntryKind' from 'vidbyte.lib.enums'
                     1 ImportError: cannot import name 'InfiniteAgentRole' from 'vidbyte.lib.enums'
                     1 ConfigurationError: Prompt family does not exist: 'infinite_memory'
                     1 ImportError: import error in vidbyte.agents.infinite (AC-33 monkeypatch target)
                     1 AssertionError: vidbyte/agents/infinite does not exist (NFR-1)
                     1 AssertionError: assert {} == {'INFINITE_ME...ription', ...} (no Prompt members)

PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider
89 failed, 4767 passed, 13 skipped in 47.47s
FAILED/ERROR lines outside tests/features/infinite_memory_agent/: 0 · collected 4868 = 4780 + 89 · no collection errors · nothing skipped

python lint/run.py --rule A001 → SDK-LINT: PASS (no finding in the new files)
python lint/run.py --rule S020 → SDK-LINT: PASS
python lint/run.py --rule A009 → SDK-LINT: PASS
```

Bootstrap deviation: `python -m pip install -e ".[dev]"` was not run. The machine's single global Python 3.11.0 has `vidbyte-sdk` installed in editable mode from the canonical checkout `C:\Users\422mi\vidbyte-repos\vidbyte-sdk`, and other worktrees and tools import it. Reinstalling from this worktree would repoint that install for every session. All dev pins were verified present instead (pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, mypy 2.3.1, build 1.5.0, twine 6.2.0), and every run used `PYTHONPATH=$(pwd)`, as spec §13 directs.

## Fixtures added

The only new fixture code is the pack's own `infinite_memory_fixtures.py`. No conftest, shared fixture, or existing test was added or changed. It imports nothing from the feature at module level; feature imports sit inside helpers and test bodies. Before the feature exists, each test therefore fails on its own and collection never aborts the session. `pytest.importorskip` is not used.

## Spec difficulties

1. **AC-41 conflicts with the design (a spec defect).**
   - AC-41 says "`run()` raises `ConfigurationError`".
   - §12.3 row 21 puts the reserved-name check inside `InfiniteMemoryRuntime.arun`, and §8.5 keeps `run`/`arun` inherited unchanged.
   - `BaseAgent._generate_reply` (vidbyte/agents/base.py, the `except Exception` around `_run_direct`) re-raises every other `Exception` as `AgentExecutionError("Agent '<name>' failed to generate a reply.")` from the original.
   - So the design surfaces `AgentExecutionError` caused by `ConfigurationError`. The test accepts a `ConfigurationError` raised directly or found in the cause chain, and still requires both no runner call and no journal. The spec should say which one callers get.
2. **INV-29's "review holds its text" loses the provider message.** A runner `VidbyteSdkError` reaches the pair as that same `AgentExecutionError`, whose text is generic; the original is in `__cause__`. AC-12 and AC-10 therefore require only a non-blank review. If the spec wants the root cause in the card, it should say so.
3. **Message wording is unspecified.** Rejections, quota lines, cards, replay labels and the resume prompt are matched against their own catalog templates (literal text exact, placeholders wildcard), plus the tokens the spec names. Where a template has little literal text, these checks are only as strong as that text, for example the count of `result_card` renderings in AC-5.
4. **AC-30's "map counts the entry" has no fixed rendering.** It is proven differentially: `entries.jsonl` is blanked to the same length and line breaks, and the map must change.
5. **Where `InfiniteWorkspace` lives.** The §8.5 internal-shape comment says `vidbyte.agents.infinite`, but row 23 exports only four names, so tests import it from `vidbyte.agents.infinite.workspace` (row 17).
6. **The map format is partly assumed.** The tests assume one line per file (INV-22: "Lines past the cap are replaced") and allow ±3 on the "N more files" count, for the bookkeeping files.
7. **Journal card shape.** The card fields carry enum values as strings and lists for tuples, from §9.1. The hand-written journals in the resume tests rely on that shape.
8. **INV-33's word list is the S2 reading:** worktree, pull request, single/one writer, git, repo or repository. Only prompt text is scanned, not code comments.
9. **EC-8 is checked in part.** It names `max_agents`, the started count, and the requested count; the test checks `max_agents` and the started count (4).
10. **EC-43 is checked literally.** Its "with the pattern" makes AC-6's bad-name case require both the name and the literal `INFINITE_TASK_NAME_PATTERN`.
11. **The leaf count changed between reviews.** S1-spec-review-2 counts 41 leaves (r2); r3 §9.2 and row 12 list 40. The tests use r3's 40.

## Commits

1. `test(infinite-memory): add failing tests for infinite-memory-agent [AC-1..AC-42]`, which adds the pack and `test-plan.md`.
2. `docs(spec): record test proof for infinite-memory-agent`, which adds the spec §6.2 Proof column and this report. The report goes in this commit so the tree is left clean, following the S1 precedent of committing reports with spec docs.

There was no push and no PR, and no worktree or stash was created.
