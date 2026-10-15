# S1 spec review, round 2: public-skill-loader (spec r2, `3a793017`; HEAD `a57b60b4`)

VERDICT: SOUND WITH FIXES — all six round-1 findings are resolved, and the r2 design (lists accepted, 0.3.1, one name rule checked across both doors) is correct against the code. But one new §13 instruction would lead the blind test author to write an INV-18 test that a correct build fails, and four small text gaps remain.

## WHAT THE SPEC GETS RIGHT

- **D-14 is the right size, and its mypy claim is true.** I type-checked the exact row 2(b) expression with `python -m mypy --config-file lint/mypy.ini` (the S009 invocation, `lint/core/mypy.py:56`), with and without `--strict`:
  - The inline form passes, and the revealed type of `self.entries` is `tuple[SkillEntry | SkillDocument, ...]`.
  - The separate-boolean form adds `arg-type` at the `SkillEntries(...)` call.

  Converting a list also takes a snapshot, so a caller who mutates its list afterwards cannot shift the results. The `Sequence[...]` annotation is narrower than the runtime check, and the Jev door already works the same way: it is annotated `tuple[...]` but accepts any iterable (`settings.py:83`, `:96-101`), and `test_skill_sources_entries.py:206` passes it a list with `# type: ignore[arg-type]`. Do not "fix" this.
- **The version move is exact.** At `c9d31a7f`, `git grep -n "0\.3\.0" -- ':!docs'` finds exactly the nine lines named in §9.2 row 7, at those line numbers. INV-16 and AC-11 check the nine places by name, with no grep for the old literal. The publish workflow's tag check (`.github/workflows/publish.yml`, step "Verify tag matches package version") requires the tag to equal `v{version}`, which supports D-13.
- **The consumer contract and the author report agree with §8.5.** I compared `reports/S1-spec-author.md` "Answers to consumer requirements" items 1–7 with §9.2 rows 1–7. They agree on:
  - the names, and that `load()` is async;
  - credentials per entry, with the environment read only at `load()`;
  - the 1 MiB inclusive whole-file cap, `TOO_LARGE` remembered, and the corrected "size and cap, or the cap alone" detail;
  - no parser by default;
  - the 13 root names;
  - 0.3.1, plus the CLI pin fact.

  I found no contradiction.
- **The R-3 fix adds no import hazard.** Row 15 is a header-only edit, so `__all__: list[str] = []` stays and nothing is imported. `import vidbyte` already loads `vidbyte.agents.skills.loader` (probe: `'vidbyte.agents.skills.loader' in sys.modules` is `True` after `import vidbyte`), so row 3(b)'s root import adds no new import-time path. A-8 holds.

## FINDINGS

R-7 [Major] [L10] §13 "Both doors" vs INV-18/AC-18 (also EC-28, and the §12.3 "Serves" column). §13 invites the blind test author to reuse all four `DUPLICATES` cases for INV-18, but one case holds strings. The public door rejects that case with different `details`, so a test built on it fails against a correct build.
  Evidence:
  - §13: "its duplicate test pins `details == {"names": [...]}` exactly (`test_skill_sources_entries.py:216-229`, whose `DUPLICATES` table gives four cross-kind cases to reuse)".
  - INV-18 covers only "any tuple or list `t` whose elements are all `SkillEntry` or `SkillDocument` instances". AC-18 names only three cases.
  - Repo: `tests/features/jev_skills_preload/test_skill_sources_entries.py:218` is `("entry-named-like-a-string", lambda: ("one", "two", InlineSkill(name="inline_skill_2", ...)), ["inline_skill_2"])`.
  - Row 1(b) runs the element check (2) before the name check (3). So `SkillLoader` raises `details == {"position": 0, "entry_type": "str"}`. `JevAlignmentSettings` turns `"two"` into `inline_skill_2` and raises `{"names": ["inline_skill_2"]}` (`vidbyte/agents/jev/settings.py:103-121`).
  - A second instance, EC-28: "A dict is iterated by its keys, so its first key is rejected as a non-entry element." This holds only when the first key is not an entry. Under D-14, `{LocalSkill(...): x}` is accepted as the tuple of its keys.
  - Traceability: no §12.3 row lists FR-12, INV-18, AC-17, or AC-18 in its "Serves" column. Only §12.1 W-2 does.

  Failure: S2 follows §13 and runs AC-18 over all four `DUPLICATES` cases.
  - After a correct implementation, the string case raises unequal `details`, and its test stays red.
  - The implementer may not edit tests (§14), so it stops BLOCKED, and the pipeline needs a round trip to repair the test.
  - An EC-28 test that uses a dict keyed by entries fails the same way.

  Smallest fix:
  - §13: "three of its four cases (`local-and-github`, `document-and-vendor`, `two-vendors`). `entry-named-like-a-string` holds strings, which INV-18 does not cover; the public door rejects that case at position 0."
  - EC-28: "A dict is iterated by its keys. A key that is not an entry is rejected at its position; a dict keyed by entries is accepted as the tuple of its keys."
  - Add FR-12, INV-18, AC-17, and AC-18 to the "Serves" column of rows 1 and 2.

R-8 [Minor] [L10] §13 "Version (INV-16, AC-11)". The note warns against `importlib.metadata.version`, but not against the two SDK paths that call it: `VersionResolver.resolve()` and `vidbyte --version`. Read through those paths, the fallback literal INV-16 names is unobservable here.
  Evidence:
  - §13: "read the expected value from the worktree's own `pyproject.toml` or the nine files, never from `importlib.metadata.version("vidbyte-sdk")`".
  - INV-16 lists "the `VersionResolver.resolve` fallback in `vidbyte/cli/__init__.py`".
  - Repo: `vidbyte/cli/__init__.py:53-58` returns `metadata.version("vidbyte-sdk")` and reaches `return "0.3.0"` only on `PackageNotFoundError`.
  - Probe, from the worktree root with and without `PYTHONPATH`: metadata `0.2.1`, `vidbyte.__version__` `0.3.0`.
  - No existing test or gate step trips on this. `tests/test_cli_interface.py:36-40` asserts only `"vidbyte-sdk "`, and the package-stage smoke test (`scripts/run_ci.py:180-217`) installs the built wheel into a fresh temporary venv.

  Failure: S2 writes `VersionResolver().resolve() == "0.3.1"`, or checks the `--version` output.
  - Locally it reads `0.2.1` and stays red after a correct build, so the implementer is BLOCKED.
  - In CI it tests the installed metadata, not the literal row 5 changes.

  Smallest fix: add one sentence to §13. "`VersionResolver.resolve()` and `vidbyte --version` read the same metadata first. The fallback at `vidbyte/cli/__init__.py:58` is observable only with `vidbyte.cli.metadata.version` patched to raise `importlib.metadata.PackageNotFoundError`, or by reading the file."

R-9 [Minor] [L11] §12.6 P3, §9.4, §14. After an approved merge or rebase, "repeat steps 1–4 as a new contract-only commit" cannot be followed when the export list (`__all__`) and the version are unchanged. §14 also both forbids and allows a rebase after the contract commit. Main has already moved, so this is a live question.
  Evidence:
  - §14 Ask first: "Merging or rebasing `origin/main` into this branch. If it is approved, … repeat P3 steps 1–4 as a new contract-only commit."
  - §14 Never: "Amend, squash, or rebase after generating the contract."
  - Repo: `scripts/generate-sdk-public-api.py:65-67` leaves the file untouched when the derived data is unchanged, and prints "already current … nothing written".
  - `--check` (`:88-106`) and C016 (`lint/rules/c016_public_api_contract_current.py`) compare only the data and the canonical bytes. Neither checks that `source.commit` is reachable. Main's own stamp, `998dc0da`, is not an ancestor of main, because PRs are squash-merged.
  - `git ls-remote origin refs/heads/main` returns `9aaf662a`, two commits past the base (#1089 and #1090). They touch only `vidbyte/context/algorithms/*` and four tests: no cited file and nothing under `lint/`.
  - Step 3's literal command, `git commit -m "chore(contracts): …"`, has no Co-Authored-By trailer and no spec ID, both of which §14 "Always" requires.

  Failure: the user approves an update from main.
  - Step 2 writes nothing, and step 3's `git add … && git commit` fails with "nothing to commit".
  - An implementer told to produce "a new contract-only commit" may be tempted to restamp the file by hand.
  - A literal reader cannot tell whether rebasing after step 3 is forbidden, or allowed with approval.

  Smallest fix:
  - §12.6 and §14: "Once the contract is committed, update from main by merge, not rebase. After any update or repair, run step 2. Commit (step 3) only if step 2 wrote the file. Always run step 4."
  - §14 Never: "Amend or squash after generating the contract, or rebase without Ask-first approval."
  - Step 3: add the trailer and "W-5, row 11" to the commit message.

R-10 [Minor] [L8] §12.3 rows 2(d) and 14. R-3's "per agent" correction reached only README `:48`. The same claim remains in the two texts that rows 2(d) and 14 already edit.
  Evidence:
  - `REPO_MAP.md:109`: "one shared loader, which reads nothing until the first run, remembers every document and permanent failure for the agent's lifetime". Row 14 replaces only "and today JevAgent's skill preload is its only consumer".
  - `vidbyte/agents/skills/loader.py:5`, ARCHITECTURE NOTE: "lives per loader (per agent)". Row 2(d) edits ROLE, FUNCTION INVENTORY, KNOWN EDGE CASES, RELATED DOCS, and TESTS, but not this line.
  - Row 12(d) already fixes README `:48` to "it lives per loader, which for JevAgent is per agent".

  Failure: after the PR, the map and the loader header still say that memory lasts for "the agent's lifetime", or "per agent". That is false for the agent-less loader the CLI builds, and it sits beside clauses this PR rewrote. This is the same review comment R-3 predicted for `:48` (AGENTS.md: "regenerate a wrong entry").

  Smallest fix:
  - Row 14 also rewords "until the first run … for the agent's lifetime" to "until it is first loaded … for the loader's lifetime (an agent's, for JevAgent)".
  - Row 2(d) also rewords the ARCHITECTURE NOTE's "(per agent)" to "(per agent, for JevAgent)".
  - AC-16 adds "or memory as living per agent".

R-11 [Minor] [L1] §9.2 row 7 and Q-8. Neither states the trade-off the user needs to weigh the override. The CLI's own pin comment makes 0.3.1 a deliberate minor-version crossing, yet the only difference in content from a 0.2.2 cut is three bug fixes.
  Evidence:
  - vidbyte-cli `pyproject.toml:42-45`: "The SDK is alpha and may change APIs between minor versions, so stay within 0.2.x until a newer minor is verified against this CLI."
  - The option text the user selected: "The CLI PR waits for SDK 0.2.2 on PyPI, which it already had to."
  - Repo: `git show --stat a7ed9cde` (#1085) touches only the eight version literals, the contract, and the release doc. The contracts at `179d8adc` and `c9d31a7f` list the same 639 exports, with none added or removed. `179d8adc..c9d31a7f` contains only #1085 to #1088, and #1086 to #1088 are compaction and Anthropic-provider fixes.
  - Row 7 says only "That excludes every 0.3.x release, so the floor must become `>=0.3.1,<0.4`."

  Failure:
  - The CLI pipeline resumes from §9.2, hits its own "stay within 0.2.x" rule, and either escalates again or re-verifies the new minor from scratch.
  - The user weighs Q-8 without knowing that 0.2.2 would buy only the `<0.3` cap, and would leave out #1086 to #1088.

  Smallest fix: add one sentence to row 7 and to Q-8. "The CLI's pin comment requires verifying a new minor. 0.3.0 (#1085) changed only version literals, and its root export list equals main's at `179d8adc` (639 names). 0.3.1 differs from a 0.2.2 cut from `179d8adc` only by #1086 to #1088 (plus this PR)." Do not change the decision.

## VERIFIED CLAIMS

Round-1 findings:
- **R-1 (version): resolved.** The base is `c9d31a7f`, and the version is 0.3.1 (D-13, NG-17, non-blocking Q-8). Rows 3(a) and 4–11 read `0.3.0` → `0.3.1`. INV-16 and AC-11 are positive, and §14 Ask-first covers updating from main. D-10 and Q-5 give three-of-three precedent: `29fbfd28` and `a7ed9cde` both add a `docs/design/release-*.md`. Only R-9's procedural gap remains.
- **R-2 (two copies of the name rule): resolved,** through INV-18, AC-18, FR-12, the §11 Conflicts entry, and Q-9. NG-10 states the message change correctly: Jev's text is "JevAlignmentSettings.skills must have unique document names." (`settings.py:121`). The fix introduced R-7.
- **R-3 (stale text): resolved for every line cited.** Rows 12(c) and (d) cover README `:20` and `:48`. Row 15 covers `__init__.py:4`, and row 3(f) covers the root `:24`. Sibling text remains (R-10).
- **R-4 (test pins): resolved.** `test_skill_sources_local.py:172-173` pins "agent" plus one of "new", "create", or "fresh". `test_skill_sources_vendor.py:287` and `test_skill_sources_github.py:208` pin "next run".
- **R-5 (tuple or list): resolved (D-14).** I checked that every listed section changed consistently: TL;DR, §2, §5, INV-2, AC-3/4/5/14/17, EC-1/2/6/28, row 2, §8.5, NFR-6, §9.2 row 1, §9.4, and the report.
- **R-6 (consumer table): resolved.** The preconditions and `details` shapes are in row 1, and the request cost is in row 3 and EC-27. The detail wording is correct: vendor body `vendor.py:202-203` and zip member `:213-214` give size and cap; the GitHub raw file goes through `fetch.py:88` (cap alone).

Repo claims:
- **Held.** At `c9d31a7f` and at HEAD, the version lives in exactly nine lines: `pyproject.toml:7`, `vidbyte/__init__.py:40`, `vidbyte/cli/__init__.py:58`, `vidbyte/mcp_server/server/core.py:79`, `vidbyte/tools/mcp/client.py:46`, `README.md:86`, `llms.txt:17`, `.github/ISSUE_TEMPLATE/bug_report.yml:19`, and `contracts/sdk-public-api.json:5`. A grep for `0, 3, 0`, `0_3_0`, and `0-3-0` finds nothing (A-6).
- **Held.** `publish.yml`'s tag check requires `v{project.version}`. Note: the workflow is currently `workflow_dispatch` only ("TEMPORARILY DISABLED").
- **Held (D-14, row 2(b)).** I ran mypy 2.3.1 with `lint/mypy.ini`, and again with `--strict`, using `--cache-dir=nul` so nothing was written. The inline form passes, and the boolean-variable form raises `arg-type`. With `Sequence`, a caller passing a generator, a set, or a str is rejected at type level. An `Iterable[...]` annotation would also pass the inline form and still reject str (an option, not required).
- **Held (INV-18) for tuples, lists, and mixed documents and entries.** Both doors turn any non-text iterable into a tuple and raise `details={"names": sorted(...)}` for repeated names. Not covered: string elements (R-7).
- **Held (§13 note).** Metadata reports `0.2.1` while `vidbyte.__version__` reports `0.3.0`. The package stage's smoke test, `vidbyte.__version__ == version('vidbyte-sdk')` (`scripts/run_ci.py:210`), runs in a fresh venv built from the wheel, so it does not fail locally. No existing test pins a version number. The gap is R-8.
- **Held (§12.6 and A-7).**
  - The generator refuses only while its inputs are dirty (`git status --porcelain` over `pyproject.toml` and `vidbyte/__init__.py`).
  - It stamps `HEAD` as `source.commit`, and it leaves the file untouched when the data is unchanged.
  - The commit-message pattern matches precedent `2d417dd9` ("chore(contracts): regenerate the public-API contract for 0.3.0").
- **Held.** Row 3's anchors are `:24` (the Error exports line), `:40`, `:301-302`, `:466-467`, `:474-488` (with `CodexAgentError` before the `ConfigurationError` slot), and `:876` (`"SkillUnavailableReason"`). There is a single `ConfigurationError` class (`vidbyte/lib/errors/base.py:284`). The #904 names reach the root through `from vidbyte.agents import (...)`, so the new deep imports duplicate no import line.
- **Held.** Row 12's anchors (`:3`, `:20`, `:48`), row 13's `vidbyte/agents/README.md:297`, row 14's `REPO_MAP.md:107-109`, and row 15's `__init__.py:4` text all match. A009 sizes: 7,545 and 22,158 characters (the spec says 7,596 and 22,470); both are far under 40,000.
- **Held.** The EC-27 and row 3 citations `github.py:118`, `:122`, `:128`, `:141`, and `:149` match the commit lookup, tree listing, file fetch, token read, and full-SHA skip.
- **Held (EC-29).** `v0.3.0` = `a7ed9cde`, and none of the three names is in its `__all__`. The CLI pins `vidbyte-sdk[codex]>=0.2.1,<0.3` at vidbyte-cli `pyproject.toml:45` and `:52`. Off by one line: `strict = true` is at `:123`, not `:122`.
- **Held (NG-15).** No test or module reads `loader.entries`, `memory`, or `resolvers`. No test pins an exact module `__all__`. `vidbyte/lib/dataclasses/__init__.py:212-221` imports the skills names explicitly, so `SkillEntries` stays internal, as §12.4 requires.
- **Held (NFR-3).** The ratchets in `lint/baseline.json` are C016 0, S009 350, S015 13, A001 642, A002 703, A003 36, A006 34, A009 0, C011 2, S012 0, S051 259, S060 32, and S063 4. `lint/baseline.json` and `lint/mypy.ini` are unchanged across `179d8adc..c9d31a7f`, and `lint/` is unchanged through `9aaf662a`.
- **Partly false (trivial, carried over from r1).** EC-2's "Today: `KeyError: 'a'`" is `KeyError: 's'` for `"skills/pdf"` (reproduced). This changes no code.
- **Stale.** §11 calls `c9d31a7f` "clean `origin/main`". `origin/main` is now `9aaf662a` (#1089 and #1090), with no overlap with any cited file (see R-9).
