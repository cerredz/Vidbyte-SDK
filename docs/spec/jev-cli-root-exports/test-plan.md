# Test plan: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs

Spec: `docs/spec/jev-cli-root-exports/spec.md` r3 · Framework: pytest 8.3.5 on `py -3.11` (3.11.0) · Prior art copied: `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py` (fresh-interpreter probe, identity with `is`, star import, contract superset plus version equality) and `tests/features/public_skill_loader/test_public_skill_loader_contract.py` / `_docs.py` (`__all__.count(name) == 1`, the `part()` / `PART_BREAK` header-bullet reader)

Pack: `tests/features/jev_cli_root_exports/` (`FEATURE.md`, `README.md`, three test files; 10 test functions, 21 collected items). No conftest, no fixtures, no mocks.

## Coverage map
| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1, G-1, FR-1..FR-4, "I dont want writes to be denied" | `_acceptance.py` → `test_spec_snippet_builds_jev_settings_from_root_names_alone_with_no_key` | acceptance (fresh interpreter) | Any of the four missing or not bindable from the root → the CLI's root-only `from vidbyte import …` raises `ImportError`; a copied `TextModelMode` → `JevAgentSettings` raises `ConfigurationError`; `allow_all()` missing a level, a changed tie-break order, or an unlisted name → a different stdout line; construction that starts needing a key → non-zero exit | It runs the §4 text verbatim in a child process and compares the full stdout list, not a substring. Every variable whose name contains `API_KEY` is removed (this shell holds five live keys), so a key requirement cannot hide. Red today with `ImportError: cannot import name 'AgentLoopSettings' from 'vidbyte'` |
| AC-2, INV-1, EC-2, EC-3 | `_contract.py` → `test_each_setting_name_is_listed_exactly_once_in_the_root_all` | contract | Import added but `__all__` entry forgotten → the generator omits it and CLI C028 rejects it; a name listed twice → S015 finding, contract silently collapses it | Compares `{name: count}` against all-ones for the four, so 0 and 2 both fail with the name shown. Red today (all counts 0) |
| AC-2, INV-2, INV-13 | `_contract.py` → `test_root_name_is_the_same_object_at_every_path_in_its_inv2_row[<name>@<path>]` (12 cases) | contract | A copy, subclass or wrapper on the root → `is` fails while `isinstance` would pass; a sub-package path that drops a name from its `__all__` or attribute → existing SDK imports break | Identity (`is`) only at the INV-2 table's positive pairings, never a cross-product or absence check. Each re-export path also asserts membership in that module's `__all__`; the two defining modules without an entry are checked by attribute. Red today: `AttributeError: module 'vidbyte' has no attribute …` |
| AC-2, FR-1..FR-4 | `_contract.py` → `test_from_vidbyte_import_binds_the_defining_objects` | contract | The statement form the CLI writes fails (`ImportError`) or binds a different object | The import runs inside the test body, so a missing name fails this test at run time instead of aborting collection. Red today with `ImportError` |
| AC-2 (allow_all), AC-8, INV-7, FR-2, T-1 | `_contract.py` → `test_root_permission_policy_keeps_its_default_and_allow_all_permits_every_level` | contract / security smoke | The SDK default widened to "fix" writes → every SDK user silently gets write and execute; `allow_all()` narrowed → the CLI cannot allow writes | Exact set equality for the default (`{SAFE, READ}`) and `== frozenset(ToolPermission)` for `allow_all()`, plus an explicit WRITE and EXECUTE subset check. No literal level count, so a new `ToolPermission` member keeps it green. Red today (`vidbyte.PermissionPolicy` missing) |
| AC-8, INV-7, D-P4 | `_contract.py` → `test_jev_settings_take_the_root_text_model_mode_and_still_reject_a_string` | contract smoke | A string `model_mode` silently coerced, or the default mode changed → a bare `agents jev run` stops inheriting the SDK defaults | `ConfigurationError` must be raised with `model_mode` in the message; the default is checked with `is TextModelMode.AUTO`; `DIRECT` built through the root enum must round-trip by identity. Red today (`vidbyte.TextModelMode` missing) |
| AC-4, INV-4, FR-5 | `_contract.py` → `test_public_api_contract_lists_the_four_names_at_the_package_version` | contract (artifact) | Commit B never made, or the contract hand-edited to another version → the CLI's vendored copy lacks the names or pins the wrong version | Superset check (`four ⊆ exports`) and the three-way equality `contract.version == pyproject version == vidbyte.__version__`; no count, no literal. Red today (four missing) and red by design between commit A and commit B |
| AC-11, INV-10 | `_contract.py` → `test_root_header_has_one_agent_setting_exports_bullet_naming_the_four` | docs contract | Bullet missing, repeated, or omitting a name → maintainers cannot see why these are root names | Counts bullet lines in the module docstring (exactly one), reads the bullet with its wrapped lines, and matches each name as a whole word (`TextModelModes` would not count). Red today: `want one '- Agent setting exports:' bullet: []` |
| AC-11 (Error exports half), INV-12 | existing `tests/features/public_skill_loader/test_public_skill_loader_docs.py::test_docs_describe_the_public_door[root header error exports]` | docs contract | Header edit drops `ConfigurationError` from `- Error exports:` | Already permanent on `main`; not duplicated here |
| AC-7, INV-1 (bound at import time), INV-5, D-1, NG-9 | `_import_time.py` → `test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process` | integration (fresh interpreter) | The four served through a lazy `__getattr__` mapping → invisible to type checkers while S015 accepts it; a root import that loads `vidbyte.harnesses.native` or starts a process → every `import vidbyte` breaks harness INV-23 | Eager binding is read from `vars(vidbyte)` right after `import vidbyte`, which a lazy hook cannot satisfy. Process starts are recorded by a `sys.addaudithook` hook installed before the import (catches `subprocess.Popen`, `_winapi.CreateProcess`, `os.system`, `os.spawn*`, `os.exec*`, `os.posix_spawn`, `os.startfile`, `os.fork*`; self-tested in this session). Red today (`eager` all False). Unlike `test_import_vidbyte_starts_no_process…` in `harness_threads`, it has no merge-base clause, so it stays green on `main` |
| AC-10, INV-11, EC-15 | same test, near-miss clause | integration (fresh interpreter) | A `__getattr__` change that resolves `vidbyte.PermissionPolicies` or `from vidbyte import TextModelModes`, or that loads the native package before checking a name | Asserts the exact exception types in order and that `vidbyte.harnesses.native` is still absent after both misses. The general misspelled-name test in `root_native_thread_exports` stays the primary AC-10 proof |
| AC-3, INV-9, EC-1 | `_import_time.py` → `test_star_import_binds_every_root_name_and_the_four_as_the_root_objects` | integration (fresh interpreter) | A name added to `__all__` without its import → every `from vidbyte import *` raises `AttributeError`; a star import that binds something other than the root's object | Asserts no `__all__` name is unbound, no bound name is a different object, and each of the four is bound as the root's attribute. Red today (the four absent from the namespace) |

## Tests deliberately NOT written
| Candidate | Why it would not earn its keep |
|---|---|
| INV-3, INV-6, INV-8, INV-14, INV-15, INV-16, INV-17 (AC-5, 6, 9, 12, 13, 14, 15): exactly four names added against the merge base, byte-identical definitions, unchanged version literals, lint counts, provenance, the 948-module set and hash, the release note | Spec NG-13 and §13 "What no test may do": each compares against the merge base or pins a count, hash or literal, so it goes red on `main` after the squash merge or at the next export. The implementer proves each once with command output |
| Absence of the four from any other module, or a sweep of module attributes | Cannot pass: `vidbyte.agents.jev.settings` holds all four as attributes, and `vidbyte.lib.config` has no `PermissionPolicy` (spec INV-2 context, §13) |
| A standalone misspelled-name test (AC-10) | Would pass before the implementation and re-prove `root_native_thread_exports::test_a_misspelled_root_name_is_still_an_attribute_or_import_error` against the same unchanged `__getattr__`; the two spec names are folded into the import-time probe instead |
| A standalone "import vidbyte leaves native unloaded" test | Would pass before the implementation and duplicate `root_native_thread_exports`; kept only as clauses of the eager-binding probe, which is red until the feature lands |
| Exact member lists and order of `TextModelMode` and `JevDynamicComputeOption`, and the other INV-7 defaults (`JevComputeSettings()`, `AgentLoopSettings()` limits) | Implied by identity (INV-2) plus byte-identical definitions (INV-6, proven once); already pinned by `tests/features/sdk_loop_settings`, `tests/test_jev_compute_clone.py:70` and `tests/test_restore_permission_policy.py:103`. A member-list pin would also go red when a later PR adds a compute option, which AGENTS.md describes as a normal change (verified green below with a fifth member) |
| `scripts/generate-sdk-public-api.py --check` run from pytest | Lint C016 owns contract freshness in the same gate; a pytest copy duplicates it and adds a git dependency |
| The release note (AC-15) | Tests do not read `docs/` (AGENTS.md opacity rule; `test_public_skill_loader_docs.py` WHAT NOT TO DO 2) |
| A mypy run over a consumer snippet | No `py.typed` marker ships, so the CLI's checker does not read the SDK's names yet, and a cold mypy over `vidbyte` costs minutes; the eager-binding probe covers the runtime half of D-1 |
| A `PermissionPolicy.check()` call with a WRITE tool | Tests existing behavior this PR does not change, and couples to `ToolSpec`'s constructor; the allowed-set equality proves the same promise |
| A network-blocking audit hook around AC-1 | Construction is offline by spec (§13, verified); the promise under test is root-only imports, not JevAgent's I/O |
| Concurrency, idempotency, stress, fuzz, property-based | No input surface; the import is serialized by Python's import lock (EC-22); there is no algebraic invariant |
| EC-14 (star-import shadowing), EC-5 (hand-edited contract), EC-6 (rebased commit A), T-3 (extra names slipped in) | Accepted limitation, or one-time provenance and diff facts (INV-3, INV-15) that a permanent test cannot check without the merge base |

## Red run (before implementation)
Bootstrap: none. No install was run; per code-map §1.3 and the briefing, every command ran from the worktree root with an inline `PYTHONPATH=$(pwd)` (never exported) and `PYTHONDONTWRITEBYTECODE=1`, on `py -3.11`. `vidbyte.__file__` resolved to the worktree (`…\vidbyte-sdk-jev-cli-root-exports\vidbyte\__init__.py`).

Area baseline before the new files (HEAD `c2b14e04`):
```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/root_native_thread_exports tests/features/public_skill_loader tests/features/sdk_loop_settings
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_every_native_export_is_listed_in_the_root_all
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_each_root_name_is_the_native_object_itself
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_the_public_api_contract_lists_every_root_native_name_at_the_package_version
3 failed, 176 passed in 2.26s
```
The 3 failures are inherited from `b7350ed6` (#1183's browser names, spec NG-1).

Each new file alone:
```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports/test_jev_cli_root_exports_acceptance.py
E         ImportError: cannot import name 'AgentLoopSettings' from 'vidbyte' (C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-jev-cli-root-exports\vidbyte\__init__.py)
FAILED tests/features/jev_cli_root_exports/test_jev_cli_root_exports_acceptance.py::test_spec_snippet_builds_jev_settings_from_root_names_alone_with_no_key
1 failed in 1.01s

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py
E           AttributeError: module 'vidbyte' has no attribute 'AgentLoopSettings'      (x3, likewise PermissionPolicy x4, TextModelMode x3, JevDynamicComputeOption x2)
test_from_vidbyte_import_binds_the_defining_objects: ImportError: cannot import name 'AgentLoopSettings' from 'vidbyte'
test_root_permission_policy_…: AttributeError: module 'vidbyte' has no attribute 'PermissionPolicy'
test_jev_settings_take_the_root_text_model_mode_…: AttributeError: module 'vidbyte' has no attribute 'TextModelMode'
test_public_api_contract_…: AssertionError: commit vidbyte/__init__.py, then run scripts/generate-sdk-public-api.py; never edit the contract by hand
test_root_header_…: AssertionError: want one '- Agent setting exports:' bullet: []
18 failed in 0.96s

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py
E       AssertionError: bind the four with ordinary imports in vidbyte/__init__.py, not through __getattr__ or a lazy mapping
E       assert {'AgentLoopSe...lMode': False} == {'AgentLoopSe...elMode': True}
FAILED tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py::test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process
FAILED tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py::test_star_import_binds_every_root_name_and_the_four_as_the_root_objects
2 failed in 1.87s
```

Focused area suite with the new pack:
```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports tests/features/root_native_thread_exports tests/features/public_skill_loader tests/features/sdk_loop_settings
FAILED tests/features/jev_cli_root_exports/… (21 items: every new test)
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_every_native_export_is_listed_in_the_root_all
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_each_root_name_is_the_native_object_itself
FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_the_public_api_contract_lists_every_root_native_name_at_the_package_version
24 failed, 176 passed in 4.92s
```
21 new red, all for a missing root name or the missing header bullet or contract entry; the same 176 existing tests pass; the 3 other failures are the inherited NG-1 trio. Collection is never interrupted, because no new file imports the four names at module level.

Lint on the new files (read-only): `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule A001` → `A001 RATCHETED: 642 known finding(s)` / `SDK-LINT: PASS`; `--rule S020` → `S020 RATCHETED: 1 known finding(s)` / `SDK-LINT: PASS`. `py -3.11 -m ruff check` and `ruff check --config lint/ruff.toml` → `All checks passed!`; `ruff format --check` → `3 files already formatted`; no comment line over 72 columns.

## Green-path and mutation proof (scratch copy; the worktree was not changed)
The implementer may not edit these tests, so each was also proven *passable* by the spec's own implementation, and able to fail for each realistic wrong one. The S2 driver `mutation_matrix.py` (session scratchpad, not committed) extracted `git archive HEAD` (`vidbyte`, `pyproject.toml`, `contracts`, `tests/__init__.py`, `tests/features/public_skill_loader`, `REPO_MAP.md`) into a scratch folder that is not a git repository, copied this pack in, and then applied spec §12.3 row 1 (a) to (e) verbatim plus a contract carrying the four names ("GOOD"). It rebuilt the folder for every scenario and ran `py -3.11 -m pytest -q -p no:cacheprovider -rf tests/features/jev_cli_root_exports` with `PYTHONPATH=<scratch>`. Because the scratch folder is not a git repository, the run also shows that no test reads git.

| Scenario | Result | Tests that went red |
|---|---|---|
| BASE (pristine HEAD) | 21 failed | all |
| GOOD (spec §12.3 row 1 verbatim + contract) | **21 passed** | none |
| GOOD + `test_public_skill_loader_docs.py` | 30 passed | none (the new header line leaves `- Error exports:` intact) |
| EC-1: `__all__` entry without the `PermissionPolicy` import | caught (9) | identity ×4, from-import, permission smoke, AC-1, star import, eager probe |
| EC-2: `TextModelMode` imported but not in `__all__` | caught (3) | listed-once, AC-1 (last line `False`), star import |
| EC-3: `PermissionPolicy` listed twice | caught (1) | listed-once |
| NG-9: `AgentLoopSettings` served lazily through `__getattr__` (same object) | caught (1) | eager probe only |
| `class PermissionPolicy(_PermissionPolicy)` subclass on the root (`isinstance` still passes) | caught (5) | identity ×4, from-import |
| Re-created `TextModelMode` enum on the root | caught (6) | identity ×3, from-import, model-mode smoke, AC-1 |
| Header bullet missing / missing `JevDynamicComputeOption` / duplicated | caught (1 each) | header |
| Contract not regenerated / contract version `0.4.1` | caught (1 each) | contract |
| Root imports `vidbyte.harnesses.native` eagerly | caught (1) | eager probe |
| Root starts a subprocess at import | caught (1) | eager probe (audit hook) |
| `PermissionPolicy` default widened to every level (T-1) | caught (1) | permission smoke |
| `allow_all()` drops EXECUTE | caught (2) | permission smoke, AC-1 |
| `__getattr__` resolves `PermissionPolicies` to `PermissionPolicy` | caught (1) | eager probe (near-miss clause) |
| `__getattr__` imports the native package before checking the name | caught (1) | eager probe (near-miss clause) |
| String `model_mode` coerced instead of rejected | caught (1) | model-mode smoke |
| `JevAgentSettings` default `model_mode` changed to `DIRECT` | caught (1) | model-mode smoke |
| `PermissionPolicy` dropped from `vidbyte.tools.security.__all__` (INV-13) | caught (1) | identity `[PermissionPolicy@vidbyte.tools.security]` |
| Legit: a fifth root export (`ModelProvider`) in root, `__all__` and contract | **green** | none |
| Legit: version bumped consistently to `0.4.1` (pyproject, `__version__`, contract) | **green** | none |
| Legit: the four appended as one cluster at the end of `__all__` (D-4 runner-up) | **green** | none |
| Legit: `PermissionPolicy` imported via `vidbyte.tools.security` (D-2 runner-up) | **green** | none |
| Legit: header bullet wrapped onto two lines | **green** | none |
| Legit: a new `JevDynamicComputeOption` member | **green** | none |

Result: 20 of 20 mutants caught, 0 survivors; 6 of 6 legitimate future changes stay green. The eager-binding probe is the only test that catches five of the mutants: the lazy hook, the eager native import, the process start, and both `__getattr__` regressions.

## Notes for the implementer
- The tests bind exactly these names: `vidbyte.AgentLoopSettings`, `vidbyte.PermissionPolicy`, `vidbyte.TextModelMode`, `vidbyte.JevDynamicComputeOption`, each listed once in the root `__all__`; the header bullet prefix `- Agent setting exports:` inside the `vidbyte/__init__.py` module docstring, naming all four as whole words; and `contracts/sdk-public-api.json` `exports` ⊇ the four with `version == pyproject.toml [project].version == vidbyte.__version__`.
- Bind them eagerly (spec D-1). A lazy `_LAZY_*_EXPORTS` entry passes S015 and every identity test but fails `test_fresh_import_binds_the_four_eagerly_…`, by design (NG-9).
- `test_public_api_contract_lists_the_four_names_at_the_package_version` is red after commit A and green after commit B; that is expected (spec §12.6). Every other new test should be green after commit A.
- Either import path for `PermissionPolicy` (D-2 or its runner-up) and either `__all__` placement (D-4 or its runner-up) passes; order is not pinned. The header bullet may wrap.
- No fixture or conftest is used, and no existing test or shared file was changed. The probes start `sys.executable` with `PYTHONPATH` set to the checkout, so run them from the worktree root with `PYTHONPATH=$(pwd)`.
- Do not edit `vidbyte/lib/dataclasses/security.py`, `vidbyte/agents/jev/settings.py` or `vidbyte/tools/security/__init__.py`: the default-widened, model-mode and dropped-path mutants above show these tests turn red if any of them changes.
- `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` (`harness_threads`) will go red locally after commit A; that is inherited, CI skips it, and this pack's import-time test carries its permanent half.
