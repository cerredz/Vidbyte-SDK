# JevAgent setting root exports tests

## Folder Description / Intent

This folder tests that `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode` and `JevDynamicComputeOption` can be imported from the root `vidbyte` package as the same objects their defining modules define, so that vidbyte-cli, which may import only root names listed in `contracts/sdk-public-api.json`, can build every JevAgent setting it maps from flags. It also tests that a plain `import vidbyte` binds them eagerly without loading `vidbyte.harnesses.native` or starting a process, and that their defaults are unchanged through the root. The classes' own behavior is tested elsewhere (`tests/features/sdk_loop_settings`, `tests/test_jev_compute_clone.py`, `tests/test_restore_permission_policy.py`).

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, its failure inventory and the strategies left out.
- `test_jev_cli_root_exports_acceptance.py` runs the spec section 4 snippet, which imports only root names, in a fresh interpreter with no key and checks its exact output.
- `test_jev_cli_root_exports_contract.py` checks that each name is listed once in `vidbyte.__all__`, is the object at every existing import path, keeps its defaults and validation, is listed by the public-API contract at the package version, and is named by the root header.
- `test_jev_cli_root_exports_import_time.py` checks, in fresh interpreters, eager binding, no process start, the native package left unloaded, near-miss names, and the star import.

## Logs

- 2026-10-19 - Created for spec `jev-cli-root-exports` (SDK PR R1), before the root exports existed. No test here compares with the merge base or pins an export count, a module hash or a version literal, so later root exports keep it green.
