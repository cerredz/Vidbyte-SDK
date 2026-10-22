# Feature: JevAgent setting types importable from the `vidbyte` root

## High-Level Feature Description

vidbyte-cli turns command-line flags into the two frozen settings objects `JevAgent` accepts, and its lint rule C028 lets it import only top-level `vidbyte` names that the vendored `contracts/sdk-public-api.json` lists. Four types those settings need are root exports: `AgentLoopSettings` (loop limits), `PermissionPolicy` (which `ToolPermission` levels tools may use, so writes and execution can be allowed), `TextModelMode` (gateway or direct text calls; `JevAgentSettings` rejects a plain string) and `JevDynamicComputeOption` (the values of `JevComputeSettings.dynamic_compute`). The root hands out the very class objects the defining modules define, binds them when `vidbyte` is imported, and lists each one once in `vidbyte.__all__`, so the contract lists them too. If this regressed, the CLI could not build loop limits or allow writes ("I dont want writes to be denied"), a copied class would make `JevAgentSettings` reject the CLI's objects, a lazy hook would hide the names from type checkers, or every `import vidbyte` would pay for a heavier import.

## Contract

- `vidbyte.AgentLoopSettings`, `vidbyte.PermissionPolicy`, `vidbyte.TextModelMode` and `vidbyte.JevDynamicComputeOption` exist as soon as `import vidbyte` returns (eager, not through `__getattr__`), and each appears exactly once in `vidbyte.__all__`.
- Each is the same object (`is`) as the class at every path in its spec INV-2 row, and each of those paths keeps working.
- `from vidbyte import *` binds every name in `vidbyte.__all__`, the four included, as the root's own objects.
- A fresh `import vidbyte` starts no process and leaves `vidbyte.harnesses.native` unloaded. Near-miss names (`PermissionPolicies`, `TextModelModes`) still raise `AttributeError` or `ImportError` and still do not load it.
- The spec section 4 snippet, which imports only root names, builds `JevAgentSettings`, `JevComputeSettings` and a `JevAgent` with no key in the environment and prints exactly its four documented lines.
- Through the root names, `PermissionPolicy()` still allows exactly `SAFE` and `READ`, `PermissionPolicy.allow_all()` allows every `ToolPermission`, the `JevAgentSettings` default `model_mode` is `TextModelMode.AUTO`, and a string `model_mode` is still rejected with `ConfigurationError`.
- `contracts/sdk-public-api.json` lists the four names, and its `version` equals `pyproject.toml`'s version and `vidbyte.__version__`.
- The root header has exactly one `- Agent setting exports:` bullet, and it names the four.

## Actors / Callers

vidbyte-cli's JevAgent adapter (`services/jev/sdk.py`, CLI PRs C2 and C4) and its C028 lint; any SDK user who writes `from vidbyte import PermissionPolicy`; existing code that imports the four from their sub-packages; agents and editors that read `vidbyte.__all__`, `dir(vidbyte)` or the root header.

## Inputs and Preconditions

A source checkout on `PYTHONPATH`. No provider key, Vidbyte key or network: nothing runs a model.

## Observable Outcomes

Root attributes and `__all__` membership, object identity across import paths, the module dictionary and `sys.modules` of a fresh interpreter, the process-start audit events it raises, the names a star import binds, the exception types for near-miss names, the snippet's exact stdout, the committed contract's `exports` and `version`, and the root header text.

## State Transitions

None. Importing `vidbyte` binds the four names once; nothing is stored or mutated.

## Invariants

- The four are root exports, bound at import time, each listed once (spec INV-1).
- Root objects are the defining objects at every INV-2 path (INV-2, INV-13).
- `import vidbyte` starts no process and leaves `vidbyte.harnesses.native` unloaded (INV-5, INV-11).
- Contract `exports` include the four; contract `version` = `pyproject.toml` version = `vidbyte.__version__` (INV-4).
- Defaults and validation are unchanged (INV-7), and the header documents the four (INV-10).

## External Dependencies

`contracts/sdk-public-api.json`, written only by `scripts/generate-sdk-public-api.py`; `pyproject.toml`; lint rules C016 (contract current) and S015 (every root `__all__` entry bound, listed once). A fresh interpreter is started with `sys.executable`.

## Known Failure Modes (failure inventory)

| Input + state | Wrong output if unguarded | Test |
|---|---|---|
| A name is added to `__all__` but its import is forgotten (EC-1) | every `from vidbyte import *` raises `AttributeError`; `vidbyte.PermissionPolicy` is missing | `test_star_import_binds_every_root_name_and_the_four_as_the_root_objects`, `test_root_name_is_the_same_object_at_every_path_in_its_inv2_row` |
| The import is added but the `__all__` entry is forgotten (EC-2) | the name works locally, the contract omits it, and the CLI's C028 rejects the import | `test_each_setting_name_is_listed_exactly_once_in_the_root_all`, `test_public_api_contract_lists_the_four_names_at_the_package_version` |
| A name is listed twice (EC-3) | S015 is red and the contract silently collapses the duplicate | `test_each_setting_name_is_listed_exactly_once_in_the_root_all` |
| The root binds a copy, subclass or wrapper | `JevAgentSettings` rejects the CLI's enum members, or `isinstance` and `except` checks miss | `test_root_name_is_the_same_object_at_every_path_in_its_inv2_row`, `test_from_vidbyte_import_binds_the_defining_objects`, `test_spec_snippet_builds_jev_settings_from_root_names_alone_with_no_key` |
| The root serves a name through a lazy `__getattr__` mapping (NG-9) | the name is missing from the module after import and invisible to type checkers, while S015 accepts it | `test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process` |
| A root import goes through a module that loads `vidbyte.harnesses.native` or starts a process | every `import vidbyte` breaks harness thread INV-23 | same |
| A `__getattr__` change resolves or loads on a near-miss name (EC-15) | `vidbyte.PermissionPolicies` stops raising, or loads the native package | same |
| The contract is not regenerated, or its version drifts | the CLI's vendored copy lacks the names, or its pin admits the wrong version | `test_public_api_contract_lists_the_four_names_at_the_package_version` |
| The SDK default policy is widened to "fix" writes (T-1), or `allow_all()` misses a level | every SDK user silently gets write and execute, or the CLI cannot allow writes | `test_root_permission_policy_keeps_its_default_and_allow_all_permits_every_level` |
| A string `model_mode` is coerced, or the default mode changes | a bare `agents jev run` stops inheriting the SDK defaults (D-P4) | `test_jev_settings_take_the_root_text_model_mode_and_still_reject_a_string` |
| A sub-package path drops a name (INV-13) | existing SDK imports, README and llms.txt examples break | `test_root_name_is_the_same_object_at_every_path_in_its_inv2_row` |
| Construction starts needing a key | the CLI's offline `settings validate` and `--dry-run` fail; masked by keys in a developer's shell | `test_spec_snippet_builds_jev_settings_from_root_names_alone_with_no_key` |
| The header bullet is missing, repeated or incomplete (INV-10) | maintainers cannot see why the four are root names | `test_root_header_has_one_agent_setting_exports_bullet_naming_the_four` |

What an easy generated test would miss: identity rather than equality; eager rather than lazy binding; a fresh interpreter, because the test process has usually loaded `vidbyte.harnesses.native` already; a duplicate `__all__` entry; provider keys in the developer's shell hiding a key requirement; and that a test pinning a count, a hash, a version literal or the merge base goes red on `main` at the next export.

## Historical Regressions

2026-10-19: created for spec `jev-cli-root-exports` (SDK PR R1 of the "JevAgent in vidbyte-cli" program). Before it, none of the four names was a root export, so the CLI could not set loop limits, allow writes, or choose the text-model mode with root names alone.

## Test Suite Map

- `test_jev_cli_root_exports_acceptance.py`: the spec section 4 snippet, run as written in a fresh interpreter with every `*API_KEY*` variable removed, against its exact stdout (AC-1).
- `test_jev_cli_root_exports_contract.py`: listed once, identity at every INV-2 path, `from vidbyte import`, the permission and model-mode defaults through the root names, the public-API contract, and the root header bullet (AC-2, AC-4, AC-8, AC-11).
- `test_jev_cli_root_exports_import_time.py`: fresh-interpreter probes for eager binding, no process, the native package unloaded, near-miss names, and the star import (AC-3, AC-7, AC-10).
- Run: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_cli_root_exports`.

## Omitted Testing Strategies

- Comparisons with `base_commit`, `origin/main` or the merge base, and pins of the export count, module count or hash, or a version literal (spec NG-13): they go red on `main` after the merge or at the next export. The implementer proves those one-time facts once (spec section 6.2, second table).
- Absence of the four names anywhere else, or a sweep of module attributes: many modules hold these classes for their own use (`vidbyte.agents.jev.settings` holds all four), so only the INV-2 positive pairings are asserted.
- A standalone misspelled-name test (AC-10): `tests/features/root_native_thread_exports` already covers the unchanged `__getattr__`; the two names the spec gives are probed in the import-time file instead.
- `- Error exports:` still naming `ConfigurationError` (INV-12): `tests/features/public_skill_loader/test_public_skill_loader_docs.py` pins it.
- The rest of INV-7 (every default, and the exact member lists of both enums): implied by identity here plus byte-identical definitions (INV-6, proven once), and already pinned by `tests/features/sdk_loop_settings`, `tests/test_jev_compute_clone.py` and `tests/test_restore_permission_policy.py`. Pinning the member lists would also go red when a later PR adds a compute option, which AGENTS.md describes as a normal change.
- Running `scripts/generate-sdk-public-api.py --check` from pytest: lint C016 owns contract freshness in the same gate.
- The release note (AC-15): tests do not read `docs/` (AGENTS.md); the implementer proves it with a diff.
- A type-checker run over a consumer snippet: no `py.typed` marker ships, so the CLI's checker does not read the SDK's names yet; the eager-binding probe covers the runtime half.
- Concurrency, idempotency, stress, fuzz and property tests: there is no input surface, and the import is serialized by Python's import lock (EC-22).
- Wheel install: `scripts/run_ci.py --stage package` installs the built wheel into a fresh virtual environment and imports `vidbyte`.
- The CLI side of the contract (its vendored copy and C028): another repository, CLI PR C4.
