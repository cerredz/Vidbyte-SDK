# S1 spec author report: public-skill-loader

Status: **DONE (r5)**. Spec r1 was committed at `db1786a2` (`eba57e6c` after the orchestrator rebased onto `c9d31a7f`), r2 at `3a793017`, r3 (approved) at `843e2852`, and r4 at `bdf23937`. Spec r5 (S5 findings R-C11 to R-C13, plus the user's Q-8 answer: version 0.4.0) and this updated report are committed together on `feat/public-skill-loader`. The FEATURE.md wording is a separate commit. See §6 to §9. The "Answers to consumer requirements" section at the end matches r5. Answer 7 is corrected in place.

## 1. What I read

- **Doctrine.** In full: `house-style.md`, `spec-template.md`, and `vidbyte-gates.md`.
- **Request and recon.** In full: `request.md`, `context/code-map.md`, and `AGENTS.md`. `CLAUDE.md` is just `@AGENTS.md`.
- **Field guide.** The index, then these entries in full:
  - `local-ci-verification.md`
  - `blocking-lint-invariants.md`
  - `strict-config-dataclasses.md`
  - `comment-format.md`
  - `class-bound-helpers.md`
  - `review-scope.md`
  - `provider-api-contracts.md`
  - `prebuilt-agents.md`
  - `agents-md-map.md`
  - `declarative-config-resolution.md`
- **SDK source.**
  - Read in full: every file in `vidbyte/agents/skills/` (`loader.py`, `__init__.py`, `README.md`, `resolver.py`, `inline.py`, `local.py`, `markdown.py`, `github.py`, `vendor.py`, `fetch.py`, `skills_sh.py`, and `anthropic.py` from line 14 on), `vidbyte/lib/dataclasses/skills.py`, `vidbyte/lib/constants/skills.py`, `vidbyte/lib/enums/skills.py`, and `vidbyte/agents/jev/alignment/skills.py`.
  - Read in part: `vidbyte/agents/jev/settings.py:1-125`; `vidbyte/agents/jev/agent.py:75-95`; the import statements in `vidbyte/__init__.py` and the skill lines of its `__all__`; `vidbyte/lib/errors/base.py` (`VidbyteSdkError`, `ConfigurationError`); `vidbyte/lib/runners/text.py:88-102`; `vidbyte/agents/base.py:1050-1062`; `vidbyte/lib/http/transport.py` (one client per request); `vidbyte/lib/registries/models.py:168-177`; `vidbyte/lib/dataclasses/jev.py:3770-3790`; `vidbyte/lib/dataclasses/coding.py:145-156`.
- **Gate and contract tooling.**
  - Lint rules: the C011 header and suffix list, and the A009 header.
  - `scripts/generate-sdk-public-api.py`: the header and lines 60-130.
  - `scripts/run_ci.py:255-272`.
  - `contracts/README.md`, and the head, skill lines, and tail of `contracts/sdk-public-api.json`.
  - The baselines in `lint/baseline.json`, and `.github/workflows/static-policy.yml:20-32`.
- **Docs and maps.** `REPO_MAP.md:100-112` and `vidbyte/agents/README.md:290-300`.
- **Tests.**
  - `test_skill_sources_contract.py` in full.
  - The conftest header and its fixture list.
  - Every `SkillLoader(` and `JevSkillsPreload(` call site under `tests/`, read to confirm each passes a tuple with unique names.
  - The wording pins in `test_skill_sources_local.py:158-175` and `test_jev_skill_preload.py:155-196`.
- **Git history.** `git show --stat` of the 0.2.1 bump (`29fbfd28`), the 0.2.0 bump (`90f36272`), and the docs file list of #904. File names only; nothing under `docs/` was opened.
- **Consumer (read-only).** The vidbyte-cli S1 report in full; vidbyte-cli `code-map.md:400-430`; the CLI's `services/mcp/sdk.py` imports (how it reaches SDK errors).
- **Commands I ran.** All were read-only:
  - `git grep` for the version literals.
  - Python probes that only import from the worktree or run in my scratchpad: the vendor environment-variable names and endpoints, root `__all__` membership, the current loader's behavior on bad inputs, import order in fresh processes, and the §4 snippet's first two output lines.

## 2. Approaches weighed

1. **Root-export only** (the smallest). Add `SkillLoader` and `SkillResolution` to the root, bump the version, and change nothing else. **Rejected.** I ran the current loader on bad inputs:
   - A generator silently gives `()`.
   - A str gives `KeyError: 'a'` from `load()`.
   - `None` gives `KeyError`; a dict gives `TypeError`.
   - The same `LocalSkill` twice gives `ValueError: too many values to unpack`, which aborts every entry.

   A public door cannot crash on its own argument. That violates the settled "not as a crash" and AGENTS.md §4 ("fails at the boundary where it enters").
2. **Expose the existing loader and validate at the boundary** (**chosen**). Root-export `SkillLoader`, `SkillResolution`, and `ConfigurationError`. Add one frozen record, `SkillEntries`, in `vidbyte/lib/dataclasses/skills.py`, built as the first step of `SkillLoader.__init__`; the signature is unchanged. Bump to 0.2.2 and update the four texts that say JevAgent is the only consumer.
   - **Budget:** 0 new files and 1 new class; 14 files modified, one of them the regenerated contract.
   - **Why:** request.md §C says "prefer exposing the loader that already exists". AGENTS.md §4 and the Placement Rules put validation in a dataclass's `__post_init__`. Two precedents fit: `CodingAgent.__init__` builds `CodingAgentSettings` (`coding.py:74`, with its tuple check at `lib/dataclasses/coding.py:152-153`), and `JevSkillsOutcome` checks a tuple of records.
3. **A public facade** (**runner-up**): `SkillSources.resolve(entries)`, which builds a fresh loader per call.
   - **For:** it keeps `memory`, `resolvers`, and `documents()` off the public surface.
   - **Against:** it is a layer that only forwards, and it drops memory.
   - **Flips if:** the owner wants the loader's internals private, or wants to restructure the loader in a patch release.

I also decided against these, each recorded as an optional `Q-n` with default no:
- a sync twin (D-2, Q-2);
- a caller byte limit (D-7, Q-3);
- a source-string parser (D-9, Q-4);
- a release-note doc (D-10, Q-5);
- a loader-level credential (D-8, Q-6);
- rewording the pinned agent-centric details (D-11, Q-7).

## 3. Where I disagreed with the scout, the request, or the briefing (with evidence)

- **"No caller can pass a credential today"** (briefing item 3's wording). This is wrong. Credentials are per entry (`GitHubSkill.token`, `AnthropicSkill.api_key`, `OpenAISkill.api_key`), and those classes are already root exports. What is missing is only a loader-level credential parameter, which is the scout's actual claim. The scout is right that the loader reads `GITHUB_TOKEN` (`github.py:141`, with `os.environ.get`, so unset means anonymous) and the vendor keys (`vendor.py:121` through `ProviderModelRegistry.resolve_api_key`) itself, and only inside `load()`.
- **`ConfigurationError` is not a root export** (checked: `'ConfigurationError' in vidbyte.__all__` is `False`), and neither is `VidbyteSdkError`. Neither the scout nor the briefing raised this. Every #904 entry constructor raises it for invalid input. The CLI reaches SDK errors today only through a deep dynamic import (`vidbyte-cli: src/vidbyte_cli/services/mcp/sdk.py:31,71`), and its C028 counts that against its baseline. Under consumer item 6 ("every name the CLI needs"), I added it as FR-3 (D-5). I also carry it as Q-1 (non-blocking, default **built**) so the user can veto it.
- **Duplicate names.** The scout recorded "two equal entries share one result". That is true only after the result is remembered. On a fresh loader, two equal single-entry-source entries crash `load()` (EC-4, observed). The spec therefore rejects repeated names, the same rule the Jev door already enforces (D-4).
- **The field guide's `AgentFallbackConfig` precedent** (`strict-config-dataclasses.md`) no longer exists in `vidbyte/lib/dataclasses/` (a grep finds nothing). I cited `CodingAgentSettings` instead.
- **Release-note doc.** Both the 0.2.0 and the 0.2.1 bumps added `docs/design/release-0-2-X.md`, by the `--stat` file names. No AGENTS.md rule requires one, request.md §C's list of literals omits it, and copying its form would mean reading `docs/design/`, which AGENTS.md forbids. Not built (D-10), with Q-5 asking.
- **The "1 MiB SKILL.md" in consumer item 4** measures the whole file, frontmatter included, before decoding. `SkillDocument.text` is the body only, and `InlineSkill.text` has no cap at all. The spec states this exactly (§9.2 row 4).

## 4. Assumptions I am least sure of

- **Q-1 / D-5, exporting `ConfigurationError`.** It is in scope only because I read consumer item 6 as covering the error raised by the public door and by the entry constructors. A strict reading of the scope rule could call it an addition. It is easy to remove: FR-3, row 3(d), and its mentions in §4 and §9.2.
- **D-4, rejecting different entries that share a name.** If the CLI wants two same-named skills from different sources, relax the check to reject only equal entries.
- **D-3, a one-field record versus an inline check.** A reviewer could call the record overbuilt. I chose it because AGENTS.md §4 and the field guide put boundary validation in a dataclass's `__post_init__`.
- **A-5, the baseline.** *(Superseded in r2: the count at `c9d31a7f` is unknown, and S2 records it.)* The S0 briefing reports the gate at 5,173 passed and 14 skipped, measured at `179d8adc`. S1 did not re-run it.
- **Strict tuple only (EC-6).** *(Superseded in r2 by D-14: a list is accepted.)* A list is rejected. Every in-repo caller passes a tuple, but the CLI must write `tuple(...)`.

## 5. Notes

- Partway through Stage B the C: drive reported 0 bytes free ("No space left on device"). It recovered to about 1.3 GB before I wrote the spec, and no data was lost. If later stages fail on writes, check free disk space first.

## 6. Revision r2 (S1 review round 1)

The orchestrator rebased the branch onto `c9d31a7f` (`main` after the 0.3.0 release, #1085, and #1086 to #1088) and settled the version as 0.3.1 (orchestrator decision 2026-10-15 16:20, pipeline.md). I applied all six findings.

- **R-1 (version).** Recorded as D-13, with 0.2.2 on a new `release/0.2.x` branch as runner-up, and Q-8 (non-blocking, default 0.3.1). Also added NG-17 and EC-29. Rows 3(a) and 4–11 now read `0.3.0` → `0.3.1`, at line numbers re-checked at `c9d31a7f`. INV-16 and AC-11 now name the nine places positively, with no old-literal grep. §9.2 row 7 states the CLI pin fact. §14 Ask first adds merging or rebasing `main`. D-10 and Q-5 now give three-of-three release-doc evidence, keeping the default of no. A grep of `lint/`, `scripts/`, `.github/`, `AGENTS.md`, `REPO_MAP.md`, and `contracts/README.md` finds no gate that requires a release doc.
- **R-2 (two copies of the name rule).** NG-10 stays. Delegation would change JevAgent's duplicate-name message ("JevAlignmentSettings.skills must have unique document names.") to one that names `SkillLoader`. That is not byte-for-byte, even though the pinned `details` would match. Added INV-18, AC-18, and FR-12 (both doors raise equal `details` for repeated names), a §11 Conflicts entry naming the field-guide lesson, and Q-9 (non-blocking, default no).
- **R-3 (stale text).** Row 12 now also rewrites the skills README at :20 and :48. INV-15 is relaxed, and the new row 15 updates the ROLE line in `vidbyte/agents/skills/__init__.py`. Row 3(f) adds `ConfigurationError` to the root header's "Error exports" line, and NG-11 is narrowed by that one line.
- **R-4 (test pins).** NG-9, D-11, and Q-7 now say that a rewording which keeps the pinned words needs no test edit.
- **R-5 (tuple or list).** I chose to accept lists (D-14). The runner-up is strict tuple, which flips if the owner wants the runtime check to match a tuple-only annotation. `SkillLoader.__init__` is annotated `Sequence[...]` and turns any non-text iterable into a tuple before it builds `SkillEntries`. The record stays tuple-strict, following `strict-config-dataclasses.md:7,13` and the precedent at `coding.py:78`. The Jev door also accepts lists, and the CLI type-checks with `mypy --strict`.
- **R-6 (consumer table).** §9.2 row 1 now gives the preconditions and `details` shapes. Row 3 gives the per-command GitHub request cost and pinning (new EC-27). Row 4 and EC-14 now say "size and cap, or the cap alone for a network download".

New facts I verified in r2:
- **The conversion guard must stay inline.** Written inline (`tuple(entries) if isinstance(entries, Iterable) and not isinstance(entries, (str, bytes)) else entries`), it passes mypy 2.3.1 under both `lint/mypy.ini` and `--strict`. Moving the test into a separate boolean variable loses the narrowing and adds an `arg-type` error. I ran both forms in the scratchpad.
- **Installed metadata is stale under `PYTHONPATH`.** With `PYTHONPATH` set to the worktree, `importlib.metadata.version("vidbyte-sdk")` prints `0.2.1` (the shared editable install), while `vidbyte.__version__` prints `0.3.0`. Version tests must read the worktree's files instead (§13).
- **Nothing the spec relies on changed between bases.** `vidbyte/agents/skills/`, `vidbyte/lib/dataclasses/skills.py`, `vidbyte/agents/jev/`, `lint/baseline.json`, and `lint/mypy.ini` are byte-identical between `179d8adc` and `c9d31a7f`, and every cited line number holds.
- **`v0.3.0` has no loader names.** None of `SkillLoader`, `SkillResolution`, or `ConfigurationError` is a root export there, so a CLI floor of `>=0.3.0` would fail at import.
- **Correction on the count.** The version lives in nine places: eight hand-edited literals plus the contract. r1's "nine version literals" in G-4 was loose, and r2 states it exactly.

## 7. Revision r3 (S1 review round 2, final; status approved)

All five round-2 findings and the orchestrator's notes are applied. Frontmatter is `status: approved`, `revision: 3`, and `base_commit` stays `c9d31a7f`.

- **R-7.** §13 now names the three reusable `DUPLICATES` cases and explains why `entry-named-like-a-string` is excluded: the public door raises `{"position": 0, "entry_type": "str"}`, while the Jev door raises `{"names": ["inline_skill_2"]}`. EC-28 now says a dict keyed by entries is accepted as the tuple of its keys. Rows 1 and 2 now serve FR-12, INV-18, AC-17, and AC-18.
- **R-8.** §13 notes that `VersionResolver.resolve()` and `vidbyte --version` read metadata first. The fallback at `vidbyte/cli/__init__.py:58` shows only with `vidbyte.cli.metadata.version` patched to raise `PackageNotFoundError`, or by reading the file. `vidbyte/cli/__init__.py:21` is `from importlib import metadata`.
- **R-9.** After the contract commit, updates from main are by approved merge only. After any update or repair, run the generator, commit only if it wrote the file (it prints "already current … nothing written" otherwise, `scripts/generate-sdk-public-api.py:112`), and always run `--check`. Step 3's command carries "W-5, row 11" and the Co-Authored-By trailer. §14 Ask first and Never now agree, and §9.4 matches.
- **R-10.** Row 2(d) rewords the loader's ARCHITECTURE NOTE to "(per agent, for JevAgent)". Row 14 rewords `REPO_MAP.md:109` to "until it is first loaded … for the loader's lifetime (an agent's, for JevAgent)". AC-16 checks for unqualified per-agent memory.
- **R-11, with one deviation from the instruction.** The reviewer's sentence is added to §9.2 row 7 and Q-8, and the decision is unchanged. But its first clause, "The CLI's pin comment requires verifying a new minor", is stale for CLI `origin/main`. `64b04b3` (#166, 15:48) already pins `vidbyte-sdk[codex]>=0.3.0,<0.4` at `pyproject.toml:46,53`, with the comment "stay within 0.3.x until a newer minor is verified". Only the CLI pipeline's branch (`b8af987`) still has `>=0.2.1,<0.3` (`:45,52`). So I scoped the clause to that branch, and added that 0.3.1 needs only a floor raise on CLI main, and that a 0.2.2 would fall outside CLI main's `>=0.3.0` floor (also added to D-13 as support). The reviewer's other two sentences are kept as given. I verified that the export sets at `179d8adc` and `c9d31a7f` are equal, not just their counts (639 names each).
- **Stale-fact notes.** EC-2 now reads `KeyError: 's'`, reproduced with `SkillLoader('skills/pdf')`.
  - The CLI's `strict = true` is not at `:123` in any ref I could read. It is at `:126` on CLI `origin/main` `64b04b3` (now cited in D-14), `:124` in the CLI pipeline worktree, and `:122` in the local CLI checkout.
  - §11 Baseline: the base stays `c9d31a7f`, with no rebase before S3. `origin/main` was at `9aaf662a` at review time. It has since reached `3b879c67` (#1091 to #1093, after the orchestrator's note).
  - None of #1089 to #1093 touches a file this PR edits, the area suites, `lint/`, `scripts/`, or `contracts/`. #1091 changed `vidbyte/agents/base.py`, which D-2 cites only as a precedent; `BaseAgent.run` moved one line there.

## 8. Revision r4 (S4 findings R-1 and R-2; spec text only)

S3 implemented the spec, now at `status: implemented`, with draft PR #1099. S4 confirmed one Major finding (R-1) and downgraded R-2 to Minor. r4 changes only `spec.md` and this report; no source or test file is touched. `status` and `pr:` stay as S3 set them.

- **R-1 (version proof).** INV-16 now gives the rule that holds through later bumps: the eight literals and the contract's `version` equal `pyproject.toml`'s version, which is never below 0.3.1. 0.3.1 stays this PR's value (D-13 unchanged). AC-11's proof has three parts:
  - the release test, after the orchestrator-approved edit the repair agent makes: each place equals `pyproject_version()`, with a `(0, 3, 1)` floor;
  - `generate-sdk-public-api.py --check` and C016 for the contract (`:95` compares the versions);
  - pyproject reading 0.3.1 at this head.

  So the next routine bump keeps the pack green, and a missed literal still fails.
- **R-2 (iterable wording).** INV-2, INV-3, §9.2 row 1, D-14, and consumer answer 1 below now state the exact rule.
  - Any `collections.abc.Iterable` except `str` or `bytes` is accepted, and every `Sequence` qualifies, including one registered with `Sequence.register`.
  - An object that iterates only through `__getitem__` is rejected as `entries_type`.
  - An exception from iterating the caller's own argument propagates unchanged.

  I reproduced all three with the built loader at `93144015`. §17 records this as a clarification, not an S3 deviation, because `loader.py:45` is exactly the prescribed expression.

## 9. Revision r5 (S5 re-review R-C11 to R-C13; user decision on Q-8: 0.4.0)

Since r4, S5 fixed S4's R-1 to R-5, merged `origin/main` `0754e01f` into the branch as `fc0175da` (parent-approved), and regenerated the contract alone at `778b094a`. Its re-review confirmed one Major finding (R-C11) and two Minors (R-C12, R-C13), and refuted R-C10 as a PR defect. While r5 was in progress, the orchestrator relayed the user's answer to Q-8, "0.4.0 (Recommended)", together with a request for release notes in the 0.3.0 precedent's shape. r5 applies all of it as text. It edits no source, test code, contract, or version literal; the repair iteration makes those changes. `status` stays `reviewed`.

- **User decision (§0.2 r5).** The version is 0.4.0 (new D-15). D-13 (0.3.1) is struck with its reason. `docs/design/release-0-4-0.md` is specified as row 16 (new D-16, FR-13, AC-19), D-10 is struck, and NG-12 is withdrawn. Q-8 and Q-5 are resolved. Every place that named 0.3.1 as this release now says 0.4.0: the title, TL;DR, §1, §2, G-4, INV-16, AC-10, AC-11, FR-8, EC-29, NFR-2, §8.4, §9.2 row 7, §9.4, §12, §13, §14, A-6, and A-9. AC-11's floor is now `(0, 4, 0)`, and the spec says the release test's `FIRST_LOADER_RELEASE` (`:36`) moves there in the repair iteration under an orchestrator grant. AC-17 names no version, so it is unchanged.
- **Reading the precedent.** I read `docs/design/release-0-3-0.md` (via `git show a7ed9cde:…`) because the user's relayed instruction names the 0.3.0 precedent. It has 15 lines: a title, a why-this-release paragraph that justifies a minor, a "What 0.3.0 adds, from git log" bullet list, and a closing paragraph on the version places, the contract count, and the release steps. Row 16 copies that shape. No other file under `docs/` outside this spec's folder was read.
- **R-C11 (consumer contract).** I verified these facts with my own commands:
  - `git log --first-parent --oneline v0.3.0..0754e01f` lists 18 PRs.
  - An `inspect.signature` probe at the `v0.3.0` tree and at `25fe2e5b` shows `api_key` gone from all 11 signatures. All 11 now take `api_keys`, and all but `AgentRunnerConfig` and `JevRunBriefSettings` also take `vidbyte_api_key`.
  - `TextModelMode` is not a root export at either ref.
  - The route probe at HEAD gives `AgentExecutionError` caused by "Missing Vidbyte API key" with 0 requests, and `Agent(api_key=…)` raises the `TypeError`.
  - The CLI-binding dump differs only in its version line (30 bindings).
  - CLI `origin/main` pins `>=0.3.0,<0.4` (`pyproject.toml:46,53`).
  - The contract counts are 639 at `v0.3.0`, 640 at `0754e01f`, and 643 at HEAD.
  - The skill entries keep `api_key=` and `token=`.

  §9.2 row 7, Q-8, D-13 (its proposed flip condition is recorded as already met and handed to Q-8), §9.4, and answer 7 below now carry these facts. EC-30 records what a 0.3.x caller of the changed agents sees on 0.4.0.
- **R-C12 (citations).** Every citation was re-checked with `grep -n` at `25fe2e5b`, and each cited body is unchanged:
  - `text.py:108-115`;
  - `base.py:1106-1113` (the reviewer's `:1106-1112` misses the `raise`);
  - `settings.py:95-128`, `:102-107`, and `:119-127`.

  Beyond the verifier's list:
  - `vidbyte/__init__.py:442`, `:627`, and `:871-880`;
  - `loader.py:49`, `:71`, and `:71-76`;
  - the skills README notes `:45` and `:47`;
  - `skills.py:41`, `:61`, `:73`, `:192-193`, and `:269-290`. The `SkillResolution` exemplar moved 36 lines, because `SkillEntries` now sits above it, not the 2 lines the verifier's optional note gave.

  `errors/base.py:287` appears only in review.md's S4 section, which stays as written. §12.2 to §12.4 keep the build-time numbers at `c9d31a7f`, and a note in §12.3 says so. Answer 2 below now cites `text.py:108-115`.
- **R-C13 (pack wording).** In test-plan.md:29, each place is now "checked to equal `pyproject.toml`'s version, which is at least 0.4.0". Line 77 of the same file records S2's red run (`'0.3.0' == '0.3.1'`); it is history, and I left it. FEATURE.md, edited under the orchestrator's grant for these three lines only, in its own commit:
  - `:10` before: "`SkillLoader(entries)` takes any iterable except `str` and `bytes`, turns it into a tuple once … `{"entries_type": <type>}` for text or a non-collection, …".
  - `:10` after: "`SkillLoader(entries)` takes any `collections.abc.Iterable` except `str` and `bytes` (every `Sequence` qualifies, including one registered with `Sequence.register`), turns it into a tuple once in iteration order, … An exception raised while iterating the argument propagates unchanged. … `{"entries_type": <type>}` for text or a non-`Iterable` (including an object that iterates only through `__getitem__`), …". The rest of the line is unchanged.
  - `:15` before: "Every version-bearing place reads `0.3.1`, and the folder docs describe the public door."
  - `:15` after: "Every version-bearing place equals `pyproject.toml`'s version, which is at least `0.4.0`, and the folder docs describe the public door."
  - `:25` before: "The argument is a tuple, list, generator, or other non-text iterable of entries and `SkillDocument`s with unique names."
  - `:25` after: "The argument is a tuple, list, generator, or other `collections.abc.Iterable` that is not `str` or `bytes`, holding entries and `SkillDocument`s with unique names."
- **R-C10.** The §16 row records that no spec change is needed: draft state is the user's call.
- **Date.** I dated the §0.2 entry and `updated:` 2026-10-15, the local date on this machine (21:16 EDT). That is 2026-10-16 in UTC, the date the orchestrator's heading suggested.

## Answers to consumer requirements

These are the answers the vidbyte-cli pipeline (`agent-skill-sources`) should resume from. They match spec r5, §9.2, "Consumer contract": version 0.4.0 (the user's choice, a deliberate minor crossing for the CLI), tuples and lists accepted, the constructor's preconditions, the GitHub request cost, the corrected oversize detail, and what 0.4.0 carries beyond the loader.

1. **The callable, its preconditions, and the result shape.**
   - Build `SkillLoader(entries)`. `entries` may be a **tuple or a list** of entry objects and/or `SkillDocument`s. The annotation is `Sequence[SkillEntry | SkillDocument]`. At runtime, any `collections.abc.Iterable` except `str` or `bytes` is accepted and turned into a tuple once, in iteration order; every `Sequence` qualifies, including one registered with `Sequence.register`. An object that iterates only through `__getitem__` (not an `Iterable`) is rejected as `{"entries_type": …}`. An exception raised while iterating your own argument propagates unchanged; it is a caller bug, not an unavailable skill. So the list a repeatable option collects can be passed as is. A set gives its own iteration order. A dict gives its keys: a key that is not an entry is rejected at its position, and a dict keyed by entries is accepted as the tuple of its keys. Pass a sequence if you pair results with entries.
   - **Preconditions, checked at construction with no I/O:** every element is one of the six entry classes or a `SkillDocument`, and no two share a `name`. Names compare exactly and case-sensitively, the same rule as `JevAlignmentSettings.skills`. A violation raises `ConfigurationError`, whose `details` has exactly one of three shapes:
     - `{"entries_type": <type name>}`: the argument is text (`str` or `bytes`) or not an `Iterable`, including an object that iterates only through `__getitem__`;
     - `{"position": <0-based index>, "entry_type": <type name>}`: the first element that is not an entry or a document;
     - `{"names": <sorted list of repeated names>}`: repeated names.

     Neither the message nor `details` ever holds the rejected value or a credential. If the CLI derives names from source strings, it must keep them unique or catch this error.
   - Then call `await loader.load()`. It returns `tuple[SkillResolution, ...]`, one result per entry, in input order, so pair them with `zip(entries, results, strict=True)`. If you passed a generator, keep your own list to pair with. No agent is constructed.
   - **Success:** `result.document` is a `SkillDocument`, and the text to append is `result.document.text`. Also available: `.name`, `.description`, and `.source`, a label such as `github:owner/repo@sha12/skills/pdf/SKILL.md`.
   - **Failure:** `result.document is None`. `result.reason` is a `SkillUnavailableReason`: `not_installed`, `not_found`, `auth_failed`, `rate_limited`, `fetch_failed`, `invalid_skill`, or `too_large` (never `decision_failed`). `result.detail` is a non-blank, SDK-written explanation that names the fix and never contains a secret or file text.
   - `result.transient` is `True` for `rate_limited` and `fetch_failed`, which a later `load()` on the same loader retries.
   - Expected failures never raise. Only a programming error or cancellation propagates.
2. **Async.** `load()` is `async`. Inside a running event loop, use `await loader.load()`. From synchronous command setup, use `asyncio.run(loader.load())`; calling that inside a running loop raises asyncio's own `RuntimeError`.
   - **Why no sync twin:** the loader runs concurrent I/O on asyncio. The SDK's sync-twin pattern (`TextModelRunner.run`, `vidbyte/lib/runners/text.py:108-115`; citation corrected r5) raises inside a running loop, so a twin would add nothing.
   - **Lint:** in the SDK, C011 is the sync-twin rule, and it covers only `*Agent`, `*Runner`, `*Harness`, `*Session`, and `*Machine` classes with `arun()`, not `SkillLoader.load()`. (The CLI's own C011 is a different rule.)
   - **Reuse:** a loader can be loaded again on a new event loop.
3. **Credentials.** Pass them per entry:
   - `GitHubSkill(..., token=...)`
   - `AnthropicSkill(..., api_key=...)`
   - `OpenAISkill(..., api_key=...)`

   **The loader reads the environment itself**, only inside `load()` and only when the entry's field is `None`:
   - `GITHUB_TOKEN` is read with `os.environ.get` and stripped; unset or blank means an anonymous request.
   - `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are read through the SDK's provider registry and stripped; missing means `auth_failed` with no request.

   There is no loader-level credential parameter. To use the CLI's keyring token, pass it as `token=` on each `GitHubSkill`; to keep the environment out of vendor reads, pass `api_key=`. `token=""` is rejected when the entry is built, so to force anonymous GitHub reads while `GITHUB_TOKEN` is set, unset the variable.

   Credentials are sent only to `api.github.com` or the vendor's fixed endpoint, never follow redirects, and never appear in details, labels, URLs, or reprs. A Vidbyte API key is refused with `auth_failed` before any request.

   **#1027 does not touch these fields (added r5).** It renamed only agent and config parameters (answer 7). `GitHubSkill` keeps `token=`, and `AnthropicSkill` and `OpenAISkill` keep `api_key=`.

   **Request cost per command.** A fresh loader per command re-reads everything, because memory is per loader. Per repository group, `GitHubSkill`s cost:
   - one commit lookup, unless `ref` is a full 40-hex SHA;
   - one tree listing, if any entry has no `path`;
   - one file request per entry.

   An unpinned entry with no path therefore costs 3 requests. Anonymous GitHub allows 60 REST requests an hour, so that is about 20 such commands an hour before `rate_limited` (transient). `ref=<40-hex SHA>` plus `path=` cuts an entry to one request, and a token raises the limit.
4. **Size.**
   - **The SDK's limits.** `SKILL_MARKDOWN_MAX_BYTES = 1_048_576` is inclusive and counts the **whole SKILL.md file in bytes, frontmatter included**, for local, skills.sh, GitHub, and vendor files. `SKILL_DOWNLOAD_MAX_BYTES = 33_554_432` bounds other downloads (GitHub commit and tree answers, vendor zips and records). Inline text and caller documents have no SDK cap.
   - **What the text is.** `document.text` is the body after the frontmatter, so it is smaller than the file.
   - **Oversize.** It comes back as `reason=too_large`. The detail gives the size and the cap, or the cap alone for a network download (a GitHub SKILL.md over the cap, or any download over 32 MiB), so match on `reason` and never parse the detail. It is never truncated and never raised, and it is remembered by that loader.
   - **No caller byte limit.** The CLI enforces its 20,000-byte budget itself: measure `len(result.document.text.encode("utf-8"))`, sum it across everything you append, and turn an over-budget skill into your own structured failure. Because `SkillResolution` is now public and validates itself, you can build `SkillResolution(reason=SkillUnavailableReason.TOO_LARGE, detail="...")` and get the same vocabulary. Never truncate.
   - **Why the budget stays on the CLI side.** The budget is a total across all instructions, which no per-entry SDK limit can enforce. A per-call limit would also clash with the loader's memory. JevAgent applies its own budget the same way.
   - **Trade-off.** A skill of up to 1 MiB is downloaded before you can measure it.
5. **Parser: none.** The CLI parses `github:owner/repo/path`, `skills.sh:<id>`, and local paths itself, and builds entry objects. The constructors validate every field and raise `ConfigurationError`, which the CLI can catch by its root name. The SDK parser is optional Q-4, default not built.
6. **Root names** (exactly as they appear in `vidbyte.__all__` and `contracts/sdk-public-api.json`):
   - **New in 0.4.0 from this PR** (version corrected r5): `ConfigurationError`, `SkillLoader`, `SkillResolution`. 0.4.0 also adds `SystemPromptPreset` from #1095, which the CLI does not need.
   - **Already root:** `AnthropicSkill`, `GitHubSkill`, `InlineSkill`, `LocalSkill`, `OpenAISkill`, `SkillDocument`, `SkillEntry`, `SkillSourceType`, `SkillUnavailableReason`, `SkillsShSkill`.
   - **Not root, and not needed by the CLI:** `SkillEntries` (internal validation record) and `SkillFetchStep`.
7. **Version: 0.4.0 (corrected r5).** The user chose 0.4.0 (spec §0.2 r5, D-15). That replaces the earlier default, 0.3.1 (D-13, now struck), which will never be released. Version 0.3.0 (tag `v0.3.0` = `a7ed9cde`, the latest on PyPI) has no `SkillLoader`, `SkillResolution`, or `ConfigurationError` root export, so a floor of `>=0.3.0` fails at import.
   - **Where it appears:** after the SDK's r5 repair iteration, `0.4.0` is in `pyproject.toml`, `vidbyte/__init__.py` (`__version__`), `vidbyte/cli/__init__.py`, `vidbyte/mcp_server/server/core.py`, `vidbyte/tools/mcp/client.py`, `README.md`, `llms.txt`, `.github/ISSUE_TEMPLATE/bug_report.yml`, and the regenerated contract (`"version": "0.4.0"`). At `25fe2e5b` these places still read `0.3.1`.
   - **Contract provenance:** the contract is regenerated in its own commit after the version commit, so its `source.commit` names the commit it was generated from.
   - **What 0.4.0 carries:** tag `v0.3.0`, plus 18 `main` PRs, plus this PR. The 18 are the fixes #1086 to #1094, #1096 to #1098, and #1100 to #1102, and the features #1036, #1027, and #1095 (`git log --first-parent --oneline v0.3.0..0754e01f`). #1103 and #1104 reached `origin/main` after `0754e01f`, so a 0.4.0 tagged from `main` after this PR merges carries them too.
     - #1027 is breaking. It removes `api_key=` from 11 signatures on 8 root exports: the constructors of `Agent`, `BaseAgent`, `AggregateAgent`, `AgentRoleSettings`, `AgentRunnerConfig` (where it was the first positional field), `JevAgentSettings`, and `JevRunBriefSettings`, plus `Agent.restore`, `BaseAgent.restore`, `Session.resume`, and `Session.fork_from`. All 11 take `api_keys=` instead, and all but `AgentRunnerConfig` and `JevRunBriefSettings` also take `vidbyte_api_key=`.
     - #1027 also changes the default. `model_mode=TextModelMode.AUTO` sends every text call through the Vidbyte gateway and needs a Vidbyte key (`VIDBYTE_API_KEY` or `vidbyte_api_key=`). With only a provider key such as `OPENAI_API_KEY` set, a text call fails with `ConfigurationError: Missing Vidbyte API key …` before any request. `TextModelMode` is not a root export (only `vidbyte.lib.enums` exports it), and the string `model_mode="direct"` is rejected.
     - Root names compared with 0.3.0: 4 added (`ConfigurationError`, `SkillLoader`, `SkillResolution`, `SystemPromptPreset`) and none removed. "Additive" holds for names only, because the contract does not record parameters.
     - The skill entries are unaffected: `GitHubSkill` keeps `token=`, and `AnthropicSkill` and `OpenAISkill` keep `api_key=`.
   - **Pin for the CLI** (the SDK spec specifies no CLI change): the CLI pins `vidbyte-sdk[codex]>=0.4.0,<0.5`, a deliberate minor crossing, and before relying on 0.4.0 the CLI run must verify #1027's gateway routing against its six agents.
     - CLI `origin/main` (`64b04b3`, #166) pins `>=0.3.0,<0.4` (`pyproject.toml:46,53`), with the comment "stay within 0.3.x until a newer minor is verified". 0.4.0 is that newer minor, so `<0.4` installs never pick it up silently.
     - The CLI pipeline's branch (`b8af987`) still has the older `>=0.2.1,<0.3` (`:45,52`) and needs the same new pin.
     - Facts for the verification, from the S5 verifier and re-run in r5: every SDK symbol CLI `origin/main` binds in its five `services/*/sdk.py` adapters (30 bindings) has the same signature at 0.3.0 and at `25fe2e5b`. Its only SDK `api_key=` calls (`DecisionModelConfig` in `services/mcp/sdk.py:110`, `LinearIssueOutput` in `services/outputs/sdk.py:75`) are unchanged. `CodexHarnessAgent` is not a `BaseAgent` and uses no text-model routing. So no current CLI binding is known to break, but the CLI still verifies the minor, as its pin comment asks.
   - **Release notes:** `docs/design/release-0-4-0.md` (spec row 16) names the loader and #1027's breaking changes.
   - **Publishing:** releasing to PyPI is the user's call after review.
