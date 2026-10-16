# Feature: Public Skill Loader (the root door to skill sources)

## High-Level Feature Description

A program that never builds a `JevAgent`, vidbyte-cli first, turns skill entries from every #904 source (inline text, a local folder, a skills.sh install, a GitHub folder, an Anthropic or OpenAI skill) into skill text it can append to any agent's prompt, importing only from the `vidbyte` package root. It builds `SkillLoader(entries)` from a tuple or the list a repeatable option collects, awaits `load()`, and gets one `SkillResolution` per entry in input order: a `SkillDocument` whose `text` is the exact body, or a `SkillUnavailableReason` with a detail that names the fix. A malformed argument fails at construction with `ConfigurationError`, before any file, key, or URL is read. If this regressed, the CLI would crash on its own argument (a generator silently loading nothing, a string raising `KeyError` mid-load, a repeated entry aborting every other entry), leak a credential through an error, or be unable to import the loader at all because a name fell off the public contract.

## Contract

- `vidbyte.SkillLoader`, `vidbyte.SkillResolution`, and `vidbyte.ConfigurationError` are root exports, the same objects as their defining-module classes, and exported nowhere else new.
- `SkillLoader(entries)` takes any `collections.abc.Iterable` except `str` and `bytes` (every `Sequence` qualifies, including one registered with `Sequence.register`), turns it into a tuple once in iteration order, and validates it through `SkillEntries` (a tuple-only record in `vidbyte.lib.dataclasses.skills`). An exception raised while iterating the argument propagates unchanged. It raises `ConfigurationError` with exactly one `details` shape: `{"entries_type": <type>}` for text or a non-`Iterable` (including an object that iterates only through `__getitem__`), `{"position": <0-based>, "entry_type": <type>}` for the first non-entry element, `{"names": <sorted repeated names>}` for repeated names (exact, case-sensitive). The element check runs before the name check. An empty collection is valid.
- No message or detail of that error holds the rejected value or any token or key. Construction reads no file, no environment variable, and sends no request.
- `await loader.load()` returns one result per element in input order; expected failures are data, never exceptions. Credentials are per entry, with `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY` read only inside `load()`, and each credential goes only to its own fixed host.
- A loader remembers documents and permanent failures for its lifetime and can be loaded again on a new event loop (`asyncio.run` twice).
- `JevAlignmentSettings(skills=t)` and `SkillLoader(t)` agree on every tuple or list of entries and documents: both accept, or both raise with equal `details`.
- Every version-bearing place equals `pyproject.toml`'s version, which is at least `0.4.0`, and the folder docs describe the public door.

## Actors / Callers

- vidbyte-cli command setup (synchronous: `asyncio.run(loader.load())`), or any SDK caller inside a running loop (`await loader.load()`).
- `JevSkillsPreload.__init__`, the existing in-repo caller, which passes a valid tuple (covered by `tests/features/jev_skills_preload/`).

## Inputs and Preconditions

- Entries are constructed (and field-validated) by their own classes before the loader exists.
- The argument is a tuple, list, generator, or other `collections.abc.Iterable` that is not `str` or `bytes`, holding entries and `SkillDocument`s with unique names.

## Observable Outcomes

- A tuple of `SkillResolution` (document or reason plus non-blank detail, with `transient` derived from the reason).
- `ConfigurationError` with one of three `details` shapes at construction.
- Requests at the `HttpTransport._send_once` seam (URL and headers), file opens and stats, and environment reads.
- Root `__all__`, module `__all__` lists, the constructor's signature, version literals, and folder-doc text.

## State Transitions

Constructed (caller documents remembered at once) → loaded (documents and permanent failures remembered; transient ones asked again next load) → loaded again on any loop. A rejected construction leaves no loader and touched nothing.

## Invariants

- One result per element, in input order (INV-5); exact text (INV-7).
- Validation is complete at construction and does no I/O (INV-2, INV-4).
- Errors describe problems only through type names, positions, and names (INV-3).
- Both doors apply one name rule (INV-18).

## External Dependencies

Local filesystem (real, under `tmp_path`); `api.github.com`, `api.anthropic.com/v1`, `api.openai.com/v1` through `HttpTransport` (faked only at `_send_once`); the three credential environment variables (removed before every test).

## Known Failure Modes (failure inventory)

| Input + state | Wrong output if unguarded | Test |
|---|---|---|
| A generator, on a fresh loader (EC-1) | `load()` silently returns `()` | `test_any_non_text_collection_is_taken_once_in_its_iteration_order[generator]` |
| A generator holding a `SkillDocument` | memory built from the spent generator; `documents()` empty, `load()` raises `KeyError` | same |
| The caller's list cleared after construction | loader kept the list, `load()` returns `()` | same `[list]` |
| A dict keyed by entries (EC-28) | rejected as `entries_type: dict` by a `Sequence`-only gate, or converted through `.values()` | same `[dict keys]` |
| A bare str or bytes (EC-2) | split into characters and reported as `position: 0`, or `KeyError` from `load()` | `test_text_or_a_single_value_is_rejected_whole_before_any_io` |
| One entry passed instead of a collection | silently wrapped, or `TypeError` | same |
| `None`, a dict, a str, a `SkillResolution` element (EC-3, EC-7) | `KeyError`/`TypeError` from `load()`, a 1-based position (the Jev door counts from 1), or the last bad element reported | `test_first_non_entry_element_is_rejected_at_its_zero_based_position` |
| A repeated name beside a bad element | name error reported first | same |
| The same entry twice (EC-4), an entry and a document sharing a name (EC-5) | `ValueError: too many values to unpack` aborting every entry | `test_repeated_names_are_rejected_sorted_and_each_listed_once` |
| Several repeated names | unsorted, or each repeat listed per occurrence | same |
| Names differing by case, a trailing space, or Unicode form | rejected by a normalizing check | `test_names_differing_only_by_case_space_or_unicode_form_are_distinct` |
| An empty tuple or list (EC-8) | rejected by an "at least one" check, or a list returned | `test_empty_tuple_and_empty_list_load_nothing` |
| A secret string as the argument or element; credentialed entries repeating a name (T-3) | value echoed (whole or truncated) in message, repr, details, or the chained cause | `test_rejection_never_echoes_the_rejected_value_or_a_credential` |
| Variables changed between construction and load (T-1) | stale value read at construction; a credential sent to another host | `test_construction_reads_no_key_and_load_sends_each_credential_only_to_its_own_host` |
| A tuple or list with a repeated name across kinds (INV-18) | the two doors disagree | `test_both_doors_agree_*` |
| `asyncio.run(loader.load())` twice (INV-11) | loop-bound state fails on the second loop; remembered entries re-read | `test_second_asyncio_run_reuses_memory_and_retries_only_transient_failures` |
| Seven failing sources beside a healthy one (G-2) | one failure aborts the load or shifts results | `test_failing_sources_come_back_as_reasons_beside_a_healthy_entry` |
| A forgotten version literal (INV-16) | the CLI floor and the package disagree | `test_every_version_bearing_place_reads_the_release_version` |
| Stale "only consumer" docs (FR-10) | maintainers told the loader is Jev-only | `test_docs_describe_the_public_door` |

What an easy generated test would miss: a list mutated after construction, a generator that also carries a document, a non-zero position, two bad elements, the check order, sorted-and-unique names, a truncated secret echo, and a variable that changes after construction.

## Historical Regressions

The pre-PR loader's EC-1 to EC-4 behavior (observed at `179d8adc`): a generator loaded nothing, a str raised `KeyError: 's'` from `load()`, `None` or a dict raised from `load()`, and a repeated `LocalSkill` raised `ValueError` that aborted every entry. Each now has a boundary test above.

## Test Suite Map

- `conftest.py`: offline fixtures (URL-routed fake of `HttpTransport._send_once`, SKILL.md writer, file/environment recorder, isolated environment). Mirrors `tests/features/jev_skills_preload/conftest.py`, whose fixtures do not reach this folder.
- `test_public_skill_loader_acceptance.py`: the spec section 4 snippet, all six sources through the root door, failures as data, and two event loops (AC-1, AC-2, AC-7, AC-13).
- `test_public_skill_loader_boundary.py`: conversion and validation at construction (AC-3, AC-4, AC-5, AC-14, AC-17, EC-1 to EC-8, EC-28).
- `test_public_skill_loader_security.py`: no secret in a rejection, credentials per entry at load only and only to their own host (AC-6, AC-9).
- `test_public_skill_loader_both_doors.py`: the Jev door and the public door agree on names, curated and over a seeded sweep (AC-18, INV-18).
- `test_public_skill_loader_contract.py`: root exports, export placement, the constructor signature, and the tuple-only `SkillEntries` record (AC-10, INV-1, INV-15, D-6, D-14).
- `test_public_skill_loader_release.py`: the eight version literals (AC-11, INV-16).
- `test_public_skill_loader_docs.py`: the folder docs and headers describe the public door (AC-16).
- Source mechanics (per-source statuses, caps, labels, memory, concurrency, crash and cancellation) stay in `tests/features/jev_skills_preload/`; this PR does not change `load()`.
- Run: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader`.

## Omitted Testing Strategies

- Per-source status maps, inclusive caps (AC-8), crash and cancellation (AC-15), overlap and per-loader memory: `load()` is byte-identical in this PR, and `tests/features/jev_skills_preload/` already pins each through the same `SkillLoader` class.
- The contract JSON (`contracts/sdk-public-api.json`) and its version: lint C016 and `scripts/generate-sdk-public-api.py --check` own it; a pytest copy would be red by design between the source commit and the contract commit (spec section 12.6).
- Live network, browser, accessibility, migration, and load tests: an in-process library call with no UI or stored data; validation is one O(n) pass with no budget to measure.
- A sync twin, a byte limit, a credential parameter, and a source-string parser are not built (D-2, D-7, D-8, D-9), so they have no tests.
