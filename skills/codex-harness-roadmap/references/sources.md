# Evidence and documentation index

Verified **2026-09-05**. All 20 official pages below were fetched and their relevant content inspected. Documentation currently redirects many historical `developers.openai.com/codex/...` links to `learn.chatgpt.com/docs/...`. The links below are the reviewed destinations.

This index is a route to authoritative sources, not a copied SDK manual. Read only the pages relevant to the selected task. Avoid inferring feature support from navigation labels or a search snippet.

## Implementation baseline

- [PR #409](https://github.com/cerredz/Vidbyte-SDK/pull/409): open/unmerged at review time; replaces #408.
- [Pinned agent/translator/transport/fork/result source](https://github.com/cerredz/Vidbyte-SDK/tree/c3842585822bb2eb950bc3a419ae1ae52ecaa21d/vidbyte/agents/codex): exact implementation snapshot used for the gap analysis.
- [Pinned Codex data contracts](https://github.com/cerredz/Vidbyte-SDK/blob/c3842585822bb2eb950bc3a419ae1ae52ecaa21d/vidbyte/lib/dataclasses/codex.py): current settings/input/result shape.
- [Pinned runtime-primitives guidance](https://github.com/cerredz/Vidbyte-SDK/tree/c3842585822bb2eb950bc3a419ae1ae52ecaa21d/skills/runtime-primitives): broader Codex/Claude intent; this new skill supplies the Codex-specific future backlog.
- Canonical main inspected at `c27dac4f`. Existing Vidbyte abstraction locations are listed in [translation-map.md](translation-map.md).
- Installed Python package inspected: `openai-codex==0.147.0`. This is a tested comparison version, not a claim that it is the latest available package.

## Public Python surface inspected

`AsyncCodex`: account, close, login_api_key, login_chatgpt, login_chatgpt_device_code, logout, metadata, models, thread_archive, thread_fork, thread_list, thread_resume, thread_start, thread_unarchive.

`AsyncThread`: id, compact, read, run, set_name, turn.

`AsyncTurnHandle`: id/thread_id, steer, interrupt, stream, run.

N labels are based on these public methods. P/E labels deliberately do not invent equivalent methods on these classes. For implementation, inspect the selected method's full signature and return annotations and the generated protocol schema in the installed package. Presence in a generated schema alone does not prove a supported high-level wrapper or a runtime permission.

## Official documentation

<a id="s01"></a>

### S01: Codex SDK

[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) — Python versus TypeScript entrypoints, bundled runtime, async usage, and sandbox override persistence. Supports C/L/T/A/V; does not document every low-level RPC.

<a id="s02"></a>

### S02: Codex app-server

[Codex app-server](https://learn.chatgpt.com/docs/app-server) — Protocol operations, notifications, server requests, thread/turn control, history, goals, tools, auth, filesystem, and experimental/deprecated boundaries. Recheck schemas for every P/E task.

<a id="s03"></a>

### S03: Configuration reference

[Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) — Authoritative key names, value types, defaults, feature flags, MCP/tool settings, and provider controls. A listed key is not proof that the Python facade has a named parameter.

<a id="s04"></a>

### S04: Config basics

[Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) — User/project/system layers, trust, precedence, common settings, and feature activation. Use for predictable override resolution.

<a id="s05"></a>

### S05: Advanced configuration

[Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) — Current profile files, provider tuning, reasoning/context limits, shell environment policy, telemetry, and history controls. Legacy profile tables are no longer current.

<a id="s06"></a>

### S06: Hooks

[Hooks](https://learn.chatgpt.com/docs/hooks) — Lifecycle events, matchers, command/MCP handlers, supported decision shapes, trust, background execution, and failure semantics. Essential to any middleware translation claim.

<a id="s07"></a>

### S07: Subagents

[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) — Native roles, inheritance, delegation behavior, concurrent work, and client/account differences. Role settings do not establish a deterministic external scheduler.

<a id="s08"></a>

### S08: MCP client integration

[MCP client integration](https://learn.chatgpt.com/docs/extend/mcp) — Stdio and streamable HTTP servers, authentication, server instructions, configuration, and plugin-provided servers. This is Codex consuming tools, not Codex being an MCP server.

<a id="s09"></a>

### S09: Permission profiles

[Permission profiles](https://learn.chatgpt.com/docs/permissions) — Beta filesystem/network profiles, enforcement, platform scope, legacy-setting precedence, and proxy prerequisites. Use before claiming policy equivalence.

<a id="s10"></a>

### S10: Sandboxing

[Sandboxing](https://learn.chatgpt.com/docs/sandboxing) — Command isolation and platform enforcement; distinguishes technical access boundaries from approval policy.

<a id="s11"></a>

### S11: Auto-review

[Auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review) — Reviewer-mediated escalation, limits, and denial behavior. Auto-review does not remove the sandbox.

<a id="s12"></a>

### S12: AGENTS.md instructions

[AGENTS.md instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md) — Instruction discovery, override filenames, project hierarchy, size limits, and diagnostics. Use for prompt provenance and placement.

<a id="s13"></a>

### S13: Build skills

[Build skills](https://learn.chatgpt.com/docs/build-skills) — Skill structure, discovery, progressive loading, resources, metadata, and enablement. Distinguish instruction packaging from executable registration.

<a id="s14"></a>

### S14: Build plugins

[Build plugins](https://learn.chatgpt.com/docs/build-plugins) — Packaging and distribution of skills/MCP integrations. Product distribution guidance does not override app-server API readiness warnings.

<a id="s15"></a>

### S15: Command rules

[Command rules](https://learn.chatgpt.com/docs/agent-configuration/rules) — Experimental command-prefix rules, decisions, compound-shell matching, and rule checks. These rules govern escalation and are not a general Vidbyte tool catalog.

<a id="s16"></a>

### S16: Authentication

[Authentication](https://learn.chatgpt.com/docs/auth) — Account/API-key access, credential storage, headless login, custom providers, and organization restrictions. Treat credentials as references, not serialized agent content.

<a id="s17"></a>

### S17: Non-interactive mode

[Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) — CLI automation, structured output, stdin, machine-readable output, and resume behavior. Flags from codex exec are not automatically Python SDK parameters.

<a id="s18"></a>

### S18: Speed

[Speed](https://learn.chatgpt.com/docs/agent-configuration/speed) — Service-tier and access-mode behavior. Recheck current rates separately; this roadmap embeds no price table or universal speed promise.

<a id="s19"></a>

### S19: Git worktrees

[Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) — Desktop/workspace isolation, branch relationships, handoff, and cleanup. Use as product context; implement application-owned Git isolation explicitly.

<a id="s20"></a>

### S20: Record & Replay

[Record & Replay](https://learn.chatgpt.com/docs/extend/record-and-replay) — Desktop workflow demonstrations that become skills, with platform/Computer Use prerequisites. This does not establish deterministic agent replay or a Python API.

## Refresh procedure

1. Record the repository branch/commit and current status of the adapter PR.
2. Inspect the installed SDK version and callable signatures without starting a model run. Check its bundled CLI version or explicit executable override.
3. Fetch the relevant official page and compare field names, lifecycle semantics, platform/account constraints, and maturity with the installed code.
4. If docs and package disagree, keep the task gated and record the difference. Do not implement a guessed method based on a newer manual.
5. Update the baseline, affected task IDs, and source date together. A global review date is not proof that an unrelated task was revalidated.

Particularly important current restrictions: app-server plugin list/read/install/uninstall is documented as unsuitable for production; thread rollback is deprecated; permission profiles are beta; dynamic tools and several history/terminal/environment fields are experimental. The exact status must be refreshed at implementation time.

