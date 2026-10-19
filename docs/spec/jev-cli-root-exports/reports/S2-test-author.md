# S2 report: test author, jev-cli-root-exports

Stage: S2 · Spec: r3 (approved) · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports` · Branch: `feat/jev-cli-root-exports` · Start HEAD `c2b14e04` · Test commit `5c3aa147` (the spec-proof commit follows it).

## What was produced

- `tests/features/jev_cli_root_exports/FEATURE.md`: the feature contract, failure inventory, suite map and omitted strategies. It was written first.
- `tests/features/jev_cli_root_exports/README.md`: folder intent, a `## File Index` that lists every direct child (S020), and `## Logs`.
- `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_acceptance.py`: AC-1.
- `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py`: AC-2, AC-4, AC-8, AC-11.
- `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py`: AC-3, AC-7, AC-10.
- `docs/spec/jev-cli-root-exports/test-plan.md`: coverage map, tests not written, red run, mutation matrix, and notes for the implementer.
- `docs/spec/jev-cli-root-exports/spec.md`: the §6.2 "Tested" Proof cells only (8 rows). The "Proven once by the implementer" table is untouched.

In total there are 10 test functions and 21 collected items. No fixture, conftest, mock or production file was added. No existing test or shared file was changed.

## Failure inventory (input + state → wrong output)

1. A name is in `__all__`, but its import is forgotten (EC-1). Every `from vidbyte import *` then raises `AttributeError`.
2. A name is imported, but its `__all__` entry is forgotten (EC-2). The contract omits it, and CLI C028 rejects the import.
3. A name is listed twice (EC-3). S015 goes red, and the contract silently collapses the duplicate.
4. The root binds a copy, subclass or wrapper. `isinstance` may still pass, but enum identity breaks `JevAgentSettings` validation and `except` or `is` checks.
5. The root serves a name lazily through `__getattr__` (NG-9). Type checkers cannot see it, and S015 still accepts it.
6. A root import loads `vidbyte.harnesses.native` or starts a process. Harness INV-23 breaks for every SDK user.
7. A `__getattr__` change resolves near-miss names, or loads the native package before it checks the name (EC-15, INV-11).
8. The contract is not regenerated, or its version drifts. The CLI's vendored copy then lacks the names or pins the wrong version.
9. The SDK default `PermissionPolicy` is widened to "fix" writes (T-1), so every user silently gets write and execute. Or `allow_all()` is narrowed, so the CLI cannot allow writes.
10. A string `model_mode` is coerced, or the default mode changes. A bare `agents jev run` then drifts from the SDK defaults (D-P4).
11. A sub-package path drops a name (INV-13), and existing imports break.
12. Construction starts needing a key. The developer's shell holds five live `*_API_KEY` variables, which would hide that.
13. The header bullet is missing, repeated or incomplete (INV-10).
14. A test pins a count, hash, version literal or merge base. It then goes red on `main` at the next export. This one is a meta-failure, and it is designed against.

The coverage map in `test-plan.md` maps each entry to its test, with why the test cannot pass vacuously.

## What was pruned, and why

The full list is in `test-plan.md`, "Tests deliberately NOT written". The main ones:

- **One-time facts.** Every 6.1.b fact (AC-5, 6, 9, 12, 13, 14, 15) is left out, per NG-13.
- **Absence and sweeps.** No absence check and no attribute sweep: neither can pass.
- **Standalone AC-10.** A standalone misspelled-name test, or a standalone "native unloaded" test, would pass before the implementation and duplicate `root_native_thread_exports`. Both checks became clauses of the eager-binding probe, which is red until the feature lands.
- **Exact enum member lists.** A later compute option would turn such a pin red. A scratch probe confirmed that adding a member keeps this pack green.
- **Freshness, docs and types.** No `--check` from pytest, because C016 owns freshness. Nothing reads `docs/`. No mypy run, because no `py.typed` ships.
- **Other strategies.** Concurrency, fuzz and property tests are left out: there is no input surface.

## Design choices a reviewer should know

- **No module-level import of the four names.** Tests use `importlib.import_module("vidbyte")` plus attribute access, or a function-level `from vidbyte import …`. A missing name therefore fails each test body on its own, instead of aborting collection or hiding behind a `FEATURE_MISSING` setup guard. As a result, every test body is independently red on base.
- **Process starts are detected with `sys.addaudithook`, not by patching `subprocess.Popen.__init__`** (the method the `harness_threads` test uses). The hook also catches `os.system`, `os.exec*`, `os.spawn*`, `os.posix_spawn`, `os.startfile` and `_winapi.CreateProcess`. I self-tested it in this session: a probe that ran `subprocess.run` and `os.system` recorded `["subprocess.Popen", "_winapi.CreateProcess", "os.system"]`, and a base `import vidbyte` recorded `[]`.
- **Eager binding is read from `vars(vidbyte)` right after import.** This is the only check that tells a lazy implementation apart from an eager one.
- **The AC-1 snippet is verbatim from §4.** It runs with every environment variable whose name contains `API_KEY` removed (case-insensitive for Windows), and its full stdout is compared as a list.

## Exact red output (worktree, before implementation)

Bootstrap: none. Every command ran from the worktree root with inline `PYTHONPATH=$(pwd)` and `PYTHONDONTWRITEBYTECODE=1` on `py -3.11`. No `pip install` was run, and `PYTHONPATH` was never exported. `vidbyte.__file__` resolved to the worktree.

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports   # at 5c3aa147
FAILED tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py::test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process
FAILED tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py::test_star_import_binds_every_root_name_and_the_four_as_the_root_objects
21 failed in 3.56s

$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports tests/features/root_native_thread_exports tests/features/public_skill_loader tests/features/sdk_loop_settings
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_every_native_export_is_listed_in_the_root_all
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_each_root_name_is_the_native_object_itself
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_the_public_api_contract_lists_every_root_native_name_at_the_package_version
24 failed, 176 passed in 4.92s
```

The area baseline before the new files was `3 failed, 176 passed in 2.26s` (the same three NG-1 inherited failures). Per-file reasons are in `test-plan.md`. Every new failure is one of these:

- `ImportError: cannot import name 'AgentLoopSettings' from 'vidbyte'`
- `AttributeError: module 'vidbyte' has no attribute '<name>'`
- counts all 0
- the contract missing the four
- `want one '- Agent setting exports:' bullet: []`
- eager map all False

Lint, read-only:

- `lint/run.py --rule A001` gives `A001 RATCHETED: 642 known finding(s)` and `SDK-LINT: PASS`.
- `--rule S020` gives `S020 RATCHETED: 1 known finding(s)` and `SDK-LINT: PASS`.
- `ruff check` and `ruff check --config lint/ruff.toml` both report `All checks passed!`.
- `ruff format --check` reports `3 files already formatted`.
- No `#` comment line is over 72 columns (field guide `comment-format.md`).
- No `.py` test basename is duplicated (only the pre-existing `conftest.py`).

## Independent verification: green path and mutation matrix

The S3 implementer may not edit these tests. So I checked, in a scratch copy, that they pass under the spec's exact §12.3 row 1 implementation and that each realistic wrong implementation turns at least one test red.

- **Driver:** `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/mutation_matrix.py`.
- **Output:** `…/scratchpad/mutation_matrix.out`.
- **Tree:** `git archive HEAD` extracted into a non-git folder, so the run also shows that no test reads git.
- **Results:**
  - Pristine HEAD: 21 failed.
  - GOOD: **21 passed**.
  - GOOD plus `test_public_skill_loader_docs.py`: 30 passed.
  - Mutants: **20 of 20 caught**.
  - Legitimate future changes: **6 of 6 green**. These were a fifth root export, a consistent version bump, cluster ordering, the D-2 runner-up import path, a wrapped header bullet, and a new compute-option member.

The full table is in `test-plan.md`.

## Fixtures added or extended

None. No shared fixture, conftest or helper module was touched. Each file holds its own small helper (`fresh_interpreter`, `header_bullet`), as the prior art does.

## Spec defects and friction found

1. **AC-10 vs. hard rule 6 (red before green).** AC-10 says that no new test is required, and a standalone test would be green before the implementation. I resolved this by folding the two names into the eager-binding probe, which is red until the feature lands. The existing `root_native_thread_exports` test stays the primary proof. This is not a defect, but the Proof cell says so.
2. **AC-7 vs. hard rule 6.** "native unloaded / no process" holds on base too. I resolved it the same way: these are clauses of a test whose eager-binding clause is red. Taken alone, the AC is a regression guard, not a red-first test.
3. **INV-7's member-order clause** ("…`subagent`, `clone` and `swarm`, in that order") is listed as a permanent 6.1.a property. Pinning it would go red when a later PR adds a compute option, which AGENTS.md describes as a normal change. I did not pin it. I recorded this under "not written", and a probe showed that adding a member keeps the pack green. The orchestrator may want to reword INV-7 to "existing members keep their values and relative order".
4. **The INV-2 table's "Defining module (attribute)" column vs. the text.** The text says that only `loop` and `security` lack an `__all__` entry, which implies that `text_model` and `jev` list theirs (verified true on base). I checked every defining module by attribute only, as the column header says. The `__all__` check covers only the re-export column. This is no defect, just the reading I chose.
5. **The ambient ruff config flags `exec` (S102).** The repo does not configure this. I avoided it by using a function-level `from vidbyte import …`. The prior-art files fail plain `ruff check` and `ruff format --check`, so neither is a repo gate for `tests/`.

## Notes for S3

- **Names the tests bind:**
  - `vidbyte.{AgentLoopSettings, PermissionPolicy, TextModelMode, JevDynamicComputeOption}`, each listed once in `__all__`;
  - one `- Agent setting exports:` line in the root module docstring, naming all four as whole words;
  - contract `exports` ⊇ the four, with `version == pyproject == vidbyte.__version__`.
- **After commit A**, only `test_public_api_contract_lists_the_four_names_at_the_package_version` stays red, by design. It turns green after commit B.
- **Bind eagerly** (D-1). A lazy mapping fails `test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process`.
- **Run from the worktree root** with `PYTHONPATH=$(pwd)`. The probes pass that path to their child interpreters.
