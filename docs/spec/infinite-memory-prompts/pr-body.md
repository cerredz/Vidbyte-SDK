feat(prompts): InfiniteMemoryAgent prompts restate its principles at every stage; the seven behavior-shaping prompts exceed 1,100 tokens
## Summary

The `InfiniteMemoryAgent` (stacked base PR #1084, with the review fixes of #1113) is built to run for days. The code enforces the hard limits: depth, batch size, agent budget, entry size and quota, card caps, history trimming. Most of what makes a run long is decided by the model, though: whether the root delegates instead of reading, whether a generator reads a range instead of a whole file, whether anyone saves only what a later agent needs, whether the verifier checks instead of trusting. Before this PR the prompts stated those rules once and briefly, and four of the seven prompts a model reads as its brief were about 240 to 420 tokens.

This PR rewrites the `infinite_memory` prompt family so that each model reads the agent's working rules at the stage where it acts on them. The user asked for two things: prompts of at least 1,000 tokens (applied to the seven behavior-shaping prompts, see Q-1), and, as "the main point", prompts that reinforce the intended behavior: memory sparse and infrequent, the context window treated as a scarce resource at every stage. The rules are placed in layers:

- **Three system prompts** (root, generator, verifier) hold each role's standing rules. They keep every heading and every #1113 rule.
- **Three briefings** (`task_prompt`, `verifier_task_prompt`, `resume_prompt`) are the first message of a generator, a verifier and a resumed root. They now carry a moment-of-use checklist and guidance on how to read each field.
- **`launch_tool_description`** carries why and when to delegate and the rules that span a task card's fields.
- **The compact leaves** stay compact. Four compact descriptions and two replies gained one nudge each; one of those descriptions, `note_path_description`, also stopped claiming that the map lists every file. The 23 compact descriptions grew 2.7 % in total. The three shape leaves (`quota_line`, `map_header`, `result_card`) are byte-identical.

All seven behavior-shaping prompts now measure at least 1,000 by the SDK's estimate and at least 1,100 by tiktoken. The four that grew most sit at 1,123 to 1,160 tiktoken, the low end of the 1,100 to 1,500 band. They aim low because each one rides in every model call of its agent. That per-call cost is the price of the user's floor; it is measured below, and every role stays under the spec's target.

The PR changes no Python file under `vidbyte/`. It adds no leaf or placeholder, and the public API is unchanged. The other changes are the size figures in `vidbyte/agents/infinite/README.md:68`, one new test module (131 cases), and the pipeline record under `docs/spec/infinite-memory-prompts/`.

**Base branch.** This PR targets `feat/infinite-memory-agent` (PR #1084), not `main`, because the agent exists only there; merging it adds these commits to #1084.

## How to use what this PR introduces

Nothing changes for a caller. `InfiniteMemoryAgent` reads the rewritten text through the same catalog, so every run, new or resumed, gets it. To see what a model receives, read each asset the way the agent does and measure it. This is the spec §4 snippet, unchanged:

```python
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.util.text import TokenEstimate
from vidbyte.prompts.catalog import Prompts

try:
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
except ImportError:
    encoding = None
    print("tiktoken is not installed; only the SDK estimate is shown")

SEVEN = (
    "ROOT_SYSTEM_PROMPT",
    "GENERATOR_SYSTEM_PROMPT",
    "VERIFIER_SYSTEM_PROMPT",
    "TASK_PROMPT",
    "VERIFIER_TASK_PROMPT",
    "RESUME_PROMPT",
    "LAUNCH_TOOL_DESCRIPTION",
)
catalog = Prompts()
for name in SEVEN:
    text = catalog.get(Prompt[f"INFINITE_MEMORY_{name}"])
    exact = len(encoding.encode(text)) if encoding else "-"
    print(f"{name.lower()}: estimate {TokenEstimate.count(text)}, tiktoken {exact}")
```

Output on this branch, run from the worktree root with `PYTHONPATH=$(pwd) python snippet4.py`:

```
root_system_prompt: estimate 2858, tiktoken 2470
generator_system_prompt: estimate 1747, tiktoken 1490
verifier_system_prompt: estimate 1434, tiktoken 1216
task_prompt: estimate 1349, tiktoken 1142
verifier_task_prompt: estimate 1373, tiktoken 1160
resume_prompt: estimate 1339, tiktoken 1151
launch_tool_description: estimate 1338, tiktoken 1123
```

The same snippet on `git archive origin/feat/infinite-memory-agent` (7efceb55) prints the "before" column below. tiktoken is optional. When it is missing, the first line says so and only the estimate is shown.

### The seven, before and after

`chars / est / tik`: est is `TokenEstimate.count` (characters divided by four); tik is tiktoken `cl100k_base`; both are read through `Prompts().get`. The floor is est ≥ 1,000 and tik ≥ 1,100. The ceilings and the aim are review thresholds from spec NFR-3, not tests.

| Asset | Reaches the model as | Before (7efceb55) | After | Review ceiling or aim (tik) |
|---|---|---|---|---|
| `root_system_prompt` | the root's system string, raw, every call (`agent.py:72-75`) | 8,516 / 2,129 / 1,829 | 11,431 / 2,858 / 2,470 | ≤ 2,600 |
| `generator_system_prompt` | each generator's system string, every call | 6,011 / 1,503 / 1,277 | 6,988 / 1,747 / 1,490 | ≤ 1,900 |
| `verifier_system_prompt` | each verifier's system string, every call | 4,981 / 1,246 / 1,059 | 5,733 / 1,434 / 1,216 | ≤ 1,600 |
| `task_prompt` | a generator's first message; never trimmed, so it rides in every call | 1,141 / 286 / 241 | 5,393 / 1,349 / 1,142 | 1,100–1,300 |
| `verifier_task_prompt` | a verifier's first message; never trimmed | 1,176 / 294 / 251 | 5,489 / 1,373 / 1,160 | 1,100–1,300 |
| `resume_prompt` | a resumed root's first message; never trimmed | 1,090 / 273 / 232 | 5,354 / 1,339 / 1,151 | 1,100–1,300 |
| `launch_tool_description` | the `launch_subagent` schema of the root and of every generator | 1,977 / 495 / 416 | 5,352 / 1,338 / 1,123 | 1,100–1,300 |

### What each role pays per model call

The table counts the prompt family's fixed load in tiktoken: system prompt + first message + the descriptions in that role's tool schema. It uses the SPARSE preset, the default, which grants `remember` and `write_note`. The map (up to its cap) and the trimmed history (up to its cap) come on top and dominate the total; neither changed. The toolset tools (`bash`, `grep`, `read_lines`) and any developer extras are outside this family and are not counted.

| Role | Before: system + briefing + schema | After | Change | Spec §7 target |
|---|---|---|---|---|
| Root | 1,829 + 0 + 3,438 = 5,267 | 2,470 + 0 + 4,247 = 6,717 | +1,450 (+28 %) | 7,224 |
| Resumed root | 1,829 + 232 + 3,438 = 5,499 | 2,470 + 1,151 + 4,247 = 7,868 | +2,369 (+43 %) | 8,524 |
| Generator | 1,277 + 241 + 3,438 = 4,956 | 1,490 + 1,142 + 4,247 = 6,879 | +1,923 (+39 %) | 7,824 |
| Verifier | 1,059 + 251 + 2,036 = 3,346 | 1,216 + 1,160 + 2,109 = 4,485 | +1,139 (+34 %) | 5,140 |

The schema now holds: for the root and generators, `launch_tool_description` 1,123 + the eight `launch_*` field descriptions 1,340 + the ten SPARSE memory descriptions 1,784; for verifiers, the ten memory descriptions + the `drop_entry` pair 325. The FULL preset adds the `edit_file` schema to every role: 607 → 637, because `note_path_description` appears in it a second time.

| Bound | Before | After | Limit |
|---|---|---|---|
| 23 compact descriptions, per-leaf sum, est / tik (tested) | 4,455 / 3,803 | 4,577 / 3,905 (+2.7 %) | ≤ 4,900 / ≤ 4,183 (110 %) |
| All 24 descriptions, per-leaf sum, est / tik | 4,950 / 4,219 | 5,915 / 5,028 | tik ≤ 5,700 (review, NFR-1) |
| Replies that changed, tik / est (tested ≤ 80) | `remember_saved_prompt` 25 / 25; `remember_staged_prompt` 29 / 31 | 32 / 33; 42 / 47 | ≤ 80 |
| Shape leaves `quota_line`, `map_header`, `result_card`, tik (tested ≤ baseline) | 38, 51, 56 | 38, 51, 56 (byte-identical) | ≤ baseline |

The four compact descriptions that changed: `launch_generator_prompt_description` 207 → 236, `remember_tool_description` 338 → 356, `note_path_description` 151 → 181, `write_note_text_description` 147 → 172 (tik).

## Flow

The diagram shows one run and where each rewritten asset reaches a model. Dotted edges are history trimming. It applies to every agent and keeps the system prompt, the map and the first message.

```mermaid
flowchart TD
  START["run(task)"] --> ROOT
  ROOT["Root plans, delegates, reads cards<br/>system: root_system_prompt, raw<br/>map: map_header, redrawn after every tool iteration<br/>schema: launch_tool_description + 8 launch_* + memory descriptions"]
  ROOT -->|"launch_subagent call"| DL{"DelegationLimitsMiddleware:<br/>max_depth, max_parallel"}
  DL -->|"over a cap: refusal names it"| ROOT
  DL --> CHECK{"Batch check in the tool:<br/>unique names, granted tools,<br/>live context ids, max_agents"}
  CHECK -->|"bad batch: launch_rejected_prompt, nothing starts"| ROOT
  CHECK -->|"name already finished: replayed_label + recorded card, nothing runs"| ROOT
  CHECK -->|"new pair: journaled pair_started"| GEN
  GEN["Generator does the task<br/>system: generator_system_prompt<br/>first message: task_prompt<br/>map drawn once<br/>schema: launch + memory descriptions"]
  GEN -->|"remember: remember_staged_prompt + quota_line<br/>write_note: note_saved_prompt"| WS[("Workspace<br/>entries.jsonl, notes, files.jsonl<br/>.runs journal")]
  GEN -->|"final answer, cut to the card cap = summary"| STATUS{"Generator status"}
  STATUS -->|"failed: no verifier runs"| UNCHECKED["Verdict unchecked:<br/>every staged entry dropped"]
  STATUS -->|"done or partial"| VER["Verifier checks and fixes<br/>system: verifier_system_prompt<br/>first message: verifier_task_prompt<br/>map drawn once<br/>schema: memory + drop_entry descriptions"]
  VER -->|"drop_entry: entry_dropped_prompt<br/>fixes through write_note or edit_file"| WS
  VER -->|"final reply, last VERDICT line"| VERDICT{"Verdict line found?"}
  VERDICT -->|"passed, fixed or failed: commit the staged entries left"| WS
  VERDICT -->|"none"| UNCHECKED
  VERDICT --> CARD
  UNCHECKED --> CARD
  CARD["result_card: summary, review, dropped and files cut to the cap,<br/>entry ids listed whole; journaled pair_finished"]
  CARD -->|"one card per pair, in task order"| ROOT
  ROOT -->|"final answer: run journaled finished, cannot be resumed"| END["Answer to the caller"]
  CRASH["Crash or cancel"] --> RESUME["resume(): fresh root conversation<br/>first message: resume_prompt with task, finished, interrupted"]
  RESUME --> ROOT
  TRIM["History trimming past the cap:<br/>oldest tool exchanges dropped"] -.-> ROOT
  TRIM -.-> GEN
  TRIM -.-> VER
```

### Which rule each model now reads at each stage

The quotes are verbatim from the shipped assets. Each row lists only rules this PR added or sharpened; the #1113 rules are still there. P1–P9 are the principles in spec §6.1, taken from request §C D-E.

| Stage | Who reads it, and where | Rules added or sharpened (principle) |
|---|---|---|
| Root planning | root, `root_system_prompt` §Your role, §How the work flows, §What to delegate; `launch_tool_description` §When to use it | root: "any other reading is work for a pair" (P1); root: "never end your turn to ask a question" (P7, unattended); root: "write every deliverable the task asks for into a plan note" (P9); root: "The workspace and its map are the record of this run, not this conversation" (P7); root: "never do a pair's work yourself" (P1); launch: "Delegate by deliverable rather than by step" (P4); launch: "size each call to what you can read and act on" (P1) |
| Task-card writing | root §How to write a task card; `launch_tool_description` §How it behaves, §Rules and refusals; the `launch_*` field descriptions | root: "Neither can see this conversation or the cards you have received" (P4); root: "Ask only for what you will use and never for a transcript" (P5); root: "grant the fewest that will do" (P1); launch: "write every card to stand on its own" (P4); launch: "the verifier never sees the generator_prompt" (P6); launch: "only the generator receives the context the card names" (P4); launch: "Never ask for a transcript" (P5); launch_generator_prompt: "ask for exactly what you will need" (P5) |
| Generator working | `generator_system_prompt` §Your role, §How to work, §Delegating further; `task_prompt` | gen: "No one answers questions while you work" (P7); gen: "Your context is limited too: search before you open a file" (P1); task: "This message is your whole brief for one task" (P4); task: "Evidence that exists only in your conversation does not count" (P6); task: "Keep a note as you go" (P3); write_note_text: "Append findings as you make them rather than at the end" (P3); note_path: "Keep one stable path for your task's subject" (P3) |
| Generator's final reply | gen §Your final answer; `task_prompt` step 7 | gen: "Check each criterion before you reply" (P6, P9); gen: "name a note rather than paste what it already holds" (P5); gen: "state plainly what is not done" (P9); gen: "Your final answer is not memory, because no later agent can search it" (P2); task: "nothing the parent does not need" (P5) |
| Verifier checking | `verifier_system_prompt` §How to check, §How to fix; `verifier_task_prompt` | vtask: "nothing below has been checked yet" (P6); ver: "since your own context is limited" (P1); ver: "The workspace is the record, not the generator's account of it" (P6, P7); ver: "Do not redo the task" (P6); vtask: "silence about a criterion is not a pass" (P6); vtask: "that choice is a claim too" (P6); vtask: "fix it when the fix stays inside the task" (P6) |
| Memory staging and commit | `remember_tool_description`, `remember_staged_prompt`, `remember_saved_prompt`; gen §Memory; task §Your memory quota; ver §Reviewing staged entries; vtask staged entries | remember_tool: "The default is not to remember" (P2); gen: "it is a ceiling, not a target" (P2); remember_staged: "Stage only what a later agent would be wrong or slower without" (P2); remember_saved: "Keep anything longer in a note" (P2); ver: "drop what is not worth keeping" (P2, P6); vtask: "a reworded duplicate gets through unless you drop it" (P2) |
| Parent reading a card | root §Reading result cards; `launch_tool_description` §How it behaves | root: "A card is not memory" (P2); root: "Keep its status and progress in the plan note, never in an entry" (P2); root: "A failed or unchecked card alone never settles a deliverable" (P6, P9); root: "read only that part of a named file" (P1); launch: "a card without a verdict saved none" (P6) |
| Resume | `resume_prompt` (the resumed root's first message) and the root system prompt | resume: "keep your context as lean as before" (P1); resume: "If the map does not show your plan note, search the workspace for it" (P7); resume: "Compare the deliverables with the finished cards" (P9); resume: "The verdict, not the status, says whether a pair counts" (P6); resume: "never save a card's status or progress as an entry" (P2); resume: "No one will answer during the run" (P7); resume: "running out of them ends the run for good" (P7) |
| History trimming | §Working within history trimming in all three system prompts | root, gen and ver: "trimming is not a reason to remember" (P2, P3); root: "never relaunch finished work under a new name just to read its result" (P5, P7); root: "Before you decide you are done, re-read the deliverables in your plan note" (P9); gen: "reading back only the parts you need" (P1); ver: "check again rather than recall it" (P6) |

P8 (any kind of work) holds for every asset: no leaf has a coding-only word, and `test_prompt_family_text_carries_no_coding_only_rules` checks this.

## What changed

Paths are relative to `vidbyte/prompts/prompts/infinite_memory/` unless they start with `vidbyte/`, `tests/` or `docs/`. Line counts are from `git diff --numstat` (added / removed).

| File | +/− | What changed |
|---|---|---|
| `root_system_prompt.md` | 31 / 20 | Same ten headings. Adds the unattended rule, flow step 2 (list the deliverables in a plan note), "the workspace is the record", the read-a-file-only-to rule, card fields that ask only for what the root will use, batches sized to what the root can read, "a card is not memory", "the default is not to remember", the quota as a ceiling, "trimming is not a reason to remember", replay a trimmed card by its name, and the check of each deliverable against the cards before the final answer |
| `generator_system_prompt.md` | 11 / 10 | Same seven headings. Adds: no one answers, so choose the reasonable reading and report it; "Read for the task"; delegate only what costs more context than its card; the default is not to remember; the quota as a ceiling; the note as the generator's record; trimming is not a reason to remember; name a note instead of pasting; the final answer is not memory |
| `verifier_system_prompt.md` | 7 / 5 | Same seven headings and the three `VERDICT:` literals. Adds: read only what each check needs; the workspace is the record; do not redo the task; drop what is not worth keeping; re-check instead of recalling; trimming is not a reason to remember; "say what you fixed" |
| `task_prompt.md` | 23 / 1 | Same eight sections and seven placeholders. Adds a preamble (the whole brief), reading guidance under each field, and a seven-step checklist |
| `verifier_task_prompt.md` | 24 / 3 | Same eight sections and eight placeholders. Adds a preamble ("nothing below has been checked yet"), guidance for a partial status, cut answers, a chosen reading, reworded duplicates and files written outside the memory tools, and a six-step checklist ending in exactly one verdict line |
| `resume_prompt.md` | 15 / 2 | Same parts and three placeholders. Adds: rebuild from notes, entries and cards; no pair is running; the verdict decides; a same-name relaunch keeps its finished children; and a six-step checklist (find the plan note, compare deliverables, the card is not memory, no one will answer, turns are limited) |
| `launch_tool_description.md` | 10 / 4 | Same four headings. Adds: only the result card comes back; delegate by deliverable; size each batch; capped fields, so detail goes in a note; only the generator gets the context; cards stand alone; the fields must agree; a failed generator's card comes back unchecked; replay a name to reread its card; never ask for a transcript or paste large excerpts |
| `launch_generator_prompt_description.md` | 1 / 1 | "ask for exactly what you will need … and never for a transcript"; says which detail belongs in a note |
| `remember_tool_description.md` | 1 / 1 | "The default is not to remember: save an entry only when a later agent would be wrong or slower without it" |
| `note_path_description.md` | 1 / 1 | "lists files by their paths" (was "every file", R-27); keep one stable path for the task's subject |
| `write_note_text_description.md` | 1 / 1 | Append findings as you make them |
| `remember_saved_prompt.md` | 1 / 1 | Adds "Keep anything longer in a note." |
| `remember_staged_prompt.md` | 1 / 1 | Adds "Stage only what a later agent would be wrong or slower without." (R-19) |
| `vidbyte/agents/infinite/README.md` | 1 / 1 | Line 68: role prompt "about 2,100" → "about 2,900" (root 2,858 est), descriptions "about 5,000" → "about 5,900" (5,915), total "near 105,000" → "near 107,000" (90,000 + 2,858 + 5,915 + 8,000 = 106,773) |
| The other 27 leaves | — | Checked against their outlines in spec §12.3.1 and against the code; unchanged |
| `tests/features/infinite_memory_agent/test_infinite_memory_prompts.py` | 414 / 0 | New: 17 test functions, 131 cases. Pure text checks through `Prompts().get`, with no model and no subprocess. Written red before the rewrite (37 failed, 94 passed at the base) |
| `tests/features/infinite_memory_agent/FEATURE.md`, `README.md` | 23 / 1 | The prompt-contract area and its failure modes, a File Index row, and a Logs entry. Line 7 now says the base test plan maps the base tests |
| `docs/spec/infinite-memory-prompts/` | 22 files + this body | The pipeline record: request, spec r4, test plan, code map, review, verify log, pipeline state, stage reports |

## Acceptance criteria → proof

Every test named below exists on this branch (`--collect-only`). "Pack" is `tests/features/infinite_memory_agent`.

| AC | What it requires | Proof | Result |
|---|---|---|---|
| AC-1 | §4 snippet: seven lines, every est ≥ 1,000 and tik ≥ 1,100 | `test_section_4_snippet_prints_seven_lines_each_at_or_over_the_floor`; `test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline` (14 ids); snippet output above | pass; lowest is 1,123 tik / 1,338 est |
| AC-2 | 40 leaves load, each maps to one `Prompt` member | `test_prompt_family_has_exactly_the_forty_documented_leaves` (existing); `test_family_folder_holds_exactly_the_leaf_assets_as_path_and_source_url` | pass |
| AC-3 | 12 formatted leaves render with each placeholder once, no stray brace; 28 raw leaves hold no brace | `test_formatted_leaf_renders_each_placeholder_once_and_leaves_no_brace` (12 ids); `test_raw_leaves_hold_no_brace_at_all` | pass |
| AC-4 | every pinned phrase of §8.5 in its leaf; the three `VERDICT:` literals | `test_pinned_phrase_is_present_in_its_leaf` (49 ids: 22 kept, 27 new); `test_verifier_system_prompt_states_the_three_verdict_literals_exactly` | pass |
| AC-5 | digits only as list markers; no coding-only word | `test_digits_appear_only_as_ordered_list_markers`; `test_prompt_family_text_carries_no_coding_only_rules` (existing) | pass |
| AC-6 | 23-description sum ≤ 110 %; ≥ 4 sentences each; replies ≤ 80; shape leaves ≤ baseline | `test_compact_description_sum_stays_within_ten_percent_of_baseline` (2 ids); `test_every_compact_description_has_at_least_four_sentences`; `test_every_reply_leaf_stays_within_eighty_tokens` (2 ids); `test_shape_leaf_never_grows_past_its_baseline` (6 ids) | pass; sums 4,577 est / 3,905 tik; largest reply 55 tik / 62 est |
| AC-7 | none of the seven below baseline; no repeated sentence of five words or more; ceilings by review | `test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline` (tik ids); `test_no_rule_sentence_repeats_inside_a_behavior_asset` (7 ids); review: root 2,470 ≤ 2,600, generator 1,490 ≤ 1,900, verifier 1,216 ≤ 1,600, the four others 1,123–1,160 | pass |
| AC-8 | 13 fragments end without a newline, 27 whole texts with one | `test_fragments_end_without_a_newline_and_whole_texts_with_exactly_one` | pass |
| AC-9 | pre-existing pack passes, no test edited | pack `244 passed`, which is 113 pre-existing + 131 new; `git diff --name-only origin/feat/infinite-memory-agent...HEAD -- tests` lists only the new module, `FEATURE.md` and `README.md` | pass |
| AC-10 | `result_card` labels in order and no cut marker; `quota_line` integers standalone; the code's four cuts | `test_result_card_keeps_its_labels_in_order_and_never_carries_the_cut_marker`; `test_quota_line_renders_each_count_as_a_standalone_integer`; `test_an_unchecked_card_with_long_dropped_and_files_lists_stays_inside_the_nfr7_bound` (existing) | pass |
| AC-11 | README figures equal the measured est values, rounded | review: root 2,858 → "about 2,900"; 24-description sum 5,915 → "about 5,900"; 106,773 → "near 107,000" | holds |
| AC-12 | lint, semgrep, API check, source and package stages | the table below | pass, except 3 failures inherited from the base branch (explained below) |
| AC-13 | every base heading present, in order | `test_every_base_heading_survives_in_order` (30 ids: every leaf with headings, `launch_tool_description` counted once) | pass |
| AC-14 | verifier system string holds the whole `verifier_system_prompt`; first message holds the `verifier_task_prompt` rendering | `test_the_verifier_gets_the_generators_outcome_but_never_its_transcript` (existing) | pass |

## Verification

All gates are local. GitHub Actions are disabled repo-wide, so `gh pr checks` reports no checks and the local gate is the gate of record. The run below is at the PR head, `77171eeb`, whose code is identical to `3825237d` (every later commit is docs only). It gives the same results as the orchestrator's earlier run at `5f41a5f4`.

| Gate | Command | Final lines |
|---|---|---|
| New module | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` | `131 passed in 0.88s` |
| Feature pack | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | `244 passed in 4.56s` |
| Custom lint | `python lint/run.py` | `S063 IMPROVED 4 -> 3 …` · `S064 RATCHETED: 4 known finding(s) …` · `SDK-LINT: PASS` (S063 is an AST rule over Python and its improvement is inherited; no baseline was touched) |
| Semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` | `Ran 1 rule on 980 files: 0 findings.` |
| Public API | `python scripts/generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at 9eca4a33… (vidbyte-sdk 0.3.0, 644 exports).` |
| Full gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | `SDK-LINT: PASS` (step 2) · three `FAILED tests/features/harness_threads/test_harness_threads_surface.py::…` · `3 failed, 6174 passed, 16 skipped in 93.09s` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| Full gate, package | `python scripts/run_ci.py --stage package` (no `PYTHONPATH`) | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| Remote checks | `gh pr checks 1176` | none: Actions are disabled |

**The three source-stage failures come from the base branch, not from this PR.** All three are in `tests/features/harness_threads/test_harness_threads_surface.py`: `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, and `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`. They compare the branch with `git merge-base origin/main HEAD`, and reject the failure codes, the `vidbyte/tools/` files and the `InfiniteMemoryAgent` export that #1084 adds. The orchestrator ran the same file in a detached worktree at the base, `7efceb55`, and it ended `3 failed, 6 passed`. This PR changes no Python file, no root export, and nothing under `vidbyte/tools` or `vidbyte/lib/configs`.

**Semgrep** ran with the exact arguments above, through a scratch virtualenv. The global semgrep CLI cannot start on this machine, because the global `mcp` 2.3.0 lacks `mcp.server.fastmcp`. The venv pins `mcp<2`. This is an environment issue; nothing in the repo changed.

**Independent measurement.** The before figures were measured with the same snippet on a `git archive` export of the base, and they equal spec §8.5's baselines exactly. The per-call table comes from a script that sums each role's actual schema leaves (`launch.py:86-115`, `memory.py`, `vidbyte/lib/registries/infinite.py:36-37`).

## Adversarial review

S4 ran three lenses (conformance, conventions, engineering), and a findings verifier merged and re-measured their findings. It confirmed **1 Blocker and 5 Majors**, refuted or downgraded 6 claims, and recorded 20 Minors. Re-review round 1 confirmed every fix and raised one more Major, R-27, which a scoped verifier confirmed. The orchestrator added one Minor, R-28. Re-review round 2: **SOUND, no new findings.** The full table is in `docs/spec/infinite-memory-prompts/review.md`.

| ID | Severity | Finding | Fixed in |
|---|---|---|---|
| R-1 | Blocker | `launch_tool_description` said both agents see "the context it names". The verifier never does (`launch.py:304-309`). Same-schema descriptions said the opposite. | `a2ae814c` |
| R-2 | Major | `task_prompt` said the map "lists every other file". Past the map cap it keeps the first lines that fit and ends with "… and N more files" (`workspace.py:219-229`). | `032dc49f` |
| R-3 | Major | Neither verifier asset said the verifier's own context is limited (INV-1). | `572667bf` |
| R-4 | Major | A generator's chosen reading of an unclear criterion became the verifier's standard. It is now "a claim too". | `d67bfadc` |
| R-5 | Major | The root's new "read a file only to decide a card" rule contradicted the kept #1113 rules on reading for detail and for small fixes. | `e04d62ea` |
| R-6 | Major | `resume_prompt` cleared 1,100 tik only through two restatements (1,098 without them). They were replaced with a code-true turn-limit rule. | `0253ed07` |
| R-27 | Major | Root `:58` and `note_path_description` still said the map lists every file. In a cut map, the root's own plan note went missing (reproduced with the real `InfiniteWorkspace`). | `fe04ab8c` |

Minor fixes: R-7 `08c412e0`, R-8 `7b5c9616`, R-9 `65c8884c`, R-10 `6647ca4e`, R-11 `60cf9597`, R-12 `19203993`, R-13 (the root `:13` part) `347c8930`, R-19 `5699f96e`, R-26 `689599d3` (with README "about 2,900"), and R-28 `3825237d`. The rest are follow-ups (below).

**#1113 text reworded, with every rule kept (INV-19).** No #1113 rule was dropped. The reviewers found 29 base clauses reworded and every one of the 29 keep-nudges still present. These four rewords came from review fixes:

1. `launch_tool_description` §How it behaves (R-1). Before: "Both agents start fresh: they see their task card, the context it names, the workspace map, and the shared workspace, but not this conversation." After: "Both agents start fresh: each sees its own part of the task card, the workspace map, and the shared workspace, but not this conversation, and only the generator receives the context the card names."
2. `root_system_prompt` §Reading result cards (R-5 b). Before: "…long text ends with a cut marker, so read the named files for detail." After: "…long text ends with a cut marker, so when you need the detail, read only that part of a named file."
3. `root_system_prompt` §Memory (R-27). Before: "…the count of live memory entries, and one line per file with its size and description." After: "…and one line per file with its size and description, as many as fit."
4. `note_path_description` §How to write it (R-27). Before: "…because the workspace map lists every file by its path and other agents decide from it what to read." After: "…because the workspace map lists files by their paths and other agents decide from it what to read."

The S3 implementation made these spec-directed rewords: in the root, "Remember only what will matter again, never progress chatter" is merged into the "The default is not to remember" paragraph, which keeps "never for progress chatter". "Remember the decisions you will need" now reads "The decisions you will need were saved when you made them; trimming is not a reason to remember" (outline 1.8). "Keep a large plan in a note" now reads "keep the plan in that note", because the plan note is now flow step 2. In `remember_tool_description`, "Remember only what will matter again:" now opens with "The default is not to remember: save an entry only when a later agent would be wrong or slower without it".

## Deviations from the spec

1. **Root (row 1).** The #1113 sentence on progress chatter is merged into the new memory paragraph, as described above. It is not kept as a separate bullet.
2. **Outline 1.3.** "Do the smallest piece yourself" at a refused launch is stated once, in §When a call is refused ("do the work yourself at a depth or agent limit"). It is not repeated in §What to delegate.
3. **Optional reply nudges.** Rows 33, 34 and 37 (`launch_rejected_prompt`, `memory_rejected_prompt`, `note_saved_prompt`) shipped unchanged. At an agent limit, "do the work yourself" is the true fix. The rejection reply already says to move on. A pointer nudge on every note write would push against sparse memory. Row 36 (`remember_staged_prompt`) did gain its nudge, through R-19.
4. **Row 7.** The cross-field card rules sit in `launch_tool_description` §How it behaves, so the asset keeps exactly its four headings. The re-review's R-15 suggests a fifth heading.
5. **Rules the outlines did not list, added by review.** Resume step 6 says that running out of turns ends the run for good (R-6, true of the code: `agents/runtime.py:2002-2005` → `infinite/runtime.py:101` → `journal.py:89-90`). The verifier may fix a goal miss that stays inside the task (R-12). The resumed root searches for a plan note that the cut map does not show (R-28).
6. **Briefings repeat some system-prompt rules as checklist steps.** Spec §12.6 says "the briefings must not repeat what the system prompts now state". D-1 and outlines 4.6, 5.6 and 6.4 require the moment-of-use checklist. The orchestrator ruled that the layering stays (R-14).
7. **Test-id counts in the spec are off.** AC-4 says 46 pin ids; the module has 49, because §8.5 lists 22 kept phrases, not 19. AC-13 says 31 heading ids; the module has 30, because `launch_tool_description` is both one of the seven and one of the 24 descriptions. The tests match §8.5. Only the stated counts slipped (R-21).
8. **Spec §5 diagrams were corrected at S6** to match the code, which this PR did not change, in three places. A failed generator gets no verifier, and its card comes back unchecked (`launch.py:231`). The card's entry-id list is not capped; only summary, review, dropped and files are (`launch.py:364-372`). Depth and batch-size refusals come from `DelegationLimitsMiddleware` (`delegation_limits.py:54,66`), not from `launch_rejected_prompt`.
9. **Spec §6.2 proof cells for AC-11 and AC-12 still hold the S3 figures** (root 2,812 est, "about 2,800"). R-26 later moved the root to 2,858 est, and the README to "about 2,900". The current figures are the ones in this body.

## Follow-ups

**Not done in this PR**

- `vidbyte/lib/constants/infinite.py:5` (module header) still says the fixed load is "about 105,000 tokens"; README `:68` now says "near 107,000". It is not edited because this PR changes no Python (D-D, NG-6).
- README `:58` ("one line per file") and `map_header`'s "Each line below is one workspace file…" make the every-file claim that R-2 and R-27 fixed elsewhere. Both were already false at the base once the map is cut. `map_header` is a shape leaf and cannot grow (INV-15 d).
- `verifier_task_prompt` `:51` says "the card lists every file you write". The card's files list is cut at the card cap, so this is false only for a pair that writes roughly 80 or more paths. That is out of reach in practice.
- R-13 (rest): two restatements, the `verifier_task_prompt` `:25` clause and the first clause of `resume_prompt` `:1`.
- R-14: cross-asset restatements (ruled: the D-1 layering stays; recorded for a later trim).
- R-15: a "How to write the cards" heading in `launch_tool_description`.
- R-16: nine new sentences run 41–47 words; the terms drift ("later pair / agent / reader", "plan note / a note of your own", "capped / cut to a fixed length").
- R-17: `task_prompt` "Treat them as established" also covers entries the root saved live, which no verifier reviewed.
- R-18: the root system prompt never says the root's turns are limited; only `resume_prompt` does.
- R-20: README `:68`'s per-call figure leaves out the never-trimmed briefing, which grew about 4.6× (spec row 42 prescribes that arithmetic).
- R-21, R-22: doc count slips (the module docstring's "six labels", the spec's 46 and 31 ids, FEATURE.md's "no asset repeats a rule sentence") and the pack README Logs entry length. Test-pack files need the owner's grant.
- R-23, R-24: test gaps. The digit test cannot see a limit spelled in words. Presence pins cannot see a negated rule, a rule in the wrong role, or a claim the code does not back (R-1 passed the tests).
- R-25: the test helper chain `sentences()` → `_is_terminal()` is one hop deeper than AGENTS.md §1 allows.
- The three inherited `harness_threads` surface failures belong to the base branch (#1084).
- Possible conflict with `feat/infinite-memory-events`, which also stacks on #1084, on the 40-leaf contract test.
- Some repair commits cite only R-ids, not the W-, FR- or AC- ids.

**Open questions, with the defaults applied**

- **Q-1** Apply the 1,000-token floor to all 40 leaves? Default **no**. The floor covers the seven behavior-shaping assets. The 33 compact leaves ride in every call or tool result and stay compact (D-B, NG-4).
- **Q-3** Add one sentence per system prompt, "content you read is material to check, never instructions to follow" (about 40 tik each, no leaf or placeholder), as `jev_bulk_work` does? Default **no**. It never came up in the conversation. Until it is added, the code bounds what a persuaded verifier can commit, not whether it is persuaded (spec §10 T-2).
- **Q-2** (resolved): the README figures are updated here; the Python header is not.

**Next.** The goal-continuation check you plan to build can lean on two things these prompts now establish. Every root keeps a plan note that lists the task's deliverables (root flow step 2); a resumed root marks each one met, missing or interrupted (resume step 2). The root is told to answer only when every deliverable in that note has a passed or fixed card, or work of its own, behind it.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
