LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the gates are clean (lint is identical to base, 186 targeted tests pass, the contract is current), but there are three Major conventions gaps: events.py meets its 400-line budget only by packing keyword arguments onto shared lines, the handoff keeps a private copy of the canonical truncate cut even though a cycle-free lib home exists, and two lib headers send routine edits into docs/spec.

WHAT THE IMPLEMENTATION GETS RIGHT
- Lint at head matches base exactly. `lint/run.py --format json` was run on head and on a `git archive` export of `origin/feat/infinite-memory-agent`. Every rule has the same count (A001 642, A002 573, A006 34, A007 255, C002 9, C016 0, S009 350, S020 1, S039 5, S060 32), and the per-rule multisets of findings have an empty diff. The IMPROVED lines (A002 703→573, S010 5→0, and others) are pre-existing and show up identically on base.
- Placement is correct:
  - The 4 enums are in `vidbyte/lib/enums/infinite.py` and exported from `vidbyte/lib/enums/__init__.py`.
  - All 16 new records are in `vidbyte/lib/dataclasses/infinite.py`: frozen, slotted, and validated through `RecordFieldValidator`.
  - Missing checks were added as options on the canonical helpers (`allow_zero`, `require_utc_datetime`, `require_callable`, and `OutputText.truncate(marker=)`), not as private validators.
  - There is no `to_dict`, no `TypedDict`, and no `seq`.
- Comments follow the house rules:
  - Every added production comment line is ≤72 columns.
  - `@intent` blocks cover the §12.4 invariants.
  - The main functions (`run_handoff`, `InfiniteMemoryRuntime.run`, the launch loop) are narrated step by step.
  - Call chains stay one level deep.
- Docs and exports are current:
  - Headers have all nine fields.
  - The folder README's File Index lists `events.py` and has the new "Events and handoff" section and the `on_event` Limits row.
  - All six export facades are updated.
  - `contracts/sdk-public-api.json` is current (647 exports).
  - The READMEs are under A009's 40,000-character limit (18,956, 29,894, and 4,046 characters).

FINDINGS

R-V1 [Major] [house-style/budget] vidbyte/agents/infinite/events.py:133 — events.py reaches exactly 400/400 lines by packing up to 4 keyword arguments per line, not by fitting the budget
  Evidence: lines 132-137 put 11 kwargs on 4 lines, for example `max_depth=self._count(settings.max_depth), max_parallel=self._count(settings.max_parallel), max_agents=self._count(settings.max_agents), max_iterations=None if iterations is None else self._count(iterations),`. Lines 202-208 put 13 kwargs on 5 lines. Lines 148, 175, 218, 279, 289, 298, and 308 are each a whole details constructor on one line; line 308 is 285 characters. The same file's `subagent_finished` constructor (lines 255-269) uses one kwarg per line.
    - An AST count over the 14 `Infinite*Details(...)` calls finds 13 packed and 1 laid out. Laying out all of them the way line 255 does adds 67 lines (≈467 in total).
    - The spec estimated this module at "~290 (≤ 400)" (spec line 425).
    - The widths count gives 400 lines after the header (0 headroom), 29 code lines over 160 columns, and 9 over 200.
    - Repo grain: the strict regex for continuation lines carrying 3 or more `kw=` items matches 4 lines in all of `vidbyte/` on origin/main and 3 in events.py alone; the regex misses the nested-call packing at lines 133-135 and 203-206.
    - The separate one-line `InfiniteEventDetails` alias at lib/dataclasses/infinite.py:565 is 414 characters long and lists 13 members.
  Failure: house style is "readability over cleverness", and the NFR-1 budget exists to bound complexity, not line breaks. Spec line 427: "_The implementer may not exceed this budget without stopping and reporting BLOCKED._" The module's honest size is about 467, so the letter of NFR-1 holds and its intent does not. The layout also follows the budget, not the content, since one constructor in the same file is laid out and 13 are not. A human reviewer would write: "Reformat these one argument per line like subagent_finished; if that breaks the budget, raise it explicitly rather than hiding it in line width."
  Smallest fix: this needs a user decision, as §8.4 requires, so it is not a repair-agent call.
    - (a) Approve an events.py cap of about 470 in the row-22 budget test (`tests/features/infinite_memory_agent/test_infinite_memory_contract.py`, the caps dict next to `_lines_after_header` at :466), then lay out the 13 packed constructors one kwarg per line.
    - (b) Or record in the PR description that the packing was accepted on purpose.
    - Either way, wrap the alias at lib/dataclasses/infinite.py:565 one member per line. That adds 14 lines (604 → 618, still ≤620).
  Spec IDs: NFR-1, D-2

R-V2 [Major] [AGENTS.md principle 5] vidbyte/context/handoff/infinite.py:106-108 — the handoff re-implements OutputText.truncate privately, although a lib home importable without the cycle exists, and the README says there are no private copies
  Evidence: the handoff's `_lines` builds its own cut, and two other call sites repeat the same UTF-8 scrub inline:
    ```
    room = INFINITE_HANDOFF_LINE_MAX_CHARS - len(INFINITE_TRUNCATION_MARKER)
    shown = [text if len(text) <= INFINITE_HANDOFF_LINE_MAX_CHARS else f"{text[:room]}{INFINITE_TRUNCATION_MARKER}" for text in collapsed]
    ```
    - It is the same algorithm as `OutputText.truncate` (vidbyte/lib/outputs/text.py: `return text[: limit - len(marker)] + marker`).
    - The header's justification holds only for `vidbyte.lib.outputs`. `cycle_probe.py` (importing `vidbyte.lib.outputs.text` from this module) fails `import vidbyte` with `ImportError: cannot import name 'FileSystemToolConfig' from partially initialized module 'vidbyte.lib.dataclasses'`, through outputs/__init__ → github_job_summary → lib.tools.filesystem → lib.dataclasses, whose `__init__.py:19` imports `vidbyte.context.primitives`.
    - `cycle_probe2.py` makes the same edit with `vidbyte.lib.util.text`, which is dependency-free and already holds `TokenEstimate.cut/cap`. With it, `import vidbyte` succeeds.
    - The surrogate scrub `text.encode("utf-8", errors="replace").decode("utf-8")` is also written twice, at agent.py:172 (`_section`) and events.py:358 (`_cut`).
    - vidbyte/agents/infinite/README.md:135 says the package "builds on canonical helpers in `vidbyte/lib/` rather than private copies: … `OutputText.truncate` … cuts event and handoff text". That is false for the handoff's list lines.
  Failure: AGENTS.md principle 5 says to "have every caller use that helper instead of re-implementing the job inline", and "if one is close, add the option you need to it rather than copying it into a variant beside your feature". The cycle blocks the location of the helper, not the rule. The fix that principle 5 prescribes, moving the logic down to a lower lib module, was available and was not taken. The D-7 deviation text does not record that this alternative was checked. A human reviewer would write: "Move the cut down to lib/util/text.py and make OutputText.truncate delegate to it; then the handoff, the events, and the outputs share one cut."
  Smallest fix:
    - Add a character cut with a marker to `vidbyte/lib/util/text.py`, for example `TextCut.chars(text, limit, *, marker)`, plus one scrub helper for lone surrogates.
    - Make `OutputText.truncate` return that helper's result.
    - Call it from `InfiniteHandoff._lines`, `InfiniteEvents._cut`, and `InfiniteMemoryAgent._section`.
    - Fix the handoff header's ARCHITECTURE NOTE, its WHAT NOT TO DO entry 1, and the README:135 sentence.
    - `tests/test_output_text_truncate_marker.py` and the handoff tests pin the behavior unchanged.
  Spec IDs: FR-23, D-7

R-V3 [Major] [AGENTS.md docs rule] vidbyte/lib/constants/infinite.py:7 — two production headers send every future cap or field edit into docs/spec, the first such headers in the package
  Evidence:
    - constants/infinite.py:7 says "a new details field adds its cap here and its worst case to the table in docs/spec/infinite-memory-events/spec.md section 9.1".
    - dataclasses/infinite.py:7 says "a new details field adds its cap and its worst case to docs/spec/infinite-memory-events/spec.md section 9.1".
    - dataclasses/infinite.py:9 says "The worst-case size of every details record lives in docs/spec/infinite-memory-events/spec.md section 9.1".
    - `git show origin/feat/infinite-memory-agent:` of both files shows no such sentence in either COMMON MODIFICATION PATTERNS.
    - `git grep -n 'COMMON MODIFICATION PATTERNS:.*docs/' origin/main -- 'vidbyte/*.py' | wc -l` prints `0`.
    - The figures that are actually enforced live in tests/features/infinite_memory_agent/test_infinite_memory_events_records.py (`_FIELDS`, `_worst`, and the per-record byte figures at :52, AC-30).
  Failure: AGENTS.md lists this as one of the two rules that apply to every change: "Do not grep, glob, or read files under `docs/` as part of ordinary work: those design documents are large and not kept in sync with the implementation". The briefing also treats docs/spec as pipeline state, not product. A header is the first thing the next agent reads, and these two make "edit docs/spec" a routine step and point to an unsynced document as the source of truth for a size bound. RELATED DOCS pointers are a different matter: they are precedent from #1084 and are fine. A human reviewer would write: "Point maintainers at the test that enforces the bound, not at a design doc we don't keep in sync."
  Smallest fix: in the three sentences, replace the docs/spec target with "the worst-case figure and the `_FIELDS` row in tests/features/infinite_memory_agent/test_infinite_memory_events_records.py". The arithmetic comments in constants/infinite.py (around :140) already explain each figure.
  Spec IDs: n/a

R-V4 [Minor] [§12.5 docs] llms.txt:714-716 — the prebuilt-handoff list still names three handoffs
  Evidence: "`MinimalHandoff`, `EngineeringHandoff`, and `ResearchHandoff` provide prebuilt section sets." `InfiniteHandoff` is now exported from `vidbyte`, `vidbyte.context`, and `vidbyte.context.handoff` next to them (the contract was regenerated at 52249854). The spec's file table (line 883) dismissed llms.txt as "no InfiniteMemory mentions", but this sentence enumerates every prebuilt handoff.
  Failure: AGENTS.md points readers at llms.txt as "the code-heavy documentation bundle". An enumerating sentence that omits a new public export is stale on merge.
  Smallest fix: add "`InfiniteHandoff` (the run handoff `InfiniteMemoryAgent.run_handoff` builds)" to that sentence.
  Spec IDs: n/a

R-V5 [Minor] [house-style/literals] vidbyte/agents/infinite/agent.py:158 — the handoff's run id metadata key is an inline literal next to a named key for the same id
  Evidence: `metadata={"filled": True, "run_id": journal.run_id}`. vidbyte/lib/constants/infinite.py:203 already names the reply key, `INFINITE_RUN_ID_METADATA_KEY = "infinite_run_id"`, and its header says "Add a named constant here before writing another InfiniteMemory policy literal". `"filled"` mirrors base.py:59 and is fine. `"run_id"` is pinned by test_infinite_memory_handoff.py:117, so the value stays.
  Failure: the house style puts constants before literals. A reader sees two spellings of one identity (`infinite_run_id` on replies and `run_id` on the handoff) with no named source for the second.
  Smallest fix: add `INFINITE_HANDOFF_RUN_ID_METADATA_KEY = "run_id"` to the constants module and use it at :158.
  Spec IDs: n/a

R-V6 [Minor] [comment-format] vidbyte/agents/infinite/memory.py:82-85 — the `@intent an-event-follows-its-durable-change` block claims events that live in other methods
  Evidence: "Each event below is announced only once the change it reports is on disk or in the staged list". It sits in `remember`, which has 2 event calls (:89 and :95). The calls at :104 (write_note), :112 (edit), and :123 (drop) are in other methods and have no marker of their own.
  Failure: the field guide's comment-format.md says a block sits directly above the code it explains. A future edit to `_write_note` or `_drop` cannot see this invariant, so a grep on the `@intent` slug lands only on `remember`.
  Smallest fix: change the wording to "Each event in this class …" and move the block to the class level, or add a one-line `# @intent an-event-follows-its-durable-change` above each of :104, :112, and :123.
  Spec IDs: INV-4 (durable before announced): its marker is misplaced, not its behavior

R-V7 [Minor] [commit hygiene] 8cd15dab and 72f1f56d — two commit subjects cite IDs that the commit does not implement
  Evidence:
    - `8cd15dab … [W-8; FR-14, AC-15, AC-16]` touches only workspace.py. AC-15 (spec line 240) is "each reply's `metadata["infinite_run_id"]` equals its journal file's stem", which is runtime work done in 5e5b845c.
    - `72f1f56d … [W-9; FR-14, FR-15, …]` touches only context/handoff/infinite.py. FR-14 is the workspace readers from W-8.
  Failure: the pipeline's commit convention ties each commit to the IDs it delivers. A wrong ID sends a bisect or traceability reader to the wrong commit.
  Smallest fix: no history rewrite is needed for a squash merge. List the corrected mapping in the PR description, or in the squash message: AC-15 → 5e5b845c, FR-14 → 8cd15dab and e8c5ef27.
  Spec IDs: n/a

Judged and not raised:
- Deviation 5 (`RecordFieldConverter` in the journal `_parse`) uses the canonical converter and is correct.
- Deviation 6 (the `removesuffix` duration key) is within house style.
- The one-line `__all__` at lib/dataclasses/infinite.py:616 (638 characters) follows the base file's grain.
- `stop_reason: str` is contract-fixed.
- 44 test comment lines over 72 columns follow the width of the base test pack.
- The context `__init__.py:29` I001 finding is pre-existing.

VERIFIED CLAIMS
1. "No new lint findings" (S3): HELD. Head and base JSON have identical counts for every rule and an empty diff of their finding multisets.
2. "Targeted tests pass" (S3): HELD. 186 passed.
3. "The public API contract is current": HELD. The generator reports 647 exports at 52249854.
4. "Every budget module is within NFR-1": HELD literally (events 400/400, launch 398/410, lib records 604/620, workspace 353, constants 301). The events module has 0 headroom and only through packing (R-V1).
5. Handoff header: "importing [vidbyte.lib.outputs] here breaks import vidbyte": HELD (cycle_probe.py, ImportError as quoted in R-V2).
6. Implied claim (D-7 deviation): no canonical lib helper could be used from the handoff: FAILED. vidbyte.lib.util.text imports cleanly there and `import vidbyte` succeeds (cycle_probe2.py).
7. README:135, "OutputText.truncate … cuts event and handoff text … rather than private copies": PARTLY FAILED. It is true for events and handoff section bodies (agent.py:172), false for the handoff's list lines (handoff:106-108).
8. "Every added production comment is ≤72 columns": HELD (awk over `git diff -U0` additions).
9. "No module header on main sends edits into docs/": HELD. The count is 0 on origin/main and this PR adds 2 (R-V3).
10. "Commit subjects cite the IDs they implement": FAILED for 8cd15dab and 72f1f56d (R-V7). The other 22 code commits match their files.
11. "READMEs are within A009": HELD (18,956, 29,894, and 4,046 characters, all ≤40,000).
12. "llms.txt needs no change" (spec line 883): FAILED (R-V4).
13. "Enums and records sit in lib/enums and lib/dataclasses and are exported": HELD (4 enums, 16 records, six facades).

COMMANDS RUN (from the worktree root; PYTHONPATH=$(pwd))
- `time python lint/run.py` → `SDK-LINT: PASS` / `real 1m20.987s`
- `python lint/run.py --format json` on head and on a scratch `git archive origin/feat/infinite-memory-agent` export (git init) → same counts for every rule; diff of finding multisets empty
- `python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider` → `186 passed in 6.47s`
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 52249854c2da0ca5961a743e961d5b8972fa35ce (vidbyte-sdk 0.3.0, 647 exports).`
- `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache --output-format concise`, filtered to PR files → only `vidbyte/context/__init__.py:29:1: I001` (pre-existing)
- widths.py (lines after the header, the budget test's count) → events 400, launch 398, lib records 604, workspace 353, constants 301, memory 277, settings 205, journal 186, agent 173, runtime 131, enums 100, handoff 100
- Code-line width after the header → events.py max 285 (:308), 29 lines over 160, 9 over 200; lib records max 638 (:616, `__all__`), alias :565 is 414
- AST count of `Infinite*Details(...)` keyword layout in events.py → 13 of 14 packed; `extra lines for one kwarg per line: 67`
- `git grep -c -E '^\s+[a-z_]+=[^,]+, [a-z_]+=[^,]+, [a-z_]+=.*,\s*$' origin/main -- 'vidbyte/*.py'` → 4 in the whole package; same regex on events.py → 3
- `python cycle_probe.py` (scratchpad; handoff imports vidbyte.lib.outputs.text) → `ImportError: cannot import name 'FileSystemToolConfig' from partially initialized module 'vidbyte.lib.dataclasses'`
- `python cycle_probe2.py` (scratchpad; handoff imports vidbyte.lib.util.text) → `import vidbyte` OK
- `git grep -n 'COMMON MODIFICATION PATTERNS:.*docs/' origin/main -- 'vidbyte/*.py' | wc -l` → `0`
- `grep -rn 'encode("utf-8", errors="replace")' vidbyte` → `agent.py:172`, `events.py:358`
- `git log --format='%h %s' origin/feat/infinite-memory-agent..24297ccf` and `git show --stat` on 8cd15dab and 72f1f56d → workspace.py only; context/handoff/infinite.py only
- `python -c "print(len(open(p,encoding='utf-8').read()))"` on the three READMEs → 18956, 29894, 4046
- semgrep: NOT RUN. The global semgrep 1.170.1 crashes on import (mcp 2.x); the Static policy workflow covers it.
