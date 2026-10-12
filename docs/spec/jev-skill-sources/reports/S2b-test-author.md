# S2b test author (narrow pass): jev-skill-sources

This pass adds the tests that the S4 review proved missing: R-1, R-2, R-4, and R-6 in `review.md`. They are bound to spec r5: EC-24, EC-68, EC-118, EC-119, EC-43, EC-25/EC-27, and §9.2 "Local and skills.sh mapping". No production code changed, and no existing assertion changed. The only removed lines are module-header lines, rewritten to list the new functions and spec IDs; A001 needs those headers to stay accurate.

- Branch `feat/jev-skill-sources`, base HEAD `18903d3d` (clean).
- Test commit: `f90b0680`.
- Python 3.11.0, pytest 8.3.5, pytest-asyncio 1.3.0, httpx 0.28.1.

## What was added

| Finding | File | Added | At HEAD |
|---|---|---|---|
| R-1 / EC-68 | `test_skill_sources_github.py` | 5 rows in `UNUSABLE_ROWS`, run by `test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load`: `[[[]]]` (the shape Python 3.12+ parses the 2,000-level body to), `[1, "a", null]`, `[{"type": "blob"}]`, `[{"path": 7, ...}]`, and one usable item beside `[]` | red |
| R-1 guard | same file | `test_well_formed_listing_without_the_skill_stays_not_found` (`empty tree`; `folders and a submodule only`): `NOT_FOUND`, remembered | green by design; mutant-proven |
| R-2 / EC-118, EC-119 | `test_skill_sources_security.py` | `test_credential_a_header_cannot_carry_is_auth_failed_before_any_request`: 3 sources × {entry field, env fallback} × {U+2019, U+00E9, U+200B, tab, newline, DEL} = 36 cases | red |
| R-2 boundary | same file | `test_credential_a_header_can_carry_is_still_sent` (3 sources): an internal space and `~` are sent unchanged | green by design; mutant-proven |
| R-2 real seam | same file | `test_unencodable_credential_is_auth_failed_through_real_header_encoding` (GitHub `token=` with U+2019; `OPENAI_API_KEY` with U+2013). It restores the real `HttpTransport._send_once` and patches only `httpx.AsyncClient.send` | red: `UnicodeEncodeError` escapes `SkillLoader.load` |
| R-4 / EC-24 | `test_skill_sources_local.py` | `test_remembered_not_found_says_to_create_a_new_agent_after_fixing` | red |
| R-6 cap | `test_skill_sources_skills_sh.py` | `test_installed_skill_md_cap_is_inclusive_and_over_it_is_too_large` | green; kills 2 mutants |
| R-6 `OSError` | same file | `test_read_error_on_the_installed_file_is_fetch_failed_and_read_again` | green; kills 1 mutant |
| R-6 lock `OSError` | same file | `test_lock_that_raises_on_read_is_treated_as_absent` | green; kills 1 mutant |
| R-6 delimiter | `test_skill_sources_markdown.py` | `MALFORMED_FILES` row `space before the opening line` (`b" " + valid file` → `INVALID_SKILL`, keyword `---`) | green; kills 1 mutant |

In all: 8 functions and 6 table rows, which is 53 collected cases. No new module was added, so `FEATURE.md` is unchanged. No fixture was added to `conftest.py`. No §6.2 Proof cell grew, because no acceptance criterion covers these EC rows, so `spec.md` is untouched.

## Design choices, and why each test cannot pass vacuously

- **R-1.**
  - **Rows.** The rows feed the already-parsed shapes directly, so they fail on 3.11 as well; the existing 2,000-level row reaches only the `RecursionError` branch on 3.11. The existing row body asserts `FETCH_FAILED`, an "unexpected" detail, and a second load that sends both requests again.
  - **Mixed row.** The row "one usable item beside a list item" pins EC-68's "items that are not *all* objects": a fix that checks `any`, or "no usable paths", fails it.
  - **Guard test.** It keeps `tree: []` and real `type: tree`/`type: commit` items as `NOT_FOUND`, so an over-strict fix cannot turn a real miss into a transient fault that is retried on every run.
- **R-2: the main test.**
  - **Seam.** Calls go through `SkillLoader` with the pack's `_send_once` fake and no routes. `sent == []` is checked after both loads, and any attempted request makes the fake raise.
  - **Remembered.** Before load 2, the env var is set to a usable value. A loader that did not remember the miss would read the env var again and send.
  - **Entry precedence.** For the entry-field path, the env var holds a usable value from the start. This catches a fix that falls back to the env when the entry value is unusable (D-30: the entry wins).
  - **Detail.** It must contain the field (`token=`/`api_key=`) and the env var, as EC-118/EC-119 require. It must also contain "header" or "character", the any-of keyword style that the test plan calls loose; neither the Vidbyte-key detail nor the missing-key detail contains either word.
  - **No echo.** The value is `<prefix>HDRleftHALF<bad>HDRrightHALF`, and both halves must be absent from the detail and from `repr(result)`.
  - **Character mix.** Printable non-ASCII characters (U+2019, U+00E9) kill an `isprintable()`-only guard. ASCII controls (tab, newline, DEL) kill an `isascii()`-only guard.
- **R-2: what is left open.** The Vidbyte-prefix-plus-unsafe case is deliberately not tested (EC-118: "may get either guard's detail").
- **R-2: the real-seam test.** It holds two non-vacuity checks:
  - `httpx.Request(..., headers={"authorization": f"Bearer {unsafe}"})` raises `UnicodeEncodeError`.
  - A usable credential on the same patched path reaches `send` exactly once and ends `FETCH_FAILED`.

  This proves that the real `_send_once` and `build_request` ran. Today the unsafe load raises from `httpx/_models.py:82 _normalize_header_value` through `vidbyte/lib/http/transport.py:66`, which is the reviewed escape.
- **R-4.**
  - **Path removed first.** The absolute path is removed from the detail before the keyword check. The temporary path holds the test's name, which could otherwise satisfy "agent" or "new" by itself; on this machine it is `...\test_remembered_not_found_says0\...`.
  - **Keywords.** `agent` plus one of `new`/`create`/`fresh`, for natural phrasing. The absolute path must still appear (EC-16). Both the first load and the remembered second load are checked.
- **R-6.**
  - **Cap.** The over-cap file's first `SKILL_MARKDOWN_MAX_BYTES` bytes are a valid `SKILL.md`, so a removed check loads it.
  - **Read error.** `failures == []` proves the injected `PermissionError` was raised.
  - **Lock.** The lock names the fork, so a lock that was read would refuse the skill, and `len(lock_reads) == 1` proves the read really raised. The existing "unreadable: a directory" row never reaches the `except OSError`, because `read_capped` returns `None` for a directory; that is why `lock-oserror-propagates` survived before.
  - **Delimiter row.** EC-25 says "first line is not `---`" is invalid, and EC-27 allows only *trailing* spaces, so `" ---"` is `INVALID_SKILL`. The expectation comes from the spec, not from the code.

## Red run

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` →
```
44 failed, 382 passed, 1 skipped in 4.57s
```
The pack was 373 passed and 1 skipped before. The 382 passes are those 373 plus 9 new guard cases: 2 R-1 guard, 3 R-2 boundary, 3 R-6 skills.sh, and 1 R-6 markdown. The skip is the earlier lowercase `skill.md` row (Windows). Every failure is a new case:

```
test_skill_sources_github.py::test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load[tree items are lists as 3.12 parses 2000 levels]
test_skill_sources_github.py::test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load[tree items are not objects]
test_skill_sources_github.py::test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load[tree item has no path]
test_skill_sources_github.py::test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load[tree item path is not text]
test_skill_sources_github.py::test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load[one usable item beside a list item]
test_skill_sources_local.py::test_remembered_not_found_says_to_create_a_new_agent_after_fixing
test_skill_sources_security.py::test_credential_a_header_cannot_carry_is_auth_failed_before_any_request[<source> <field or env var>-<character>]  (36 ids:
    sources/paths: github token=, github GITHUB_TOKEN, anthropic api_key=, anthropic ANTHROPIC_API_KEY, openai api_key=, openai OPENAI_API_KEY;
    characters: curly quote, accented letter, zero-width space, tab, newline, delete)
test_skill_sources_security.py::test_unencodable_credential_is_auth_failed_through_real_header_encoding[github token= with a curly quote]
test_skill_sources_security.py::test_unencodable_credential_is_auth_failed_through_real_header_encoding[OPENAI_API_KEY with an en dash]
```

Reasons, from `--tb=line`:
- **37 cases: `conftest.py:104: AssertionError: unexpected skill-source request: GET <url>`.** These are the 36 R-2 cases and the mixed R-1 row. A request was attempted.
- **4 cases: `test_skill_sources_github.py:244: assert <SkillUnavailableReason.NOT_FOUND> is <SkillUnavailableReason.FETCH_FAILED>`.** These are R-1.
- **2 cases: `UnicodeEncodeError: 'ascii' codec can't encode character` U+2019 (position 22) / U+2013 (position 26).** These are the real-seam R-2 test. The traceback runs `loader.py:64` → `github.py:125`/`vendor.py:87` → `fetch.py:54` → `transport.py:48` → `transport.py:66 _send_once` → `httpx/_client.py:367 build_request` → `httpx/_models.py:82 _normalize_header_value`.
- **1 case: `AssertionError: No SKILL.md file at C:\...\skills\pdf\SKILL.md; point path= at the folder that holds it.` (`assert 'agent' in ...`).** This is R-4.

## Proofs in scratch copies

Harness: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4d43667e-6c86-4da6-8d31-a29ffd6bcc34/scratchpad/s2b/prove.py`.
- **Per variant.** The harness copies the worktree's `vidbyte/`, `tests/`, and `pyproject.toml` into a fresh `copies/<variant>/` folder and applies the edits. Each anchor must match exactly once.
- **Run.** It runs the same two test paths with `cwd` and `PYTHONPATH` set to the copy, then deletes the copy. The worktree is only read.
- **Killed.** A variant is "killed" when it adds failing ids to its baseline. The baselines are the HEAD copy (44 failing) for the R-6 mutants, and the fixed copy (0 failing) for the over-strict variants.
- **Runs.** The final run below came after the last test edit. An earlier run, before non-ASCII literals were rewritten as escapes, gave identical results.

```
head                             BASELINE | 44 failed, 382 passed, 1 skipped in 4.78s | failing: 44
fixed                            BASELINE | 426 passed, 1 skipped in 4.52s | failing: 0
skillssh-too-large-removed       KILLED | 45 failed, 381 passed, 1 skipped in 4.61s | new failures: 1
    test_skill_sources_skills_sh.py::test_installed_skill_md_cap_is_inclusive_and_over_it_is_too_large
skillssh-cap-off-by-one          KILLED | 45 failed, 381 passed, 1 skipped in 4.75s | new failures: 1
    test_skill_sources_skills_sh.py::test_installed_skill_md_cap_is_inclusive_and_over_it_is_too_large
skillssh-oserror-remembered      KILLED | 45 failed, 381 passed, 1 skipped in 4.74s | new failures: 1
    test_skill_sources_skills_sh.py::test_read_error_on_the_installed_file_is_fetch_failed_and_read_again
lock-oserror-propagates          KILLED | 45 failed, 381 passed, 1 skipped in 4.71s | new failures: 1
    test_skill_sources_skills_sh.py::test_lock_that_raises_on_read_is_treated_as_absent
markdown-strip-delimiter         KILLED | 45 failed, 381 passed, 1 skipped in 4.73s | new failures: 1
    test_skill_sources_markdown.py::test_malformed_file_is_invalid_with_an_sdk_written_detail[space before the opening line]
fix+tree-refuses-empty           KILLED | 1 failed, 425 passed, 1 skipped in 4.59s | new failures: 1
    test_skill_sources_github.py::test_well_formed_listing_without_the_skill_stays_not_found[empty tree]
fix+tree-blobs-only              KILLED | 1 failed, 425 passed, 1 skipped in 4.55s | new failures: 1
    test_skill_sources_github.py::test_well_formed_listing_without_the_skill_stays_not_found[folders and a submodule only]
fix+tree-any-not-all             KILLED | 2 failed, 424 passed, 1 skipped in 4.51s | new failures: 2
    ...[one usable item beside a list item], ...[empty tree]
fix+guard-isascii-only           KILLED | 18 failed, 408 passed, 1 skipped in 4.69s | new failures: 18   (every tab, newline, delete case)
fix+guard-isprintable-only       KILLED | 14 failed, 412 passed, 1 skipped in 4.59s | new failures: 14   (every curly quote and accented letter case + both real-seam cases)
fix+guard-refuses-space          KILLED | 3 failed, 423 passed, 1 skipped in 4.50s | new failures: 3    (test_credential_a_header_can_carry_is_still_sent[github, anthropic, openai])
fix+guard-github-only            KILLED | 25 failed, 401 passed, 1 skipped in 4.69s | new failures: 25   (all 24 vendor cases + the OPENAI_API_KEY real-seam case)
```

**The `fixed` variant.** It applies review.md's smallest fixes:
- **R-1.** The line-173 condition gains `or not all(isinstance(item, dict) and isinstance(item.get("path"), str) for item in tree)`.
- **R-2.** An `isascii() and isprintable()` guard goes before the bearer header in github.py `resolve` and before the prefix check in vendor.py `_key`. Each guard's detail names the field, the env var, and "a character an HTTP header cannot carry".
- **R-4.** The local not-found detail gains "This agent remembers the miss; create a new agent after fixing it."

With these fixes the pack is fully green, so no new test over-constrains wording or shape. The five R-6 mutants are byte-for-byte the verifier's `mutate.py` set, and all five survived before S2b.

## Lint

The test files were `git add`ed before linting.

- **`PYTHONPATH=$(pwd) python lint/run.py --rule A001`** → `A001 agent-readable-file-headers 642 642 RATCHETED` … `SDK-LINT: PASS`.
- **`PYTHONPATH=$(pwd) python lint/run.py`** → `SDK-LINT: PASS`. Nothing regressed.
  - The listed IMPROVED verdicts (A002, A007, C012, S001, S010, S051) are below-baseline counts in code that is not mine; the five test files have 0 S051 findings.
- **`ruff check`** (0.16.4, repo config) on the five files reports the same counts as HEAD: one pre-existing I001 per module, caused by the import guard inside `try`, and two in skills_sh. My first version added one PLE2515, because the file tool wrote a literal zero-width space. It is gone after the rewrite described under Deviations.
- **`ruff format --check`** reports every pack module, at HEAD as well. The pack is not ruff-formatted and the lint loop does not run the formatter, so I matched the existing long-line style.

## Deviations and things worth knowing

- **The file tools decode `\uXXXX` escapes.**
  - The Edit and Write tools turned the `"\u2019"`, `"\u200b"`, and similar escapes in my parameter text into literal characters, including an invisible U+200B in source. `\t`, `\n`, and `\x7f` were kept as typed.
  - I rewrote the two affected lines with a script that writes `chr(92) + "u%04x"`: `scratchpad/s2b/escape_nonascii.py`. The test files are pure ASCII again.
  - The same fix was applied to the error text in `test-plan.md`.
- **Deadline and seams.** No sleeps, no wall clock, and no network. The real-seam test refuses every connection at `httpx.AsyncClient.send` with `httpx.ConnectError`. The transport never retries a connection error.
- **Windows.** Environment values that hold a newline, a tab, DEL, or non-ASCII text were set and read back through `monkeypatch.setenv` with no problem (the fixed copy passes every env row).
- **`REAL_SEND_ONCE`** is taken from `HttpTransport.__dict__` when the module is imported, which happens during collection, before any fixture patches it.

## Commands run (final lines)
- Baseline: `... pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` → `373 passed, 1 skipped in 4.09s`.
- Red run, after the last edit and after the commit: `44 failed, 382 passed, 1 skipped in 4.57s`.
- `python -I scratchpad/s2b/prove.py <worktree>` → see the proofs section (`prove-final.txt`).
- `python lint/run.py --rule A001` and `python lint/run.py` → `SDK-LINT: PASS`.
- `git commit` → `f90b0680 test(skills): add tests for S4 findings R-1 R-2 R-4 R-6 [EC-24, EC-68, EC-118, EC-119]`.
