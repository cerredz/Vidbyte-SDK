# S2 test author report: jev-skill-sources

Spec: `docs/spec/jev-skill-sources/spec.md` r3 (approved). Branch `feat/jev-skill-sources`. Base `ba3e4ca5`; S1 head `48709a8c`.

**Commits:**
- `b248bc3d test(skills): add failing tests for jev-skill-sources [AC-1..AC-29]`: the tests, `conftest.py`, `FEATURE.md`, and `test-plan.md`.
- A second commit records the §6.2 Proof column and this report.

## Inventory

The new tests are 12 modules plus one `conftest.py` in `tests/features/jev_skills_preload/`: 90 test functions and 354 collected cases. Every module has an A001 header. Feature imports sit inside `try/except ImportError`. An autouse `_feature_present` fixture then fails each test at setup with `raise FEATURE_MISSING.with_traceback(None)`, so collection never breaks the rest of the suite.

| Module | Functions | Cases | Covers |
|---|---|---|---|
| `test_skill_sources_acceptance.py` | 3 | 3 | AC-1 (§4 snippet verbatim), AC-2 (lazy construction), AC-18 (gate and specialist) |
| `test_skill_sources_contract.py` | 4 | 4 | AC-17 exports, enum values, INV-17 on `JevSkillResult`, `SkillResolution` |
| `test_skill_sources_entries.py` | 10 | 76 | INV-2, INV-3, INV-20, EC-1 to EC-15, EC-37, EC-38, EC-48 to EC-51, EC-75, D-4, D-15 |
| `test_skill_sources_markdown.py` | 3 | 36 | INV-11, EC-25 to EC-35, EC-109, EC-110, D-12, D-13, D-29 |
| `test_skill_sources_local.py` | 8 | 13 | AC-4, EC-15 to EC-22, EC-24, D-23 |
| `test_skill_sources_skills_sh.py` | 6 | 18 | AC-5, AC-6, AC-23, EC-39 to EC-46, EC-111 |
| `test_skill_sources_github.py` | 11 | 41 | AC-7, EC-52 to EC-71, EC-112, EC-117, D-18, D-30 |
| `test_skill_sources_vendor.py` | 15 | 115 | AC-8, AC-9, AC-19, AC-25, AC-26, AC-28, AC-29, EC-75 to EC-93, EC-115 |
| `test_skill_sources_fetch.py` | 8 | 15 | AC-20, AC-24, INV-19, NFR-1, D-9, D-27 |
| `test_skill_sources_memory.py` | 8 | 9 | AC-10, AC-15, AC-27, INV-5 to INV-10, EC-95 to EC-101 |
| `test_skill_sources_security.py` | 7 | 18 | AC-11, AC-12, AC-13, AC-22, INV-13, INV-14, EC-89 |
| `test_skill_sources_jev_wiring.py` | 6 | 6 | AC-3, AC-14, INV-22 to INV-27, EC-12, EC-104 to EC-108, D-8 |

AC-16 is the unchanged `tests/test_jev_skill_preload.py` (20 tests). AC-21 and the contract-JSON half of AC-17 are gate checks, so no pytest test was written for them. The reasons for every candidate not written are in `test-plan.md`.

Other files:
- `tests/features/jev_skills_preload/FEATURE.md` was rewritten (§12.3 row 29). It gains the source contract (entries, sources, content, requests, reasons, memory), the new actors and dependencies, three failure modes, the Test Suite Map for all new modules, and the updated omitted strategies.
- `docs/spec/jev-skill-sources/test-plan.md` and the spec's §6.2 Proof column were written. Nothing else in the spec changed.

## Fixtures added (`conftest.py`)

- **`fake_http` (`FakeSkillHttp`)** replaces `HttpTransport._send_once` with a URL-routed fake.
  - Answers are used in order, and the last one repeats.
  - An unrouted URL raises `AssertionError`.
  - `HANG` never finishes, `oversized(size)` reproduces the transport's cap refusal, and `connection_error()` mirrors `ProviderRequestError(status_code=None)`.
  - It records each request's URL, lowercase headers, `max_response_bytes`, `timeout_seconds`, and `client.follow_redirects`.
  - It records the backoff delays from a patched `vidbyte.lib.http.transport.asyncio.sleep`.
- **`jev(...)` (`NamedJev`)** replaces `DecisionModelHelper` with a stand-in that answers by skill name. It can fail a batch, omit an answer, or drop token counts, and it raises for a skill it was not told about.
- **`make_agent(skills)`** builds a `JevAgent` with `JevRuntimeSettings(preflight=())` and a capturing main runner (`CapturingRunner.systems`). **`bind_main_runner`** binds that runner to an agent built elsewhere.
- **`skill_md` and `write_skill`** write byte-exact `SKILL.md` files under `tmp_path`.
- **`record_io` (`IoRecord`)** records files opened, `stat` paths, environment keys read, and writes.
- **`spin_loop`** yields to the event loop a fixed number of times using the real sleep, never wall-clock time.
- **`_isolated_skill_environment`** (autouse) removes the three key variables and changes into `tmp_path`.

## Red run (before implementation)

Bootstrap: none needed. The pins were verified, not installed: Python 3.11.0, pytest 8.3.5, pytest-asyncio 1.3.0, PyYAML 6.0.2, httpx 0.28.1. `PYTHONPATH=$(pwd)` resolves `vidbyte` to this worktree.

```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q
...
ERROR tests/features/jev_skills_preload/test_skill_sources_vendor.py::test_mutated_archives_end_as_a_document_invalid_or_too_large[stored]
ERROR tests/features/jev_skills_preload/test_skill_sources_vendor.py::test_mutated_archives_end_as_a_document_invalid_or_too_large[deflated]
20 passed, 354 errors in 3.12s
```

Every error is the module's stored `ImportError`, raised at setup:

| Missing name | Errors |
|---|---|
| `ImportError: cannot import name 'AnthropicSkill' from 'vidbyte'` | 242 |
| `'GitHubSkill'` | 41 |
| `'SkillUnavailableReason'` | 36 |
| `'SkillsShSkill'` | 18 |
| `'LocalSkill'` | 13 |
| `'SkillSourceType'` | 4 |

The 20 passes are the existing module. `PYTHONPATH=$(pwd) python -m pytest tests/test_jev_skill_preload.py -q` → `20 passed`.

Errors per file, run one at a time:

| File | Errors |
|---|---|
| acceptance | 3 |
| contract | 4 |
| entries | 76 |
| fetch | 15 |
| github | 41 |
| jev_wiring | 6 |
| local | 13 |
| markdown | 36 |
| memory | 9 |
| security | 18 |
| skills_sh | 18 |
| vendor | 115 |

## Passability and non-vacuity check (scratch prototype)

To show the tests can go green under the spec, I wrote a throwaway implementation in the session scratchpad, outside the repository. It is never committed and was never placed in this worktree. It covers:
- the §8.5 records;
- the `vidbyte.agents.skills` package with every module in §12.3;
- the `JevSkillResult` and settings changes;
- the preload rewrite;
- the exports.

Results against it:
- **The whole pack passes:** `373 passed, 1 skipped`. The skip is the lowercase-`skill.md` row on Windows' case-insensitive filesystem. Five repeated runs gave the same result, and so did each file run alone (every file finishes in under 2.3 s).
- **51 seeded bugs, all caught:** I applied 51 single-line mutations to the prototype, and the new tests failed on every one. They included:
  - remembering transient failures;
  - replacing a remembered resolution;
  - resolving groups one after another;
  - no GitHub grouping, or grouping that ignores the token;
  - no Vidbyte-key check, or checking an unstripped token;
  - following redirects;
  - a narrowed zip catch list, no compression-method check, or no encrypted-member check;
  - no bare-body cap;
  - a stripped body, or lenient UTF-8;
  - an uncaught YAML `ValueError` or `RecursionError`, or `unsafe_load`;
  - a lock read outside `.agents/skills`;
  - an absolute local label;
  - a cap off by one;
  - a disk read on the event loop;
  - no deadline, a deadline frozen at import, or any `TimeoutError` treated as the deadline;
  - two retries;
  - a wrong `403` rule;
  - an unencoded ref;
  - the deepest tree match winning;
  - a vendor 3xx mapped to `not_found`;
  - a `bool` accepted as a version;
  - `latest_version_id` ignored;
  - no beta header;
  - a generic failed-batch detail;
  - `TOO_LARGE` dropped;
  - entries rejected by settings.
- **The fuzz test works alone:** run by itself, it fails when the zip catch list is narrowed (`ValueError: negative seek value`, `NotImplementedError: zip file version`).

The prototype found one real test defect, fixed before the first commit: AC-15 (see spec defect 2 below).

## What was pruned or changed while authoring

- **Detail wording loosened:** checks are case-insensitive keywords, often any-of, taken from the spec's "Detail must name" and "User sees" columns. They no longer require `api.github.com` in details other than connection failures.
- **Lock row removed:** the "lock without a `version` field" row is gone, because D-17 says only "version below 1".
- **Folded description accepts both values:** the AC-4 and parser rows accept both YAML readings (spec defect 4).
- **Symlink-loop test dropped:** the spec contradicts itself here (spec defect 3).
- **AC-15 assertion corrected at the agent boundary** (spec defect 2).
- **Smaller fixes:**
  - An unused commit route was removed from the retry test.
  - The `LocalSkill` import in the fetch module was moved inside the guarded block.
  - The `Oversized` import was replaced with `fake_http.oversized`.
  - A meaningless assertion in the AC-14 test was replaced with an exact system-prompt check.
- **Collection speed:** re-raising one stored `ImportError` grew its traceback with every raise, so the vendor file took 385 s. `with_traceback(None)` fixed it.
- **Imports sorted:** with `ruff --select I001 --fix --config lint/ruff.toml`. `ruff --select F,B,E9` is clean. Ruff-based lint rules scan only `vidbyte/`.

## Gates

- `python lint/run.py --rule A001` was run after `git add`: `A001 643 643 RATCHETED`, `SDK-LINT: PASS`, so no regression.
- The full `python lint/run.py` also gave `SDK-LINT: PASS`, with no rule REGRESSED.
  - Seven rules report IMPROVED at the S1 head. That is not this change; no baseline was touched.
- No production file, existing test, or other `docs/` file was modified.

## Spec defects found (testing the spec as written unless noted)

1. **The briefing says 30 acceptance criteria; the spec has 29 (AC-1 to AC-29).** All 29 are cited in `test-plan.md`.
2. **INV-9, AC-15, and EC-97 say a programming error "propagates out of `arun` unchanged". That cannot happen in this repo.**
   - `BaseAgent.arun` (`vidbyte/agents/base.py`, the `except Exception` branch near line 879) re-raises every non-`BaseException` as `AgentExecutionError(...)`, chained `from exc`.
   - Only `CancelledError` propagates unchanged.
   - Changing that would touch a file outside §12.3. The tests therefore check the binding intent:
     - at the agent, the raised `AgentExecutionError.__cause__ is error`;
     - at `JevSkillsPreload.run`, the original error passes through unchanged;
     - nothing is remembered.
   - S1 should correct the wording, and S3 must not wrap errors in the loader or the preload.
3. **EC-19 contradicts the specified `read_capped`.**
   - EC-19 maps a symlink loop to `fetch_failed`, which is not remembered.
   - But `read_capped` returns `None` "when no regular file at path", using `is_file()` like the cited exemplar. On Python 3.11 `is_file()` is `False` for a loop: verified here, `is_file False`, and `open` raises `OSError` errno 22.
   - So the specified design yields `not_found`, which is remembered. No test pins either reading.
4. **The folded `description: >` value is ambiguous (EC-31, AC-4).** "Kept as YAML returns it" depends on whether the frontmatter passed to `safe_load` ends with the line break before the closing `---`. That changes `"...them.\n"` to `"...them."`, so the tests accept both.
5. **`SkillResolution`'s invalid-construction error type is unspecified (§9.1).** The tests accept `ConfigurationError`, `TypeError`, or `ValueError`.
6. **A `skills-lock.json` without a `version` field is not covered by D-17 or EC-43.** It is not tested.
7. **D-21 does not say what label to use when `version="latest"` downloads directly.** It says "`<version>` is the version actually downloaded". The tests expect `anthropic:<id>@latest` (the requested segment) when no fallback happened, and the record's version after a fallback.

## Notes for the next agent

- The prototype lives at `<session scratchpad>/proto` (with sources in `proto_src`). It is not authoritative: it has no A001 headers, no narration, and no lint compliance. It shows only that a spec-faithful implementation passes. Do not copy it into the repo.
- The fake transport asserts on any unrouted URL, so the URL shapes in §9.2 are binding.
- The AC-24 and rendezvous tests patch `vidbyte.agents.skills.fetch.SKILL_FETCH_DEADLINE_SECONDS`. Read it when `get` runs.
- `core.autocrlf=true` is set in this checkout. The committed blobs are LF.
