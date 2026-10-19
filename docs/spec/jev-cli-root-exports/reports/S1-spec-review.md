VERDICT: SOUND WITH FIXES — The design (eager root bindings from modules that are already loaded, a contract written by the generator, three edits to the release note) checks out end to end on a scratch copy built from the spec's row 1. What needs fixing is the test-facing contract, which would produce permanent tests that go red after merge (R-1, R-3), and the commit order, which cannot be executed as written (R-2).

WHAT THE SPEC GETS RIGHT (max 4 bullets, concrete, so the author does not "fix" what works)

- **The seven insertion points in §12.3 row 1 are exact and pass ruff.** I applied row 1 (a) to (e) verbatim to a `git archive` copy of the tree. ruff I001 over the whole `vidbyte` tree reports no `vidbyte\__init__.py` line (223 findings across the tree, the same as base). A negative control, moving `TextModelMode` above `SystemPromptPreset`, does fire I001 at `vidbyte\__init__.py:44`. S015's `ExportIntegrityAnalyzer` reports the same 4 root findings before and after the edit. The new `__all__` holds 668 unique names, each of the four appears once, and the sorted neighbours match row 3. The edit is +9 lines (1467 → 1476).
- **D-1, D-2 and D-3 are correct.** A fresh interpreter on the edited copy loads the identical set of 948 `vidbyte*` modules (SHA-256 prefix `ff657e9052f220c0` on both sides). It starts no process and leaves `vidbyte.harnesses.native` unloaded. Every existing re-export path returns the root's object, and star import binds all four. D-2 follows the AGENTS.md wording "Import it from its domain module" and the `SkillResolution` precedent at `:480`. There is no import cycle: by that line, `vidbyte.lib.dataclasses.security` is already in `sys.modules`.
- **AC-1 holds.** The §4 snippet, run against the edited copy with `OPENAI_API_KEY` and `VIDBYTE_API_KEY` unset, prints exactly the four lines shown, with empty stderr.
- **Row 2 and D-8 are sound.** The three "before" strings in row 2 appear verbatim in `docs/design/release-0-4-0.md`. The arithmetic holds: `git show v0.3.0:contracts/sdk-public-api.json` has 639 exports, 3+4+17+1+4 = 29, and 639+29 = 668. The two-commit order in D-8 is forced by `_dirty_inputs`/`_head_commit` in `scripts/generate-sdk-public-api.py`. EC-5's trap is real: C016 compares data and canonical bytes, never provenance.

FINDINGS (ranked, most severe first, max 15)

R-1 [Blocker] [L10] §6.1/§6.2/§13 — Facts that are true only at this commit are written as testable invariants, so the blind test author will make them permanent tests, and those go red the moment this PR merges or the next export lands
  Evidence:
  - The spec says:
    - AC-5: "the root `__all__` on `base_commit` and at the PR head … the head adds exactly the four names".
    - AC-6: "`git diff --name-only <base_commit> -- vidbyte/tools vidbyte/lib/configs` prints nothing".
    - AC-7: "the set of loaded modules equals the set that `base_commit` loads".
    - §13 "Facts the tests may rely on": "The sorted `vidbyte*` names hash to a SHA-256 beginning `ff657e9052f220c0` … Nothing in this PR may change that set".
    - INV-4: "(668 names)".
    - AC-4: "`git show <source.commit>:vidbyte/__init__.py` lists the four names".
    - AC-9: "each reads `0.4.0`".
    - §13 points the test author at `optional_merge_base()` and `literal_all(git show <base>:…)`.
  - The author's report (`reports/S1-spec-author.md`) says: "It is harder for a test written blind, so I gave the test author the 948-module fingerprint as a fact."
  - The repo already shows this pattern and its cost:
    - Field guide `local-ci-verification.md`: "`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails on main itself … pins main's `FailureCode` count at 120, but later merges … added members".
    - The same guide: "Two `harness_threads` surface tests fail locally on any branch that touches … root exports".
    - `tests/features/harness_threads/test_harness_threads_surface.py:259-261`.
  - Both precedents that read the contract use subset checks instead: `tests/features/infinite_memory_agent/test_infinite_memory_contract.py:166-168` and `test_root_native_thread_exports_contract.py:140-142`.
  Failure:
  - After the squash merge, a local run on `main` has `git merge-base origin/main HEAD` == HEAD. A test of "the head adds exactly the four names" then sees an empty difference and is red on `main` for every developer, which repeats the `167 == 120` problem.
  - A hash pin or a 948 pin of the module set fails in CI too, the first time any PR adds a `vidbyte` module that loads at import.
  - A 668 pin fails when Q-1's 11 browser names, or any later root export, lands. That includes the program's own later SDK PRs if they add one.
  - A literal `"0.4.0"` pin fails at the next version bump.
  - `git show <source.commit>` fails in CI's depth-1 clone, where commit A is not fetched, and it fails on `main` once the branch is gone.
  - The implementer of each later PR may not edit tests (§14 "Ask first"), so each of these becomes a BLOCKED stop or a field-guide entry.
  Smallest fix: Split §6 into two kinds of statement, and tell §13 which kind tests may assert.
  - **(a) Permanent properties: the test author tests these.**
    - The four names are in `vidbyte.__all__`, once each.
    - Identity, per the name→path table in R-3.
    - Each default, built through the root names.
    - `vidbyte.harnesses.native` is unloaded after `import vidbyte` and after a misspelled name.
    - The header bullet.
    - The contract `exports` is a superset of the four, and `version == pyproject == vidbyte.__version__` (the subset form both precedents use).
  - **(b) One-time diff facts: the implementer proves these with command output in the Proof column, never with a test.**
    - INV-3/AC-5: the set difference against `b7350ed6`.
    - INV-6/AC-6: `git diff --name-only`.
    - INV-5/NFR-1/AC-7: module-set equality, from a scratch probe of base against head.
    - INV-8/AC-9: no version line in `git diff b7350ed6`.
    - The 668 count: the `--check` output.
    - AC-4: `git show <source.commit>`.
  - Strike the hash and the 948 from "Facts the tests may rely on", or label them "for the one-off probe; never pin".
  - Add one §13 line: "No test compares against `base_commit` or the merge base, or pins an export count, a module hash, or a version literal". Cite the two field-guide entries.
  - T-3 keeps its control, because S4 reviews the AC-5 diff fact.

R-2 [Major] [L8/L11] §12.6/A-1 — Row 2 needs this PR's number inside commit A, but the PR does not exist until the end of implementation, so the run is built to stop at BLOCKED
  Evidence:
  - §12.6: "P1 — Source commit (commit A) … rows 1 and 2".
  - A-1: "This PR's number is in the spec frontmatter `pr:`, which is filled at S3, when the implementer applies row 2". The frontmatter has an empty `pr:`, and the orchestrator opens the draft PR at the end of S3.
  - The release note is not an input to the generator:
    - `lint/core/public_api_contract.py:431`: `read = tuple(sorted({PYPROJECT_REL, *resolver.resolved_modules()}))`, which is `pyproject.toml` plus `vidbyte/__init__.py`.
    - `scripts/generate-sdk-public-api.py` `_dirty_inputs` runs `git status --porcelain -- *paths` over exactly those paths.
  Failure: The implementer reaches row 2 (b) or (c) with no number. It then either stops BLOCKED every time (§14), or it guesses the next number and puts a wrong `#n` into a release record that is auto-merged. GitHub numbers issues and PRs from one sequence, and other sessions open PRs at the same time, so a guess is unsafe.
  Smallest fix: Re-sequence the work into three commits and update every section that assumes two.
  - **Commit A:** row 1 only.
  - **Commit B:** the regenerated contract.
  - **Then open the draft PR.**
  - **Commit C:** row 2, with the number from `gh pr view --json number -q .number`.
  - State in the spec that commit C changes no generator input. `source.commit` (commit A) therefore still satisfies INV-4, C016 stays CLEAN, and nothing is regenerated.
  - Update D-8 ("two commits" becomes three), A-1, the §14 "Ask first" line on the PR number, §12.3 row 2's Phase column, and the §12.6 dependency order.

R-3 [Major] [L10] §6.1 INV-2/INV-13 — The export-path list does not say which name lives at which path, and one natural pairing does not exist
  Evidence:
  - INV-2: "identical to the object at every existing export path: `vidbyte.agents`, `vidbyte.agents.settings`, `vidbyte.tools.security`, `vidbyte.lib.dataclasses`, `vidbyte.lib.enums`, and `vidbyte.lib.config`".
  - INV-13 lists files and line numbers with no names.
  - The author's report: "Which sub-packages export them: … `vidbyte.lib.dataclasses` and `vidbyte.lib.config` do."
  - The repo: `vidbyte/lib/config/__init__.py:16,34` exports only `TextModelMode`. My probe found `getattr(vidbyte.lib.config, "PermissionPolicy", None)` is `None`. `vidbyte.agents.settings` exports only `AgentLoopSettings` of the four, and `vidbyte.tools.security` only `PermissionPolicy`.
  Failure: A test author who parametrizes name × path, or who pairs `PermissionPolicy` with `vidbyte.lib.config` (code-map §2.3 names them together), writes a test that can never pass. The implementer may not edit it, so the run stops BLOCKED at S3.
  Smallest fix: Replace the flat list in INV-2 and INV-13 with a table of four rows. On the post-change probe, every entry below returned True:
  - `AgentLoopSettings`: `vidbyte.agents.settings.loop`, `vidbyte.agents.settings`, `vidbyte.agents`.
  - `PermissionPolicy`: `vidbyte.lib.dataclasses.security`, `vidbyte.lib.dataclasses`, `vidbyte.tools.security` (and `vidbyte.tools.security.permissions`).
  - `TextModelMode`: `vidbyte.lib.enums.text_model`, `vidbyte.lib.enums`, `vidbyte.lib.config`.
  - `JevDynamicComputeOption`: `vidbyte.lib.enums.jev`, `vidbyte.lib.enums`.

R-4 [Minor] [scope-adding] [L1/L9] §1/NG-2/A-2 — §1's parity-test argument for `JevDynamicComputeOption` applies just as well to `ModelProvider`, and NG-2 excludes `ModelProvider` for a reason that also applies to `dynamic_compute`
  Evidence:
  - §1: "`JevComputeSettings.dynamic_compute` accepts strings, but … a parity test against the installed SDK … needs `JevDynamicComputeOption` itself."
  - NG-2 excludes `ModelProvider` because "`provider` and `api_keys` accept strings".
  - A-2: "So the CLI's C2 and C4 need no further SDK export."
  - The repo: `vidbyte/agents/jev/settings.py:137` has `provider: ModelProvider | str`, and `"ModelProvider"` is absent from root `__all__`.
  - request.md §C.0 "Framing": "Static `click.Choice` lists must be CLI-local StrEnum mirrors of the SDK enums … with a parity test against the installed SDK". The agreed `--provider` flag and `capabilities` listing need such a list.
  Failure: An S4 reviewer, or the C2 author, applies §1's own argument to `--provider` and finds A-2 false. C2's provider parity test cannot reach `vidbyte.ModelProvider` under C028.
  Smallest fix: Do not change this PR's four names; they are settled.
  - Rest `JevDynamicComputeOption` on "request.md §C names it", not on the parity argument.
  - Amend A-2: `ModelProvider` is the one closed vocabulary in the flag map that stays non-root. A provider parity check can still go through root names, by validating `JevAgentSettings(provider=…)`.
  - Optional Q-3: "Root-export `ModelProvider` in a later SDK PR?" Default: not built.
  - Name it in the §12.5 follow-ups.

R-5 [Minor] [L2] §6.2/§6.3 — Much of the weight is ceremony: AC-8 and AC-10 re-prove behavior that INV-2 plus INV-6 already imply and that existing tests pin, and about 11 of the 22 EC rows restate §14
  Evidence:
  - AC-8 (the defaults) follows from INV-2 (same object) plus INV-6 (definitions byte-identical). It is already pinned by `tests/features/sdk_loop_settings/test_contract.py`, `tests/test_jev_compute_clone.py:70` and `tests/features/coding_agent/test_coding_agent_environment.py:96`.
  - AC-10 is the same `__getattr__` path that `test_root_native_thread_exports_contract.py::test_a_misspelled_root_name_is_still_an_attribute_or_import_error` already tests, and INV-11 keeps that path unchanged.
  - AC-9 duplicates `test_public_skill_loader_release.py:99-115`, which pins 8 literals to pyproject's version.
  - EC-8 to EC-12 and EC-16 to EC-21 are implementer-process mistakes, already covered by §14 Always/Never.
  Failure: The test author writes about 12 tests where about 5 carry information, several of them duplicates. Reviewers then work through 22 EC rows for a 9-line diff.
  Smallest fix: This still satisfies every FR and INV.
  - Mark AC-8 "implied by INV-2 + INV-6; proof: the existing tests named above; at most one smoke check through root names".
  - Mark AC-10 "proof: the existing misspelled-name test".
  - Move AC-9 under R-1 (b).
  - Collapse the process ECs into one line: "process mistakes: see §14".
  - §8.3 and §8.4 need no change.

R-6 [Minor] [L4] §11 "Nearest sibling"/D-9 — The spec tells the implementer to copy #1099, but #1099 also edited the defining package's header and its README to name the root re-export, and the spec does not say why this PR departs from that
  Evidence:
  - `git show 64e2bd67 -- vidbyte/agents/skills/__init__.py`: ROLE IN CODEBASE gained "and by the package root vidbyte/__init__.py, which re-exports SkillLoader as a public name".
  - `vidbyte/agents/README.md` gained "for any caller that imports `SkillLoader` from the package root".
  - `test_public_skill_loader_docs.py` pins this ("Row 15: the package header names the root re-export").
  - CONTRIBUTING.md step 3: "Update nearby documentation when behavior, imports … change."
  - D-9: "Nothing in them becomes false." This is true: I found no "not the root" claim about the four outside `docs/`.
  Failure: An S4 conventions reviewer cites #1099 and step 3 and asks for header notes in `loop.py`, `security.py`, `text_model.py` and `jev.py`. That exceeds the 3-file budget, so the run stops BLOCKED or goes to a repair round.
  Smallest fix: In D-9, cite #1099's header edits as the runner-up's precedent. Give the concrete difference: these four headers already omit most of their re-exporters (for example, `security.py:12` omits `vidbyte.lib.dataclasses`). Keep the Q-2 default of No.

VERIFIED CLAIMS
- **Insertion points in `vidbyte/__init__.py` (§12.3 row 1): HELD.**
  - The anchors sit at the stated lines: `:52` `AgentInput`, `:53` `AgentMessage`, `:479` `)`, `:480` `SkillResolution`, `:485` `InfiniteMemoryPreset`, `:486` `MuseReasoningEffort`, `:490` `SystemPromptPreset`, `:824` `"JevComputeSettings"`, `:1053`/`:1054` `"AgentStopReason"`/`"ToolSettings"`, `:1373` `"ToolPermission"`, and header `:12`.
  - `__all__` is one literal list (`:762`).
  - The edit adds +9 lines.
- **ruff I001 and S051: HELD.** ruff accepts the positions (scratch probe plus a negative control). S051 is at 259 on HEAD.
- **S015 (`lint/rules/s015_public_export_integrity.py:38-45`): HELD.** Baseline 13, measured 13. The root findings are the same 4 before and after the probe.
- **C016: HELD.** It is CLEAN at 0. `--check` prints "current at ebd18517… (vidbyte-sdk 0.4.0, 664 exports)".
- **Other baselines: HELD.** A001 is 642 and S020 is 1, as `lint/baseline.json` says.
- **`PermissionPolicy` imported from `vidbyte.lib.dataclasses.security` (D-2): HELD.** The probe shows the same object as `vidbyte.tools.security` and `vidbyte.lib.dataclasses`, and no cycle.
- **Every export path in INV-2: PARTLY FALSE.** `vidbyte.lib.config` has no `PermissionPolicy` (R-3). The citations in INV-13 hold.
- **The generator (`scripts/generate-sdk-public-api.py`): HELD.**
  - It refuses to write while an input is dirty, stamps HEAD, and keeps `source.commit` when the data is unchanged.
  - Its inputs are only `pyproject.toml` and `vidbyte/__init__.py`, which is what makes commit C in R-2 possible.
- **"Computed `__all__` fails closed" (§12.4): IMPRECISE.** The deriver accepts `+`, `+=`, `.extend` and `.append` (`lint/core/public_api_contract.py:5`). It is S015's `_exports`, which reads the first literal list only, that makes the one-literal-list rule binding. The obligation stands; the cited source is wrong.
- **Release note (§12.3 row 2): HELD.** The three "before" strings are verbatim, and the counts work out to 639 → 668 and 25 → 29. The working copy is CRLF and the index is LF (`core.autocrlf=true`), so line endings are harmless.
- **Inherited reds: HELD.**
  - `root_native_thread_exports` has 3 failures, and 11 browser names are missing, as computed.
  - `assert 167 == 120` fails.
  - `test_import_vidbyte_starts_no_process…` compares against the merge base (`:259-261`). It is green on main and red on this branch once `__all__` changes. CI runs it but skips that clause.
- **Module set: HELD.** 948 `vidbyte*` modules, with the hash prefix `ff657e9052f220c0`, identical before and after the change. The total module count depends on the environment (1423 here against the spec's 1,343).
- **The four names are absent from root on base: HELD.**
- **Version literals (INV-8): HELD.** All nine places read 0.4.0.
- **Commands and environment: HELD.**
  - `pyproject.toml:7`, `:45-50` and `:78-81` say what the spec says.
  - `run_ci.py:_assert_no_tracked_bytecode` exists.
  - No `.pyc` file is tracked.
  - `.semgrep/typed-mapping-boundary-policy.yml` exists.
- **CONTRIBUTING.md citations: HELD.** Steps 1 to 4 sit at `:38-45`, and `contracts/README.md` says what the spec quotes.
- **Header bullet: HELD.**
  - `BaseAgent` takes `permission_policy`, `agent_loop_settings` and `model_mode` (`vidbyte/agents/base.py:98-108`), so the bullet's claim is true.
  - The `PART_BREAK` in the docs test leaves `- Error exports:` intact.
- **T-1: HELD, but it overstates the control.** `PermissionPolicy.check` honors `PermissionCeiling`, but the ceiling's default is `None` (`vidbyte/lib/permission_ceiling.py:27`). It caps nothing unless `read_only` or another scope opens it. `allow_all()` was already reachable through `vidbyte.tools.security`, so the root export does not change the SDK's security posture.
- **G-1's permission path: HELD.** `JevAgent` passes `settings.permission_policy` into its agents (`vidbyte/agents/jev/agent.py:75,96`, `bulk_work.py:59`).
- **Flag-map types in A-2: HELD except `ModelProvider`.** `JevSpecialist`, the skill entries, the toolsets, the presets and the gates are root names. `ModelProvider`, `ProviderKeys` and `ToolErrorPolicy` are not (R-4).
