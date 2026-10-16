LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — The change follows the repo's layering, header, comment-width, placement and lint conventions, but its six new numeric tool schemas drop the bounds that every existing Codex numeric schema carries, and one wire value lives outside lib/constants, against spec §12.4.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets)
- Layering and placement follow the plan. The five new records are frozen, slotted dataclasses in `vidbyte/lib/dataclasses/codex_host.py`. `CodexSkillScope` and the 12 operations are in `vidbyte/lib/enums/codex.py` and exported from `enums/__init__.py`. Every bound and method name is in `vidbyte/lib/constants/codex.py` `__all__`. `CodexSkillFunctions` reaches the host through the `CodexSkillHost` Protocol, so it never imports `host.py`, and the package import loads no `openai_codex`.
- The host stays guard-then-delegate. Each of the 12 new `CodexHost` methods (host.py:508-611) guards and hands off to one collaborator. The collaborators keep call chains one level deep, narrate their main functions, and keep every added comment line within 72 columns. `host.py` is 891 lines, under the spec's 900-line cap, and the new modules are 279, 251, 238 and 211 lines.
- The model-facing text follows the house contract. All 22 new descriptions are 4 sentences with no examples. Delete is a plain function with no tool, and `toolsets/codex.py:3` and `:69-71` say so. No new tool resumes a thread.
- The lint ratchets hold: `SDK-LINT: PASS` with no new finding in any of the 18 changed vidbyte files. A002 improved (578/703). C002, C008, S008, S009, S024, S025, S051, S062, S064 and A007 are at or under their baselines. The public API contract is current, and the byte-pinned paths have an empty diff.

FINDINGS (ranked, max 15)

R-V1 [Major] [model-facing contract parity] vidbyte/tools/builtins/codex/thread_helpers.py:60 — The six new numeric tool schemas carry no bounds, while every existing Codex numeric schema does
  Evidence: `grep -rn '"type": "integer"\|"type": "number"' vidbyte/tools/builtins/codex/` returns 12 schemas.
    - The six that predate this run all carry a bound: `threads.py:92` `goal_token_budget` has `"minimum": CODEX_HOST_MIN_TOKEN_LIMIT`. `threads.py:96` and `:167` (`max_output_tokens`) carry `minimum`. `threads.py:97`, `:168` and `live.py:61` (`timeout_seconds`) carry `exclusiveMinimum`.
    - The six this run adds carry none:
      - `thread_helpers.py:60`, `:92` and `:125`, the listing `limit` (enforced range 1 to 1,000 by `RecordFieldValidator.require_int` at native `thread_helpers.py:208`).
      - `thread_helpers.py:90`, `since` (enforced at least 0, at native `:211` and `_base.py:156`).
      - `thread_helpers.py:185`, the turns `limit` (enforced at least `CODEX_HOST_MIN_LIST_LIMIT`).
      - `skill_functions.py:84`, `token_budget` (enforced at least `CODEX_HOST_MIN_TOKEN_LIMIT` by `CodexGoal`, `lib/dataclasses/codex_host.py:119`).
    - `run_codex_goal.token_budget` and `spawn_codex_thread.goal_token_budget` are the same concept with the same rule, and only the older one states it.
  Failure: The schema the model reads no longer matches what the tool validates. The model is never told that `limit` stops at 1,000; `LIMIT_DESCRIPTION` says only "Very large values are refused". It is not told that `token_budget` and `since` have a floor either. A call such as `limit: 5000` or `token_budget: 0` passes the schema and is refused only at execution, which costs a model turn. A provider that enforces schemas strictly would have caught it before the call was sent. This breaks the validation/rendering parity in the model-facing-tool-contracts field guide, and the toolset's own schema convention.
  Smallest fix: Add the bounds from lib/constants, which are already imported or importable in these modules:
    - the three listing `limit` schemas: `"minimum": CODEX_HOST_MIN_LIST_LIMIT, "maximum": CODEX_HOST_THREAD_LIST_MAX_LIMIT`;
    - the turns `limit`: `"minimum": CODEX_HOST_MIN_LIST_LIMIT`;
    - `since`: `"minimum": 0`, or a named zero constant if A007 flags the literal;
    - `token_budget`: `"minimum": CODEX_HOST_MIN_TOKEN_LIMIT`.
    This is safe for the tests: they compare only property names, order and `required`, and they call `tool.execute` directly. AC-33's §9.2 table names only the types, which do not change.
  Spec IDs: §9.2 tool table, AC-33, D-20, INV-6; field guide model-facing-tool-contracts.

R-V2 [Major] [constants placement] vidbyte/harnesses/native/codex/skill_functions.py:66 — The wire value "userMessage" is defined in a harness module, not in lib/constants, against spec §12.4
  Evidence: `USER_MESSAGE_ITEM_TYPE = "userMessage"` sits at `skill_functions.py:66` and is used at `:220`. The same wire value is already a member of `CODEX_SUPPORTED_ITEM_TYPES` at `vidbyte/lib/constants/codex.py:85`. Spec line 1116 (§12.4) says: "Every bound, method name and fixed value is a named constant in `vidbyte/lib/constants/codex.py`, appended to `__all__`. No bare meaningful literal in the host, collaborators or tools, except message text constants." This value is not a message text, and the module's other fixed values (lines 57-64) are message fragments. In the same read-back check, the JSON member names `"type"`, `"name"` (`:161`) and `"content"` (`:220`) are inline literals.
  Failure: The item-type vocabulary now has two homes. If the app-server renames the item, `CODEX_SUPPORTED_ITEM_TYPES` changes and this copy does not, and then the D-17 read-back stops matching the skill turn. `run_codex_skill` would then interrupt every skill run as unrecorded. Risk note: the harness-threads static policy keeps JSON member names and wire values in lib/constants. Only the pre-existing `HOST_SUBPACKAGE = "codex"` exemption in `tests/features/harness_threads/test_harness_threads_static_policy.py`, added in merge c181be65, keeps this file out of that check.
  Smallest fix: Add `CODEX_USER_MESSAGE_ITEM_TYPE = "userMessage"` to `vidbyte/lib/constants/codex.py` and its `__all__`, import it in `skill_functions.py`, and delete line 66. You can also reference the new name from the `CODEX_SUPPORTED_ITEM_TYPES` tuple so the value is written once. Optionally name the three member keys as well, for example `CODEX_INPUT_CONTENT_KEY`.
  Spec IDs: §12.4 (spec.md:1116), D-17; field guides model-facing-tool-contracts ("centralize vocabularies") and strict-config-dataclasses.

R-V3 [Minor] [file header / narration] vidbyte/harnesses/native/codex/host.py:6 — The host header and the __init__ narration still describe the pre-collaborator host, at 891 of 900 lines
  Evidence: Line 6, COMMON MODIFICATION PATTERNS, still reads "A new operation is one public method: guard, field rules, preflight, the calls through CodexConnection, then a record from CodexResponseTranslator." This run added 12 operations that are guard plus delegate to `CodexThreadHelpers` or `CodexSkillFunctions`. Line 4 (ROLE) names only `oneshot.py` and `CodexHostTools` as drivers. The `__init__` narration at lines 121-123 ("The connection, translators, registry and preflight exist only once the host opened") omits the new `_threads` and `_skills` slots, which are also open-only. AGENTS.md §2 says: "When you change the steps of a main function, update its comments in the same edit".
  Failure: The header's recipe sends the next operation into `host.py`, which has 9 lines of headroom under the spec cap. AGENTS.md §3 asks to "split … before adding more". A follow-up that copies the recipe breaches the cap and undoes the collaborator split.
  Smallest fix: Change line 6 to say that a new thread helper goes in `CodexThreadHelpers`, a new run wrapper in `CodexSkillFunctions`, and that the host method is guard plus delegate. Add the two collaborators to ROLE. Change the narration to "The connection, translators, registry, preflight and the two collaborators exist only once the host opened."
  Spec IDs: §12.3 row 11, §12.5; AGENTS.md §2, §3.

R-V4 [Minor] [docstring accuracy] vidbyte/tools/toolsets/codex.py:54 — The class docstring says "one agent tool per CodexHost function", but delete_codex_thread has none
  Evidence: Line 54 reads `"""Catalog of one agent tool per CodexHost function over one host.`. The same file's header (line 3) says "one tool per CodexHost function except delete_codex_thread", and the comment at lines 69-71 says "delete_codex_thread has none". `grep -rn "Catalog of one agent tool" tests/` returns nothing, so the docstring is not pinned. The S3 note that it "mirrors the pinned bullet" describes the README bullet, not this text.
  Failure: The `help(CodexHostTools)` docstring contradicts the class's own header and the settled rule that delete is never a tool.
  Smallest fix: Append ", except delete_codex_thread, which has no tool" to the first docstring line.
  Spec IDs: §8.5, §12.3 (toolsets row), INV-2.

R-V5 [Minor] [header accuracy, unchanged siblings] vidbyte/tools/builtins/codex/delegation.py:4 — This run makes the ROLE header "CodexHostTools lists these last" false
  Evidence: `delegation.py:4` reads "CodexHostTools lists these last, in the order of the CodexHost functions". The 11 new tools now follow the delegation tools, as positions 16-26 in §9.2. The same staleness, in milder form, is in `harnesses/native/codex/errors.py:4` and `preflight.py:4`. Their ROLE lines name the callers (host, connection, preflight and translator, or just CodexHost), and now `CodexThreadHelpers` and `CodexSkillFunctions` also call `CodexErrorMapper` and `CodexPreflight`.
  Failure: A reader who places the next delegation tool by its header will put it in the wrong part of the catalog.
  Smallest fix: Change `delegation.py:4` to "CodexHostTools lists these after the turn tools and before the thread helpers". These files are outside the §12.3 file list, and Q-7 keeps the pre-existing native/codex modules unchanged, so the orchestrator decides whether the change belongs here or in a follow-up. The `errors.py` and `preflight.py` lines can wait.
  Spec IDs: §9.2, §12.3, §12.5, Q-7.

R-V6 [Minor] [§12.5 TESTS lines] vidbyte/agents/codex/result.py:10 — Three modified files do not name the S2 test files that now test them
  Evidence:
    - `result.py:10`: "TESTS: Offline typed-result checks and python scripts/run_ci.py."
    - `lib/constants/codex.py:9`: "TESTS: python scripts/run_ci.py."
    - `lib/enums/codex.py:9`: "TESTS: python scripts/run_ci.py."
    `result.py` gained `CodexResultSerializer.items()`, and the other two gained the new constants, `CodexSkillScope` and 12 operations. All are exercised by `tests/features/codex_host/test_codex_host_records.py`, `test_codex_host_helper_surface.py` and `test_codex_host_thread_helpers.py`. Spec line 1142 (§12.5) says: "`TESTS:` lines of the new and modified files name the test files S2 created in `tests/features/codex_host/`." The four new files and `host.py` comply.
  Failure: A maintainer who edits the serializer or the enum is not pointed to the tests that pin it.
  Smallest fix: Append the relevant `tests/features/codex_host/test_codex_host_*.py` names to each of the three TESTS lines.
  Spec IDs: §12.5 (spec.md:1142); A001.

VERIFIED CLAIMS:
- Held. `host.py` is 891 lines, under the 900 cap. The new modules are 279, 251, 238 and 211 lines. There are 4 new files, and exactly 18 vidbyte files changed.
- Held. `SDK-LINT: PASS`. The full `--all --format json` run filtered to the changed paths shows only a pre-existing A001 on `vidbyte/tools/builtins/__init__.py`.
  - Ratchets: A007 255/255, C008 45/45, S024 25/25, S008 19/19, S064 4/4, S009 350/350, S062 889/889, C002 9/9, S051 259/259, S025 261/263, A002 578/703 (IMPROVED).
- Held. `ruff --select I001` over `vidbyte` finds 223 hits, none on a PR path.
- Held. `scripts/generate-sdk-public-api.py --check` reports "contracts/sdk-public-api.json is current … (vidbyte-sdk 0.3.0, 639 exports)".
- Held. No added comment line is over 72 columns.
- Held. All 22 new descriptions have exactly 4 sentences and no examples.
- Held. The wire names match the installed SDK: `thread_compact(thread_id)`; the `ThreadTurnsListParams` aliases `threadId`, `itemsView`, `sortDirection`, `cursor` and `limit`; and `SkillsListParams.cwds`. The `wire.py` builders hand-roll those keys.
- Held. Importing the package loads no `openai_codex`, and `skill_functions.py` does not import `host.py`. The Protocol placement follows precedent (`agents/codex/transport.py`), and AGENTS.md has no rule on where a Protocol goes.
- Held. The pinned paths have an empty diff: `native/__init__.py`, the REPO_MAP `native/` section, `llms.txt`, the harnesses README `native/` bullet, `toolsets/__init__.py:11` (Q-18), `pyproject`, `lint/`, `contracts/`, and the pre-existing `preflight`, `errors`, `turns` and `oneshot` modules. No folder README was added under native/codex or tools/builtins/codex.
- Held. The §12.5 header counts are updated (`codex_host.py`, `toolsets/codex.py` "twenty-six").
- Held. All 24 commits carry the Co-Authored-By trailer, and the feature commits cite spec IDs. Intermediate commits 8520600c-b55ece4e failed C002 until 96b572d9 fixed it, and e221ab1e had a 75-column comment that e46509e3 fixed. Neither affects the PR, because it is squash-merged.
- Held. The area tests ran 1 failed, 627 passed and 2 skipped. The one failure is the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (148 == 120), which is not this PR's to fix. `scripts/test-session-failure-vocabulary.py` passed 45/45.
- Held. The S3 claim that the toolset docstring "mirrors the pinned bullet" is true of the README bullet, but the class docstring itself is unpinned and wrong (R-V4).
- False. §12.4 "no bare meaningful literal" (R-V2).
- Partly false. §12.5 "TESTS lines name the S2 test files" (R-V6).
- Considered and not raised:
  - `ONE_TURN = 1` is now defined three times (`threads.py:68`, `delegation.py:38`, `tools/builtins/codex/skill_functions.py:37`). A007 passes, so I did not raise it.
  - `since` is checked both in the host (`thread_helpers.py:211`) and in the tool normalizer (`_base.py:156`). This follows the toolset's existing `_resolve_*` pattern and spec §12.3 rows 9 and 13.
  - The `RecordFieldValidator` message for `limit` is swapped for the pinned `LIMIT_MESSAGE` with `from None`. This matches the native/codex convention of 15 `ConfigurationError` raises, none with `details`.
  - `CODEX_TURN_ITEMS_VIEW_FULL` is a str constant, not an enum, as spec §9.3 decided.
  - The records reuse the C008-baselined `_require_*` helpers in `codex.py`, as the spec requires.

COMMANDS RUN:
- `git log --oneline c181be65..c81ba632`, `git status`, `git diff c181be6577245e8112d7a781deb814e088b6c1ab...c81ba632 --stat`, and per-file `git diff` (read-only).
- `VPY lint/run.py` → `SDK-LINT: PASS`.
- `VPY lint/run.py --all --format json` > scratchpad `s4conv-lint-all.json`, filtered to the changed paths with scratchpad `s4conv_lint_filter.py`.
- `VPY -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` → "Found 223 errors.", none on a PR path.
- `VPY scripts/generate-sdk-public-api.py --check`.
- `PYTHONPATH=$(pwd) VPY -m pytest -q -p no:cacheprovider tests/features/codex_host tests/features/harness_threads` → 1 failed (inherited), 627 passed, 2 skipped.
- `VPY scripts/test-session-failure-vocabulary.py` → 45/45.
- A VPY import-boundary check: `sys.modules` after the import has no `openai_codex`, and `skill_functions` does not import `host`.
- A VPY signature inspection of `openai_codex` (`thread_compact`, `ThreadTurnsListParams`, `SkillsListParams` aliases).
- A sentence-count script over the 22 new descriptions, an awk 72-column check on the added comment lines, and a commit-trailer loop over the 24 commits.
- `grep` / `sed -n` for line evidence, including `grep -rn '"type": "integer"\|"type": "number"' vidbyte/tools/builtins/codex/` and `grep -rn "Catalog of one agent tool" tests/` (no hits).
(VPY = C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python. No file other than this report was written in the worktree.)
