# S4 review — conventions (loop-spend-cap, PR #1192)

LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the change follows the repo's placement, header, @intent, comment-width, complexity, copy-path and docs conventions, but its new module adds one mypy finding that baseline slack hides, so S009 moves from 346 to 347 against a spec that says that slack is not this PR's.

Range reviewed: `git diff origin/main...daad59fb` (merge base `22993b5f`), 52 files, +6715/-35. Pristine base: a `git worktree add` of `22993b5f`, removed after the review.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **Headers, `@intent` blocks and comment width.**
  - `vidbyte/agents/spend_cap.py` carries all ten header fields. A001 is 642 at both trees.
  - Every §12.4 policy site has a named `@intent` block. The touched files hold the same 61 A002 findings at base and at HEAD.
  - The longest added `#` line is 72 columns, and none is over 72.
- **Lint and complexity hold everywhere except S009.**
  - Across the touched files, A001, A002, A006, A007, C001, C002, C006, S024 and S051 have the same findings at base and at HEAD. `ruff check --config lint/ruff.toml` passes on all 20 changed `.py` files.
  - S008 stays at 19. Only the baselined `BaseAgent.__init__` and `_arun_once` grew. `_process_tool_call` (10/10/27) and `_generate_reply` (10/9/50) are unchanged.
  - NFR-5 holds: `base.py` +20 and `runtime.py` +37.
- **The copy paths match the earlier loop fields.**
  - `max_spend_usd` goes through `to_runtime_config`, the `__repr__` tuple, `_export_loop_settings`, `AgentForker._loop_settings`, `_LOOP_FIELDS` and `CODEX_UNSUPPORTED_LOOP_FIELDS`, as `max_tool_calls` and `timeout_seconds` do.
  - The fork tool leaves the cap out of `_LOOP_SETTING_FIELDS` and the schema (`additionalProperties: False`) and puts it back in `_inherited_guardrails`. This is the deliberate guardrail path (D-12) that `max_queued_prompts` and `tool_settings` already use.
- **Docs and the S2 pack are placed and shaped correctly.**
  - `## Spend Cap` sits before `## Key Modules` (`vidbyte/agents/README.md:386`). The README is 33,125 characters, and A009 is CLEAN.
  - The relationship to `CostBudgetMiddleware` is stated where `runtime-boundaries.md:24-29` asks: at `vidbyte/agents/README.md:423` and in `skills/output-contracts/SKILL.md:58`.
  - The contracts, `FailureCode` and the root `__init__` are untouched.
  - The pack's 11 `.py` files all have A001 headers and basenames that are unique under `tests/`. Its README and FEATURE.md are in the expected format. S020 is 1 at both trees.

## FINDINGS (ranked)

R-V1 [Major] [lint: S009 staged mypy] `vidbyte/agents/spend_cap.py:111` — The new module adds a mypy `arg-type` error, and S009 rises from 346 to 347. The gate still says PASS only because of pre-existing baseline slack.
  Evidence:
  - The lint summary differs between base and HEAD on exactly one rule:
    ```
    < S009   staged-mypy-contracts                     346    350 IMPROVED
    > S009   staged-mypy-contracts                     347    350 IMPROVED
    ```
    Both trees end with `SDK-LINT: PASS`.
  - A finding-level diff of `--rule S009 --format json`, keyed on path, code, message and source line, finds one new finding:
    `vidbyte/agents/spend_cap.py:111 arg-type: Argument 2 to "resolve" of "ModelPricingRegistry" has incompatible type "str | None"; expected "str"`.
    The only other difference is the existing `runtime.py` `no-redef` entry, which moves from line 1128 to line 1139 and is otherwise the same finding.
  - A direct mypy run on a copy of the file, which matches HEAD apart from line endings, prints:
    `spend_cap_probe.py:111:119: error: Argument 2 to "resolve" of "ModelPricingRegistry" has incompatible type "str | None"; expected "str"  [arg-type]`
  - The cause is `bool(runner.provider and runner.model_name) and registry.resolve(...)`. Wrapping the guard in `bool()` discards mypy's narrowing of `runner.model_name`.
  Failure:
  - **Rule.** Spec §11 (`spec.md:671`) records S009 at 346/350 on the base and says the IMPROVED slack "is not this PR's". §12.5 (`spec.md:857`) calls the seven IMPROVED rules "pre-existing slack". NFR-3 asks for no lint regression.
  - **Field guide.** `blocking-lint-invariants.md:13` explains why ratchets exist: new code is held to a stricter bar than old code, so a new finding in a new file is a regression even when the total count stays under the baseline.
  - **Effect.** This PR spends one unit of S009 slack. The next `--update-baseline` would lock in 347 instead of 346.
  - **The S3 report misses it.** `S3-implementer.md:138` says the IMPROVED rules "show the same counts as base", but the list there leaves out S001 and S009, and S009 is the one that moved.
  - **What a human reviewer would write:** "New file, new mypy error. Fix the narrowing instead of riding the baseline."
  Smallest fix: Move the guard inside `bool(...)` so mypy narrows `model_name` before the call. No `# type: ignore` is needed, and §14 forbids suppressions anyway.
  ```python
  priced = bool(runner.provider and runner.model_name and registry.resolve(ModelProvider(runner.provider), runner.model_name) is not None)
  ```
  - The two forms behave the same. If both parts are truthy, both evaluate `resolve(...) is not None`. If either is falsy, both give `False`.
  - Verified: mypy prints nothing on the patched copy and exits 0. After the fix, S009 returns to 346.
  Spec IDs: NFR-3; §11 (`spec.md:671`); §12.5 (`spec.md:857`); row 1 (`spend_cap.py`); FR-7.

R-V2 [Minor] [docs format] `skills/failure/vocabulary.md:107` — The added sentence is a 106-column line in a file that is otherwise hard-wrapped at 81 columns or less, and the insert leaves `:106` as a short, broken line.
  Evidence:
  - Line widths in the file: `awk '{ if (length($0) > 81) print FNR": "length($0) }'` prints only `107: 106`.
  - On base, the longest line is 81 columns.
  - The diff splits the old wrapped paragraph `Limit failures normally stop cleanly or route to a continuation strategy. A` / `middleware implementation error …` into three lines, of 73, 106 and 66 columns.
  - The other docs edits keep their file's style. The table rows in the SKILL files are long at base too, and the added `llms.txt` lines are all 100 columns or less.
  Failure: No written rule sets Markdown line width, so this is consistency only. Row 15 (`spec.md:800`) fixes the words, not the wrap. A reviewer reading the rendered diff would ask for the paragraph to be rewrapped like its neighbors.
  Smallest fix: Rewrap the paragraph at `:106-109` at 80 columns or less, keeping row 15's words exactly.
  Spec IDs: row 15; FR-9, FR-10, W-9.

## VERIFIED CLAIMS

**Placement and dependency direction**
- AGENTS.md placement holds. There is no new dataclass, enum or error class.
  - `AgentStopReason.MAX_SPEND` and `AgentRuntimeConfig.max_spend_usd` are in-place edits under "Placement Rules → Existing code".
  - `spend_cap.py` sits in `vidbyte/agents/` beside `fallback.py` and `contract.py`.
  - `vidbyte/lib/dataclasses/agents.py` imports only `vidbyte.lib`. A006 is 34 at both trees.
- The error types match the spec.
  - `AgentLoopSettings` and every construction refusal raise `ConfigurationError`.
  - The old fields of `AgentRuntimeConfig` keep raising `ValueError`. The new field uses `RecordFieldValidator`, which raises `ConfigurationError`, as INV-14 and AC-3 require.
  - The non-linear refusal (`base.py:254`) has no `details`, matching the spec's text (`spec.md:572`) and its sibling refusals at `base.py:230-247`.
- `AgentLoopSettings` gains no `raise`, so C001 stays at 26. It gains no `isinstance(..., bool)` guard, so C002 stays at 9. It adds no bare range guard, so C006 stays at 104. The spend comparison has no numeric literal, so A007 stays at 255.

**The new module**
- The header style follows the §12.4 template. The new module uses the full A001 header, not the "Context Protocol Header" its neighbors use, which the spec calls debt not to copy.
- The docstrings are one line each, the module is 118 lines, and the names follow the `Agent*` pattern.

**Comments, narration and commits**
- Comment format follows `comment-format.md`. Every added or edited `#` block is directly above the code it explains, and the widest is 72 columns. `spend_cap.py` has no comment line over 72.
- Principle 2 holds. The CP2 and CP4 steps in `_arun_once` each get one narration line, and the lead comments of `_budget_stop` and `_enforce_tool_settings` describe the spend check.
- Principle 1 holds wherever this change can control it. The CP3 call depth (`_process_tool_call` → `_enforce_tool_settings` → `_spend_cap_stop`) is inherited from main, and §14 forbids editing `_process_tool_call`.
- `2a69ffee` changes comments only.
  - `git show --stat` shows 11 files, +44/-22.
  - A comment-stripped AST comparison of all 11 files, decoded as `utf-8-sig`, is identical before and after.
  - Its subject's IDs (`W-5, W-10; FR-4, FR-11`) cover fewer rows than the files it rewraps. That does not matter for a commit that only rewraps comments.
- The phase commits match §12.6, and each uses Conventional Commits with W-/FR- IDs and a Co-Authored-By line.

**Model-facing text**
- `fork.py:76-78` `_STATIC_DESCRIPTION` does not mention the spend cap. That is consistent with D-14 and INV-16, which keep the cap out of model-visible text. It is not a finding.

**Docs**
- The Spend Cap section is 38 lines against "about 36". No rule sets a length for a README section; A009 sets only the 40,000-character limit, which the file meets. This is the recorded deviation.
- The SKILL rows sit where row 27 says: `agentic-loop-settings/SKILL.md:95`, `:173`, `:202` and the §6 list, and `output-contracts/SKILL.md:58`.

**Files that must not change**
- These are untouched:
  - the `lint/baseline.json` and `contracts/` diffs are empty;
  - the test tree is unchanged since S2's `b5a9e689`;
  - the version is still `0.4.0`;
  - no key-shaped literal was added;
  - no `__pycache__` or `.pyc` file was added.
- The only red test is the inherited `test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, which is not a finding.

## COMMANDS RUN

**Lint**
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py`, run at HEAD and at the base worktree.
  - Final line at both trees: `SDK-LINT: PASS`.
  - `diff lint-base.txt lint-head.txt` shows only the S009 summary line (346 → 347) and the matching IMPROVED hint line.
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule S009 --format json`, at both trees, followed by a Counter diff on (path, code, message, source line). Output:
  ```
  only at HEAD: vidbyte/agents/spend_cap.py arg-type ... [111]; vidbyte/agents/runtime.py no-redef "...line 1139" [1591]
  only at base: vidbyte/agents/runtime.py no-redef "...line 1128"
  ```
- `py -3.11 lint/run.py --rule <A001|A002|A006|A007|C001|C002|C006|S024|S051> --format json`, at both trees, filtered to the touched files. Base equals HEAD for each rule: A002 61, A001 15, A007 25, C001 8, C002 0, C006 11, S024 4, S051 13, A006 7.

**Type check**
- `MYPYPATH=<worktree> py -3.11 -m mypy --config-file lint/mypy.ini --follow-imports=silent <scratch>/mypyprobe/{a,b}/spend_cap_probe.py`
  - Copy `a` matches HEAD (`diff -q --strip-trailing-cr` matches). Output: `spend_cap_probe.py:111:119: error: ... [arg-type]`.
  - Copy `b` has the one-line fix. It prints nothing and exits 0.

**Ruff and complexity**
- `py -3.11 -m ruff check --no-cache --config lint/ruff.toml <20 changed vidbyte .py files>` printed `All checks passed!`, and so did the same check on `spend_cap.py` alone.
- `py -3.11 -m ruff check --no-cache --isolated --select C901,PLR0912,PLR0915`, run per function at both trees.
  - `BaseAgent.__init__` went from 17/17/87 to 19/19/92, and `_arun_once` from 45/44/167 to 47/46/171. Both are baselined.
  - Every other touched function is within 10/12/50. `_process_tool_call` and `_generate_reply` are unchanged.
  - `AgentRuntimeConfig.__post_init__` went from 4 to 5, measured by its own row.

**Semgrep**
- `git status --short` printed nothing, so the tree was clean.
- `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, run with the S3 venv on PATH, printed `Ran 1 rule on 1031 files: 0 findings.`

**Public API**
- `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check` printed `contracts/sdk-public-api.json is current at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports).` and exited 0.

**Tests**
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap tests/test_codex_output_contracts.py` gave `174 passed in 1.51s`.
- The same command plus the briefing's area list gave `855 passed in 9.88s`. The area list is `tests/features/sdk_loop_settings`, `tests/features/sdk_model_usage`, `tests/test_agent_runtime.py`, `tests/test_session_failures.py`, `tests/test_fork_tool.py`, `tests/test_jev_usage_ledger.py`, `tests/test_algorithms_honor_middleware_abort.py`, `tests/multi_agent`, `tests/test_queued_prompt_usage.py`, `tests/features/infinite_memory_agent`, `tests/test_reflexion_algorithm.py`, `tests/test_independent_critic_algorithm.py` and `tests/test_multi_provider_agentic_grader.py`.

**Diff checks**
- `git diff --numstat origin/main...daad59fb -- vidbyte/agents/base.py vidbyte/agents/runtime.py` printed `20 3` and `37 2`.
- An awk pass over the added `#` lines in the `vidbyte/*.py` diff printed `comment lines max 72 over72 0`.
- `git diff origin/main...daad59fb -- lint/baseline.json contracts | wc -l` printed `0`.
- `git show --stat 2a69ffee` printed `11 files changed, 44 insertions(+), 22 deletions(-)`. The AST comparison found all 11 files identical.
- `awk` over `skills/failure/vocabulary.md` printed `107: 106`. On base, the longest line is 81 columns.
- `find tests -name <basename>` was run for each of the 11 pack files and found each name exactly once.
