---
slug: public-skill-loader
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-15 15:04
flags: --repo C:\Users\422mi\vidbyte-repos\vidbyte-sdk (run S0 through S6; no --until, no --keep-worktree)
---

# Request: Public, root-exported skill loader in vidbyte-sdk (resolve every #904 skill source without JevAgent), version 0.2.2

## A. Every user prompt in this conversation, verbatim and in order

The conversation took place in a parent Claude Code session. Prompts 1 to 3 were typed by the user; prompt 4 is the user's selection in a multiple-choice question (questions, selected answers, and the option text the user was shown, all verbatim).

**Prompt 1** (start of the conversation; context only, already done):
````
resolve merge conflicts for pr #904 on vidbyte-sdk/ and then merge into main
````

**Prompt 2** (context only; a different repo):
````
same for pr #164  for vidbyte-cli/ repo (launch subagent)
````

**Prompt 3** (the feature that led to this run; it targets vidbyte-cli, and this SDK run exists because of it):
````
can you launch a subagent with the "spec-pipeline" skill for the following for the vidbyte-cli/: 

  8. [ ] Add skill-source commands to the CLI —
     GitHubSkill, SkillsShSkill, AnthropicSkill and
     OpenAISkill are now public SDK exports, so a command
     like vidbyte skills add github:owner/repo/path is
     possible. Builds on: the 9 skill exports from #904.
     First step: check whether vidbyte-cli already has a
     skills or jev command group.

 (want these  "attach skills to agents" to be a universal command inside of the cli
````

**Prompt 4** (the user's answers to a two-question multiple-choice prompt raised by the paused vidbyte-cli pipeline):

- Q: "How should vidbyte-cli let you attach skills to every agent, given that the SDK's skill loader is private and only JevAgent uses it?"
  A (selected): **"SDK PR first (Recommended)"**
  Option text shown to the user: "Make the skill loader public in the SDK and bump it to 0.2.2. The CLI PR then adds one shared repeatable option on AgentCommand that loads skills from all six sources and adds them to all six CLI agents' prompts. This follows the repo's 'SDK PR comes first' rule. The CLI PR waits for SDK 0.2.2 on PyPI, which it already had to."
- Q: "If the SDK change comes first, how should it be built?"
  A (selected): **"Own spec-pipeline run (Recommended)"**
  Option text shown to the user: "Run a full spec-pipeline in vidbyte-sdk (spec, blind tests, adversarial review, draft PR) to make the loader public and bump to 0.2.2. The CLI pipeline waits, then resumes against it. Slower, with the most scrutiny on a public API change."

**Prompt 5** (2026-10-15 evening, during S5; the user's answer to a multiple-choice question relayed by the parent session; question, selected answer, and option text verbatim):

- Q: "SDK main now carries #1027, which is unreleased and breaking: it removes `api_key=` from Agent, BaseAgent and 6 other root exports, and default text calls go through the Vidbyte gateway, so an OPENAI_API_KEY-only setup fails with 'Missing Vidbyte API key'. What version should PR #1099 (the public skill loader) stamp for the next release?"
  A (selected): **"0.4.0 (Recommended)"**
  Option text shown to the user: "Ship the breaking change as a new minor, per AGENTS.md's 'APIs may change between minor versions'. CLI installs pinned `<0.4` won't silently pick up the gateway routing. The CLI skill PR pins `>=0.4.0,<0.5` and has to verify #1027's behavior, as the CLI's pin comment asks. Cost: 9 version-literal edits, a regenerated contract, and one repair iteration."
- Relayed with it (the parent session's instruction, carrying the user's decision): "The version bump's release notes or docs, following the repo's 0.3.0 precedent, should name #1027's breaking changes alongside the loader, if the precedent includes such notes."

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### Why this run exists
- A paired spec-pipeline run in vidbyte-cli (slug `agent-skill-sources`) is PAUSED at its S1 waiting on this SDK change. The user wants one universal "attach skills to agents" mechanism in the CLI, covering all six CLI agents and every skill source.
- SDK PR #904 (squash `179d8adc` on SDK `origin/main`, this run's base commit) added the skill-source **types** to the public surface: `AnthropicSkill, GitHubSkill, InlineSkill, LocalSkill, OpenAISkill, SkillEntry, SkillSourceType, SkillUnavailableReason, SkillsShSkill`.
- The code that **resolves** an entry into skill text is private:
  - `vidbyte/agents/skills/__init__.py:16` is `__all__: list[str] = []`, and `SkillLoader` is not a root export.
  - The entry records are data only; their header says "No record reads a file, an environment variable, or the network".
  - The only consumer is `JevAlignmentSettings.skills` (`vidbyte/agents/jev/settings.py:83`), resolved through the Jev preload.
- The CLI never runs a `JevAgent`. Its lint rule C028 lets it import only names in the SDK's public contract (`vidbyte.__all__` and `contracts/sdk-public-api.json`). Its own rule (`skills/agent-building/SKILL.md` in vidbyte-cli) says "If something is missing, the SDK PR comes first", and also "A merged SDK PR is not a published one". **This run is that SDK PR.**

### Key decisions (settled by the user; do not reopen)
- **SDK PR first.** The SDK exposes a **public, root-exported way to resolve skill entries from every source #904 supports**: inline text, local folders, skills.sh, GitHub, Anthropic and OpenAI. Each resolves into skill documents (name plus text) that a non-Jev caller can put into any agent's prompt, with per-entry unavailability reported in a structured way (`SkillUnavailableReason`), not as a crash. The spec designs the exact shape. — Reason: the CLI may import only root exports (C028/C011), and the repo rule is "the SDK PR comes first".
- **Prefer exposing or wrapping the loader that already exists over writing a second one.** — Reason: one loader, one set of fetch/parse/limit rules.
- **`JevAgent` must keep its current behavior.** — Reason: it is the existing consumer; this PR only adds a public door.
- ~~**The SDK version goes to 0.2.2 in this PR.**~~ *Superseded by the user's decision of 2026-10-15 evening (Prompt 5) below; kept for history.* — Reason: the CLI will raise its floor to the first release that contains the loader, and CLI lint rule C029 requires the CLI's floor to match the vendored contract's version, so an SDK commit with `version = "0.2.2"` must exist.
- **The SDK version goes to 0.4.0 in this PR** (user decision, Prompt 5, verbatim answer: "0.4.0 (Recommended)"; option text: "Ship the breaking change as a new minor, per AGENTS.md's 'APIs may change between minor versions'. CLI installs pinned `<0.4` won't silently pick up the gateway routing. The CLI skill PR pins `>=0.4.0,<0.5` and has to verify #1027's behavior, as the CLI's pin comment asks. Cost: 9 version-literal edits, a regenerated contract, and one repair iteration."). — Reason: main (merged into this branch) carries #1027, an unreleased breaking change (removes `api_key=` from Agent, BaseAgent and other root exports; default text calls go through the Vidbyte gateway), so the next release is a new minor. The release notes follow the 0.3.0 precedent (`docs/design/release-0-3-0.md`) and name #1027's breaking changes alongside the loader. Consequence for the CLI: its pin becomes `vidbyte-sdk[codex]>=0.4.0,<0.5`, and the CLI run must verify #1027's gateway routing against its six agents before relying on 0.4.0.
- **Built as its own full spec-pipeline run** (spec, blind tests, adversarial review, draft PR) — "the most scrutiny on a public API change".

### Rejected alternatives
- CLI imports the internal loader through a `services/*/sdk.py` adapter — rejected by the CLI pipeline: C028 regresses past its baseline (9 → at least 11), the CLI gate goes red, and it couples the CLI to an SDK path that may move in a patch release.
- Narrow the CLI to local folders only via `CodexSkillInput` — rejected: drops GitHub, skills.sh, Anthropic, and OpenAI, which are the premise of the request, and is not universal across agents.
- Jev-only skills (use `JevAlignmentSettings.skills`) — rejected: the CLI never builds a `JevAgent`, and the user wants every agent.

### Constraints and assumptions
- Out of scope unless a repo rule forces it:
  - adding a `skills` field to generic `Agent`/`BaseAgent`;
  - publishing to PyPI or tagging a release (the user's call after review);
  - any change in vidbyte-cli.
- The PR stays a **draft**. Never merge it, tag it, or publish it.
- Version bump convention: the last bump (0.2.0 → 0.2.1) moved every literal that names the version together: `pyproject.toml`, `vidbyte/__init__.py`, the CLI fallback, the MCP server default, the MCP `clientInfo`, `README.md`, `llms.txt`, the bug template, and the regenerated contract. Find them all with a grep for `0.2.1`; miss none.
- Public API contract: adding root exports or changing the version means regenerating `contracts/sdk-public-api.json` with `python scripts/generate-sdk-public-api.py`. It refuses to write while `vidbyte/__init__.py` or `pyproject.toml` have uncommitted changes. Commit the source change first, then run the generator, then commit the regenerated file as its own commit. Never edit the contract by hand; never amend after generating (amending changes the SHA it stamped). `--check` must pass. Lint rule C016 enforces this.
- The SDK repo's `AGENTS.md` binds every stage (placement rules, one-level call chains, narrated main functions, validated frozen dataclasses, and `docs/` is opaque except the files this pipeline writes under `docs/spec/public-skill-loader/`).

### Consumer requirements (from the paused vidbyte-cli pipeline, relayed by the parent session; NOT user decisions — the spec designs the answers and must state each one explicitly)
Relayed verbatim:
````
1. **Callable without JevAgent.** For each entry it returns the skill's **text** or a `SkillDocument`, or a structured unavailable status with `SkillUnavailableReason`. The CLI puts that text into every agent's system prompt through its `AgentInstructions.append_to`.
2. **Sync or async.** State which, and why. The CLI calls it from command setup before an agent runs.
3. **GitHub token.** State how a caller passes the token, and whether the loader reads `GITHUB_TOKEN` from the environment itself. The CLI's default is to read `GITHUB_TOKEN` from the environment.
4. **Size limits.** The SDK allows a SKILL.md of up to 1 MiB, but the CLI caps the instructions it adds at **20,000 bytes**. The SDK spec must state its own limits and how an oversized skill is reported. Say whether a caller can pass a byte limit, so the CLI can turn an oversized skill into a structured failure instead of truncating it or crashing.
5. **Source-string parser (optional, your call).** Decide whether the SDK exposes a parser from a source string such as `github:owner/repo/path`, `skills.sh:<id>` or a local path to a `SkillEntry`. Without one, the CLI writes its own small parser that only builds SDK entry objects. If you add one, say so, along with the grammar.
6. **Root-level names only.** The CLI may import only names exported from the `vidbyte` package root, through its `services/*/sdk.py` adapters. Its lint rules C028 and C011 fail on any deep import. Every name the CLI needs must be in `vidbyte.__all__` and in the regenerated `contracts/sdk-public-api.json`.
7. **Version.** The CLI's lint rule C029 requires the SDK floor it declares to match the vendored contract's version. Keep `0.2.2` consistent across `pyproject.toml`, `vidbyte/__init__.py` and the regenerated contract in this PR.
````
Scope note on these: items 1, 2, 3, 4, 6, 7 are answers the spec must give (they fall inside the settled scope). Item 5 is optional; rule 11 of the pipeline applies (scope is the conversation): a parser is an addition the user never asked for, so the spec either justifies it from a requirement or carries it as an optional `Q-n` with default **not built**.

### Clarifications and answers
- Q: "How should vidbyte-cli let you attach skills to every agent, given that the SDK's skill loader is private and only JevAgent uses it?" — A: "SDK PR first (Recommended)".
- Q: "If the SDK change comes first, how should it be built?" — A: "Own spec-pipeline run (Recommended)".
- Q: "… What version should PR #1099 (the public skill loader) stamp for the next release?" (full text in §A, Prompt 5) — A: "0.4.0 (Recommended)".

### Terminology
- **Skill entry** — one of the #904 record types (`InlineSkill`, `LocalSkill`, `SkillsShSkill`, `GitHubSkill`, `AnthropicSkill`, `OpenAISkill`), unioned as `SkillEntry`. Data only.
- **Resolve / load** — turn a skill entry into a skill document (name plus SKILL.md text) by reading a file, an inline string, or the network.
- **Unavailable** — an entry that could not be resolved; reported per entry with a `SkillUnavailableReason`, never as an exception that aborts the other entries.
- **Six sources** — inline text, local folders, skills.sh, GitHub, Anthropic, OpenAI.
- **Six CLI agents** — the six vidbyte-cli catalog agents that opt in to `AgentCommand` (five Codex harness agents plus the CLI-owned suggestion gateway). The CLI side is out of scope here; it is only the consumer.
- **Root export** — a name in `vidbyte.__all__`, recorded in `contracts/sdk-public-api.json`.

### Implementation hints
- Existing internal loader: `vidbyte/agents/skills/loader.py` (`SkillLoader`, `async def load`; `SkillResolution`), package `vidbyte/agents/skills/` with `__all__ = []`. Its only consumer: `JevSkillsPreload.__init__` in `vidbyte/agents/jev/alignment/skills.py`.
- Records: `vidbyte/lib/dataclasses/skills.py` (entry records, `SkillDocument`); enums: `vidbyte/lib/enums/skills.py` (`SkillSourceType`, `SkillUnavailableReason`).
- The skills package README reportedly forbids `from vidbyte.agents import …` inside the loader package because of an import-order hazard; the root export must be placed with care.
- Version literals: grep for `0.2.1` (pyproject, `vidbyte/__init__.py`, CLI fallback, MCP server default, MCP `clientInfo`, README.md, llms.txt, bug template; then regenerate the contract).
- Read-only context from the paused CLI run (do not edit; outside this repo, so the SDK's `docs/` rule does not apply to them):
  - `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-cli-agent-skill-sources/docs/spec/agent-skill-sources/reports/S1-spec-author.md` (the full escalation and evidence; its §5 lists the CLI-side size limit 20,000 bytes and the credentials question)
  - `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-cli-agent-skill-sources/docs/spec/agent-skill-sources/request.md`
  - `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-cli-agent-skill-sources/docs/spec/agent-skill-sources/pipeline.md`
  - `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-cli-agent-skill-sources/docs/spec/agent-skill-sources/context/code-map.md`

### Open questions (for the spec author to resolve as A-/Q-items)
- The exact public shape: root-export the existing `SkillLoader`/`SkillResolution` as-is, or a thin public facade over them? Names, signature, sync vs async.
- How a caller supplies credentials (GitHub token; Anthropic/OpenAI keys) and whether the loader reads the environment itself.
- Size limits and how an oversized skill is reported; whether the caller can pass a byte limit.
- Whether any relevance selection (the Jev decision model) is part of the public path. Likely not: the public path resolves what it is given.
- Whether a source-string parser is in scope (default: not built, per rule 11).

## D. Weighted words

- "want these  \"attach skills to agents\" to be a universal command inside of the cli" — Prompt 3
- "loads skills from all six sources and adds them to all six CLI agents' prompts" — Prompt 4 (option text the user selected)
- "This follows the repo's 'SDK PR comes first' rule." — Prompt 4 (option text the user selected)
- "The CLI PR waits for SDK 0.2.2 on PyPI, which it already had to." — Prompt 4 (option text the user selected)
- "Slower, with the most scrutiny on a public API change." — Prompt 4 (option text the user selected)
- Settled scope (parent session's statement of the decision): "resolve skill entries from **every** source #904 supports"; "per-entry unavailability reported in a structured way (`SkillUnavailableReason`), **not as a crash**"; "`JevAgent` **must** keep its current behavior"; "**never** edit the contract by hand, and **never** amend after generating"; "Find them with a grep for `0.2.1`, and **don't miss any**".
