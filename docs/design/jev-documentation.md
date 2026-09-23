# JevAgent documentation lookup

## What and why

A generative model's knowledge of libraries, SDKs, APIs, and hosted platforms goes out of date, and the model does not know when it is stale, so it will not look anything up by itself. This change adds one setting to `JevAgentSettings`:

```python
JevAgentSettings(..., documentation="exa")   # or "tavily", "brave", "parallel"; None (default) = off
```

The one value both turns the capability on and picks the web search provider. Nothing else can be configured: the questions, the threshold, the link cap, and the search agent's prompt are fixed inside the package, as the owner asked.

When it is on, each run does this before the main loop:

1. **Jev decides.** One Jev request asks ten fixed `noul` questions over `{request}`. Each one recognizes a visible sign that the work depends on an outside interface: the general question, an error from someone else's code, package code, a tool's config file, CLI commands, calls to someone else's web API, integration work, a version change, a request for an exact name, and a fact only the vendor documents. The questions follow `skills/asking-jev-questions/SKILL.md` (definition, markers, boundary, focus, question). None of them needs Jev to recognize a library's name.
2. **Code combines.** The signs are independent, so the highest P(true) decides: `needs_documentation = max(P) >= 0.7`. A mean would bury one strong sign, such as a pasted `node_modules` stack trace.
3. **A search subagent finds links.** If documentation is needed, `JevDocumentation` (a `BaseAgent` subclass, the same shape as `JevAgentAlignment` in PR #445) runs its own short loop with one tool: the priced search tool for the chosen provider, bound to a real client. It returns up to five official documentation links.
4. **Code verifies.** A middleware on the subagent records every URL that search returned. Only links that the subagent returned *and* that search returned are kept, so a made-up URL never reaches the main agent.
5. **The main agent gets the links.** `JevRuntime` appends a `## Documentation` section listing the links to this run's context system prompt only. Settings, the agent, and later runs are unchanged.
6. **The result records the decision.** `metadata["jev_documentation"]` holds a `JevDocumentationResult`, including the boolean `needs_documentation` that the owner will act on later.

## How it fails

Everything fails open for the main run. A missing TypeSafe key, a Jev error, a missing search key, a search or subagent failure, or no verified links each produce a status and `needs_documentation` (False when Jev could not answer), and the main run continues without links. The subagent never runs without a real search client, because a priced tool without a client returns a contract stub, not results.

The search API key comes from the provider's usual environment variable (`EXA_API_KEY`, `TAVILY_API_KEY`, `BRAVE_API_KEY`, `PARALLEL_API_KEY`), read when the agent is built. Construction never fails because a key is missing, which matches how the TypeSafe key is treated.

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/enums/__init__.py`: `JevDocumentationProvider` (exa, tavily, brave, parallel).
- `vidbyte/agents/jev/settings.py`: the `documentation` field and its validation.
- `vidbyte/agents/jev/documentation/`:
  - `questions.py`: the ten questions and the fixed threshold.
  - `search.py`: provider → (search tool, client, env var) table, and the hit-recording middleware.
  - `result.py`: `JevDocumentationStatus`, `JevDocumentationLink`, `JevDocumentationResult`.
  - `agent.py`: `JevDocumentation`, which runs assess → search → verify.
  - `__init__.py`.
- `vidbyte/agents/jev/agent.py`, `runtime.py`: build one `JevDocumentation` when the setting is on; run it before the loop and append the links.
- `vidbyte/prompts/prompts/jev_documentation/`, `vidbyte/lib/enums/prompts.py`: the search agent's system prompt as a prompt asset.
- Exports in `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`.
- `vidbyte/agents/jev/README.md`, `skills/jev-agent/SKILL.md`: describe the capability.
- `tests/test_jev_documentation.py`, `scripts/test-jev-agent-scaffold.py`.

## Risks and open questions

- The 0.7 threshold is untuned. Taking the highest of ten answers raises false positives; tune on a labeled set.
- Only the current message is judged. A follow-up such as "still broken" after an error pasted earlier will be missed.
- The main agent receives links, not page contents. Fetching pages (for example with `vidbyte.sources`) is a later step.
- PR #445 (self-alignment) also edits `JevAgent.__init__`, `JevRuntime.__init__`, and `JevRuntime.arun`. Whichever PR merges second must combine both passes: align first, then add documentation.
- The draft preflight PRs (#443, #444) are not on `main`. This capability does not depend on them and makes its own Jev call.

## Verification

- Unit tests with a scripted Jev runner, scripted generative runners, and a fake search client, with no network access. They cover: the question set's shape; a single strong sign giving True; all weak signs giving False; Jev failure; a missing search key; links the search never returned being dropped; the link cap; the main run's system prompt gaining the section while settings stay unchanged; and the setting's validation.
- `python scripts/run_ci.py --stage source` and `--stage package`, then the PR's GitHub checks.
