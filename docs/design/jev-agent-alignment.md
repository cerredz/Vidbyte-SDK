# JevAgent self-alignment

## What and why

A `JevAgent` runs every request against one fixed system prompt. When the prompt has no output standard, no method, or no rule for declining a request, the model fills the gap by guessing, and nobody learns which part of the prompt was missing.

This change adds an opt-in capability, `JevAgentSettings(self_align=True)`. Before each run, Jev checks the agent's system prompt against the incoming request with 21 yes/no questions written with `skills/asking-jev-questions/SKILL.md`. Each "no" becomes a gap tied to one named prompt section. A small editor agent, `JevAgentAlignment`, then fixes the gaps it is allowed to fix by calling one tool, `edit_system_prompt_section`. Jev checks the edits, and the main agent runs with the edited prompt.

Only the system prompt of the main agent's current run changes. `JevAgentSettings`, `JevAgent.system_prompt`, the editor's own prompt, and later runs are never modified.

## How it works

1. **Settings.** `JevAgentSettings.self_align: bool = False`. When it is true, `JevAgent` builds one `JevAgentAlignment` and passes it to each run-local `JevRuntime` through `_runtime_extension_kwargs()`.
2. **Assess (Jev).** `JevAgentAlignment.align(request, system_prompt, tools)` asks the questions in `alignment/questions.py`. Every question is a `noul` with `true`/`false` criteria. The positive phrasing means `true` always means aligned.
   - *Static* questions (does the prompt have a role, scope, output, or exceptions section) depend only on the prompt and tool list. They are asked with state `{system_prompt, tools}` and cached by a SHA-256 of that state, so a warm agent skips them.
   - *Dynamic* questions (does the request fit the scope, are its terms and output covered) use state `{system_prompt, request, tools}`.
   - On a cache miss, the two requests run concurrently. Questions that cannot apply, such as tool guidance for an agent with no tools, are not asked.
3. **Gate.** Three fit questions (task in scope, within boundaries, role kept) never cause edits. If any is "no", the request is out of scope and the prompt is left alone, so an off-topic request cannot widen the agent's scope.
4. **Route gaps.** Every other "no" becomes a `JevAlignmentGap` with a section and an owner.
   - `AGENT` sections (TOOLS, METHOD, OUTPUT, EXCEPTIONS, PRIORITIES, GLOSSARY) go to the editor.
   - `OWNER` sections (ROLE, SCOPE, BOUNDARIES, AUDIENCE, KNOWLEDGE, PERMISSIONS) become `owner_actions`: plain sentences telling the developer what to add. The agent never edits these.
5. **Edit.** If there are agent gaps, the editor runs its ordinary loop with one tool. A context variable binds the tool to this call's `JevPromptDraft`. Edits are additive only: content goes under a `## <Section>` heading, which is created if missing. Owner text is never replaced or deleted. The tool rejects locked sections, fixes that don't cite an open gap for that section, blank content, and content over the size caps. The editor's instructions are a prompt asset (`jev_alignment.editor_system_prompt`).
6. **Verify (Jev).** One more request re-asks every fixed gap question plus the consistency question against the edited prompt.
   - An edited section is kept only if at least one of its cited questions now passes.
   - If the consistency question passed before and now fails, every edit is reverted.
7. **Run.** `JevRuntime.arun` swaps the original prompt prefix in `context.system_prompt` for the edited prompt. It also sets the run-local runtime's `system_prompt`, so context-window hooks see the same prompt. It then runs the inherited loop and attaches the `JevAlignmentResult` as `metadata["jev_alignment"]`.

**Failure policy.** Missing credentials, provider errors, and editor errors all return the original prompt with status `UNAVAILABLE`, and the run continues. If verification fails, every edit is dropped. If the caller supplied its own context system prompt, the capability is skipped without any Jev call.

**Result.** `JevAlignmentResult` reports:
- `status` (`ALIGNED`, `NO_GAPS`, `OUT_OF_SCOPE`, `EDITS_REJECTED`, `UNAVAILABLE`, `SKIPPED`);
- the prompt that ran;
- gaps, kept and reverted edits, and owner actions;
- the probability of each answer;
- summed `JevUsage`.

The editor's generative tokens stay on `JevAgentAlignment.get_usage()`, not on the main agent's usage, so nothing is double counted.

## Files

- New `vidbyte/agents/jev/alignment/`: `__init__.py`, `questions.py`, `draft.py`, `tool.py`, `result.py`, `agent.py`.
- New prompt family `vidbyte/prompts/prompts/jev_alignment/` and a `Prompt.JEV_ALIGNMENT_EDITOR_SYSTEM_PROMPT` enum member.
- Modify `vidbyte/agents/jev/settings.py` (`self_align`), `agent.py` (builds the alignment), `runtime.py` (align, then run), and the `jev`/`agents`/root exports.
- New `tests/test_jev_alignment.py`; add it to `scripts/test-jev-agent-scaffold.py`.
- Update `skills/jev-agent/SKILL.md` with the capability and its invariants.

## Risks and open questions

- Draft PR #443 (preflight) also overrides `JevRuntime.arun`. Whichever lands second must run alignment after preflight's clarification check.
- A prompt with an unheaded section that the model judged present but not covering the request gets a new `## Section` heading, which can repeat a topic.
- Thresholds are `JEV_NOUL_YES_THRESHOLD` (0.5) starting points. They have not been tuned on a labeled set.
- With alignment on, each run adds one or two Jev calls. When gaps exist, it also adds one short generative call and one more Jev call.

## Verification

- `tests/test_jev_alignment.py` covers:
  - settings off (no calls);
  - question set shape;
  - gates block edits;
  - owner gaps are reported, not edited;
  - an agent gap is edited, verified, and used for the main run only;
  - a failed verification reverts;
  - the tool rejects locked sections;
  - Jev and the editor being unavailable fail open;
  - the static cache avoids a second static call;
  - a caller context prompt is skipped.
- `python scripts/test-jev-agent-scaffold.py`, `python lint/run.py`, `python scripts/run_ci.py --stage source`, `python scripts/run_ci.py`.
