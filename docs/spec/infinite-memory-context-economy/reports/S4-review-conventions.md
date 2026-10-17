LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, exports, the lint ratchet, layering, narration and prompt numbers all hold, but S3's 72-column claim does not: 214 added comment lines are wider than 72 columns (47 of them in vidbyte/), and the new Anthropic cache-mark code adds a third call level. Every fix is mechanical and changes no behavior.

Reviewed: `git diff origin/main...84e566bb` (merge-base 845a4d9b) against spec r4. The worktree HEAD is 31475216, which differs from 84e566bb only in `pipeline.md`, so every path:line below holds at both commits.

WHAT THE IMPLEMENTATION GETS RIGHT
- Placement and exports are clean.
  - `InfiniteRecallMode` is in `vidbyte/lib/enums/infinite.py`. It is exported from `lib/enums/__init__.py` and `vidbyte/__init__.py`, and the contract carries it: `--check` reports the contract current with 645 exports.
  - Every new record (`FullTextRow`, `FullTextHit`, `FullTextMatches`, `InfiniteMapSnapshot`, `InfiniteRecallRequest`, `InfiniteRecallCitation`) is a validated record in `vidbyte/lib/dataclasses/`.
  - The two new settings fields are appended last and validated through `RecordFieldConverter` and the cap loop (`vidbyte/agents/infinite/settings.py:76-77`, `:91`, `:104`).
- The lint loop only moved down. `SDK-LINT: PASS`, exit 0.
  - IMPROVED: A002 703→562, S001 59→56, S009 350→346, S010 5→0, S025 263→261, C011 2→1, S061 6→5, S063 4→3.
  - A007 stayed at 255/255 (RATCHETED), so the condition for row 56 did not fire.
  - No baseline was raised and no suppression was added.
- Layers and sizes follow the plan.
  - The `windows.py` split leaves `strategies.py` at 933 lines, and `windows` imports `strategies`, never the reverse.
  - The trim's nested `cost` became a method.
  - Each of the 9 modules in the infinite package stays at or under 400 lines after its header.
  - Nothing in `vidbyte/lib/` imports a higher layer. The lazy `FullTextIndex` export, marked with an `@intent`, avoids a real import cycle with `validation.py`.
- Main functions are narrated, and the model-facing prose follows the field guides.
  - Comment lines in each main function: `InfiniteRecallTool.execute` 21 of 56 lines; `_after_tool_iteration` 15 of 34; `_attach_cache_breakpoints` 16 of 31; `BashTool.execute` 14 of 41; `InfiniteSearchMemoryTool.execute` 12 of 27; `ReadLinesTool.execute` 10 of 36; `GrepTool.execute` 9 of 59.
  - The `search_memory` description is 5 sentences and its parameter description is 4.
  - The 10 new leaves are registered and contain no limit numbers.
  - `@intent` markers sit on repeat-gating and on copy-not-mutate.

FINDINGS

R-V1 [Blocker] [comment-format] vidbyte/middleware/compaction/context_compaction.py:165 — 214 added comment lines are wider than 72 columns, 47 of them in vidbyte/
Evidence:
- Method: the field guide's check (`awk 'length($0) > 72' | grep '^\s*#'`), applied to the added lines of `git diff -U0 origin/main...84e566bb -- '*.py'`, prints 214 lines.
- The 47 lines in vidbyte/:
  - `providers/anthropic.py`: 9
  - `middleware/compaction/windows.py`: 8
  - `agents/infinite/recall.py`: 7
  - `lib/util/fulltext.py`: 5
  - `code_search/search_memory.py`: 3
  - `context_compaction.py`: 3
  - `lib/dataclasses/code_search.py`: 2
  - `agents/infinite/runtime.py`: 2
  - one each in `read_lines.py`, `grep.py`, `engine.py`, `lib/util/__init__.py`, `lib/dataclasses/infinite.py`, `settings.py`, `memory.py` and `agent.py`
- The other 167 lines are spread across 21 test files.
- Widest source lines (columns):
  - `context_compaction.py:165`: 135; `:252`: 135; `:175`: 125
  - `engine.py:197`: 129
  - `windows.py:123`: 119; `:127`: 119; `:51`: 107
- Widest test lines (columns): `tests/test_anthropic_cache_breakpoints.py:86`: 156; `tests/test_grep_smart_case.py:126`: 150.
- `S3-implementer.md:61` reports "72-col comments" as held.
Failure:
- This contradicts the comment-format lesson ("Wrap every comment line at 72 columns, counting the indent"). These are the 100–120-column blocks the owner explicitly rejected.
- It fails the §12.4 checklist item at spec.md:1174.
- The next `@claude` review will raise it file by file.
Smallest fix:
1. Rewrap each listed line as an evenly filled PEP 8 block of at most 72 columns, placed directly above the code it explains. Keep each `# @intent` line first, and within 20 lines of its `def`.
2. Rerun the awk check until it prints nothing.
3. Rerun `python lint/run.py --rule A002`.
Spec IDs: §12.4 (spec.md:1174)

R-V2 [Blocker] [AGENTS.md principle 1] vidbyte/providers/anthropic.py:148 — the cache-mark helper calls three helpers of its own, adding a third call level
Evidence:
- An AST scan of calls within each class finds this chain:
  - `run_text` / `stream_text` call `_create_payload` (`:65`). This first step already exists on main.
  - `_create_payload` calls `_attach_cache_breakpoints` (`:139`).
  - `_attach_cache_breakpoints` calls `_holds_cache_control` and `_is_repeat` (`:148`), and `_marked_message` (`:169`).
- None of the six existing `_attach_*` helpers calls a method of its own class.
- Spec row 15 (spec.md:1122) says only that `_attach_cache_breakpoints` "checks the conditions". Splitting it into three helpers was the implementer's choice.
Failure:
- This contradicts AGENTS.md principle 1: "that second function should not call a third … lift that call up into the main function".
- S3 reported the §12.4 item at spec.md:1173 as held.
- A reader of `_create_payload` cannot see that marking depends on a stored set of request digests.
Smallest fix:
1. In `_create_payload`, narrate the gate and call it there: `if not self._holds_cache_control(payload) and self._is_repeat(payload): self._attach_cache_breakpoints(payload, config)`.
2. Have `_attach_cache_breakpoints` return the message indices to mark, and let `_create_payload` replace each one with `self._marked_message(...)`. Folding `_marked_message`'s body into the loop also works.
3. Move the `@intent` blocks with their lines.
This leaves the same depth the existing `_attach_*` steps have.
Spec IDs: W-9.1, FR-9.1, INV-9.3, §12.4 (spec.md:1173)

R-V3 [Major] [AGENTS.md principle 5] vidbyte/agents/infinite/recall.py:174 — the masking-and-trim middleware pair and the map context item are each written out three times
Evidence:
- The same two-middleware tuple appears at `agent.py:91-92`, `launch.py:298` and `recall.py:174-175`. Each copy uses the same five constants and the same `Prompts().get(Prompt.INFINITE_MEMORY_MASKED_OUTPUT)` call.
- The same `TextContextItem(title=INFINITE_MAP_TITLE, content=…map_text(), primitive_id=INFINITE_MAP_PRIMITIVE_ID)` is built at `runtime.py:161`, `launch.py:284` and `recall.py:159`.
Failure:
- FR-2.2, FR-4.2 and FR-10.5 require every InfiniteMemory agent to get the same masking and trim.
- A later change to the masked tools, the keep count or the watermark that misses one of the three sites silently gives the root, the pairs or the retriever a different history policy.
- A reviewer will ask why the same policy is written out three times.
Smallest fix:
- Add one package-level builder for each, and call it from all three sites. For example: `InfiniteWorkspace.map_item()` beside `map_text()`, and one `history_middleware()` static method next to it.
- This changes no behavior.
Spec IDs: FR-2.2, FR-4.2, FR-10.5

R-V4 [Major] [prompt-families; model-facing-tool-contracts] vidbyte/prompts/prompts/infinite_memory/retriever_system_prompt.md:1 — the retriever leaf lacks the role-prompt sections its sibling leaves have, and the question description gives examples
Evidence:
- `prompt-families.md:5` says: "Give role prompts headed sections: purpose, tools, workflow, memory, limits, and reply".
- The retriever leaf (2,162 characters) has three headings: its role, how to search, and its final reply.
- `verifier_system_prompt.md` has seven, including "Working within history trimming" and "When a call is refused". `generator_system_prompt.md` also has seven.
- The retriever runs under the same masking and trim (`recall.py:174-175`), and its reads and citations can be refused. Its leaf says nothing about masked older results or refused calls.
- `recall_question_description.md:1` says "any limit such as a period, a source, or a version". This goes against `model-facing-tool-contracts.md:5`: "omit concrete examples from model-facing prose".
Failure:
- When a retriever's fourth result replaces an older one with the masked placeholder, or a read is refused, the leaf gives it no instruction. It may search again or stop early.
- The example list narrows what the asking agent treats as a limit.
Smallest fix:
1. Add "Working within history trimming" and "When a call is refused" sections, adapted from `verifier_system_prompt.md`, with no numbers.
2. Split "How to search" into a tools section and a workflow section.
3. Drop the "such as …" clause.
Spec IDs: FR-10.5, FR-10.7

R-V5 [Minor] [module headers] vidbyte/lib/registries/infinite.py:76 — the literal "grep" breaks a rule stated in the file's own header
Evidence:
- `registries/infinite.py:8` (WHAT NOT TO DO 1) says "name tools by their constants", but `:76-77` return `("grep",)`.
- `constants/infinite.py:7` says "Add a named constant here before writing another InfiniteMemory policy literal", but `:137` is `("grep", "read_lines", INFINITE_SEARCH_MEMORY_TOOL_NAME)`.
- No constant for the grep or read_lines tool name exists under `vidbyte/lib/constants/`.
- The spec prescribes these values (spec.md:731, :1136), but not writing them as literals.
Failure:
- The names of two tools that the tools layer owns are spelled out in three places.
- If `GrepTool`'s spec name changes, the DELEGATED mode silently stops withholding grep, and grep output is no longer masked.
Smallest fix:
- Add `INFINITE_GREP_TOOL_NAME = "grep"` and `INFINITE_READ_LINES_TOOL_NAME = "read_lines"`, with the same values, and add both to `__all__`.
- Use them at the three sites.
Spec IDs: FR-2.2, FR-10.4

R-V6 [Minor] [§12.5; agents-md-map] llms.txt:519 — llms.txt and artifacts/file_index.md list code_search's exports without the new tool
Evidence:
- `llms.txt:519` reads "`vidbyte.tools.builtins.code_search`: `GlobTool`, `GrepTool`, `SemanticSearchTool`."
- `artifacts/file_index.md:422` reads "Repository search tools: `GlobTool`, `GrepTool`, and `SemanticSearchTool`."
- The PR adds `InfiniteSearchMemoryTool` to `code_search/__init__.py`.
- spec.md:1197 says both files "need no change: verified that none lists these files or the moved classes". The PR-body note is to repeat that.
Failure:
- The two indexes that AGENTS.md:9 points agents to now miss a public export.
- The PR body would make a claim that is false.
Smallest fix:
- Add `InfiniteSearchMemoryTool` to both lines.
- Drop those two files from the PR body's "need no change" sentence.
Spec IDs: §12.5 (spec.md:1197), FR-8.1

R-V7 [Minor] [README accuracy] vidbyte/providers/README.md:615 — "(see below)" points to a section that is above it
Evidence: Contract Invariants note 1 (under the heading at line 610) ends with "gates prompt-cache marks (see below)". The section "## Anthropic Prompt-Cache Marks" is at line 532.
Failure: The note amends an invariant that review already enforces ("Adapters are stateless per call"), and it sends the reader the wrong way to find the exception.
Smallest fix: Change it to "(see Anthropic Prompt-Cache Marks above)".
Spec IDs: §12.5 (README rows)

R-V8 [Minor] [module headers] vidbyte/tools/toolsets/infinite.py:4 — two module headers miss a new caller and the tests that cover new code
Evidence:
- The toolset's ROLE IN CODEBASE names `agent.py` and `launch.py` as `get_tools` callers. `recall.py:114` also calls it.
- The toolset's TESTS line (`:11`) omits `test_infinite_memory_recall.py` and `test_infinite_memory_search.py`, though both import `InfiniteMemoryAgentTools`.
- The TESTS line of `vidbyte/agents/infinite/memory.py:11` lists only the workspace and verification tests. `test_infinite_memory_recall.py:205-213` tests `memory.recalled` and the recall builder.
Failure: An agent that changes `get_tools`' signature by following the header will miss the retriever's call site and the tests that would catch the break.
Smallest fix:
- Add `recall.py` to the toolset's ROLE.
- Add the two test files to the toolset's TESTS and `test_infinite_memory_recall.py` to memory.py's TESTS.
Spec IDs: §12.4 (module headers)

R-V9 [Minor] [house style] vidbyte/lib/util/__init__.py:85 — the lazy-export table's module path is never read
Evidence:
- `_LAZY_EXPORTS = {"FullTextIndex": "vidbyte.lib.util.fulltext"}` is at line 71.
- `__getattr__` checks only that the name is in the table (line 83). It then always runs `from vidbyte.lib.util.fulltext import FullTextIndex` and returns `FullTextIndex` (lines 85-87).
Failure:
- A second name added to the table would resolve to `FullTextIndex` instead of raising or loading its own module.
- The table looks authoritative but is not.
Smallest fix: `return getattr(importlib.import_module(_LAZY_EXPORTS[name]), name)`.
Spec IDs: W-8.1, FR-8.3

VERIFIED CLAIMS:
1. FALSE in part: S3-implementer.md:61, "§12.4: all items held … 72-col comments, A002 clean".
   - The 72-column part fails (R-V1).
   - "A002 clean" holds: A002 IMPROVED 703→562.
2. FALSE at one site: §12.4 "Call chains are one level deep" (spec.md:1173).
   - It fails at `anthropic.py` (R-V2).
   - The AST scan found three other two-level chains in changed classes. Two are prescribed by the spec:
     - `InfiniteWorkspace.map_text → map_snapshot → _text/_descriptions` (FR-7.2, spec.md:236)
     - `InfinitePair.run → render → finished_lines` (INV-5.1, D-7)
   - The third already exists on main: `ContextCompactionEngine._build_strategy → _string_tuple` (5 calls on main).
3. HOLDS: "no A007 literal defaults; no baseline raised".
   - A007 is 255 against an allowance of 255 (RATCHETED, not IMPROVED), so ratcheting it down was not due.
   - No rule REGRESSED, and lint passes with exit 0.
4. HOLDS: "strategies.py < 1,000" and the package size rule.
   - `strategies.py` has 933 lines.
   - The largest package file, `launch.py`, has 394 lines in total.
5. HOLDS: "enum placement/exports; contract current".
   - `generate-sdk-public-api.py --check` prints "contracts/sdk-public-api.json is current … (vidbyte-sdk 0.3.0, 645 exports)".
6. HOLDS: "READMEs < 40,000 chars".
   - `infinite/README.md` has 16,016 characters.
   - `providers/README.md` has 42,731, under its legacy A009 ceiling of 55,000.
   - A009 passes.
7. HOLDS: "narrated mains". Every main function listed at spec.md:1172 has comments throughout (see the counts above).
8. HOLDS: "no numbers in leaves; leaves registered". The 10 new leaves are in the family JSON and `Prompt`, and none contains a limit number.
9. FALSE: spec.md:1197, "llms.txt and artifacts/file_index.md need no change" (R-V6).
10. HOLDS: commit hygiene.
    - All 61 first-parent commits after 4f30a0d9 cite W- or FR- IDs.
    - Seven are fixups (a81862dc, 7ebf289c, 7ecb8109, 46a15421, 48415efc, 06b148b2, e21463fe). They are harmless because the repo squash-merges.
    - The diff contains no generated files (no egg-info, `__pycache__`, `.pyc`, `.db` or `.log`).
11. Checked and not reported as defects:
    - `recall_mode: InfiniteRecallMode | str` follows the same file's existing `provider: ModelProvider | str` (`settings.py:122`). The three `InfiniteRecallMode(...)` re-coercions only satisfy the type checker.
    - The third copy of the placeholder default at `context_compaction.py:174` follows main's pattern for the `keep_recent` and `max_chars` defaults.
    - `windows` importing helpers from `strategies` is the direction §12.4 prescribes.
    - No settings field for the recall, masking and watermark caps is planned in spec row 16 (spec.md:1123). That conflicts with the rule in the folder README (`vidbyte/agents/infinite/README.md:120`: "A new cap is a constant, a settings field, and a check"). It is flagged as a risk only. Reconciling the README note is a follow-up.

COMMANDS RUN:
- `PYTHONIOENCODING=utf-8 timeout 600 python lint/run.py </dev/null`: SDK-LINT: PASS, exit 0 (ratchet table as above).
- `PYTHONIOENCODING=utf-8 timeout 300 python lint/run.py --rule A007 --all </dev/null`: A007 RATCHETED 255/255, exit 0.
- `PYTHONIOENCODING=utf-8 timeout 180 python scripts/generate-sdk-public-api.py --check </dev/null`: the contract is current (645 exports), exit 0.
- `PYTHONPATH=<cygpath -w worktree> timeout 400 python -m pytest tests/test_anthropic_cache_breakpoints.py tests/test_compaction_windows.py tests/features/infinite_memory_agent/test_infinite_memory_recall.py tests/test_fulltext_index.py -q -p no:cacheprovider`: 56 passed in 1.36s.
- Comment widths: `git diff -U0 origin/main...84e566bb -- '*.py'`, piped through awk that prints each added `#` line longer than 72 columns with its file and new line number. Result: 214 lines (list at C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/wide.txt).
- Call depth: an AST scan of changed vidbyte/ classes that prints A→B→C chains where B and C are methods of the same class and A or B was touched. Result: 4 distinct chains (see claim 2).
- Python AST counts of narration comments in the 7 main functions.
- `git diff --stat 84e566bb HEAD`: only `pipeline.md` changed. `git log --first-parent 4f30a0d9..84e566bb`: commit hygiene.
- `grep -n` and `sed -n` probes on `anthropic.py`, `registries/infinite.py`, `constants/infinite.py`, `llms.txt`, `artifacts/file_index.md`, `providers/README.md`, the toolset, memory and util headers, the retriever and recall-question leaves, spec.md rows 236, 731, 1122, 1136, 1172-1176 and 1197, and `S3-implementer.md:61`.
- The comment-format, prompt-families and model-facing-tool-contracts entries in the field guide (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`).
