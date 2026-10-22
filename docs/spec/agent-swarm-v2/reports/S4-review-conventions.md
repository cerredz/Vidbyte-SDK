LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the revision puts records, enums, prompts, and docs where the house rules say, but `runtime.py` passes its 400-line test only by breaking the 72-column comment rule, and the new code adds a helper-to-helper chain and three policy functions with no `@intent` that the stale lint ratchet does not report.

WHAT THE IMPLEMENTATION GETS RIGHT
- Layering and placement hold. `AgentSwarmSettings`, the v2 event fields, and the four new enums live in `vidbyte/lib/dataclasses/agent_swarm.py` and `vidbyte/lib/enums/agent_swarm.py`, the enums are exported from `vidbyte/lib/enums/__init__.py`, and no `vidbyte/lib/` module imports a higher layer (checked with grep; A006 clean). Bounds and defaults are named constants in `vidbyte/lib/constants/agent_swarm.py`.
- The prompt leaves follow `prompt-families.md`: headed sections, no digits, no role words, keys in `vidbyte/lib/enums/prompts.py`. The enum header's "162 static prompt assets across 36 families" matches a count of the members.
- The shared loop is untouched. `git diff` of `vidbyte/agents/runtime.py`, `base.py`, `validation.py`, and `lint/baseline.json` is empty. The swarm middleware imports the runtime only under `TYPE_CHECKING` and is not re-exported.
- Docs and contracts stay in step. The package README File Index lists `compaction.py` and drops `settings.py`. All READMEs are under A009 (12,253 / 33,476 / 33,831 characters). The public-API contract `--check` is current. Every feature commit cites W-/FR-/AC- IDs, and no `__pycache__` is tracked.

FINDINGS (ranked)

R-V1 [Blocker] [field guide: comment-format] vidbyte/agents/agent_swarm/runtime.py:51 (and 43 more lines) — runtime.py meets its 400-line test only because 44 comment lines run past 72 columns, some up to 399 columns
  Evidence: `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'` finds 0 such comment lines in runtime.py at base 39ce8b20 and 44 at head 936e3278: lines 51, 54, 65, 86, 95, 98, 102, 105, 108, 113, 118, 124, 128, 131, 137, 140, 146, 159, 167, 174, 175, 181, 183, 188, 213, 215, 220, 227, 236, 251, 255, 263, 274, 276, 320, 327, 333, 339, 347, 358, 377, 390, 398, 405. member.py has 3 (93, 107, 181, at 73 columns) and agent_swarm_observer.py has 5 (43, 54, 63, 64, 83, at 73–75 columns). S3's report says the full runtime "first came to 531 lines" and reached 398 by compressing it. Wrapping the 44 comments at 72 columns brings runtime.py to about 471 lines after its header. The contract test allows at most 400 (`tests/features/agent_swarm/test_agent_swarm_contract.py:121-135, 826-836`, seven `PACKAGE_MODULES` exactly).
  Failure: `field-guide/vidbyte-sdk/comment-format.md:3-7`: "Wrap every comment line at 72 columns … A single-line comment that would pass 72 columns becomes a wrapped block too". The owner rejected 100–120-column blocks; these go up to 399. Spec NFR-8 and the §12.4 checklist (spec.md:941) require the same. An owner reviewing this would write "stop writing comments like this". The line-count test hides the problem: it makes the cheapest way to pass it the one the owner already rejected.
  Smallest fix: Wrap all 52 lines at 72 columns. To keep runtime.py at or under 400 lines, move two pieces into modules that already exist, so `PACKAGE_MODULES` still holds. First, move the tool-outcome classification (`_FILE_TOOLS`, `_SHELL_TOOL`, `_TIMEOUT`, and the changed-path and command-failure logic) into `AgentSwarmTools` (`vidbyte/tools/toolsets/agent_swarm.py`, 85 lines), which owns those tool names. Second, move the prompt assembly (`_SECTIONS`, `_render_system_prompt`, `_build_member`) next to `AgentSwarmMemberAgent` in member.py. If it still does not fit, S2 changes the §8.4 budget: row 34 calls 400 a "target", and AGENTS.md §3's limit is 1,000. The fix must not keep the line count by giving up the comment rule.
  Spec IDs: NFR-8, §12.4 (spec.md:941), §8.4 / INV-37, row 34.

R-V2 [Major] [AGENTS.md §1] vidbyte/agents/agent_swarm/runtime.py:375-386 — `_end_check` now calls `_stop`, a helper-to-helper chain added in v2
  Evidence: The main functions `_run_member` (lines 151, 168) and `end_turn` (line 233) call `_end_check`, and `_end_check` calls `_stop` at 382, 384, and 386. `_stop` (356–373) is 18 lines with three loops. At base, `_end_check` (base line 271) decided the reason itself, and `_stop` did not exist.
  Failure: AGENTS.md §1: "a function may call another of its own functions, but that second function should not call a third … lift that call up into the main function". Spec row 34 asks for "`_end_check` calls `_stop`" while also citing "AGENTS.md §1–§2 … helpers one level", so the conflict starts in the spec. A reviewer would ask for the decision and the effect to be split.
  Smallest fix: Turn `_end_check` into a pure decision, `_end_reason() -> AgentSwarmStopReason | None`. Each of the three callers runs `reason = self._end_reason()` and then `if reason is not None: self._stop(reason)`, all in the same await-free block, so INV-12 does not change. This adds about 3 lines. Update row 34's wording to match.
  Spec IDs: INV-12, row 34, NFR-8.

R-V3 [Major] [A002 / @intent] vidbyte/agents/agent_swarm/member.py:134, runtime.py:295, runtime.py:301 — three new A002 findings pass only because the ratchet baseline is stale
  Evidence: `python lint/run.py --all --format json`, filtered to the swarm files, reports A002 at exactly member.py:134 (`_compact`), runtime.py:295 (`request_compaction`), and runtime.py:301 (`take_compaction_request`). All three functions are new in this diff. The text run prints only `A002 IMPROVED 703→565` and `SDK-LINT: PASS`, so the findings stay hidden. `_compact` applies INV-35's failure policy (it catches `VidbyteSdkError`, records `model_error`, and keeps the history) with a plain comment and no `# @intent`. `request_compaction` applies the rule that a new request replaces the earlier one's focus, also with no `# @intent`.
  Failure: the §12.4 checklist (spec.md:941) says "Every policy branch within twenty lines of a policy-token identifier carries an `@intent` comment". S3-implementer.md:212 claims "Lint (A001, A002, …) passes", but that holds only for the exit code. The prompt's own rule applies: a passing exit does not clear a finding in the changed code.
  Smallest fix: Add `# @intent a-failed-summary-keeps-the-history` above the `try` in `_compact`. Add `# @intent one-pending-compaction-per-agent` as the first line in `request_compaction`, and the same intent, or a one-line `@intent`, in `take_compaction_request`. Re-run the JSON lint and confirm the swarm files have no A002 findings.
  Spec IDs: INV-35, §12.4 (spec.md:941), row 34 (A002).

R-V4 [Minor] [AGENTS.md §3] vidbyte/agents/agent_swarm/runtime.py:249-269 — `record_tool_outcome` does three jobs because its two helpers were inlined to save lines
  Evidence: The docstring reads "a cut result, a changed file, or a failed command". S3-implementer.md:74 (deviation 7) says `_changed_path` and `_command_failure` were inlined "to keep `runtime.py` within the 400-line module target".
  Failure: AGENTS.md §3 says each function "does exactly one thing" and gives the "and" test. A line target does not justify merging functions, and the second and third jobs are pure classification that the runtime does not need to own.
  Smallest fix: As part of R-V1, restore the two classifiers as pure functions on `AgentSwarmTools`. `record_tool_outcome` then keeps three short branches that only record events.
  Spec IDs: row 34, S3 deviation 7.

R-V5 [Minor] [house style: constants] vidbyte/agents/agent_swarm/runtime.py:55-57, vidbyte/middleware/builtins/agent_swarm_observer.py:31 — policy literals and repeated tool names live in module scope, not in the swarm constants module
  Evidence: `_FILE_TOOLS = {"write_text": "path", "patch_file": "file_path"}`, `_SHELL_TOOL = "bash"`, and `_TIMEOUT = "timeout"` in runtime.py; `_STOPPING_REASON = "agent_swarm_stopping"` in the observer. The tool names are already set in `vidbyte/tools/filesystem/write_text.py:17` and `vidbyte/tools/builtins/editing/patch.py:35`, and the runtime types them a second time. `vidbyte/lib/constants/agent_swarm.py:7` says "Add a named constant here before writing another AgentSwarm policy literal."
  Failure: This breaks the constants module's own header rule. If a tool is renamed, the runtime's copy of the name goes stale.
  Smallest fix: Move the four literals into `vidbyte/lib/constants/agent_swarm.py` as named constants, or let `AgentSwarmTools` expose the path-argument map (see R-V1 and R-V4).
  Spec IDs: row 34; constants header.

R-V6 [Minor] [A001 headers] vidbyte/agents/agent_swarm/runtime.py:4, vidbyte/lib/dataclasses/agent_swarm.py:7 — two headers describe the code inaccurately
  Evidence: runtime.py ROLE IN CODEBASE says that of `stopping, record_model_call, record_model_error, …`, "the first two [are called] also by the member runtime for its summary call". But member.py:140 also calls `record_model_error` when the summary call fails, and member.py:91 calls `stopping` in the between-iteration check, not for the summary. The dataclasses header says "A new event field adds one field, its name in _OPTIONAL_FIELDS". But `_OPTIONAL_FIELDS` is now derived (line 87: `("message_id", *_COUNT_FIELDS, *_TEXT_FIELDS, *_ENUM_FIELDS)`), so a new field belongs in one of the typed tables.
  Failure: The agentic-engineering header obligation says agents follow ROLE and COMMON MODIFICATION PATTERNS literally. An agent following this pattern would edit the derived tuple and skip the per-type check.
  Smallest fix: Correct the two sentences. Name `record_model_error` among the member runtime's calls, and say a new field goes in `_COUNT_FIELDS`, `_TEXT_FIELDS`, or `_ENUM_FIELDS`.
  Spec IDs: row 34 (header rewritten), §12.4.

R-V7 [Minor] [folder README] vidbyte/prompts/README.md:112 — the family paragraph still says "the three refusals"
  Evidence: Lines 111–112 read "`message_sent` and the three refusals are its replies". In v2, `message_stopped_recipient` is a success reply: INV-6, AC-5, and row 22 say "Reword as a success reply", and runtime.py:187 returns it. Only `message_blank_text` and `message_unknown_recipient` go through `_refuse` (runtime.py:178, 180). This diff edited the paragraph to add the compact leaves but kept the old sentence.
  Failure: A README that is wrong about a model-facing contract leads the next agent to treat a stopped recipient as an error.
  Smallest fix: "`message_sent` and `message_stopped_recipient` are its success replies, and `message_unknown_recipient` and `message_blank_text` are its two refusals".
  Spec IDs: INV-6, AC-5, row 22, row 39.

R-V8 [Minor] [error packet] vidbyte/agents/agent_swarm/member.py:63-67 — the runtime-selection refusal checks two inputs but reports only one
  Evidence: `if swarm_runtime is None or summarizer is None:` raises with `details={"received_swarm_runtime": type(swarm_runtime).__name__}`. When only `summarizer` is missing, the details show a valid runtime type, and nothing names the missing summarizer.
  Failure: The agentic-engineering error-message rule says an error names the field and value that failed.
  Smallest fix: Add `"received_summarizer": type(summarizer).__name__` to `details`.
  Spec IDs: row 34/35 (member runtime), D-16.

VERIFIED CLAIMS
1. S3: the pack passes (268 passed). HELD: `pytest tests/features/agent_swarm -q -p no:cacheprovider` → `268 passed in 7.04s`.
2. S3: the public-API contract is regenerated for `AgentSwarmWebSearch`. HELD: `--check` → current at a319f44d, 650 exports.
3. S3: lint passes, including A002. EXIT HELD, CLAIM DOES NOT: `SDK-LINT: PASS`, but the JSON run shows 3 new A002 findings in the changed code (R-V3).
4. S3: runtime.py is 398 lines after its header. HELD (410 total, 12-line header), but only with 44 comment lines over 72 columns (R-V1).
5. Spec NFR-8 / §12.4: "comment blocks are wrapped at 72 columns". DOES NOT HOLD: 52 lines in 3 files (R-V1).
6. Spec §3/§12.3: the shared loop is never edited. HELD: `git diff --stat 39ce8b20...936e3278 --` on `vidbyte/agents/runtime.py`, `base.py`, `validation.py`, and `lint/baseline.json` is empty.
7. Spec §12.3: the touched files stay within the listed set. HELD: every non-doc path in `git diff --name-status` is a §12.3 row or part of the S2 test pack.
8. AGENTS.md §3 / A006: lib imports no higher layer. HELD: grep of `vidbyte/lib/{dataclasses,enums,constants}/agent_swarm.py` imports shows only `vidbyte.lib.*` and the standard library.
9. Prompt enum header: "162 static prompt assets across 36 families". HELD (counted the members and family prefixes).
10. §12.5: READMEs stay under A009. HELD: 12,253 / 33,476 / 33,831 characters.
11. S3 deviation note: S2's fix commit 1ddc6b9d corrected defects and did not weaken any test. HELD: the oracle excludes COMPACTION from the base prompt, adds the "System prompt:\n" label, and gates EC-6's side call on the tester's IDLE. No assertion was removed.
12. Prompts interface test passes. HELD: `pytest tests/test_prompts_interface.py` → `5 passed in 0.79s`.

COMMANDS RUN
- `git -C <wt> diff --name-status 39ce8b20...936e3278` → every non-doc path is in §12.3 or tests/features/agent_swarm.
- `git -C <wt> diff --stat 39ce8b20...936e3278 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/agents/validation.py lint/baseline.json` → (empty).
- `PYTHONPATH=<wt> python lint/run.py` → `A002 IMPROVED 703→565 … S063 IMPROVED 4→3 … SDK-LINT: PASS`.
- `PYTHONPATH=<wt> python lint/run.py --all --format json`, filtered to `agent_swarm` → `A002 member.py 134`, `A002 runtime.py 295`, `A002 runtime.py 301`.
- `PYTHONPATH=<wt> python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` → `268 passed in 7.04s`.
- `PYTHONPATH=<wt> python -m pytest tests/test_prompts_interface.py -q -p no:cacheprovider` → `5 passed in 0.79s`.
- `PYTHONPATH=<wt> python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at a319f44dfec4d2577e0707767bad87bbb7063fa8 (vidbyte-sdk 0.3.0, 650 exports).`
- `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/' <file> | wc -l` (head vs `git show 39ce8b20:<file>`) → runtime.py 44 vs 0; member.py 3 vs 0; agent_swarm_observer.py 5 (new); compaction.py, agent_swarm_turn.py, lib dataclasses, and toolset 0.
- Wrap estimate (scratchpad script that rewraps each over-wide comment at 72 columns) → runtime.py 398 → about 471 lines after the header.
- `wc -l vidbyte/agents/agent_swarm/*.py vidbyte/tools/toolsets/agent_swarm.py` → runtime.py 410, member.py 242, compaction.py 91, toolset 85.
- `git show 39ce8b20:vidbyte/agents/agent_swarm/runtime.py | grep -n "def _end_check\|def _stop"` → only `_end_check` at 271 (no `_stop` at base).
- `git ls-files tests/features/agent_swarm | grep -c pycache` → `0`.
- `git log --format='%h %s' 39ce8b20..936e3278` → 35 commits. The feature, test, and chore commits cite W-/FR-/AC- IDs, and the docs(spec) commits record the pipeline.
