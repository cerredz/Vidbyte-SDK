LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the production change is sound under hostile arguments, at scale, across event loops, and against every §10 attacker; the test pack kills all 15 single-bug mutants I applied, but its release test will go red on the next routine version bump, and one docs rule can pass vacuously.

Diff reviewed: `git diff c9d31a7f...c691c176` (36 files; 15 outside `docs/` and `tests/`). Every changed production file was read whole: `vidbyte/agents/skills/loader.py`, `vidbyte/lib/dataclasses/skills.py`, the root `vidbyte/__init__.py` hunks, the 7 version-literal files, and the 4 docs/headers. All 7 test modules and the pack's `conftest.py` were read in full.

WHAT THE IMPLEMENTATION GETS RIGHT (so nobody "fixes" what works)

- **The argument is converted once, and memory is built from that conversion.** `loader.py:45` turns the argument into a tuple once. `loader.py:49` then builds the memory from `self.entries`, not from the raw argument, so a generator, a list the caller later clears, and a dict keyed by entries all resolve. Mutants M1 (memory built from the raw argument) and M14 (the list stored unconverted) are each killed. Do not point the memory comprehension back at the raw argument.
- **The checks run in the right order and never echo a value or credential.** `vidbyte/lib/dataclasses/skills.py:249-264` checks, in order:
  1. that the argument is a tuple;
  2. the first element that is not an entry or a document, by 0-based position;
  3. repeated names, found in one `Counter` pass, sorted, each listed once.

  The errors carry only type names, positions, and names. Probes put a fake token and key into the argument, into an element, into a dict element, and into credentialed entries with a repeated name, and they bypassed the type checks with str and bytes. No marker appeared in `str`, `repr`, `.message`, `.details`, `.args`, `__cause__`, or `__context__`. None appeared in `repr(SkillEntries(...))`, `repr(loader)`, or `repr(loader.__dict__)` with a `GitHubSkill(token=...)` and two vendor entries with `api_key=` inside.
- **The name rule also closes the one tuple shape that used to crash `load()`.** The default `group_key` returns the entry itself (`vidbyte/agents/skills/resolver.py:28-31`). The single-entry resolvers unpack with `(entry,) = entries` (`local.py:49`, `skills_sh.py:45`, `vendor.py:79`). So only *equal* entries can share one of those groups, and equal entries need equal names. Unique names therefore also make the memory dict, which is keyed by entry equality, unambiguous.
- **`load()` is unchanged and holds up for an outside caller.**
  - It works with no running event loop: `HttpTransport.request` opens a new `httpx.AsyncClient` per call (`vidbyte/lib/http/transport.py:64`), and `SkillFetch` builds its `asyncio.timeout` per call (`fetch.py:53`).
  - Two `asyncio.run(loader.load())` calls return the same remembered objects.
  - Overlapping `gather(load(), load())` calls agree.
  - Cancellation propagates and remembers nothing.
  - Construction is O(n): 100,000 entries take 18.7 ms to accept and 15.5 ms to reject one duplicate.

FINDINGS (ranked, most severe first)

R-E1 [Major] [test quality] tests/features/public_skill_loader/test_public_skill_loader_release.py:35 — The release test pins the literal `0.3.1` permanently, so every future version bump fails 8 tests even though nothing is wrong
  Evidence:
  - `:35` reads `RELEASE_VERSION = "0.3.1"`, and `:113` reads `assert read(monkeypatch) == RELEASE_VERSION, place`. The header (`:7`) admits it: "The next bump changes RELEASE_VERSION".
  - `git show --stat a7ed9cde`: the 0.3.0 release bump touched 10 files (`.github/ISSUE_TEMPLATE/bug_report.yml`, `README.md`, `contracts/sdk-public-api.json`, `docs/design/release-0-3-0.md`, `llms.txt`, `pyproject.toml`, `vidbyte/__init__.py`, `vidbyte/cli/__init__.py`, `vidbyte/mcp_server/server/core.py`, `vidbyte/tools/mcp/client.py`) and no test file.
  - A grep of `tests/` for `__version__|RELEASE_VERSION|"0\.3\.\d"` finds only this file. So nothing else ties the CLI fallback, the MCP server default, the MCP `clientInfo`, the README line, `llms.txt`, or the bug template to `pyproject.toml`: C016 covers only the contract against pyproject, and the package smoke test covers only `__version__` against installed metadata.
  Failure: The next release PR follows the a7ed9cde precedent and moves the eight literals to `0.3.2`. Then `test_every_version_bearing_place_reads_the_release_version` fails 8 cases (`'0.3.2' == '0.3.1'`) inside a skill-loader feature pack the release author never touched. The test fails for the wrong reason, and the quickest way to green, editing or deleting it, also drops the only cross-literal consistency guard the repo has. A feature pack should pin "the smallest durable behavior boundary" (`agentic-engineering/references/feature_test_packs.md:13`), and "the version is 0.3.1" stops being true by design.
  Smallest fix:
  - Compare each of the seven non-pyproject places with `pyproject_version(monkeypatch)` instead of the literal.
  - Pin the durable floor once, for example `assert tuple(int(part) for part in pyproject.split(".")[:3]) >= (0, 3, 1)` (the first release with the root door, EC-29).
  - For this PR the result is identical: pyproject reads 0.3.1, so all eight must read 0.3.1. Exactly 0.3.1 at merge remains enforced by C016 and review.
  Spec IDs: AC-11, INV-16 (the proof's durability), FR-8

R-E2 [Minor] [test quality] tests/features/public_skill_loader/test_public_skill_loader_docs.py:44-46 — The REPO_MAP rule passes vacuously once its heading changes, so the test plan's "a renamed heading cannot hide a stale phrase" claim is false for this rule
  Evidence:
  - `:46` reads ``return text.split("##### `vidbyte/agents/skills/`", 1)[-1].split("\n#", 1)[0]``. `str.split(sep, 1)[-1]` returns the *whole text* when `sep` is absent.
  - The rule at `:70` has only `absent=` phrases, and the guard at `:99` (`assert section.strip()`) only checks that the section is non-empty.
  - In-memory probe (no file edited): change the heading to `#### ...`, or rename the path to `skill_sources/`, and put the stale clause "today JevAgent's skill preload is its only consumer" back into the entry. Output: `section starts: '# Vidbyte SDK Repository Map\n\n> **This file is a Map.**...' | guard passes: True | stale seen: False`.
  - With the heading unchanged, the same stale clause is caught: `heading kept -> rule sees stale phrase: True`.
  Failure: The REPO_MAP entry is regenerated, which AGENTS.md says to do because the map "is expected to drift", and its heading changes level or path. The rule then checks the map's preamble, and a reintroduced "only consumer" or "for the agent's lifetime" passes. Test-plan row AC-16 claims "Each rule first asserts the part it reads exists (a renamed heading cannot hide a stale phrase)". That holds for the `part(...)` rules and for `intro_paragraph` (both have `present=` words), but not for this one.
  Smallest fix: ``head, found, tail = text.partition("##### `vidbyte/agents/skills/`"); return tail.split("\n#", 1)[0] if found else ""``. The existing guard at `:99` then fails loudly when the heading moves.
  Spec IDs: AC-16, FR-10, W-4

No other findings. The sub-lenses I attacked and found clean:

- **Failure modes (new code):**
  - Every odd argument either converts or is rejected with a `ConfigurationError`: generators, sets, dicts, `dict.values()`, `bytearray`, `memoryview`, `range`, `UserString`, `Path`, and `__getitem__`-only sequences. The only exceptions are iterables that raise during iteration (see Verified claims 19).
  - An entry that passes `SkillEntries` cannot crash `load()`. A NUL byte, or the Windows-invalid characters `<>|`, in `LocalSkill.path` or `SkillsShSkill.directory` comes back as `NOT_FOUND` or `NOT_INSTALLED`, not as an exception.
  - Every URL field the resolvers build is `quote(..., safe='')` encoded (`github.py:153,214`; `vendor.py:132,136`).
- **Data and scale:** checked at 1,000, 10,000, and 100,000 entries (see Verified claims 12). Memory holds at most one resolution per entry.
- **Security:** checked against T-1 to T-4 (see Verified claims 5, 14, and 18).
- **Error handling:** partial failure comes back per entry, and programming errors and cancellation propagate unchanged.

Three plausible bugs named and checked (plus 12 more), each applied as a single in-memory mutant through a scratch pytest plugin, with no file edited:

| Mutant | Failing cases (of 67) |
|---|---|
| M1 memory built from the raw argument | 2 |
| M2 names checked before elements | 9 |
| M3 str/bytes guard dropped from the `Iterable` test | 5 |
| M4 bytes not excluded | 3 |
| M5 1-based positions | 9 |
| M6 casefolded names | 2 |
| M7 stripped names | 2 |
| M8 `Sequence` instead of `Iterable` | 4 |
| M9 documents rejected | 11 |
| M10 unsorted names | 2 |
| M11 value echoed in `details` | 9 |
| M12 stat at construction | 4 |
| M13 empty collection rejected | 6 |
| M14 list stored unconverted | 2 |
| M15 duplicates dropped silently | 18 |

All 15 are killed. The baseline with no mutant applied is 67 passed.

VERIFIED CLAIMS

1. S3: "67 passed" for the new pack. HELD: `67 passed in 0.33s`.
2. S3: area suite "426 passed, 1 skipped". HELD: `426 passed, 1 skipped in 4.70s`.
3. S3 tricky part 2: "Memory comes from `self.entries`". HELD: `loader.py:49`; M1 is killed by the generator and dict container cases.
4. S3 tricky part 3: element check before name check; `(local pdf, local pdf, None)` gives `position: 2`. HELD: `skills.py:254-264`; M2 is killed by 9 cases.
5. S3: "Every message names `SkillLoader`, and none contains a value, a token, or a key". HELD: probe §2, 5 rejections and 4 reprs, `leak=False` in every one.
6. S3: contract current, 642 exports. HELD: `--check` printed `current at 56541481… (vidbyte-sdk 0.3.1, 642 exports)`.
7. S3: "Files outside §12.3 are byte-identical". HELD: `git diff --stat c9d31a7f..c691c176 -- . ':!docs' ':!tests'` shows `15 files changed`, exactly rows 1–15.
8. S3: lint PASS. HELD: `SDK-LINT: PASS`, and `git status --short` was unchanged by the run.
9. INV-16 / AC-11: nine places read 0.3.1, and none is missed ("don't miss any"). HELD: `git grep` finds all nine at `c691c176` and no `0.3.0`, `0, 3, 0`, or `0_3_0` outside `docs/`.
10. INV-11 / AC-13 / EC-19 / EC-17: new loop per call, overlapping loads, and cancellation. HELD: two `asyncio.run` calls return the same objects (`True`); overlapping loads agree (`True`, memory size 2); cancellation propagated with `remembered=0`.
11. INV-18: equal `details` from both doors on lists and on mixed entries and documents. HELD: list inline+document, list triple-repeat (`['a', 'b']`), tuple unique mixed, and the same object twice are all equal.
12. NFR-1: validation is O(n). HELD: 1,000 / 10,000 / 100,000 entries take 0.1 / 1.3 / 18.7 ms to accept.
13. §4 snippet (AC-1). HELD: run directly from an empty temp folder, it printed exactly `house-review loaded 22 bytes` / `pdf not_found False` / `rejected: ['house-review']`.
14. T-2: "`SkillEntries` rejects ... an entry tuple built to crash the loader". HELD: no distinct-named pair shares a single-entry group (resolver.py:28-31), and NUL or invalid-character paths come back as data, not exceptions.
15. Test plan: "Ten single bugs ... were each caught". HELD and extended: 15 of 15 in-memory mutants are killed.
16. Test plan AC-16 row: "Each rule first asserts the part it reads exists (a renamed heading cannot hide a stale phrase)". DID NOT HOLD for the REPO_MAP rule (R-E2).
17. Test plan: the Unicode-form cases are real. HELD: both files hold `'caf\xe9'` (NFC) and `'café'` (not NFC), so the exact-name and sweep cases are not vacuous.
18. T-4: two loaders never share memory. HELD by existing tests: `test_skill_sources_memory.py::test_each_agent_has_its_own_memory` and `test_skill_sources_local.py::test_not_found_is_remembered_until_a_new_loader`. No new-pack gap.
19. Briefing questions on hostile arguments. All answered as the spec says, none a defect:
    - `bytearray`, `memoryview`, and `range` are iterated and rejected as `{"position": 0, "entry_type": "int"}`. This is exactly INV-2 (only `str`/`bytes` are rejected whole). It is harmless: a 5 MB bytearray peaks at about 45 MB before rejection, and no realistic caller passes one.
    - An `__iter__` that raises, or a generator that fails mid-way, propagates the caller's own `RuntimeError`, `TypeError`, or `ValueError` unchanged. That is right ("programming errors propagate"), and "not as a crash" in request.md concerns per-entry resolution.
    - The Jev door differs only for a `__getitem__`-only object or a `TypeError` while iterating, both outside INV-18's tuple/list scope.
    - A set is accepted in its iteration order (EC-28), and a dict keyed by entries is accepted.
    - An infinite iterator never returns from `tuple()`. That is the caller's bug under D-14, and a bound would be `[scope-adding]`.
20. A-8: no import-order hazard from the root import. HELD: fresh processes importing `vidbyte.agents.skills.loader`, `vidbyte.lib.dataclasses.skills`, `vidbyte.agents.jev.alignment.skills`, `vidbyte.agents.skills`, or the root first all print `ok`, and root `SkillLoader is loader.SkillLoader`.
21. Public README "Public door." bullet against the code. HELD: tuple or list accepted; `ConfigurationError` before I/O; one result per entry in order; credentials per entry or from the three variables, read at load; caps are the only limits; memory per loader. Nothing is promised that the code does not do.

COMMANDS RUN

- `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte), vidbyte.__version__)"` → `...\vidbyte-sdk-public-skill-loader\vidbyte\__init__.py 0.3.1`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader` → `67 passed in 0.33s`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/jev_skills_preload tests/test_jev_skill_preload.py` → `426 passed, 1 skipped in 4.70s`
- `PYTHONPATH=$(pwd) python <scratchpad>/s4_eng_probe.py` (hostile arguments, leaks, both doors, scale, loops) → last lines `cancelled propagated; remembered=0` / `python 3.11.0`
- NUL and invalid-character path probe (inline Python) → `load -> [(None, ''), (NOT_FOUND, ...)]` for each case, no exception
- `PYTHONPATH="$(pwd);<scratchpad>" S4_MUTANT=<M1..M15> python -m pytest -q -p no:cacheprovider -p s4_mutants tests/features/public_skill_loader` → baseline `67 passed`; every mutant `N failed` (counts above)
- In-memory REPO_MAP heading-rename probe → `guard passes: True | stale seen: False`
- `git show --stat a7ed9cde` / `git show --stat 29fbfd28` → the 0.3.0 bump touched 10 files with no test file
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 56541481fbb32624aa70ff26b9f4feeb496ea273 (vidbyte-sdk 0.3.1, 642 exports).`
- `git diff --stat c9d31a7f..c691c176 -- . ':!docs' ':!tests'` → `15 files changed, 88 insertions(+), 33 deletions(-)`
- `git grep -n -E "0\.3\.0|0, 3, 0|0_3_0" c691c176 -- ':!docs'` → no output; `git grep -n "0\.3\.1" c691c176 -- ':!docs' ':!tests'` → 9 lines
- §4 snippet saved as a file and run from an empty temp folder → the three exact lines
- `PYTHONPATH=$(pwd) python lint/run.py` → `SDK-LINT: PASS`; `git status --short` was identical before and after
- Fresh-process import-order checks (5 statements) → each `ok`
