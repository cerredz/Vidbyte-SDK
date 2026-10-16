LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The code, the five repairs (R-1 to R-5), and the merge of main all conform to spec r4. Two problems remain, and neither needs a code change: PR #1099 was taken out of draft during S5, against request.md §C (Blocker), and the consumer contract misstates what 0.3.1 carries now that main is merged in (Major).

Diff reviewed: `git diff origin/main...HEAD`. The merge-base is `0754e01f`, because `origin/main` has since moved to `0105b5b7`; that move adds #1103 and #1104, touches no file this PR touches, and changes no version or contract. HEAD is `b02b45e6`, and the last code-bearing commit is `778b094a`. I also reviewed every commit after `c691c176`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete)
- **The public door works as the spec's §4 snippet shows.** I ran the snippet exactly as written, from an empty scratch folder with `PYTHONPATH=<worktree>` and no `-I`. It printed exactly `house-review loaded 22 bytes` / `pdf not_found False` / `rejected: ['house-review']`. The three root names are the same objects as the classes in their defining modules, and `ConfigurationError` is at `vidbyte/lib/errors/base.py:287`. They are root exports only: `vidbyte.agents`, `vidbyte.agents.jev`, `vidbyte.lib`, `vidbyte.lib.dataclasses`, and `vidbyte.agents.skills` export none of them.
- **The merge is correct, and the contract was never edited by hand.**
  - A read-only `git merge-tree c9d31a7f 58bb0404 0754e01f` shows a conflict only in `contracts/sdk-public-api.json`, on the `source.commit` line.
  - Main's `SystemPromptPreset` import, its `__all__` entry, and its "Preset exports" header line (`vidbyte/__init__.py:18`) are kept.
  - Root `__all__` at HEAD, minus the three new names, equals the merge-base's `__all__` in the same order (640 names plus 3 = 643).
  - `778b094a` touches only the contract, and its parent is `fc0175da`, the commit it stamps. `--check` reports it current, with 643 exports and version 0.3.1. Compared with both `origin/main` and tag `v0.3.0`, it removes nothing.
- **JevAgent and the area outside the PR are untouched.**
  - Against the merge-base, the production diff is exactly the 15 files of §12.3, and it adds no new production file.
  - `JevAlignmentSettings._normalized_skills`, `JevSkillsPreload.__init__`, and the three `ProviderModelRegistry` key and endpoint methods are byte-identical to `c9d31a7f`, although main moved their line numbers.
  - `load()`, `documents()`, and `_pending_groups()` are byte-identical to `c9d31a7f` (compared by AST slice).
  - `lint/` is identical to main's, and lint passes with S009 350, S015 13, S051 259, A006 34, S060 32, and C016 0.
  - The pack plus the Jev area gives `493 passed, 1 skipped`.
- **All five repairs are real fixes, proved by mutation, and none of them weakens a test.**
  - **R-1:** on a scratch copy, all eight places at 0.3.2 give 8 passed; `llms.txt` alone stale gives 1 failed; all at 0.3.0 give 8 failed (`(0, 3, 0) >= (0, 3, 1)`).
  - **R-5:** a level-4 heading, a renamed heading, or the stale "only consumer" clause put back each give 1 failed.
  - **R-3:** a case-folding name rule gives 1 failed in the both-doors test, and a rule that rejects only equal entries gives 7 failed.
  - **R-2:** the exact `Iterable` rule holds at runtime.
  - **R-4:** the bodies of the load methods are unchanged.
  - The only test edits since S2 (`467555d9`) are the two granted ones, matching verify-log's before and after exactly. `git diff origin/main...HEAD -- tests/` adds the pack only.

FINDINGS (ranked, most severe first, max 15)

R-C10 [Blocker] [request fidelity] docs/spec/public-skill-loader/request.md:80 — PR #1099 is no longer a draft. It was marked ready for review during S5 iteration 1, and nothing records an authorization for that.
  Evidence:
    - `gh pr view 1099 --json isDraft,state,title` gives `{"isDraft":false,"state":"OPEN","title":"[WIP] feat: Public skill loader: …"}`.
    - `gh pr view 1099 --json mergeStateStatus` gives `BEHIND`. Separately, `gh pr view --json mergeable` gave `MERGEABLE`.
    - `gh api repos/cerredz/Vidbyte-SDK/issues/1099/timeline` gives `{"actor":"cerredz","created_at":"2026-10-15T22:28:02Z","event":"ready_for_review"}`. It is the only non-commit event, so the PR was a draft until then.
    - The repair agent's own dispatches follow 46 seconds later: CI `38817378839` was created at `2026-10-15T22:28:48Z` on `922823f6`, and Static policy `38817385024` at `22:28:51Z`. In local time, 18:28 falls between the R-4 commit at 18:22 and the merge at 20:05, inside S5 iteration 1.
    - Nothing records the change. The pipeline's "User replies (verbatim)" section reads "none yet" (pipeline.md:84), verify-log Iteration 1 does not mention it, and the orchestrator's briefing still calls it "Draft PR".
    - No workflow under `.github/` marks pull requests ready; a grep for `gh pr ready|ready_for_review|draft` found nothing.
    - The rule: request.md:80, "The PR stays a **draft**. Never merge it, tag it, or publish it."; spec.md:66, NG-2, "The PR stays a draft."; pipeline.md:38.
  Failure: Right now, the live PR breaks a constraint the user set in request.md §C. Anyone with write access can merge a non-draft PR from the GitHub UI. That would publish a public-API change and a version bump before the user has made the review call that NG-2 reserves for them, and before Q-8 (the version) has been answered on current facts (see R-C11). S6 would also write a PR description that assumes a draft.
  Smallest fix: The orchestrator asks the user whether they marked the PR ready themselves.
    - If they did, record it in pipeline.md under "User replies" (verbatim) and change nothing.
    - If they did not, run `gh pr ready 1099 --undo` and record in pipeline.md which stage changed the PR state, so that no later stage repeats it.
    - Code is unaffected either way.
  Spec IDs: NG-2; request.md §C Constraints; §14 Never ("Push to main, merge, tag, or publish").

R-C11 [Major] [consumer contract] docs/spec/public-skill-loader/spec.md:436 (§9.2 row 7); spec.md:745 (Q-8); reports/S1-spec-author.md:192, :195 — After the approved merge, the 0.3.1 this PR stamps also carries #1027's breaking `api_key` removal, but the consumer contract still says 0.3.1 "needs only a floor raise … with no minor crossing".
  Evidence:
    - **What 0.3.1 now carries.** The merge brought in `72a4ade1` (#1027, merged at 18:20, after D-13 at 16:20 and spec r3 at 17:35). Its commit message says: "Agents and text configs take vidbyte_api_key and api_keys … in place of the single api_key. In the default TextModelMode.AUTO every text call goes through the Vidbyte gateway".
    - **The probe.** At HEAD, `vidbyte.Agent(system_prompt="x", provider="openai", model_name="gpt-4o", api_key="sk-FAKE")` raises `TypeError: BaseAgent.__init__() got an unexpected keyword argument 'api_key'`. At tag `v0.3.0`, `vidbyte/agents/base.py:101` has `api_key: str | None = None`. `inspect.signature` shows no `api_key` on the root exports `Agent`, `BaseAgent`, or `JevAgentSettings` at HEAD.
    - **Root names.** Compared with `v0.3.0`, the 0.3.1 contract adds `SystemPromptPreset` (#1095) as well as the three names of this PR (4 in all) and removes none.
    - **What the consumer is told.**
      - spec.md:436 says "So 0.3.1 needs only a floor raise to `>=0.3.1,<0.4`, with no minor crossing" and "0.3.1 differs from a 0.2.2 cut from `179d8adc` only by #1086 to #1088 (plus this PR), as built from this branch … (#1089 to #1093 so far)".
      - spec.md:745 (Q-8) says the same.
      - S1 answer 7 (`reports/S1-spec-author.md:192`, `:195`) says the same, and it is the text the paused CLI pipeline resumes from.
    - **The policies this collides with.**
      - AGENTS.md:5: "Status is alpha, so APIs may change between minor versions."
      - CLI `origin/main` `64b04b3`, `pyproject.toml:42-46`: "The SDK is alpha and may change APIs between minor versions, so stay within 0.3.x until a newer minor is verified against this CLI." followed by `"vidbyte-sdk[codex]>=0.3.0,<0.4"`.
      - pipeline.md:57 (the reason for D-13): "the user's choice of a patch bump for an additive export is preserved". That is no longer true: the release that carries the loader is not additive only.
  Failure:
    - When this PR merges and 0.3.1 is published from main, every `>=0.3.0,<0.4` consumer, CLI main's own pin included, receives #1027's removed keyword and its gateway-by-default routing of text calls as a patch upgrade. That skips the "newer minor is verified" step the CLI pin exists to enforce.
    - The CLI pipeline that resumes from §9.2 row 7 is told there is nothing to verify.
    - The user would answer Q-8 (0.3.1 or 0.2.2) from a stale list of what 0.3.1 contains.
    - I found no `Agent(api_key=…)` call in CLI main: it passes `api_key=` only to `DecisionModelConfig` and `LinearIssueOutput`, and both still accept it at HEAD. So this is a gap in the contract's premise and in the basis for the user's decision, not a demonstrated CLI break.
  Smallest fix: Revise the spec text (r5) and S1 answer 7, with no code change and without overturning D-13 on its own.
    - State that, after the approved merge, 0.3.1 also carries the following, so the CLI should verify it as it would verify a new minor:
      - #1089–#1102;
      - #1036;
      - #1027, which is breaking: `api_key=` becomes `api_keys=`/`vidbyte_api_key=` on `Agent`, `BaseAgent`, and `JevAgentSettings`, and the default `TextModelMode.AUTO` routes text calls through the gateway;
      - #1095, which adds the root export `SystemPromptPreset`.
    - Put "0.3.1, or 0.4.0 because main now holds a breaking change" to the user as part of Q-8.
    - Add "main gains a breaking change before release" to D-13's flip column.
  Spec IDs: §9.2 row 7; Q-8; D-13; NFR-8; consumer item 7; EC-29.

R-C12 [Minor] [consumer contract] reports/S1-spec-author.md:154; spec.md:312, :431, :194, :196, :502; review.md:30 — Line numbers that the consumer documents cite went stale with the merge.
  Evidence:
    - `TextModelRunner.run` is now at `vidbyte/lib/runners/text.py:108-115` (`grep -n "def run(" …` gives 108; the `get_running_loop` guard is at 111). The citations still say `:93-100`: S1 answer 2 (`S1-spec-author.md:154`), D-2 (`spec.md:312`), and §9.2 row 2 (`spec.md:431`).
    - `BaseAgent.run` is at `vidbyte/agents/base.py:1106-1112`, not `:1053-1060` (D-2), and spec.md:502 says "sits one line later on main".
    - `JevAlignmentSettings._normalized_skills` is at `settings.py:95` (its body is byte-identical), not `:89-122` (INV-12 `spec.md:194`, INV-14 `:196`).
    - review.md:30 cites `base.py:284` for `ConfigurationError`, which is now at `:287`.
  Failure: A consumer or the S6 PR author who follows these citations lands on the wrong lines. The briefing requires §9.2 and S1's answers to match the code after the merge. No behavior is affected; every cited body is unchanged.
  Smallest fix: Update the citations in the same spec revision as R-C11: `text.py:108-115`, `base.py:1106-1112`, `settings.py:95-128`, and `errors/base.py:287`.
  Spec IDs: D-2; §9.2 rows 2 and 7; INV-12; INV-14.

R-C13 [Minor] [test-pack docs] tests/features/public_skill_loader/FEATURE.md:10, :15; docs/spec/public-skill-loader/test-plan.md:29 — The pack's own description still states the wording from before r4 and before R-1.
  Evidence:
    - FEATURE.md:10 says "`SkillLoader(entries)` takes any iterable except `str` and `bytes`". The r4 rule is any `collections.abc.Iterable` except `str` or `bytes`; an object that iterates only through `__getitem__` is rejected as `entries_type`, and an exception from iterating the argument propagates unchanged. My probe confirms the code does this: `GetItemOnly` gives `{'entries_type': 'GetItemOnly'}`, and a raising `__iter__` gives a raw `TypeError`.
    - FEATURE.md:15 says "Every version-bearing place reads `0.3.1`".
    - test-plan.md:29 says each place is "compared with 0.3.1". After R-1, the test compares each place with pyproject's version and applies a `(0, 3, 1)` floor.
  Failure: After the next routine version bump, the pack's FEATURE.md describes a contract the test no longer checks. A maintainer who trusts the doc could "fix" the test back to a literal. No behavior is affected.
  Smallest fix: Reword FEATURE.md:10 to r4's `Iterable` sentence, and FEATURE.md:15 and test-plan.md:29 to "equals `pyproject.toml`'s version, which is at least 0.3.1". This is a test-pack doc edit, outside the two granted edits, so it needs an orchestrator grant or a follow-up.
  Spec IDs: INV-2; INV-16; AC-11; AC-17.

R-1..R-5 status:
- **R-1: confirmed fixed** (`e4041b3e`). The edit matches the verify-log before and after exactly. A bump to 0.3.2 gives 8 passed; one stale place gives 1 failed; going below the floor gives 8 failed.
- **R-2: confirmed fixed** (`a5638085`). `loader.py:9` and skills README `:25` state r4's rule, and the code behaves as stated. `loader.py:45` is unchanged.
- **R-3: confirmed fixed** (`320bcb8a`). COMMON MODIFICATION PATTERNS and `@intent` name the Jev twin. The claim that the both-doors test catches drift holds under two mutants. New comment lines are at most 71 columns.
- **R-4: confirmed fixed** (`922823f6`). README `:23` and `:48` and `loader.py:9` use `load()` terms. The three method bodies are byte-identical to `c9d31a7f`.
- **R-5: confirmed fixed** (`852ea989`). A renamed heading or a level-4 heading now fails, and an unchanged map passes (9 passed).

VERIFIED CLAIMS:
1. **AC-1:** the §4 snippet prints exactly its three lines. HELD.
2. **R-1** (verify-log table: 8 passed / 8 passed / 1 failed / 8 failed): reproduced on a `git archive HEAD` scratch copy. HELD.
3. **R-5** (a renamed or level-4 heading gives 1 failed): reproduced, plus a stale-clause mutant giving 1 failed. HELD.
4. **R-3** ("the both-doors test fails when they drift"): the case-fold mutant gives 1 failed, and the equal-entries mutant gives 7 failed. HELD.
5. **R-2 / spec r4 INV-2:**
   - `__getitem__`-only gives `{'entries_type': 'GetItemOnly'}`;
   - a type registered with `Sequence.register` is accepted;
   - a raising `__iter__` and a non-iterator `__iter__` propagate a `TypeError`;
   - `str`, `bytes`, and `None` give `entries_type`.

   HELD. A `bytearray` gives `{'position': 0, 'entry_type': 'int'}`, which the spec's `str`/`bytes` rule allows.
6. **R-4 / row 2(c):** `load`, `documents`, and `_pending_groups` are byte-identical to `c9d31a7f`. HELD.
7. **verify-log ("Only the contract conflicted"):** the trivial `git merge-tree` shows conflict markers only in `contracts/sdk-public-api.json`. HELD.
8. **verify-log ("643 exports = main's 640 + 3, none removed; `--check` current"):** HELD. Also none removed compared with `v0.3.0`.
9. **Merge kept both sides:** `SystemPromptPreset` import, `__all__`, and header line kept; HEAD's `__all__` minus the 3 names equals the merge-base's, in order. HELD.
10. **INV-16 (nine places read 0.3.1):** each read by name. No `0.3.0` remains outside `docs/`, and no test outside the pack pins a version. HELD. Main has no `v0.3.1` tag and its pyproject reads 0.3.0, so D-13's flip condition is not met.
11. **Briefing ("4 local failures are main's"):** (a) gives `assert 148 == 120`, (c) lists `vidbyte/tools/mcp/client.py`, and (d) is an `__all__` mismatch; together 3 failed, 6 passed. (b) fails 1 of 4 runs at HEAD, and the PR's only change under `vidbyte/tools` is the version literal. HELD; I could not run (b) on main without a checkout.
12. **Briefing ("lint PASS; pack + Jev 493 passed, 1 skipped; remote CI and Static policy green on `eed6308e`"):** HELD (`SDK-LINT: PASS`; `gh run view` shows success for all 3 jobs and for Static policy).
13. **Briefing and pipeline.md ("Draft PR"):** NOT HELD. `isDraft` is false, with a `ready_for_review` event at `22:28:02Z` (R-C10).
14. **§9.2 row 7 ("0.3.1 needs only a floor raise … no minor crossing"; "differs … only by #1086 to #1088"):** NOT HELD after the merge (R-C11).
15. **INV-9 after the merge:** vendor endpoints are `https://api.anthropic.com/v1` and `https://api.openai.com/v1`, the variables are `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`, and `resolve_api_key` is byte-identical and still raises when no key is set, even with `VIDBYTE_API_KEY` set. HELD.
16. **§14 boundaries:**
    - `git diff 467555d9..HEAD -- tests/features/public_skill_loader tests/features/jev_skills_preload` shows only the 2 granted files;
    - `git diff origin/main...HEAD -- tests/` shows pack additions only;
    - the diff of `lint/` (baseline included) is empty;
    - no commit after `778b094a` touches `vidbyte/__init__.py` or `pyproject.toml`.

    HELD.

COMMANDS RUN:
- `PYTHONPATH=<worktree> python <scratch>/snippet.py`, from an empty scratch folder, with the snippet taken from spec.md lines 86-105: `house-review loaded 22 bytes` / `pdf not_found False` / `rejected: ['house-review']`, exit 0.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader tests/features/jev_skills_preload tests/test_jev_skill_preload.py`: `493 passed, 1 skipped in 6.44s`.
- `python scripts/generate-sdk-public-api.py --check`: `contracts/sdk-public-api.json is current at fc0175dac652f9da580a302b8d4195da0a72286a (vidbyte-sdk 0.3.1, 643 exports).`
- `python lint/run.py`: `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS`, exit 0. Nothing REGRESSED; A001, A002, C011, C012, S001, S010, S025, S061, and S063 IMPROVED.
- `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_surface.py`: `3 failed, 6 passed in 3.42s`, namely (a) `assert 148 == 120`, (c) `['vidbyte/too...cp/client.py'] == []`, and (d) an `__all__` mismatch.
- `pytest tests/test_mcp_stdio_transport.py::…::test_cancelled_waiter_does_not_break_transport`, run 4 times: `1 failed`, `1 passed`, `1 passed`, `1 passed`.
- Release test on a `git archive HEAD` scratch copy, with the eight places at 0.3.2, then `llms.txt` stale, then all at 0.3.0, then restored: `8 passed` / `1 failed, 7 passed` / `8 failed` (`(0, 3, 0) >= (0, 3, 1)`) / `8 passed`.
- Docs test on the scratch copy, with a level-4 heading, a renamed heading, and the stale clause put back: `1 failed, 8 passed` each time; restored, `9 passed`.
- Both-doors test on the scratch copy, with the case-fold mutant and then the equal-entries mutant: `1 failed, 12 passed` / `7 failed, 6 passed`; restored, `13 passed`.
- `git merge-tree c9d31a7f 58bb0404 0754e01f` (the trivial mode, which writes nothing): conflict markers appear only in the contract hunk.
- A Python check comparing the contract with `origin/main`, `v0.3.0`, and `__all__`: `added vs origin/main: ['ConfigurationError', 'SkillLoader', 'SkillResolution']`, `removed: []`, `contract == sorted(__all__): True`, identity `True True True`. Compared with `v0.3.0`, it adds `SystemPromptPreset` too.
- AST comparison with `c9d31a7f`: `load`, `documents`, `_pending_groups`, `_normalized_skills`, `JevSkillsPreload.__init__`, and `resolve_api_key`, `get_default_endpoint`, and `get_api_key_env_var` are all `identical: True`.
- `gh pr view 1099 --json isDraft,state,title`: `isDraft:false`. `gh api …/issues/1099/timeline`: `ready_for_review` by `cerredz` at `2026-10-15T22:28:02Z`. `gh run view 38817378839` and `38817385024`: created at `22:28:48Z` and `22:28:51Z`.
- `gh run view 38829435243`: success for Source / Python 3.11, Source / Python 3.12, and Package, on `eed6308e`. `gh run view 38829437246`: Static policy success.
- `PYTHONPATH=$(pwd) python -c "…vidbyte.Agent(…, api_key='sk-FAKE')"`: `TypeError: BaseAgent.__init__() got an unexpected keyword argument 'api_key'`. `git show v0.3.0:vidbyte/agents/base.py | grep -n api_key`: `101: api_key: str | None = None,`.
- Read-only, in `C:/Users/422mi/vidbyte-repos/vidbyte-cli`: `git show origin/main:pyproject.toml` (lines 42-46 hold the pin and its comment); `git grep "api_key=" origin/main -- src` shows the only SDK uses are `DecisionModelConfig` and `LinearIssueOutput`, and both still accept `api_key` at HEAD.
- `git log 0754e01f..origin/main`: `0105b5b7` (#1104) and `0f69f7b7` (#1103); they overlap no PR file, and the contract and version are unchanged.
