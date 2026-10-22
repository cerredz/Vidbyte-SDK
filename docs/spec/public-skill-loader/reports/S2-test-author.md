# S2 test author report: public-skill-loader

Branch `feat/public-skill-loader` · base `c9d31a7f` · spec r3 · commits `d34a8c3e` (tests and plan), `7f7594bc` (spec Proof column), then this report with a test-plan addendum (the baseline line).

## What was produced

A new feature pack, `tests/features/public_skill_loader/`:

| File | Tests (cases) | Covers |
|---|---|---|
| `FEATURE.md` | — | feature boundary, contract, failure inventory, strategies |
| `conftest.py` | — | fixtures (see below) |
| `test_public_skill_loader_acceptance.py` | 4 (4) | AC-1, AC-2, AC-7, AC-13 |
| `test_public_skill_loader_boundary.py` | 6 (23) | AC-3, AC-4, AC-5, AC-14, AC-17, INV-2 exact names |
| `test_public_skill_loader_security.py` | 2 (6) | AC-6, AC-9 |
| `test_public_skill_loader_both_doors.py` | 2 (13) | AC-18, INV-18 |
| `test_public_skill_loader_contract.py` | 4 (4) | AC-10 (exports), D-14, INV-15, `SkillEntries` |
| `test_public_skill_loader_release.py` | 1 (8) | AC-11 (eight places) |
| `test_public_skill_loader_docs.py` | 1 (9) | AC-16 |

20 test functions, 67 cases. Plus `docs/spec/public-skill-loader/test-plan.md` and the §6.2 Proof column (18 rows; nothing else in the spec changed).

## Inventory

From the spec: INV-1 to INV-18, AC-1 to AC-18, EC-1 to EC-29, T-1, T-3, NFR-5, NFR-6, D-2, D-4 to D-8, D-13, D-14. Added beyond the spec's own cases:

- position bugs: 1-based positions (the Jev door uses `enumerate(start=1)`), the last bad element instead of the first, the name check running before the element check;
- name bugs: unsorted names, a name listed once per repeat, case folding, stripping, Unicode normalization;
- argument bugs: a list kept by reference and mutated after construction, a generator carrying a `SkillDocument` (the memory comprehension consumes it), a dict keyed by entries, one entry passed bare;
- leak bugs: a truncated echo (all secrets share one marker), the value in `repr`, `args`, or a chained cause;
- credential bugs: variables changed between construction and load, so a value read at construction is detectably stale;
- loop bugs: a second `asyncio.run` that must do real async work (a 503 then 200), with both folders changed on disk between runs;
- release: each version read through the code that uses it, not grepped.

The full map is the test plan's coverage table.

## Pruned, and why

- **Contract JSON pytest test.** Not written. C016 and `scripts/generate-sdk-public-api.py --check` own it (INV-17), and §12.6 commits the contract after the source on purpose, so the test would be red between those commits by design. `test_skill_sources_contract.py` WHAT NOT TO DO 1 says the same.
- **AC-8, AC-15, EC-19, per-loader memory through the root door.** `load()`, `documents()`, `_pending_groups()` stay byte-identical (row 2(c)), and the resolvers do not change. The Proof column cites the existing tests by name. AC-7 also loads an over-cap file through the root door.
- **Jev duplicate-message regression guard.** It passes today, so it cannot go red. INV-14, the §14 byte-identity rule, and AC-12's unedited suite cover it.
- **EC-9, EC-13, perf, set order, frozen-ness, root `__all__` count, Hypothesis.** The reasons are in the test plan's table. Hypothesis is not installed; a seeded `random.Random` sweep replaces it.

## Red run (exact final lines)

```
$ PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -rfE tests/features/public_skill_loader
17 failed, 50 errors in 0.55s
```

Reasons, grouped from the `E` lines:

- 33 × `ImportError: cannot import name 'ConfigurationError' from 'vidbyte'`, 17 × `... 'SkillLoader' from 'vidbyte'`. These are setup errors from the `FEATURE_MISSING` and autouse `_feature_present` idiom, so collection of the rest of the suite is unaffected.
- 8 × `assert '0.3.0' == '0.3.1'`.
- 9 docs failures. Each names its stale phrase or missing word: `'only consumer' not in`, `'from the package root' in`, `'package root' in`, the "Public door" part is missing, `'only stores them' not in`, `'vidbyte/__init__.py' in`, `'vidbyte.SkillLoader' in`, `'(per agent)' not in`, `'ConfigurationError' in`.

Area suite, unedited: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/jev_skills_preload tests/test_jev_skill_preload.py` → `426 passed, 1 skipped in 4.69s`.

Full suite with the new tests: `17 failed, 5176 passed, 14 skipped, 50 errors in 54.53s`. Baseline at `c9d31a7f` before any test was written: `5176 passed, 14 skipped in 58.83s`, with no pre-existing failure. The red is confined to the new folder.

`python lint/run.py` → `SDK-LINT: PASS` with the new files present. `ruff check --config lint/ruff.toml tests/features/public_skill_loader` → `All checks passed!`.

## Red for the right reason, beyond the import

Shim diagnostic (scratch pytest plugin, never committed): it injects only the three root names into `vidbyte`, then runs acceptance, boundary, security, both doors, and contract. Result: `34 failed, 12 passed, 4 errors`.

- The 34 fail on behavior: `DID NOT RAISE ConfigurationError`, wrong `details`, `load()` returning `()`, a `KeyError` or `ValueError` from `load()`.
- The 4 contract errors are the missing `SkillEntries`.
- The 12 that pass with the shim are import-only red, on purpose:
  - AC-2, AC-7, AC-9, and AC-13 pin P0 promises of the public door that hold behind the deep import today.
  - The exact-names test, the dict-keys container case, the two empty cases, and the both-doors unique and empty rows (4) guard the new validation against over-rejecting.

## Green proof and mutation check (scratch only, deleted)

A copy of the tree was made in the scratchpad. The §12.3 reference change (rows 1, 2, 3, 4 to 10, 12 to 15) was applied to the copy only. Result: `493 passed, 1 skipped` over the new folder plus the area suite, so every new case passes against a spec-conforming implementation. The sweep's split was 185 accepted and 115 rejected, against a floor of 60 each.

Ten single bugs were then applied to that copy one at a time. Each was caught:

| Mutant | Caught by |
|---|---|
| memory built from the raw argument | containers test only |
| list stored unconverted | containers test only |
| positions start at 1 | element-position test, leak test |
| names unsorted | repeated-names test, sweep |
| names case-folded | exact-names test, sweep |
| names checked before elements | element-position test (`bad element after a repeated name`) |
| element echoed in the message | leak test |
| text accepted as an iterable | text test, leak test |
| empty collection rejected | empty test, both doors, `SkillEntries` record test |
| `SkillLoader` missing from `__all__` | root-export test |

## Fixtures added or extended

Only the new `tests/features/public_skill_loader/conftest.py`. No existing fixture or test file was changed. It re-creates the jev pack's seam, because that pack's fixtures do not reach a sibling folder (the jev pack did the same with coding_agent's).

- `fake_http`: patches `HttpTransport._send_once` and the transport module's `asyncio.sleep`. It is URL-routed, records each attempt's URL and lowercased headers, and raises `AssertionError` on an unrouted URL. Real `httpx.AsyncClient`s are still opened per request, so AC-13 exercises a new client on each loop.
- `record_io`: records `open`, `io.open`, `os.open`, `os.stat`, and environment reads inside a `with` window.
- `skill_md`, `write_skill`.
- autouse `_isolated_environment`: removes `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY`, and changes to `tmp_path`.

Module basenames are unique repo-wide (there is no `__init__.py` under `tests/features`).

## Spec observations (none blocking)

1. **AC-10 and AC-11 are split across two checkers.** pytest covers the root exports and eight version places. The contract file (its three names, `"version": "0.3.1"`, `--check`) is C016's, and the Proof column says so. An implementer who sees pytest green has not yet proven AC-10 or AC-11 in full.
2. **AC-8, AC-12, and AC-15 are proven by existing tests.** The Proof column names them. This is valid only while row 2(c)'s byte-identity of `load()` holds.
3. **`bytearray` and `memoryview` arguments.** These are not `str` or `bytes`, so under INV-2 and row 2(b) they are iterated. `bytearray(b"x")` is then rejected as `{"position": 0, "entry_type": "int"}` rather than `{"entries_type": "bytearray"}`. Nothing leaks, because only type names are reported. The spec is silent, so no test was written. Flagged only in case the owner wants text-like buffers rejected whole.
4. **EC-28 sets.** A set's order follows hash randomization, so no deterministic test pins it beyond the dict-keys case, which shares its code path.
5. **The element message must contain `InlineSkill` for every element type,** not only `str`. This is from row 1(b) check 2 ("the InlineSkill hint"). It is tested, so an implementer who adds the hint only for strings will see the element-position test fail.
