---
slug: infinite-memory-prompts
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-16 (resumed run; first attempt stopped at a usage limit before S0 produced anything)
flags: --repo C:/Users/422mi/vidbyte-repos/vidbyte-sdk
---

# Request: Rewrite and expand the InfiniteMemoryAgent prompt family so every prompt reinforces the agent's intended behavior

This run is STACKED on an open pull request. The feature whose prompts change lives only on PR #1084 (https://github.com/cerredz/Vidbyte-SDK/pull/1084, branch `feat/infinite-memory-agent`); `main` does not contain `vidbyte/agents/infinite/` or the `infinite_memory` prompt family. The base branch of this run is therefore `feat/infinite-memory-agent`, not `main`, and the pull request this run opens targets that branch.

## A. Every user prompt in this conversation, verbatim and in order

_The pipeline was invoked by an orchestrating session that relayed the user's words. Prompts 1 and 2 were said earlier in the same conversation, about the InfiniteMemoryAgent's architecture; Prompt 3 is the invoking prompt. Section A.4 lists the user's statements from the earlier conversation that produced PR #1084; they are captured in full, verbatim, in `docs/spec/infinite-memory-agent/request.md` on the base branch, and bind this job too._

**Prompt 1** (earlier in the conversation, rejecting a set of architectural recommendations):

````
dont like these architectural recommendations, your recommendations should be small, simply features that have the goal of optimizzing how long a task/goal can run for, that is the primary goal
````

**Prompt 2** (earlier in the conversation, about the agent's architectural decisions):

````
do you see what i did with these architectural decisions, they support an agent that is going to run forever.
````

**Prompt 3** (the invoking prompt):

````
one architectural change that i want to immplement, in a subagent you can launch using the "/spec-pipeline" skill is the following: (make sure local  main is up to date), for all of the prompts assocaited with the InfiniteMemoryAgent I want you to 1) expand them and have sure each of them  are at least 1k tokens in length and 2) this is the main point, you should try to better reinforce the intended behavior of the infinite memory agent in the prompts themselves (ex: memories should be sparse and infrequent and not take up too much context, we should train main agent context window as as a scarce resource at every stage, etc). Think about the principles of the infinite memory agent at every stage in the implementation, then determine how through tweaking the prompts you can converge towards this behavior through the actual prompts themselves. kick this job off to a subagents.
````

**A.4 — The user's words from the conversation that produced PR #1084** (verbatim fragments; the full prompts are in `docs/spec/infinite-memory-agent/request.md` §A on the base branch, which the scout and the spec author must read):

````
treating the main agent's context window as somethingg that is VERY limitied
````
````
I just want to instruct it though that it shoulld ruthlessly delegate work to subagents
````
````
want thge updated  to be sparse and limited when creating them
````
````
just important memories after few/10s of compactions
````
````
I was thinking of this architecture for all types of work in general and not just coding
````
````
I want to keep all agents and all subagents minimal in terms of tools
````
````
Unattended, resumable
````
````
the verifier subagent will run after the generator and fix anything that it finds
````
````
try to keep implementation of all features avoid very simple  and elegant, dont overengineer anthing
````

## B. Handoff block and decision ledger (verbatim, if present)

none. The design record of the feature itself is `docs/spec/infinite-memory-agent/spec.md` (revision 5) on the base branch; its §6.1 invariants and §9.2 schema are the authoritative description of what the agent does.

## C. Structured conversation notes

### What this job is, in one paragraph

The InfiniteMemoryAgent (PR #1084) is a root agent that plans, delegates every piece of work to generator/verifier subagent pairs, reads back one compact result card per pair, and keeps a small guarded file workspace as memory so a run can go on for days and be resumed. Its model-facing prompts exist, are correct, and are short. This job rewrites and expands them so that the prompts themselves push each model (root, generator, verifier) toward the agent's intended behavior at every stage of a run: the context window is scarce, memory is sparse and infrequent, work is delegated with complete task cards, only cards come back, verification is real, the run is long and resumable, and the agent is for any kind of work. The seven behavior-shaping assets must each be at least 1,000 tokens; the other 33 leaves are rewritten compactly where model-facing. No Python code changes except tests. The pull request is stacked on `feat/infinite-memory-agent`.

### Key decisions (settled; the spec author treats them as given)

- **D-A. Scope of "all of the prompts associated with the InfiniteMemoryAgent"** — the `infinite_memory` prompt family only: the 40 JSON leaves of `vidbyte/prompts/prompts/infinite_memory/infinite_memory.json` and the Markdown assets in the same folder. No other prompt family changes and no BaseAgent prompt changes. *Reason:* the user named the InfiniteMemoryAgent's prompts; every other prompt family is shared by other agents.
- **D-B. The "at least 1k tokens" floor applies to the SEVEN behavior-shaping assets a model reads as instructions** — `root_system_prompt.md`, `generator_system_prompt.md`, `verifier_system_prompt.md`, the `task_prompt` leaf, the `verifier_task_prompt` leaf, the `resume_prompt` leaf, and `launch_tool_description.md`. Each must be at least 1,000 tokens by the SDK's own `TokenEstimate.count` (characters divided by four, `vidbyte/lib/util/text.py`) AND by `tiktoken` `cl100k_base` (tiktoken 0.12.0 is importable in this environment's Python 3.11; if a future environment lacks it, say so and use the chars/4 figure). Target 1,100 to 1,500 tokens so both measures clear the floor with margin. *Reason the floor is not applied to the other 33 leaves:* tool and parameter descriptions are sent inside the tool schema on every model call, and the reply strings, the quota line, the map header and the result-card template appear in every tool result or in the parent's context; making each of them 1,000 tokens would add tens of thousands of tokens to every call, which contradicts the agent's first principle (the context window is scarce) and NFR-7 of the feature spec (a card adds at most 4 x 400 tokens to its parent). Record this as assumption **A-1** and as open question **Q-1** ("apply the 1k floor to every leaf?", default no) so the user can steer later.
- **D-C. The other 33 leaves are still rewritten where they are model-facing, to carry the same principles in compact form** — tool descriptions and parameter descriptions keep the field guide's four-to-five-sentence rule (`field-guide/vidbyte-sdk/model-facing-tool-contracts.md`); the replies (`remember_saved_prompt`, `remember_staged_prompt`, `note_saved_prompt`, `entry_dropped_prompt`, `memory_rejected_prompt`, `launch_rejected_prompt`, `replayed_label`) stay one to three sentences and may add one short nudge toward the principle (for example, after a save: keep the rest in the workspace, not in memory); `quota_line`, `map_header` and `result_card` keep their exact shape and placeholders and change wording only if it reinforces a principle without growing them.
- **D-D. The leaf count stays exactly 40 and every placeholder name stays as it is. No Python code changes except tests.** If the spec author or the implementer finds a principle that genuinely cannot be carried without a new leaf or a new placeholder, that is a BLOCKED question for the orchestrator (default: carry it in an existing asset instead). *Reason:* adding or removing a placeholder forces a code change in the module that formats it; the user asked for prompt tweaks.
- **D-E. The main point: the rewritten prompts must reinforce the agent's intended behavior at every stage of a run.** The spec author writes the principle list and maps each principle to each stage. The starting list, derived from the user's words above and from the feature spec's invariants:
  - **P1** The context window is the scarce resource at every stage. The root plans, launches, reads cards and answers; it does not read large files itself, does not paste material into its own context, asks each pair for a compact summary, and keeps its own turns few. Generators keep their own context lean too (read line ranges, not whole files; write notes rather than carry content). Verifiers check with tools rather than re-reading everything.
  - **P2** Memory is sparse and infrequent. The default is NOT to remember. An entry is saved only when a later agent would be wrong or slower without it; it is one short line; it supersedes a stale entry rather than sitting beside it; a pointer to a note beats pasted content; the quota is a ceiling to stay well under, not a target to fill. Longer material goes to a note with a one-line description, appended rather than rewritten.
  - **P3** Save before it is gone, but only the few things that matter: old tool results drop out of history as the run goes on.
  - **P4** Delegate ruthlessly with complete task cards: a fresh agent cannot see the conversation, so the card must be self-contained, with done criteria a verifier can check, and name only the entries, paths and tools the pair needs.
  - **P5** Cards are the only thing that comes back: ask for exactly what you will need in the summary, never for a transcript; the summary is capped.
  - **P6** Verification is real: the verifier checks every criterion with tools, fixes directly, reviews each staged entry and drops what is not worth keeping, and ends with exactly one VERDICT line; a verdict given without checking is worthless.
  - **P7** The run is long and resumable: finished work is never redone; relaunching a finished name replays its card; the workspace and the map are the source of truth, never the conversation; a resumed root continues from the journal.
  - **P8** Any kind of work, not just coding: no repository- or code-specific rules in any prompt (feature spec INV-33).
  - **P9** Finish only when the original task's deliverables are met; before finishing, check each deliverable against the cards received and launch what is still missing.
  - The stages to map against: root planning, task-card writing, generator working, generator's final reply, verifier checking, memory staging and commit, the parent reading a card, resume, and history trimming. The spec must show, for each prompt asset, which principles it carries and in which sentences.
- **D-F. Writing standard** — plain, direct English in the voice of the existing prompt families (`vidbyte/prompts/prompts/jev_bulk_work/` and the coding-agent prompts are style references; `house-style.md` in the pipeline's references applies). Headings are fine in the `.md` assets. No examples with concrete domain content that would bias the agent toward coding (P8). Length must come from genuinely useful instruction (what to do, what not to do, why, how to decide edge cases), never from repetition or filler; a reviewer should be able to delete no sentence without losing a rule.
- **D-G. Tests (S2 writes them from the spec)** — a token-floor test over the seven assets using `TokenEstimate.count` (and tiktoken when importable, skipped otherwise); the existing 40-leaf and placeholder tests must keep passing; a test that the rendered root, generator and verifier system prompts and the three briefing templates contain the key rules (assert on distinctive phrases the spec fixes, not on whole text); a test that every placeholder the code formats is still present in its leaf (format each template with dummy values and assert no KeyError). Existing tests in the pack that assert on exact prompt text may need updating; the implementer may not touch tests, so S2 must anticipate this by reading which existing tests pin prompt text and updating them in S2.

### Rejected alternatives

- Applying the 1k-token floor to every one of the 40 leaves — rejected because the 33 compact leaves ride along on every model call or tool result (see D-B); carried as Q-1 with default no.
- Adding new leaves or placeholders to carry a principle (for example a dedicated "memory policy" leaf) — rejected because it forces code changes; carried as a BLOCKED question only if a principle truly cannot live in an existing asset (D-D).
- Changing Python code in `vidbyte/agents/infinite/` to enforce behavior (new limits, new checks) — rejected: the user asked that the behavior converge "through the actual prompts themselves"; architecture stays as PR #1084 built it.
- Large architectural recommendations of any kind — the user rejected them in Prompt 1 ("your recommendations should be small, simply features that have the goal of optimizzing how long a task/goal can run for").

### Constraints and assumptions

- Base branch is `feat/infinite-memory-agent` (PR #1084), base commit `7efceb5504b0d2ac64a3b5874ada635a47ac35cf` (includes the user's review-fix PR #1113). The PR of this run is opened with `--base feat/infinite-memory-agent`. Never push to `feat/infinite-memory-agent`, never rebase or amend it, never touch `main`.
- The user is still fixing PR #1084 in a separate checkout, so the base branch may gain commits during the run; the drift check and any rebase are against `origin/feat/infinite-memory-agent`.
- A sibling pipeline runs at the same time in the worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-events` on branch `feat/infinite-memory-events`, also stacked on `feat/infinite-memory-agent`. Nothing in this run touches that worktree or branch. Every change of this run stays inside the `infinite_memory` prompt family and its tests so the two stacked PRs do not conflict; the PR body lists "possible conflict with feat/infinite-memory-events on the 40-leaf test" under follow-ups.
- The leaf count is exactly 40 (contract test `test_prompt_family_has_exactly_the_forty_documented_leaves` in `tests/features/infinite_memory_agent/test_infinite_memory_contract.py`); every placeholder name the code formats is unchanged.
- A-1 (see D-B): the 1k floor applies to the seven behavior-shaping assets, not to the 33 compact leaves.
- Token measurement: `TokenEstimate.count` in `vidbyte/lib/util/text.py` (characters divided by four) is the SDK's own measure; tiktoken `cl100k_base` is the independent check.
- Gates (from PR #1084's verification table): the feature pack `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` (111 passed on the base branch at the time of the brief); `python lint/run.py` must end `SDK-LINT: PASS` with no baseline count rising; `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off`; `python scripts/generate-sdk-public-api.py --check` (no export change expected); full gate `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` then `python scripts/run_ci.py --stage package` without PYTHONPATH. GitHub Actions are disabled repo-wide, so the local gate is the gate of record and `gh pr checks` reports none. One pre-existing flaky test on Windows: `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`; a failure there alone is not a red gate, rerun it.
- Lint rule S025 requires model-facing sentences to live in prompt assets, not in code.
- Platform: Windows 11, Git Bash, Python 3.11. Long quoted heredocs in the Bash tool can fail with "unexpected EOF": write helper scripts to a file and run them by path. `git worktree remove` fails with "Permission denied" if a shell's cwd is inside the worktree.

### Clarifications and answers

- Q: Does "all of the prompts" include prompt families shared with other agents? — A (settled by the orchestrating session, D-A): no; the `infinite_memory` family only.
- Q: Does "each of them at least 1k tokens" mean every leaf including tool-result strings? — A (settled, D-B, carried as A-1/Q-1): the seven behavior-shaping assets; the compact leaves stay compact because they ride along on every call.
- Q: May code change to help the prompts? — A (settled, D-D): no Python changes except tests.

### Terminology

- **Root** — the InfiniteMemoryAgent itself: the model that plans, launches pairs, reads cards, and answers; its system prompt is `root_system_prompt.md` formatted with `{max_parallel}` and `{max_depth}`.
- **Pair** — one generator agent followed by one verifier agent, launched for one task card by the `launch_subagent` tool.
- **Generator** — the subagent that does the task; its system prompt is `generator_system_prompt.md`; its first message is the `task_prompt` leaf.
- **Verifier** — the subagent that checks the generator's work with tools, fixes what it finds, reviews staged memory entries, and ends with one `VERDICT:` line; its system prompt is `verifier_system_prompt.md`; its first message is the `verifier_task_prompt` leaf.
- **Card / result card** — the only thing that returns to the parent after a pair: the rendered `result_card` leaf, each free-text field capped by `TokenEstimate.cut`.
- **Task card** — the item a parent passes to `launch_subagent`: name, goal, done criteria, context entry ids, paths, tools, generator prompt, verifier prompt (the `launch_*_description` leaves describe its fields).
- **Memory / workspace** — the guarded file workspace: numbered entries (`remember`, with `supersedes`), notes (`write_note`), a map rendered with `map_header` at the top of every agent's context, and a journal that makes a run resumable.
- **Staged vs committed** — a generator's `remember` stages an entry; the verifier reviews staged entries and `drop_entry` removes the ones not worth keeping; the rest commit at the end of the pair.
- **Leaf** — one key of `infinite_memory.json`, read through `Prompts().get(Prompt.INFINITE_MEMORY_*)`.
- **Seven assets** — the behavior-shaping prompts under the 1k floor (D-B).
- **Principles P1 to P9** — D-E's list.

### Implementation hints

- Prompt family: `vidbyte/prompts/prompts/infinite_memory/infinite_memory.json` (40 leaves; the folder also holds 40 `.md` files, one per leaf by name, so the scout must establish exactly how the JSON references the Markdown assets and which leaves are inline strings, if any). Enum keys: 40 `Prompt.INFINITE_MEMORY_*` members in `vidbyte/lib/enums/prompts.py`. Loaded through `vidbyte/prompts/catalog.py` (`Prompts().get(...)`), which validates enum and asset sync.
- Where each leaf is used: `vidbyte/agents/infinite/agent.py` (root system prompt formatted with `{max_parallel}` and `{max_depth}`; the resume prompt), `launch.py` (task_prompt, verifier_task_prompt, result_card, replayed_label, the launch tool description and the `launch_*` parameter descriptions, the finished-pair lines), `memory.py` (remember / write_note / edit_file / drop_entry tool and parameter descriptions, the saved / staged / dropped / rejected replies, quota_line), `workspace.py` (map_header), `runtime.py`. Every `{placeholder}` these modules format must keep its exact name.
- READMEs that describe the family and may need their wording kept in sync: `vidbyte/agents/infinite/README.md`, `vidbyte/prompts/README.md`, `vidbyte/prompts/prompts/infinite_memory/` (check for a README there).
- Design record: `docs/spec/infinite-memory-agent/spec.md` r5 (read §1 Goal; §6.1 invariants, in particular INV-4, INV-5, INV-6, INV-12, INV-14, INV-15, INV-17, INV-18, INV-23, INV-28, INV-32, INV-33; §9.2 the launch schema), `docs/spec/infinite-memory-agent/request.md` (the user's original words), `docs/spec/infinite-memory-agent/pr-body.md`. These three files, and this run's own `docs/spec/infinite-memory-prompts/`, are the only files under `docs/` any agent of this run may read; the AGENTS.md "docs/ is opaque" rule stands for everything else.
- Repo rules that bind prompts: the field guide `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/` (AGENTS.md points to it): `model-facing-tool-contracts.md` (parameter descriptions are four to five general sentences, no examples), `prompt-families.md`, `comment-format.md`; lint rule S025 (model-facing sentences in prompt assets, not code).
- Style references for voice: `vidbyte/prompts/prompts/jev_bulk_work/` and the coding-agent prompt family.
- Existing tests that may pin exact prompt text live in `tests/features/infinite_memory_agent/` (eight files plus `FEATURE.md`, `README.md`, `infinite_memory_fixtures.py`); S2 must find and update the ones that would break under rewritten prompts, since the implementer may not touch tests.
- Baseline token counts of the seven assets before this job (chars/4 and tiktoken cl100k_base) are recorded in `pipeline.md`; the spec author should carry them into the spec as the "before" column.

### Open questions

- **Q-1** — Apply the 1k-token floor to every one of the 40 leaves instead of the seven behavior-shaping assets? Default: **no** (A-1, D-B). Only the user can flip this.
- **Q-2** — Should the two READMEs (`vidbyte/agents/infinite/README.md`, `vidbyte/prompts/README.md`) be updated where they quote or summarize the prompts? Default: yes where a sentence there would become false; otherwise no.
- Anything else the spec author cannot settle from the code or the three allowed design-record files becomes a `Q-n` with a stated default.

## D. Weighted words

- "for all of the prompts assocaited with the InfiniteMemoryAgent" — Prompt 3 (scoped by D-A to the `infinite_memory` family).
- "have sure each of them  are at least 1k tokens in length" — Prompt 3 (scoped by D-B to the seven behavior-shaping assets; A-1/Q-1).
- "this is the main point, you should try to better reinforce the intended behavior of the infinite memory agent in the prompts themselves" — Prompt 3.
- "memories should be sparse and infrequent and not take up too much context" — Prompt 3.
- "we should train main agent context window as as a scarce resource at every stage" — Prompt 3.
- "Think about the principles of the infinite memory agent at every stage in the implementation" — Prompt 3.
- "converge towards this behavior through the actual prompts themselves" — Prompt 3.
- "your recommendations should be small, simply features that have the goal of optimizzing how long a task/goal can run for, that is the primary goal" — Prompt 1.
- "they support an agent that is going to run forever" — Prompt 2.
- "treating the main agent's context window as somethingg that is VERY limitied" — A.4.
- "it shoulld ruthlessly delegate work to subagents" — A.4.
- "want thge updated  to be sparse and limited when creating them" — A.4.
- "just important memories after few/10s of compactions" — A.4.
- "for all types of work in general and not just coding" — A.4.
- "keep all agents and all subagents minimal in terms of tools" — A.4.
- "Unattended, resumable" — A.4.
- "the verifier subagent will run after the generator and fix anything that it finds" — A.4.
- "try to keep implementation of all features avoid very simple  and elegant, dont overengineer anthing" — A.4.
