# Jev profile coordinator

## Folder Description / Intent

This package owns the opinionated `Jev` coordinator. Developers give it one or more `JevAgent` profiles; the coordinator runs preflight, selects the best profile when there are multiple candidates, applies that profile's reusable settings for one run, and then restores its own configuration. `Jev` retains the normal BaseAgent conversation, trace, usage, and session lifecycle.

This folder is for named Jev capabilities and their execution boundary. It is not the TypeSafe wire adapter or a general-purpose arbitrary decision framework; provider serialization belongs in `vidbyte/providers/typesafe.py`, fixed question contracts belong in `vidbyte/lib/jev/`, and ordinary BaseAgent execution belongs in `vidbyte/agents/base.py` and its runtime.

## Non-Goals

- Do not add caller-defined question lists, arbitrary decision callbacks, or a generic `decisions` collection; keep the profile-matching question fixed and internal.
- Do not add a no-match option or confidence threshold; the coordinator selects the top-probability profile.
- Do not execute the selected profile as a child agent; apply its supported execution configuration to the main Jev instance.
- Do not copy a profile's conversation history, trackers, active session, or live MCP handles onto Jev.
- Do not silently select another profile after TypeSafe or the selected model fails.
- Do not put provider request/response JSON in this folder; `vidbyte/providers/typesafe.py` owns the wire contract.
- Do not put fixed preflight question text here; those typed questions live in `vidbyte/lib/jev/preflight/`.
- Do not add profile selection to `JevRuntime`; it runs only after Jev selected the profile and BaseAgent resolved its runner.

## File Index

- `__init__.py` - Exposes the public coordinator, profile, runtime settings, and response records. Open it when changing Jev imports; keep its exports aligned with `vidbyte/agents/__init__.py` and `vidbyte/__init__.py`.
- `agent.py` - Owns the public `Jev` coordinator, run serialization, preflight-before-selection sequence, and temporary profile configuration scope. Open this first when the profile needs additional BaseAgent settings copied or restored.
- `settings.py` - Defines `JevAgentSettings` (the profile array only) and `JevRuntimeSettings` (decision, preflight, and tool-selector controls). Open this when changing validated caller configuration.
- `specialists.py` - Implements `JevAgentRouter`, the TypeSafe Choice request, and stable maximum-probability selection. Open this when revising the profile-fit question or ranking behavior.
- `prompts.py` - Loads packaged Jev Markdown and validates the structured brief and option criteria. Open this when adding a prompt key or changing prompt asset structure.
- `response.py` - Is the sole writer of `JevAgentResponse`, including the selected profile and full probability ranking. Open this when adding observable feature output.
- `runtime.py` - Enforces the precomputed preflight result and preserves the tool-selector/linear-loop behavior. Open this when changing runtime sequencing after profile application.
- `gate/` - Owns the fixed-question preflight gate and generative clarification writer. Open this when changing clarity or preset behavior.
- `preflight.py` - Contains `JevPreflightTools`, the per-run tool selector. Open this when changing tool-selection behavior; keep its threshold in `JevRuntimeSettings`.

## Public API

```python
from vidbyte import BaseAgent, Jev, JevAgent, JevAgentSettings, JevRuntimeSettings

research = JevAgent(
    title="Research",
    description="Finds and summarizes source-backed information.",
    metadata={"team": "research"},
    agent=BaseAgent(
        name="research-model",
        system_prompt="Research carefully and cite sources.",
        provider="openai",
        model_name="gpt-4.1",
    ),
)

agent = Jev(JevAgentSettings(agents=(research,)))
reply = await agent.arun("Find sources about the SDK.")
```

With one profile Jev makes no profile-selection call. With multiple profiles, it sends one Choice question using the current request and each profile's title, description, and metadata, then selects the option with the highest probability. Exact ties preserve input order. The ranking is exposed as `agent.response.selection`; probabilities are relative TypeSafe outputs, not guarantees of correctness. Profile metadata is sent to TypeSafe and must not contain secrets.

```python
selection = agent.response.selection
if selection is not None:
    print(f"Selected {selection.title} with probability {selection.probability:.0%}")
    print(selection.ranked_agents)
```

Use `JevRuntimeSettings(preflight=(JevPreflightPreset.CLARITY,))` to enable existing preflight behavior, or `JevRuntimeSettings(preflight=(JevPreflightPreset.TOOL_SELECTOR,), tool_selector_threshold=0.2)` to select tools. The clarity writer uses the first configured profile's generative model because preflight runs before profile selection. An unavailable clarity check keeps existing fail-open behavior; a multi-profile routing error is surfaced rather than choosing arbitrarily.

## Logs

- 2026-09-26 - Replaced specialist forks with profile settings temporarily applied to the coordinator - preserves the requested single-main-agent execution model and restores settings after each run.
