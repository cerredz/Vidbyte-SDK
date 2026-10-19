# S1 spec review, round 1: public-skill-loader (spec r1, `db1786a2`)

VERDICT: SOUND WITH FIXES — the design is the right size and is grounded in the code, but `origin/main` moved to 0.3.0 after this run's base, so the settled 0.2.2 bump has to go back to the user as a blocking question before S2 binds tests to it. A few doc and contract details also need correcting.

## WHAT THE SPEC GETS RIGHT

- **It exposes the one loader instead of building a second.** I reproduced the crashes that justify adding validation (§8.3, EC-4) on the base commit. `SkillLoader((LocalSkill(...), LocalSkill(...)))` with the same entry twice raises `ValueError: too many values to unpack (expected 1)` from `load()`, which aborts every entry. The same InlineSkill twice happens to load. So a root export alone is not a complete public door, and rejecting repeated names is required, not over-engineering.
- **JevAgent is provably untouched by the new constructor check.** I wrapped `SkillLoader.__init__` with a probe and ran `tests/features/jev_skills_preload`, `tests/test_jev_skill_preload.py`, and `tests/test_jev_done.py`. All 296 constructions passed a `tuple` of valid entries with unique names, so `SkillEntries` rejects none of them. `JevAlignmentSettings._normalized_skills` always returns such a tuple (`settings.py:89-122`). INV-12 holds.
- **The consumer contract states verified code facts.** Credentials are per entry, and the environment is read only inside `load()` (`github.py:141` uses `os.environ.get` and strips; `vendor.py:121-123` goes through `resolve_api_key`, and a missing key gives `AUTH_FAILED` with no request). The 1 MiB cap counts the whole file (`local.py:41` uses `fstat`). `TOO_LARGE` is not transient, so it is remembered. `load()` is async, and the reasoning about C011 and `TextModelRunner.run` is correct. Root-exporting `ConfigurationError` (D-5) is justified: no error base class is a root export today (`VidbyteSdkError` is absent too), and every entry constructor raises it.
- **The export and contract mechanics are exact.** I applied row 3's four edits to a copy of `vidbyte/__init__.py` and piped it to `ruff --select I001`: "All checks passed!". The generator's inputs are exactly `('pyproject.toml', 'vidbyte/__init__.py')`, and the contract records only names, version, and distribution. So the order in §12.6 is right (source commit, then generate, then a contract-only commit, then `--check`), and A-7 holds.

## FINDINGS

R-1 [Blocker] [L11] §1, §9.4, §12.3 rows 4–11, INV-16/AC-11, §15. The spec assumes its base is the current `main`, but `origin/main` moved to 0.3.0 after the base. The settled 0.2.2 bump now conflicts with `main` on every version file and would lower `main`'s version if merged. The spec never says so.
  Evidence:
  - The spec sets `base_commit: 179d8adc…`. Rows 4–10 say "`0.2.1` … becomes `0.2.2`". INV-16 says "`git grep -n "0\.2\.1" -- ':!docs'` prints nothing". D-10 cites two release-doc precedents.
  - `git log --format='%h %cd %s' 179d8adc..origin/main` shows `a7ed9cde 2026-10-15 15:34:51 release: bump vidbyte-sdk to 0.3.0 with the output connectors (#1085)`, followed by #1086, #1087, and #1088 (`origin/main` is now `c9d31a7f`).
  - `git show origin/main:contracts/sdk-public-api.json` shows `"version": "0.3.0"`.
  - `git show --stat a7ed9cde` lists the same nine literal files plus `docs/design/release-0-3-0.md`.
  - request.md was captured at `invoked: 2026-10-15 15:04`, before the bump. Its premise is "the last bump (0.2.0 → 0.2.1)".
  - vidbyte-cli `pyproject.toml:45,52` pins `vidbyte-sdk[codex]>=0.2.1,<0.3`.

  Failure: an implementer builds exactly §12 on `179d8adc`.
  - (a) The draft PR conflicts with `main` on all ten version-bearing files. Resolving toward the PR sets `main`'s `[project].version` from 0.3.0 back to 0.2.2 (`publish.yml` checks that the tag equals `v{version}`). Resolving toward `main` leaves no commit with `version = "0.2.2"`, which the CLI's C029 needs.
  - (b) After any merge or rebase of `main`, the INV-16/AC-11 grep passes even with no bump, because `main` has no `0.2.1` literal left. And S2 would pin "0.2.2" in tests on a premise that is no longer true.
  - (c) If the CLI floor is ever written `>=0.2.2` without the `<0.3` cap, pip installs 0.3.0, which has no `SkillLoader`, and the CLI fails with `ImportError` at startup.
  - (d) Q-5's evidence is stale: three of three bumps (0.2.0, 0.2.1, 0.3.0) added `docs/design/release-*.md`.

  Smallest fix: keep 0.2.2 in the spec (it is settled), but escalate.
  - Add a **blocking** Q-8: "`origin/main` has been at 0.3.0 since #1085 (`a7ed9cde`), 30 minutes after this run started. Keep 0.2.2 as decided? If so, this PR cannot merge into `main` without lowering its version, and 0.2.2 would be released from this branch. Or name the version." Default: the pipeline holds before S2.
  - Record the fact in §11 "Baseline" and §9.4.
  - Restate INV-16 as a positive check: the nine named places and the contract read the confirmed version. Do not rely on a grep for the old literal.
  - Add "merge or rebase `origin/main`" to §14 Ask first, pointing to §12.6's rule to repeat the contract steps.
  - Update Q-5's evidence to three of three. If the user wants a release note, the user can name `release-0-3-0.md` as readable, which satisfies the AGENTS.md rule on `docs/`.

R-2 [Major] [L4] NG-10, D-3/D-4, §11 "Conflicts". NG-10 leaves the unique-name rule written twice, in `SkillEntries` and in `JevAlignmentSettings`. The field guide says a rule like this belongs to one record. The spec neither names the conflict nor guards against the copies drifting apart.
  Evidence:
  - NG-10: "Making `JevAlignmentSettings._normalized_skills` delegate to the new record. *Why not:* that code is untouched…". Row 1(b)(3) adds the same seen/duplicate check with `details={"names": sorted(repeated)}`.
  - Repo: `vidbyte/agents/jev/settings.py:113-121` has the same loop, with `details={"names": sorted(duplicates)}`.
  - `field-guide/vidbyte-sdk/strict-config-dataclasses.md:18-23`: "Any primitive value validated inline in more than one call site belongs in its own frozen dataclass … after the refactor only the dataclass's `__post_init__` should contain them". This comes from owner review on PR #352. AGENTS.md §5 says the same.
  - Jev's duplicate behavior is pinned only as `ConfigurationError` with `details == {"names": names}` (`test_skill_sources_entries.py:226-229`, `test_jev_skill_preload.py:175-185`).

  Failure: a later fix to one copy leaves the other door on the old rule. For example, names could become case-insensitive because a skills.sh name is a folder and Windows folders ignore case. One tuple would then pass `JevAlignmentSettings` and fail `SkillLoader`, or the reverse, and D-4's stated reason ("a skill name means one thing through both doors") would quietly stop being true. A reviewer who applies the field guide will flag the second copy. Without delegation, `SkillEntries` is also a record with a single caller.

  Smallest fix: keep NG-10, because JevAgent must keep its behavior and §14 bars edits under `jev/`. Then:
  - (a) Name the field-guide lesson in §11 "Conflicts", with the reason it gives way here.
  - (b) Add a must-not-regress invariant: for any tuple `t` of entries and documents, `JevAlignmentSettings(skills=t)` and `SkillLoader(t)` either both accept repeated names or both raise, with the same `details["names"]`. That gives the test author a check that catches drift.
  - Optionally, give the user a non-blocking Q-n (default no): `_normalized_skills` could end with `SkillEntries(entries=tuple(skills)).entries`. The details already match, so only the message text would change.

R-3 [Major] [L8] §12.3 row 12, INV-15, NG-11. Row 12 adds a "Public door" bullet but leaves the README's existing contract bullet, which says the constructor "only stores" the entries. INV-15 also freezes a header that names `JevSkillsPreload` as the only module that imports the loader. An implementer who does exactly §12 ships text that the change makes false.
  Evidence:
  - `vidbyte/agents/skills/README.md:20`: "`SkillLoader(entries)` only stores them". After this PR the constructor validates and raises.
  - README `:48`: "it lives per agent".
  - `vidbyte/agents/skills/__init__.py:4`, ROLE IN CODEBASE: "Imported through its modules: vidbyte.agents.skills.loader (SkillLoader) by JevSkillsPreload…". After this PR, `vidbyte/__init__.py` imports it too.
  - Spec INV-15: the file "stays byte-identical". Row 12 changes only `:3` and adds one bullet.
  - The root header line "Error exports: MCP, pipeline, workflow, multi-agent execution, task-ledger, and agent-transfer error families" is frozen by NG-11, while this PR root-exports the general `ConfigurationError`.

  Failure: the README's first contract bullet says the constructor only stores the entries, directly above the new bullet that says it raises `ConfigurationError`. The package header lists one importer where there are now two. AGENTS.md says to "regenerate a wrong entry", and A001's guidance is to "update it when the module's contract changes", so this draws a review comment.

  Smallest fix:
  - Row 12 also rewrites `:20` to "checks the tuple (entries or documents with unique names) and stores it; nothing is read", and `:48` to "lives per loader, which for JevAgent is per agent".
  - Relax INV-15 to "`__all__ == []`, with no new imports or exports". Add a row that updates the `__init__.py` ROLE line to name the root import.
  - Add `ConfigurationError` to the root header's "Error exports" line. This narrows NG-11 by one line.

R-4 [Minor] [L10] NG-9, D-11, Q-7. The premise that rewording the agent-centric details "requires editing tests" is false. The tests pin words, not sentences.
  Evidence:
  - `test_skill_sources_local.py:170-174` asserts only that "agent" and one of "new", "create", or "fresh" appear.
  - `test_skill_sources_vendor.py:287` and `test_skill_sources_github.py:208` pin the substring "next run".
  - So a detail such as "…create a new agent (or a new SkillLoader) after fixing it" passes the unedited tests.

  Failure: Q-7 asks the user to approve test edits that are not needed. The user may turn down a free clarification because of a cost that does not exist.

  Smallest fix: correct NG-9, D-11, and Q-7 to say that a rewording which keeps the pinned words needs no test edit. Keep the default as not built (NG-14; nothing in the conversation asked for it).

R-5 [Minor] [L4] EC-6, D-3. Accepting only a `tuple` departs from both nearby examples. D-3 cites the field-guide entry that says to convert loose inputs before building the record, but skips that step.
  Evidence:
  - `strict-config-dataclasses.md:13`: "Before building the record, `__init__` turns loose inputs into concrete values: … a `Tools` catalog becomes a tuple."
  - `vidbyte/agents/coding.py:78`: `tools=tools.all() if isinstance(tools, Tools) else tuple(tools)`.
  - The Jev door accepts a list: `test_skill_sources_entries.py:206` passes `skills=[...]`.

  Failure: the CLI's repeatable `--skill` option collects a list. `SkillLoader(list_of_entries)` raises `ConfigurationError`, while the same list is accepted by `JevAlignmentSettings`.

  Smallest fix: choose one, and state it in the consumer table row 1.
  - Either convert any non-`str`/`bytes` iterable with `tuple(...)` before building `SkillEntries`. EC-1 and EC-2 stay fixed, and a `str` is still rejected.
  - Or keep the strict tuple, and record it as a D-row with its runner-up and the condition that would flip it.

R-6 [Minor] [L1] §9.2 consumer rows 1 and 4, EC-14. The consumer table the CLI will resume from leaves out the constructor's preconditions and misstates the oversize detail.
  Evidence:
  - (a) Row 1 says only "Call `SkillLoader(entries)` (validates, no I/O)". The tuple-only rule, unique names, and the `ConfigurationError` `details` keys appear only in INV-2/INV-3 and the author report.
  - (b) Row 4 says oversize is reported with "`detail=<size and cap>`", and EC-14 says the same. But `fetch.py:88` (a GitHub SKILL.md over the cap, or any download over 32 MiB) says only "is larger than its {max_bytes}-byte cap". Local, skills.sh, and vendor details do include the size.
  - (c) Each command builds a fresh loader, which pays the commit, tree, and file requests (3 GitHub requests) for each `GitHubSkill` with no pinned ref and no path (`github.py:139-152`). Anonymous GitHub allows 60 requests an hour, so about 20 commands an hour before `RATE_LIMITED`. `ref=<40-hex SHA>` plus `path=` cuts this to one request.

  Failure: a CLI author working only from the table either hits `ConfigurationError` on a list or on derived names that collide, or matches on a byte count the detail does not contain.

  Smallest fix: three sentences in §9.2. Add the preconditions and `details` keys to row 1. Correct row 4 and EC-14 to "size and cap, or the cap alone for a network download". Add one line on per-command request cost and pinning to row 3 or EC-10.

## VERIFIED CLAIMS

- **Held.** `SkillLoader`, `SkillResolution`, and `ConfigurationError` are not in `vidbyte.__all__` (639 names), and neither is `VidbyteSdkError`. There is no root-name collision for the three new names.
- **Held for the base, now stale (R-1).** `git grep -n "0\.2\.1" -- ':!docs'` finds exactly the nine places in §9.2 row 7, and the line numbers match. But `origin/main` is at 0.3.0.
- **False now.** "`base_commit` is the origin/main the worktree was created from" was true at creation. `origin/main` has since gained four commits, including the 0.3.0 bump.
- **Held (A-7).** The generator refuses when its inputs are dirty, and `derived.read_paths == ('pyproject.toml', 'vidbyte/__init__.py')`. The contract data is exports, version, and distribution only. `--check` passes today at 0.2.1 with 639 exports.
- **Held (INV-12, A-4).** All 296 `SkillLoader` constructions in the area suites and `test_jev_done.py` pass a tuple of valid entries with unique names (probe plugin). Every in-repo call site passes a tuple.
- **Held.** EC-4 (the same `LocalSkill` twice raises `ValueError`) was reproduced. The same `InlineSkill` twice loads both.
- **Held.** AC-1's first two output lines (`house-review loaded 22 bytes`, `pdf not_found False`) were reproduced on the base with the private import.
- **Held (INV-11, AC-13).** A second `asyncio.run(loader.load())` on the same loader returns equal results. `HttpTransport.request` opens one `httpx.AsyncClient` per request (`transport.py:66`).
- **Held (INV-9, §9.2 row 3).** `github.py:141` reads `GITHUB_TOKEN` with `os.environ.get` and strips it, and unset means anonymous. Vendor keys go through `resolve_api_key`, and a missing key gives `AUTH_FAILED` with "pass api_key= on the entry or set {env_var}". The endpoints are `https://api.anthropic.com/v1` and `https://api.openai.com/v1`, and the variables are `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`. Nothing is read at construction (`get_default_endpoint` and `get_api_key_env_var` are static maps).
- **Held, with one exception.** `SKILL_MARKDOWN_MAX_BYTES = 1_048_576` is at `constants/skills.py:30` and is measured over the whole file. `TOO_LARGE` is not in `SKILL_TRANSIENT_REASONS`, so it is remembered. The claim that the detail carries the size is false for `fetch.py:88` (R-6).
- **Held.** C011 `_ENTRY_SUFFIXES = ("Agent", "Runner", "Harness", "Session", "Machine")`. `TextModelRunner.run` raises inside a running loop (`text.py:93-100`). No `*_sync`/`load_sync` precedent exists for loaders.
- **Held.** Row 3's import placements and the `ConfigurationError` slot after `CodexAgentError` pass ruff I001 (simulated over stdin). A006 skips the root `__init__.py`. No file-length lint rule exists.
- **Held.** The NFR-3 ratchets match `lint/baseline.json`: C016 0, S015 13, A001 642, A002 703, A006 34, A009 0, C011 2, S012 0, S051 259, S060 32.
- **Held.** `documents()` already exists (`loader.py:77`), so it is not new and needs no budget line.
- **Held.** D-6's precedents for root deep imports (`vidbyte/__init__.py:301`, `:441`). The CodingAgentSettings tuple check (`lib/dataclasses/coding.py:152-153`), although `CodingAgent` converts to a tuple first (R-5).
- **Held.** NG-16: there are no skill-source mentions in `README.md`, `llms.txt`, `skills/`, or `artifacts/`.
- **Partly held (R-4).** NG-9 says tests pin the details. They pin words, not whole sentences.
