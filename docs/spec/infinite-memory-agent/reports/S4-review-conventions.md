LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, layering, exports, prompt wiring and headers follow the house rules, but the PR passes the lint ratchet partly on stale headroom and an offset edit to untouched code, and four written conventions (call depth, comment width, parameter-description depth, model-facing text through Prompts) are not met; all fixes stay inside §12.3 files except where noted.

WHAT THE IMPLEMENTATION GETS RIGHT (do not "fix" these)
- Placement is clean: the six enums live in `vidbyte/lib/enums/infinite.py` and are exported from `vidbyte/lib/enums/__init__.py`; the six records are frozen, slotted, and validated in `vidbyte/lib/dataclasses/infinite.py`; the settings sit in `vidbyte/agents/infinite/settings.py` (AGENTS.md exception 1); every constant is in `vidbyte/lib/constants/infinite.py`, and launch/memory define no module constants. The toolset imports nothing from `vidbyte.agents`, A006 is unchanged, and the registry imports through the facade (`from vidbyte.agents.infinite import InfiniteMemoryRuntime`).
- The runtime is wired the way runtime-boundaries.md asks: an enum member, a registry row, membership in `_LINEAR_LOOP_RUNTIMES`, a refusal message that names InfiniteMemoryAgent, and `launch_subagent` marked `metadata={"internal": True}`. Because `BaseAgent._runtime()` builds a new runtime for every run (base.py:1227/1264/1331), mutating `self.tools` needs no restore in `finally`, which matches the JevRuntime precedent.
- Docs and exports are complete. The 40-leaf prompt family matches its enum (the header's "138 assets / 34 families" holds). The prompts README has both a row and an entry. The folder README has a File Index and Notes for agents (8,852 chars, under A009). The REPO_MAP entries are general prose. The public-API contract is regenerated and `--check` reports it current. Every new module header has the full A001 sections, the main functions are narrated, and each `@intent` tag is the first line of its block.
- The gates hold: lint exits 0; S041/S047/S004/S009/A001/S051 are unchanged; 89/89 feature tests pass; production code has no suppressions; `git diff origin/main...def85360 -- lint/` is empty; every module body is ≤ 358 lines; there are no nested defs or lambdas.

FINDINGS (ranked, most severe first)

R-V1 [Major] [lint-ratchet] vidbyte/agents/infinite/settings.py:134, vidbyte/agents/infinite/workspace.py:79 — The PR adds one C012 and one S061 finding, and the gate misses them only because main's baselines have headroom
  Evidence: `model_name: str` (settings.py:134, C012 kind unvalidated-model); `shutil.copyfile(seed, self.root / INFINITE_SEED_DIRNAME / Path(seed).name)` (workspace.py:79, S061 file I/O on a non-literal path outside a reviewed helper). On an export of origin/main, `python lint/run.py --rule C012` gives 23 (baseline 24, IMPROVED) and `--rule S061` gives 5 (baseline 6, IMPROVED). At HEAD they give 24 and 6 (RATCHETED, at the allowance). S3 reported "no baseline raised", which is literally true, but the counts went up.
  Failure: lint/README.md says the ratchet exists to "freeze existing debt while failing any count increase and preserving reductions", and that after a real improvement the allowance should be lowered rather than spent. A reviewer would write: "This PR spends someone else's ratchet reduction on two new violations. Validate the model and copy through the reviewed filesystem helper."
  Smallest fix: In `InfiniteMemoryAgentSettings.__post_init__`, validate the model with `ProviderModelRegistry.validate_provider_model_pair(self.provider, self.model_name)` (or `validate_model`), the registry check C012 looks for, and confirm the tests' model names still pass. Copy seeds through `LocalFileSystemBackend` (`vidbyte/lib/tools/filesystem/backends/local.py`, which is allowlisted) instead of `shutil.copyfile`. Re-run both rules and expect 23 and 5.
  Spec IDs: §12.4 (lint row), FR-1, FR-4

R-V2 [Major] [scope/ratchet] vidbyte/lib/registries/runtimes.py:52, tests/features/infinite_memory_agent/test_infinite_memory_workspace.py:399 — A new S062 finding is hidden by rewriting untouched code in the registry
  Evidence: The test adds implicit concatenation: `'{"path": ...}\n'` / `"{oops\n"` / `'["notes/broken.md", ...]\n',` (3 adjacent literals, new S062). The same PR merges the registry's two pre-existing adjacent f-strings into one (`-f"Unknown runtime type '{runtime_type.value}'. "` / `-f"Supported: {cls.supported_runtimes()}"` → one f-string). That join is unrelated to adding the registry row, and it removes base S062 at runtimes.py:51. Net S062 stays at 889 = 889.
  Failure: AGENTS.md says "Do not rewrite untouched code just to make it conform; that belongs in its own pull request." Spec §12.4 says "No implicit string concatenation." The ratchet is meant to fail new debt, not net it against unrelated cleanup. A reviewer would write: "Revert the registry reformat, or keep it and lower the S062 baseline, and fix the new concatenation in the test."
  Smallest fix: Join the three test literals into one string, or build it with `"\n".join(...)`. Then either revert the runtimes.py string join or keep it and lower the S062 allowance by one. Touching tests/ needs the user's OK under §14, and touching lint/ may need it too.
  Spec IDs: §12.4, §14

R-V3 [Major] [model-facing-tool-contracts] vidbyte/prompts/prompts/infinite_memory/*_description leaves — The parameter descriptions are one- or two-sentence labels with concrete examples, and they pass S025 only through its Prompts().get exemption
  Evidence: All 18 parameter-description leaves are 1–2 sentences, for example `launch_goal_description` 1, `remember_text_description` 1, `note_path_description` 1, `drop_entry_id_description` 1. Five of them carry concrete input examples: `launch_context_description`, `remember_refs_description`, `note_path_description` ("such as notes/pricing.md"), `drop_entry_tool_description`, and `drop_entry_id_description` ("such as s2"). S025's summary says "ToolSpec and ToolParameter descriptions read as general 4-5 sentence context, not a label", and its how_to_fix says "do not add concrete input examples" (lint/rules/s025_model_facing_description_depth.py:281/297). The sibling `jev_bulk_work/tasks_description` runs 3+ sentences. The five tool descriptions are 5 sentences each, which is fine.
  Failure: The field-guide lesson model-facing-tool-contracts.md and S025's stated contract say each parameter description should tell the model what the value is for, its limits, and what happens on misuse, in general prose. Labels leave the model guessing at the closed task-card schema. A reviewer would write: "Expand these to 4–5 general sentences and remove the examples. The exemption lets the build pass; it does not make the text right."
  Smallest fix: Rewrite the 18 parameter leaves in place (prompt JSON only, with no new leaves or code changes) to 4–5 general sentences each, without "such as" examples.
  Spec IDs: §12.4 (prompt row), FR-13

R-V4 [Major] [call-depth] vidbyte/agents/infinite/launch.py:299 — `_task_message` calls `finished_lines`, so `InfinitePair.run` reaches its steps through two levels
  Evidence: `run` (launch.py:208) calls `self._task_message(...)` (launch.py:290), and that helper does `finished = self.finished_lines(launch.journal.finished_children(memory.key))` at :299. `finished_lines` (launch.py:365) is a method of the same class.
  Failure: AGENTS.md principle 1 says a helper "should not call a third. … lift that call up into the main function." A reviewer would write: "Compute `finished` in `run` and pass it into `_task_message`."
  Smallest fix: Move the `finished_lines(...)` call into `run`, give `_task_message` a `finished: str` parameter, and update the narration comment in `run`.
  Spec IDs: §12.4 (style row)

R-V5 [Major] [comment-format] 21 comment lines across the new modules exceed 72 columns
  Evidence: `awk 'length($0) > 72' <file> | grep -E '^\s*#'` hits journal.py:132,146; launch.py:107,122,140,150,213,354; memory.py:166; settings.py:66,158,178,190,207; workspace.py:113,132,133,183,198; lib/dataclasses/infinite.py:103,128. The edited legacy comment block in vidbyte/agents/base.py (~line 78) also runs to about 100 columns.
  Failure: The field-guide lesson comment-format.md says wrapped comment lines stay within 72 columns. Most blocks in these files already follow it, so the overruns stand out as inconsistencies. A reviewer would write: "Rewrap these to 72."
  Smallest fix: Rewrap the listed lines without changing any words.
  Spec IDs: §12.4 (comments row)

R-V6 [Minor] [model-facing-text] vidbyte/agents/infinite/launch.py:249, vidbyte/agents/infinite/memory.py:113-116 — Two model-facing sentences are hard-coded inline, and the empty-list placeholder is inconsistent
  Evidence: `f"{item.key} ({item.draft.text}): not committed, because the verdict is {verdict.value}"` (launch.py:249) and `f"{staged.key} ({staged.draft.text}): dropped by the verifier"` (memory.py:115) both reach the parent model on the result card. memory.py:113 uses `or 'none'`, while memory.py:116 and launch.py:296-305 use `or "-"`.
  Failure: Spec §12.4 says "Every model-facing … sentence is loaded with Prompts().get", and §9.2 puts short labels in INFINITE_ constants. A reviewer would write: "Move these into a leaf or a label constant, and pick one placeholder."
  Smallest fix: Add two INFINITE_ label constants (for example the "not committed" and "dropped" reasons) in lib/constants/infinite.py, format them in, and use "-" in memory.py:113.
  Spec IDs: §9.2, §12.4

R-V7 [Minor] [intent-accuracy] vidbyte/agents/infinite/launch.py:227-231 — The `@intent` comment promises an ordering that `asyncio.sleep(0)` cannot guarantee
  Evidence: `# @intent sibling-generators-finish-before-verifiers-judge` / `# … and every generator has staged before a verdict.` / `await asyncio.sleep(INFINITE_PAIR_TURN_SECONDS)` (= 0). Yielding once orders siblings only when each runner completes without suspending, which is the scripted-test case (AC-5/AC-37). A real network runner can still be mid-call.
  Failure: An `@intent` tag is a contract for future editors (house-style). As written, it claims a guarantee that does not hold. The constant itself is acceptable under A007's own note that zero and one are findings when they set policy.
  Smallest fix: Reword the comment to the true intent ("give sibling pairs one turn so a batch moves forward together"), and drop "every generator has staged before a verdict".
  Spec IDs: AC-5, AC-37

R-V8 [Minor] [strict-config] vidbyte/agents/infinite/settings.py:82, :192 — Bound minimums are literals beside a constant used for the third bound
  Evidence: `… or value < 1:` (settings.py:82); `for name, minimum in (("max_depth", 1), ("max_parallel", 1), ("max_agents", INFINITE_MIN_AGENTS)):` (settings.py:192).
  Failure: The quick check in strict-config-dataclasses.md says each validation comparison should reference the feature's constants module. Mixing literals with a constant in one tuple reads as an oversight.
  Smallest fix: Add `INFINITE_MIN_LIMIT = 1` (or similar) to lib/constants/infinite.py and use it at both sites.
  Spec IDs: FR-1, AC-2

R-V9 [Minor] [header-accuracy] vidbyte/agents/infinite/launch.py:4 — ROLE says the opposite of the depth check
  Evidence: "InfinitePair adds one to each generator that is still above the depth cap". The code adds the tool when the level is below `settings.max_depth`.
  Failure: A001 headers must describe the shipped behavior.
  Smallest fix: Change "above" to "below".
  Spec IDs: FR-11

R-V10 [Minor] [readme-accuracy] vidbyte/agents/infinite/README.md:66 — The trimming sentence reads as though the newest exchanges are dropped
  Evidence: "Each agent's history is trimmed to 60,000 tokens, newest tool exchanges first". The middleware keeps the newest exchanges and drops the oldest.
  Failure: The folder README must not contradict the code (folder_readme checklist).
  Smallest fix: "…trimmed to 60,000 tokens by dropping the oldest tool exchanges first…"
  Spec IDs: FR-14

R-V11 [Minor] [readme-accuracy] tests/features/infinite_memory_agent/README.md:7 — The tests README says the pack is red
  Evidence: "until the feature lands every test here fails on a missing import or name". All 89 tests now pass.
  Failure: The statement will be false on main as soon as this merges.
  Smallest fix: Replace it with one sentence on what the pack covers. This touches tests/, so it needs the user's OK under §14.
  Spec IDs: n/a

R-V12 [Minor] [naming/constants] vidbyte/agents/infinite/journal.py:126, launch.py:188, runtime.py:74 — `INFINITE_MIN_AGENTS` does two jobs, and the run-bound tool names are re-listed inline
  Evidence: `INFINITE_MIN_AGENTS = 2` is the settings floor (settings.py:192), and it is also used as "agents per pair": `return INFINITE_MIN_AGENTS * len(self._started)` (journal.py:126), `wanted = INFINITE_MIN_AGENTS * new` (launch.py:188). runtime.py:74 spells out the five INFINITE_*_TOOL_NAME constants inline, and those are the first five of `INFINITE_RESERVED_TOOL_NAMES`.
  Failure: The name lies at the multiplication sites. The inline tuple will drift when a tool is added.
  Smallest fix: Add `INFINITE_AGENTS_PER_PAIR = 2` for the multiplier, and an `INFINITE_RUN_TOOL_NAMES` tuple that `INFINITE_RESERVED_TOOL_NAMES` extends and runtime.py uses.
  Spec IDs: §9.2

R-V13 [Minor] [scope-adding] vidbyte/agents/infinite/workspace.py:299-307 — `_replace` is a third inline copy of the temp-file-plus-`os.replace` atomic write
  Evidence: `tempfile.mkstemp(dir=target.parent, …)` → `os.fdopen` → `os.replace(temporary, target)`. The same pattern is in vidbyte/sessions/stores/file.py:132-138 and vidbyte/sources/cache/file.py:44-49.
  Failure: AGENTS.md principle 5 says to add the option to a lib helper rather than copy it. Here that means adding an `atomic` option to `LocalFileSystemBackend.write_text`. That file is outside §12.3, so this is a follow-up, not a fix for this PR.
  Smallest fix: Follow-up PR: add the atomic write to the lib filesystem helper and point all three callers at it.
  Spec IDs: §12.3, §14

R-V14 [Minor] [style] vidbyte/agents/infinite/launch.py:214, vidbyte/prompts/README.md:69/:259 — There is a missing space after `=`, and the prompts README entry splits the Jev group
  Evidence: `writer =InfiniteAgentMemory(` (launch.py:214). The "InfiniteMemory Agent" row and entry are inserted between "Jev Bulk Work" (row 68 / entry 247) and "Jev Clone" (row 70 / entry 276).
  Failure: These are formatting and ordering inconsistencies a reviewer would flag in passing.
  Smallest fix: Change it to `writer = InfiniteAgentMemory(`, and move the row and entry after the Jev block (or into alphabetical position).
  Spec IDs: FR-13

VERIFIED CLAIMS
- "SDK-LINT PASS": held (exit 0). C012 and S061 rose to the allowance, though (R-V1).
- "No baseline raised": held literally (`git diff … -- lint/` is empty). It hides a +1/+1 increase spent from main's headroom (R-V1).
- "S062 unchanged at 889": held, but only by offsetting a new test finding with an unrelated rewrite in runtimes.py (R-V2).
- "No suppressions": held for production code. The only one is a deliberate `# type: ignore[arg-type]` in the test pack.
- "89 passed": held (`89 passed in 2.12s`).
- "138 assets / 34 families / 40 infinite_memory leaves": held.
- "launch.py 358 lines; every module ≤ 400": held (launch 358, workspace 325, memory 259, settings 218, dataclasses 212, journal 180, constants 155, runtime 110, agent 102).
- "27 classes in 11 modules; no files outside §12.3; P4 as one commit per §12.6": held.
- "Public-API contract current": held.
- "ANN401/S007/A001/S041/S047/S004/S009/S051 unchanged": held. S051 at runtimes.py:33 is pre-existing on main.
- "A007 workaround constants are justified": held. INFINITE_ROOT_DEPTH, DEPTH_STEP, and PAIR_TURN_SECONDS fit A007's own "zero and one stay findings when they set policy" note. The `@intent` wording overclaims (R-V7).
- "Every §12.4 row done": did NOT hold. Comment width (R-V5), call depth (R-V4), model-facing text (R-V6), and parameter-description depth (R-V3) are open.

COMMANDS RUN
- `python lint/run.py --format json` (HEAD) → exit 0, SDK-LINT PASS.
- `git archive origin/main | tar -x -C <scratch>/s4conv/base`; `git init && git add -A` in the scratch copy only; `python lint/run.py --rule C012` → 23 (baseline 24, IMPROVED); `--rule S061` → 5 (baseline 6, IMPROVED); `--rule S062` → 889; `--rule S051` → 259. At HEAD: C012 24 RATCHETED, S061 6 RATCHETED, S062 889, S051 259, S009 350=350, A001 642=642.
- `git diff origin/main...def85360 -- vidbyte/lib/registries/runtimes.py` → the registry row added, plus the two f-strings at old :51-52 joined into one.
- `git diff origin/main...def85360 -- lint/` → empty.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `89 passed in 2.12s`.
- `python scripts/generate-sdk-public-api.py --check` → "contracts/sdk-public-api.json is current at 41e9421044f1f8bf91111262b451ab86b031d792 (vidbyte-sdk 0.2.1, 643 exports)."
- `awk 'length($0) > 72' <file> | grep -E '^\s*#'` over the new modules → 21 lines (listed in R-V5).
- A sentence count over `vidbyte/prompts/prompts/infinite_memory/*_description` → 18 parameter leaves at 1–2 sentences; the 5 tool descriptions at 5.
- `grep -n "finished_lines\|def _task_message\|def run(" vidbyte/agents/infinite/launch.py` → 208 run, 290 _task_message, 299 call to finished_lines, 365 def finished_lines.
- `git status --porcelain` → empty before this report was written. This report is the only new file.
