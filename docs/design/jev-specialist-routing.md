# Design Doc: Jev Specialist Routing

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-22
**Last Updated:** 2026-09-22

## Overview

Allow `JevAgentSettings` to hold a validated catalog of specialist agent templates. At the start of each run, Jev receives only the current prompt and the specialists' IDs and descriptions, selects the best fit or `no_suitable_agent`, and the selected specialist handles the entire task. A weak match, explicit no-match, missing decision credentials, or a decision failure uses the existing general JevAgent model loop.

## Goals & Non-Goals

### Goals

- Add a named specialist-matching capability to Jev settings without changing `JevAgent`'s one-settings-object constructor.
- Validate specialist metadata, catalog size, option IDs, decision threshold, and agent template types before a run.
- Ask one explicit Choice question at run start and use one selected specialist for the whole task.
- Honor the selected specialist's own prompt, provider, model, tools, permissions, middleware, and loop settings through an isolated fork.
- Apply a minimum option-probability threshold and use the general agent on weak matches.

### Non-Goals

- Mid-run handoffs, multiple specialists, history-based matching, specialist-to-specialist delegation, YAML catalog loading, and custom caller-authored Jev questions.
- Automatic retry on the general agent after a specialist has started and may have caused side effects.

## Background & Context

`JevAgentSettings` is the closed configuration surface; `JevRuntime` currently delegates to the standard linear loop without calling Jev. `DecisionModelRunner` provides TypeSafe Choice decisions, and the Jev records already validate option uniqueness, option count, state size, and probability distributions. `BaseAgent` builds a run-local runtime with the configured settings and owns final reply, trace, session, usage, and speed handling.

## Requirements

### Functional Requirements

1. `JevAgentSettings(agents=())` preserves current behavior and does not call Jev.
2. Each `JevSpecialist` has a unique stable ID, a non-blank description, and a `BaseAgent` template. The template is forked for the selected run.
3. Jev receives the current prompt as decision state and one fixed question: “Which registered specialist best fits this task?” Options contain each specialist ID and a reserved `no_suitable_agent`; option descriptions state the specialist's scope. Instructions direct Jev to choose the strongest direct fit and choose no-match if none clearly applies.
4. A selected specialist runs only when its normalized option probability meets the configured minimum. No-match, a weak selection, or decision unavailability uses the general agent.
5. Once specialist execution starts, its error propagates. The system does not replay the task through the general agent.
6. Routing metadata records the selected specialist or fallback reason without including raw prompt text or secrets.

### Non-Functional Requirements

- Validate against TypeSafe limits: at most 255 Choice options (including no-match), unique labels, non-blank bounded labels and descriptions, and the existing state character limit. The token limit remains ultimately enforced by TypeSafe because the SDK has no tokenizer for the decision model.
- Preserve per-run isolation by forking the selected template and closing its MCP resources after execution.
- Record TypeSafe decision usage once in the parent JevAgent tracker; expose specialist usage separately in the run metadata.

## High-Level Design

Add immutable `JevSpecialist` metadata and an `agents` catalog plus a probability threshold to `JevAgentSettings`. `JevRuntime` skips matching when the catalog is empty. Otherwise it builds one typed `JevDecisionRequest` from the normalized prompt and fixed Choice question, invokes `DecisionModelRunner`, and checks the returned choice and its probability against the threshold.

For a qualified specialist selection, the runtime forks the specialist template, calls its ordinary `generate_reply()` with the original prompt, input context, and conversation history, then returns that output as the parent runtime's `AgentResult`. The parent's ordinary `BaseAgent` flow therefore still owns the returned message, history, and session boundary. No catalog agent is mutated across calls.

## Detailed Design

### 6.1 Specialist contract and settings

**File(s):** `vidbyte/agents/jev/specialists.py`, `vidbyte/agents/jev/settings.py`
**Type:** New file; modified file

#### What it does

`JevSpecialist` holds an ID, description, and concrete `BaseAgent` template. Settings normalize `agents` to an immutable tuple and reject invalid, duplicate, or over-limit catalogs and invalid threshold values.

#### Interface / API

```python
JevAgentSettings(..., agents=(JevSpecialist(id="research", description="Researches with sources", agent=research_agent),), specialist_match_threshold=0.6)
```

#### Logic / Algorithm

1. Require IDs to be non-blank and within TypeSafe's option-name bound; require unique IDs and reserve `no_suitable_agent`.
2. Require descriptions to be non-blank strings within the shared state bound.
3. Require each template to be a `BaseAgent` and reject nested `JevAgent` templates.
4. Permit no more than 254 specialists, leaving one Choice option for no-match.
5. Require a finite threshold from 0 through 1 and normalize the catalog to a tuple.

#### Edge Cases & Error Handling

Invalid configuration raises `ConfigurationError` at construction. An empty catalog is valid and disables routing.

### 6.2 Pre-run routing and execution

**File(s):** `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified files

#### What it does

Creates the one fixed Choice question, applies selection policy, and delegates the full run to one isolated specialist when qualified.

#### Interface / API

The routing question, its name, the no-match option, and the question wording are internal constants; callers configure only the catalog and threshold.

#### Logic / Algorithm

1. If there are no specialists, invoke the inherited linear runtime directly.
2. Build a `JevDecisionRequest` with current prompt state and one Choice question. Each specialist option description contains the supplied specialist description; `no_suitable_agent` has a fixed explanation.
3. On a Jev decision failure or missing answer, record a safe fallback reason and invoke the inherited runtime.
4. If Jev chooses no-match or a specialist probability below threshold, record the reason and invoke the inherited runtime.
5. Fork the selected template, call its `generate_reply()` with the prompt and user-visible context/history, and always close the fork's MCP resources.
6. Return an `AgentResult` containing the specialist output and bounded routing metadata. Preserve the specialist's structured result where available.

#### Edge Cases & Error Handling

Decision failure is fail-open to the general agent. Specialist execution failure propagates after cleanup; it does not replay potentially side-effecting work. Oversized state fails the Jev request and follows the decision-failure fallback.

## Data Model Changes

### 7.1 `JevSpecialist`

**Change type:** New

Frozen, slotted in-memory record containing `id: str`, `description: str`, and `agent: BaseAgent`. No persistence or migration.

## API Changes

### 8.1 `JevAgentSettings`

**Change type:** Modified

Add `agents: Sequence[JevSpecialist] = ()` and `specialist_match_threshold: float = 0.6`. The constructor remains `JevAgent(settings)`.

## File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-specialist-routing.md` | Record agreed scope and behavior |
| CREATE | `vidbyte/agents/jev/specialists.py` | Strict specialist catalog record and limits |
| MODIFY | `vidbyte/agents/jev/settings.py` | Add and validate catalog and threshold |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Perform one pre-run decision and specialist dispatch |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Export the public specialist descriptor |
| MODIFY | `vidbyte/agents/jev/README.md` | Document matching and fallback behavior |
| MODIFY | `tests/test_jev_agent.py` | Verify strict catalog validation and routing outcomes without network calls |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export the descriptor |
| MODIFY | `vidbyte/__init__.py` | Re-export the descriptor at the package root |
| MODIFY | `skills/jev-agent/SKILL.md` | Document the supported named capability and invariants |
| MODIFY | `lint/baseline.json` | Ratchet the verified intent-comment improvement |

## Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `DecisionModelRunner` / TypeSafe System One | Configured TypeSafe endpoint | Select one specialist before task execution | Network/key failure falls back to the general loop |

## Rollout & Deployment

- No feature flag, migration, or rollout sequencing is needed; an empty default catalog preserves current behavior.
- Rollback by removing specialist settings or reverting the feature commit.

## Open Questions

- N/A - the initial matching timing, prompt inputs, fallback behavior, and whole-task dispatch are specified by the user.

## Alternatives Considered

### Alternative 1: Route only inside the existing runtime loop

- What: Use Jev's selected ID to mutate the general agent's prompt/model/tools.
- Why rejected: `BaseAgent` settings and histories are shared mutable state; this risks cross-run leakage and does not preserve a specialist's complete execution configuration.

### Alternative 2: Pass arbitrary questions or routing callbacks

- What: Let callers define Jev question lists and dispatch policy.
- Why rejected: This conflicts with JevAgent's opinionated capability contract and makes valid option schemas and outcome handling caller-dependent.
