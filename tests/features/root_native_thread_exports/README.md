# Root native thread exports tests

## Folder Description / Intent

This folder tests that the native harness thread surface (the nine `run_`, `continue_` and `fork_` functions for Grok Build, opencode and Muse Code, plus their result record, error, config records and config enums) can be imported from the root `vidbyte` package as the same objects that `vidbyte.harnesses.native` exports. It also tests that `import vidbyte` still never loads that package, and that `contracts/sdk-public-api.json` lists the names. The thread functions themselves are tested in `tests/features/harness_threads/`. This folder never calls them.

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, its failure modes and the strategies left out.
- `test_root_native_thread_exports_contract.py` checks root `__all__` membership, object identity, lazy loading in a fresh interpreter, star import, misspelled names and the public-API contract.

## Logs

- 2026-10-17 - Created for the 0.3.1 root export of the native thread surface, which vidbyte-cli's `resolve` command needs. The native package's `__all__` drives the checks, so a harness PR that adds a name there fails here until the root and the contract list it too.
