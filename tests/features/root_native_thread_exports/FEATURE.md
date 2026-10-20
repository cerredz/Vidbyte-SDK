# Feature: Native harness thread surface importable from `vidbyte`

## High-Level Feature Description

The harness thread functions (`run_`, `continue_` and `fork_` for Grok Build, opencode and Muse Code), their result record, error, config records and config enums are importable from the root `vidbyte` package, not only from `vidbyte.harnesses.native`. vidbyte-cli depends on this: its lint rule C028 lets it import only names listed in the vendored `contracts/sdk-public-api.json`, which is `vidbyte.__all__`, and its scheduled `vidbyte-cli resolve` job calls these functions. If a name drops off the root, or the root hands out a different object, the CLI stops building or its `except NativeThreadError` stops matching.

## Contract

Every name in `vidbyte.harnesses.native.__all__` is in `vidbyte.__all__`, and `vidbyte.<name>` is the same object as `vidbyte.harnesses.native.<name>`. The names first exported in 0.3.1 never leave the root. A plain `import vidbyte` still does not import `vidbyte.harnesses.native` (harness thread spec INV-23): every native function (the thread functions, their browser counterparts, the thread helpers and the command functions) loads the first time a caller names one, and an attribute miss never loads them. `dir(vidbyte)` and `from vidbyte import *` include the functions. A misspelled name is still an `AttributeError` or `ImportError`. `contracts/sdk-public-api.json` lists every one of these names, and its `version` equals `pyproject.toml` and `vidbyte.__version__`.

## Actors / Callers

vidbyte-cli (its `resolve` command and its C028/C029 lint), SDK users who write `from vidbyte import run_opencode_thread`, editors and type checkers that read `vidbyte/__init__.py`, and agents that read `vidbyte.__all__` or `dir(vidbyte)` to discover the API.

## Inputs and Preconditions

A source checkout on `PYTHONPATH`. No vendor CLI, key or network is needed, because no thread function is called.

## Observable Outcomes

The membership of `vidbyte.__all__`, object identity between the root and the native package, `sys.modules` in a fresh interpreter before and after first use, the names that `dir()` and a star import bind, the exception type and message for a missing name, and the committed contract's `exports` and `version`.

## State Transitions

On first use, the root module stores the loaded function in its own namespace, so later lookups do not go through `__getattr__` again. Nothing else changes state.

## Invariants

- Root `__all__` is a superset of `vidbyte.harnesses.native.__all__`, plus the 0.3.1 floor names.
- Root objects are the native objects, not wrappers or copies.
- `import vidbyte` and any attribute miss leave `vidbyte.harnesses.native` unloaded.
- Contract `version` = `pyproject.toml` version = `vidbyte.__version__`.

## External Dependencies

`contracts/sdk-public-api.json` and its generator `scripts/generate-sdk-public-api.py`, and lint rules C016 (contract current) and S015 (every `__all__` entry is bound or listed in the lazy-export mapping).

## Known Failure Modes

- A harness PR adds a name to `vidbyte.harnesses.native.__all__` but not to the root, so the CLI cannot import it.
- An eager import in the root breaks INV-23 for every user.
- A `__getattr__` that imports the native package before it checks the name loads that package whenever a tool probes a missing attribute (`hasattr`, `copy`, `inspect`).
- A wrapper function on the root breaks `is` checks and makes `except vidbyte.NativeThreadError` miss.
- A `__getattr__` that type checkers can see makes every misspelled `vidbyte.X` silently typed as `object`.
- The contract is not regenerated, or the version literals drift apart.

## Historical Regressions

2026-10-17: created when 0.3.1 first exported the native thread surface from the root, so that vidbyte-cli could call the thread functions. Before that, the names lived only in `vidbyte.harnesses.native` (PR #1036).

2026-10-19: the probes for `dir(vidbyte)` and the star import picked the lazy functions by the `_thread` suffix, which assumed the nine thread functions were the only ones. PR #1147's `get_grok_thread`, `read_muse_thread` and `delete_opencode_thread` end in `_thread` too, so the probes now take the lazy function list from the lowercase names in `vidbyte.harnesses.native.__all__`.

## Test Suite Map

- `test_root_native_thread_exports_contract.py`: native floor names, root `__all__` membership, object identity, the fresh-interpreter lazy-load and attribute-miss checks, star import, misspelled names, and the public-API contract.

## Omitted Testing Strategies

- Calling a thread function end to end: `tests/features/harness_threads/` already runs all nine against stand-in vendors, and the root hands out the same objects.
- Static type-checker runs over the `TYPE_CHECKING` import: no `py.typed` marker ships yet, and lint already checks that the names are bound.
- Stress, concurrency and fuzz testing: the surface is a fixed list of names with no input to vary.
- Wheel install: `scripts/run_ci.py --stage package` already installs the built wheel into a fresh virtual environment and imports `vidbyte`.
