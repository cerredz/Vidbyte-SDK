# Design Doc: JevAgent prompt refinement preflight

**Status:** Draft
**Created:** 2026-10-01

## What and why

The clarity preflight asks Jev 14 yes/no questions about the user's request. When the request fails, `JevClarificationAgent` asks the user to fill the gaps. When it passes, every per-check probability is recorded on `JevAgent.response` and then ignored, even though a passing request can still score 0.3 on constraints or completion.

This change adds a `JevPreflightPreset.REFINE` flag. When it is enabled and the clarity preset passes, the gate routes the user's request to `JevRefinementAgent`, a separate generative agent. That agent reads the request together with Jev's answer to every clarity check and returns an improved prompt. The main agent (or the chosen specialist) then reads the improved prompt instead of the raw request. The agent's behavior, including a checklist of every way it may improve a prompt and the rule that it never invents facts, lives in its system prompt.

## How it works

```
JevRuntime.arun(message)
  -> JevPreflightGate.pass_(message)
       one Jev request (clarity questions, specialist question)
       match outcome:
         CLARITY unavailable          -> fail open, prompt = message
         CLARITY failed               -> JevClarificationAgent, run stops   (unchanged)
         CLARITY passed + REFINE on   -> JevRefinementAgent.refine(message, outcome) -> gate.prompt
  -> specialist / tool selector / main loop read gate.prompt
  -> JevRunState.begin(message)       (done checks keep judging the user's own words)
```

- **Setting.** `JevRuntimeSettings(preflight=(JevPreflightPreset.CLARITY, JevPreflightPreset.REFINE))`. REFINE has no fixed questions (like TOOL_SELECTOR), so it adds nothing to the combined Jev request. It consumes the clarity result, so `JevPresets.normalize` rejects REFINE without CLARITY with a `ConfigurationError` at construction.
- **Agent.** `JevRefinementAgent(BaseAgent)` in `vidbyte/agents/jev/gate/refinement.py`, next to `JevClarificationAgent` because it is the step the clarity case triggers. It cannot implement the `JevPreflight` contract in `vidbyte/agents/jev/preflight.py`, which returns a tool catalog. Like the clarifier, it reuses the JevAgent's generative model and key, has a fixed prompt, and returns a structured reply. Its logic is split into small methods: `refine` (orchestration), `reset` (clears history and the context window), `context` (builds the per-call input), `signal` (renders one check), and `accept` (turns the reply into a record or None).
- **Context window.** The agent owns one `ContextManager` (`window`), passed to `BaseAgent` as its `context_manager`, so the runtime renders it on every iteration. Its reasoning tools write into the same manager. Each `refine` call clears the window's registry and the agent's history, so no earlier request leaks into a later one. The clarity signal arrives as a per-call `TextContextItem` titled "Clarity of the request", listing every check weakest first with Jev's P(yes) and, for checks below `JEV_REFINEMENT_CLEAR_THRESHOLD`, the check's existing `gap` sentence.
- **Tools.** Four existing deep chain-of-thought tools from `vidbyte/tools/builtins/cot_events.py`, all `SAFE` and all bound to `window`:
  - `assumption_check`: record any detail it is tempted to add and decide whether the request supports it;
  - `decision`: choose which improvements to apply;
  - `uncertainty`: check progress;
  - `backtrack`: undo a change that drifted from the request.
  No new tool code is written.
- **Limits.** `JEV_REFINEMENT_MAX_ITERATIONS = 25` and `JEV_REFINEMENT_MAX_TOKENS = 100_000`, matching the clarifier.
- **Output.** `JevRefinementPayload`, with three fields:
  - `prompt`: the full improved prompt;
  - `changes`: what was improved;
  - `unresolved`: gaps it could not fill without inventing facts.
  `JevRefinement` is the frozen record, and `JevAgentResponse.refinement` exposes it.
- **Prompt.** `vidbyte/prompts/prompts/jev_refinement/system_prompt.md` with Identity, Goal, Guidelines (the full improvement checklist), Instructions, Input, Environment, and Output sections. Its key is `Prompt.JEV_REFINEMENT_SYSTEM_PROMPT`.

## Fail-open behavior

| Situation | Result |
|---|---|
| REFINE disabled | No refinement agent is built; behavior is unchanged. |
| Jev unavailable or CLARITY missing an answer | The preset is unavailable, so no refinement runs and the main agent reads the original message. |
| Refiner raises, returns no matching structure, or returns a blank prompt | `refine` returns None; the main agent reads the original message and `response.refinement` stays None. |

## Files

| File | Change |
|---|---|
| `vidbyte/lib/enums/jev.py` | `JevPreflightPreset.REFINE` |
| `vidbyte/lib/enums/prompts.py` | `Prompt.JEV_REFINEMENT_SYSTEM_PROMPT` |
| `vidbyte/lib/constants/jev.py` | Refinement limits and clear threshold |
| `vidbyte/lib/dataclasses/jev.py` | `JevRefinementPayload`, `JevRefinement`, `JevAgentResponse.refinement` |
| `vidbyte/lib/jev/presets.py` | REFINE requires CLARITY |
| `vidbyte/prompts/prompts/jev_refinement/` | The prompt and its manifest |
| `vidbyte/prompts/README.md` | Catalog row and description |
| `vidbyte/agents/jev/gate/refinement.py` | New `JevRefinementAgent` |
| `vidbyte/agents/jev/gate/gate.py`, `gate/__init__.py` | Build the agent, the new match case, `prompt` |
| `vidbyte/agents/jev/response.py` | `refined()` |
| `vidbyte/agents/jev/runtime.py` | Read `preflight.prompt` |
| `vidbyte/agents/jev/__init__.py`, `vidbyte/__init__.py` | Export `JevRefinement` |
| `vidbyte/agents/jev/README.md`, `skills/jev-agent/SKILL.md`, `AGENTS.md` | Document the flag and its files |
| `tests/test_jev_preflight.py` | Tests below |

## Risks and open questions

- **Drift.** A rewrite can change what the user asked for. The prompt forbids invented facts and requires pasted material to stay verbatim. Done checks keep reading the original message, so a refinement cannot add requirements that would send the main agent back to work. A Jev fidelity check ("does `improved` ask for the same work as `request`?") is a follow-up, not part of this change.
- **Cost.** One extra generative call per refined run, on the critical path. Skipping refinement when every check is already clear is a follow-up.
- **History.** `BaseAgent` history keeps the user's original message; only the model-visible prompt for this run changes.

## Verification

- New tests in `tests/test_jev_preflight.py`:
  - REFINE without CLARITY is rejected;
  - the agent's limits, schema, tools, and shared context manager;
  - the signal is rendered weakest first;
  - a passing request reaches the main agent as the refined prompt, and `response.refinement` is set;
  - refiner failure, a blank prompt, and a failing clarity result all fall back to the original;
  - REFINE disabled builds no agent;
  - the refiner sees only the current request.
- Gates: `python lint/run.py`, `python scripts/run_ci.py --stage source`, `python scripts/run_ci.py`.
