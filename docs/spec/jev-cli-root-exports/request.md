---
slug: jev-cli-root-exports
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-19
flags: none
program: jev-in-cli (8 PRs; this file's §C 'This run's scope' names this run's slice)
---

# Request: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs

_Part of the program "JevAgent in vidbyte-cli" (8 PRs across vidbyte-sdk and vidbyte-cli). Only the slice in §C "This run's scope" is built in this run._

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening request, before any planning):
````
thinking about adding the "JevAgent" to be able to be ran through the vidbyte-cli/, all the setting/things that are possible to be tweaked/customized through the jevAgent I want to add to the vidbyte-cli/ in terms of a command/subcommands.. Can you give me a checklist of all the basic/required commands that we should include/how to implement and what they do in the vidbyte-cli/
````

**Prompt 2** (after the assistant's checklist, reproduced in §C.0; invoked the build pipeline):
````
/spec-pipeline I like this and I agree with the setup, can you start building it into the vidbyte-cli/.
````

**Prompt 3** (the user's answers to the ten alignment questions reproduced in §C.1):
````
1) you can create 3 seperate prs, that is fine. 2) you can create a new seperate pr in the vidbyte-sdk/ that you can just auto merge that applies this change and updates the version. 3) I dont want writes to be denied. 4) just run the jev agent with no parameters. i think that in the sdk we have defaults, and whatever these defaults are they will run. 5) For now, I want to make sure that the user has one of the 7 provider keys. I dont want them to be able to use a key outside of this, you can maybe create a helper class that runs before the core logic runs that checks something like: "is the user signed in/provided credentials to one oof the 7 providers that we have in the cli", and if they dont you can raise an error with a message explaining that they need 1 of these 7 api providers. 6) just explained this in question 5. this whole feature could even be its own pr 7) i want youto make "max_spend" a universal command in the cli. dont know if we already did this or not, but i want every agent to be tracking usage, figure out the best way to do this. (maybe vidbyte/ repo computes this and returns, or we compute it on the cli/ side of things and keep track in memory there). 8) this is actually a good question. typically, an agent will be using this cli, so another agent will be answering these questions. The target outcome I want, integrates into the cli, is that if there are clarifying questions the JevAgent will stop, stream these questions back to the main agent running the cli, and then the main agent has a way to "input" the answer to the questions back into the run. 9) whatever you want 10) JevAgent should have a reasoning effort, this can be a pr into vidbyte-sdk/ and then update cli with this
````

## B. Handoff block and decision ledger

none

## C. Structured conversation notes

### This run's scope — PR R1 of 8 (vidbyte-sdk): root exports the CLI's JevAgent command needs

**Build exactly this:** make `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode`, and `JevDynamicComputeOption` importable from top-level `vidbyte` (listed in `vidbyte.__all__`), regenerate `contracts/sdk-public-api.json` with the repo's generator, and satisfy every obligation the repo attaches to a new root export (whatever lint rule, contract test, README/llms listing, or REPO_MAP entry pins the public surface — the spec author finds and cites each).

**Why:** vidbyte-cli may import only top-level `vidbyte` names that its vendored copy of this contract lists (CLI lint C028). Verified 2026-10-19 on vidbyte-sdk main b7350ed6: none of these four names is in `vidbyte/__init__.py`. Without them the CLI cannot set JevAgent's loop limits (`JevAgentSettings.loop: AgentLoopSettings`), cannot allow write/execute tools (`JevAgentSettings.permission_policy: PermissionPolicy`, default allows only SAFE+READ — the user said "I dont want writes to be denied"), cannot set `JevAgentSettings.model_mode: TextModelMode` (the validator rejects a non-enum), and must pass compute options as bare strings. Their definitions: `vidbyte/agents/settings/loop.py:46` (`AgentLoopSettings`), `vidbyte/lib/dataclasses/security.py:33` (`PermissionPolicy`), `vidbyte/lib/enums/text_model.py:17` (`TextModelMode`), `vidbyte/lib/enums/jev.py:278` (`JevDynamicComputeOption`).

**Version (D-P2):** do not change the version number. `pyproject.toml` already says `0.4.0` and 0.4.0 is unpublished; these exports ship in it. If the repo keeps a changelog or release-notes file for the unreleased version that lists new exports, add them there (the spec author decides from the code which file, if any, is that record).

**Not in this run:** the spend cap (R3), reasoning effort (R2), tagging or publishing, any vidbyte-cli change, any behavior change to the four classes.

**After S6:** the orchestrator squash-merges this PR with `--admin` (user answer to Q2: "you can just auto merge"). The PR is therefore created as a normal (non-draft-blocking) PR; S6 still writes the full body.


### C.0 The plan the user agreed to ("I like this and I agree with the setup")

This is the assistant's checklist that Prompt 2 approved, condensed faithfully. Facts in it were verified against vidbyte-sdk main (b7350ed6 area) and vidbyte-cli main on 2026-10-18/19. Where Prompt 3 later changed something, §C.1 and §C.2 win.

**Framing.** The CLI translates argv (plus an optional settings file) into the two frozen SDK settings objects JevAgent accepts: `JevAgentSettings` and `JevRuntimeSettings` (vidbyte-sdk `vidbyte/agents/jev/settings.py`). `JevAgent.__init__(settings, runtime_settings=None)` accepts nothing else. Click parses types; the SDK's own `__post_init__` validation (`ConfigurationError`) owns ranges and semantics, wrapped once into a CLI error. Static `click.Choice` lists must be CLI-local StrEnum mirrors of the SDK enums (commands may not import the SDK: lint C011/C012/C035), with a parity test against the installed SDK. With no preflight preset, no done check, no specialist, no compute, and no skills, a run makes zero Jev decision calls (vidbyte-sdk `skills/jev-agent/SKILL.md:48`).

**Commands agreed:**
1. `vidbyte-cli agents jev run <PROMPT>` — builds a JevAgent from SDK defaults ← settings file ← flags, runs it, emits result kind `agents.jev.result` (output, specialist, done-check verdicts, continuations, read_only, usage split generative/decision). Registered as `@parent.command(cls=AgentCommand, name="run", agent=RunAgent.JEV)` like `commands/agents/bug_finder/run.py:69`; positional-argument command alone in its module (C001); service in `services/jev/service.py`; the only SDK importer is `services/jev/sdk.py` with a guarded top-level `__import__("vidbyte")` (copy `services/bug_finder/sdk.py:120-129`; do NOT copy `services/mcp/sdk.py`, which deep-imports and holds baseline C011/C019 findings); `types/jev.py` holds a validated run input and a CLI-side projection of `JevAgentResponse` (large evidence records `run_state`/`handoff`/`review` only behind `--include-evidence`). Extra run flags: `--settings FILE`, `--dry-run` (validate + print resolved settings and which features bill; read no keys), `--include-evidence`.
2. `vidbyte-cli agents jev capabilities` — lists every closed vocabulary with defaults and ranges: preflight presets, the 24 done checks with one-line descriptions, dynamic-compute options, continuation gates, providers, toolsets, skill source forms. Free, offline.
3. `vidbyte-cli agents jev settings init [PATH]` (commented TOML template of every field and default; `--preset minimal|coding|thorough`), `settings validate <PATH>` (build both settings objects through the SDK adapter without running; ConfigurationError → CLI error envelope, SDK text only as `cause` per C021), `settings show [--settings F] [flags…]` (fully resolved settings with the source of each value — default/file/flag — like `config get`; keys always redacted). Free, offline, no keys.
4. Already covered with no new code once `RunAgent.JEV` exists: `runs list|last --agent agents.jev`, `runs show <id>`, root `--json`/`--format jsonl`, `--send-to` (after wiring `agents.jev.result` into `types/outputs.py:34-36` OUTPUT_TEXT_RESULT_KINDS or a builder in `services/outputs/service.py:205-218`; otherwise every target is silently SKIPPED).

**Settings file:** TOML (stdlib `tomllib` on 3.11), named explicitly by `--settings FILE`; precedence flag > file > CLI default > SDK default. No named-profile store in config.json (universal-agent-options spec NG-6 keeps agent config argv-only; an argv-named file stays within it).

**Flag ↔ SDK field map (agreed):**

| SDK field | Flag | Default / allowed | Note |
|---|---|---|---|
| `JevAgentSettings.provider` | `--provider` | text providers except `typesafe` | SDK rejects TypeSafe |
| `.model_name` | `--model` (universal) | CLI default per provider | non-blank |
| `.system_prompt` | `--system-prompt` / `--system-prompt-file` | shipped prompt asset | non-blank |
| `.name` | `--name` | `jev` | |
| `.temperature` / `.timeout_seconds` | `--temperature`, `--timeout-seconds` | unset; 0–2 / >0 | |
| `.tools` | `--tools none\|minimal\|coding` + `--root DIR` | `none` | `ParadigmMinimalToolset` / `CodingAgentTools` |
| `.alignment.skills` | `--skill` (repeatable) | none | path → `LocalSkill`; `github:o/r@ref:path` → `GitHubSkill`; `skills.sh:src` → `SkillsShSkill` |
| `.bulk_work` | `--bulk-agents`, `--bulk-threshold` | 4 (≥2), 0.75 | only with `--preflight bulk_work` |
| `.agents` (specialists) | settings file `[[specialists]]` | none | title, description, provider, model, prompt → BaseAgent each |
| `.permission_policy` | `--allow` | see §C.2 D-P3 | needs SDK root export (PR R1) |
| `.loop` | `--max-iterations --max-tokens --max-tool-calls --loop-timeout` | unlimited | needs SDK root export (PR R1) |
| `.outputs` | do NOT map | — | `--send-to` already delivers at CLI level; mapping both double-posts |
| `JevRuntimeSettings.preflight` | `--preflight` (repeatable) | none; clarity, tool_selector, run_state_relation, bulk_work, read_only | |
| `.tool_selector_threshold` / `.skills_threshold` | `--tool-selector-threshold`, `--skills-threshold` | 0.20 / 0.5, each 0–1 | |
| `.continual.checks` | `--done-check` (repeatable) | none; 24 checks | |
| `.continual.max_continuations` | `--max-continuations` | 3 (≥0) | 0 = report only |
| `.continual.gate` | `--continuation-gate` | same_context \| fresh | fresh needs ≥1 check |
| `.continual.{run_state,handoff,review}_max_*`, `faithful_scope_extra_*` | settings file only | 25 it.; 100k/400k/400k tok; 2/16k/4 | 9 advanced knobs |
| `.compute.dynamic_compute` | `--compute` (repeatable) | off; on → fresh_agent, fork_agent, subagent; clone, swarm opt-in | pass strings |
| `.compute.clones` / `.swarm_agents` | `--clones`, `--swarm-agents` | 2 (1–4) / 10 (2–10) | |
| `.compute.brief.*` | `--brief-model`, `--brief-provider`, `--brief-every` | main model; every 10 it. | provider needs model; rest file-only |
| `.decision` | never exposed | Vidbyte-managed | SDK rejects anything else |

**Facts surfaced in the plan:** Jev decisions always go to the hard-coded production gateway `VIDBYTE_JEV_GATEWAY_ENDPOINT = "https://vidbyte-backend.onrender.com/api/v1/models/typesafe"` (vidbyte-sdk `vidbyte/lib/constants/jev.py:26`), so `config set api_url` does not reach Jev. The Vidbyte key comes from `auth login` through a `lib/auth` accessor (C019 forbids `.secret_value()` elsewhere). Files every CLI agent PR touches (from `skills/agent-building/references/registration-points.md` and the gates): command package + `prompts/*.md` help assets (C007, C001 ≥4 sentences); `commands/agents/__init__.py` registration; `types/runs.py` RunAgent; `commands/agents/catalog.py` AgentWorkflow; `lib/errors/failures/<family>.py` re-exported (C027 fixed code/exit/description/trace/hint; C024 lock via `python scripts/lock-error-vocabulary.py`); progress StrEnum to stderr via `context.output().diagnostic(...)`; offline `scripts/test-<x>.py` registered in `scripts/run_ci.py` (C010); hard-coded agent sets in `scripts/test-runs-recording.py:710`, `scripts/test-universal-agent-options.py:62-78`, `scripts/test_research_only_surface.py:72`; `pyproject.toml` package-data + `run_ci.py` `_WHEEL_RUNTIME_PROMPTS` (C009); README Commands table (C012) and agent lists; regenerate `contracts/cli-commands.json` with `python scripts/generate-cli-commands.py` after committing code (C035) plus a changelog line; `docs/design/<name>.md`; zero new findings against `lint/baseline.json`.

### C.1 Alignment questions asked (verbatim) and the user's answers

The assistant asked (verbatim):

1. **PR scope for this run.** I earlier suggested three PRs (offline settings commands → `run` → loop/permission flags). Should this pipeline build PR 1 and PR 2 together as one PR: `agents jev run`, `agents jev capabilities`, and `agents jev settings init|validate|show`? *Default:* yes, all of those in one draft PR.
2. **SDK-blocked settings.** Loop caps (`--max-iterations/--max-tokens/--max-tool-calls`) and `--allow write,execute` need `AgentLoopSettings` and `PermissionPolicy` exported from top-level `vidbyte`. Should this PR leave them out entirely, or should I also open a small separate vidbyte-sdk PR exporting them (aimed at 0.4.0)? *Default:* leave them out of this PR and list the SDK export as a follow-up; no SDK PR from this run.
3. **Read-only toolsets.** Without `PermissionPolicy`, `--tools minimal|coding` can read and search files but every write and bash call is denied. Ship those toolsets anyway, with help text and `--dry-run` saying writes are denied, or offer only `--tools none` in v1? *Default:* ship them as read-only, stated plainly.
4. **What a bare `run` does.** With no Jev flags, `run` can be "free mode" (a plain agent, zero Jev decision calls), or it can turn on a recommended bundle by default (for example `clarity` + the `multi_part` done check), which bills for decisions. *Default:* free mode; bundles only through `settings init --preset`.
5. **Generation billing without your own key.** `auth` stores keys for 7 providers (openai, claude, grok, deepseek, glm, muse, gemini). When the chosen provider has no stored key, the SDK falls back to generation billed to the user's Vidbyte balance. Allow that automatically, or refuse unless the user passes an explicit opt-in flag? *Default:* allow it, and print on stderr before the run which path pays; `--dry-run` shows the same.
6. **Which providers v1 offers.** *Default:* only the 7 above, mapped to the SDK's names (claude→anthropic, grok→xai, muse→meta). The SDK's other text providers (minimax, kimi, mistral, openrouter) wait until `auth` can store their keys.
7. **No local spend cap in v1.** Without loop caps, a run is bounded only by the Vidbyte balance and the gateway's daily spend cap. `--compute clone/swarm` and the `bulk_work` preset launch extra agents. *Default:* ship them; help text and `--dry-run` name them as the costliest options. The alternative is holding them back until loop caps exist.
8. **When Jev stops to ask clarifying questions.** In an interactive terminal, ask and re-run in the same process with the answers. Under `--no-input` or JSON output, print an `agents.jev.clarification` document and exit with a distinct non-zero status; answers come back through `--answers FILE`. *Default:* exactly that. The alternative is exit 0 with a `status` field.
9. **What `--send-to` posts.** The output text alone, or the output plus a one-line done-check summary ("4/5 checks passed, 1 continuation"). *Default:* output plus the one-line summary.
10. **`--reasoning-effort` and settings discovery.** The universal `--reasoning-effort` flag has no JevAgent field to map to. *Default:* a non-empty value fails with a clear error (not silently ignored), and settings load only from an explicit `--settings FILE`, never auto-discovered.

The user's answers are Prompt 3 in §A (verbatim). Mapped per question:
- Q1 → "you can create 3 seperate prs, that is fine."
- Q2 → "you can create a new seperate pr in the vidbyte-sdk/ that you can just auto merge that applies this change and updates the version."
- Q3 → "I dont want writes to be denied."
- Q4 → "just run the jev agent with no parameters. i think that in the sdk we have defaults, and whatever these defaults are they will run."
- Q5 → "For now, I want to make sure that the user has one of the 7 provider keys. I dont want them to be able to use a key outside of this, you can maybe create a helper class that runs before the core logic runs that checks something like: "is the user signed in/provided credentials to one oof the 7 providers that we have in the cli", and if they dont you can raise an error with a message explaining that they need 1 of these 7 api providers."
- Q6 → "just explained this in question 5. this whole feature could even be its own pr"
- Q7 → "i want youto make "max_spend" a universal command in the cli. dont know if we already did this or not, but i want every agent to be tracking usage, figure out the best way to do this. (maybe vidbyte/ repo computes this and returns, or we compute it on the cli/ side of things and keep track in memory there)."
- Q8 → "this is actually a good question. typically, an agent will be using this cli, so another agent will be answering these questions. The target outcome I want, integrates into the cli, is that if there are clarifying questions the JevAgent will stop, stream these questions back to the main agent running the cli, and then the main agent has a way to "input" the answer to the questions back into the run."
- Q9 → "whatever you want" (the assistant's default stands: output plus a one-line done-check summary).
- Q10 → "JevAgent should have a reasoning effort, this can be a pr into vidbyte-sdk/ and then update cli with this" (settings discovery: the default stands — explicit `--settings FILE` only).

### C.2 Key decisions (program level; the user may interrupt to change any)

- **D-P1 Program shape: 8 PRs, ordered by dependency.** SDK lane (each merged by the orchestrator with `gh pr merge --squash --admin`, per the user's Q2 answer "just auto merge"): **R1** root-export `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode`, `JevDynamicComputeOption` from top-level `vidbyte`; **R3** a USD spend cap on `AgentLoopSettings` that the loop enforces from the run's own priced usage; **R2** reasoning effort on `BaseAgent` (mapped per provider) and on `JevAgentSettings`. CLI lane (draft PRs, stacked linearly, the user merges): **C1** provider-key gate helper; **C2** `agents jev capabilities` + `agents jev settings init|validate|show`; **C4** `agents jev run` (SDK defaults, writes allowed, gate, clarification protocol, `--send-to`, permissions and loop flags via R1); **C3** universal `--max-spend` with per-agent usage tracking; **C5** jev `--reasoning-effort` via R2. — *Why:* Q1 accepts three Jev PRs (C2, C4, C5); Q2 and Q10 ask for SDK PRs; Q6 asks for the gate as its own PR; Q7 asks for universal max_spend.
- **D-P2 SDK version.** vidbyte-sdk main is already `0.4.0` (pyproject `version = "0.4.0"`, `vidbyte/__init__.py:41`) and 0.4.0 is NOT published (PyPI latest is 0.3.0; tag v0.3.1 exists but 0.3.1 was never published). SDK PRs in this program land in the unreleased 0.4.0 and do not invent a new number. The CLI pin moves to `>=0.4.0,<0.5` in C4. Publishing 0.4.0 is a separate, user-approved step: the repo's release note says not to tag v0.4.0 until SDK #1184 (Meta `LLM_` key-shape fix, still a draft) merges.
- **D-P3 Writes are not denied (Q3).** When tools are enabled, the CLI's default `PermissionPolicy` allows all four `ToolPermission` levels (SAFE, READ, WRITE, EXECUTE); `--allow` narrows it. Jev's own `read_only` preflight preset may still cap a run Jev judges assessment-only; that is the SDK feature working, not a denial by the CLI.
- **D-P4 Bare run = SDK defaults (Q4).** `agents jev run "<prompt>"` with no Jev flags constructs `JevRuntimeSettings()` with SDK defaults (no preflight, no done checks, no compute, no skills → zero decision calls). The CLI supplies only the four fields the SDK requires without defaults: `name`, `system_prompt`, `provider`, `model_name`.
- **D-P5 Only the 7 CLI providers, only with the user's own key (Q5, Q6).** Before any core logic, a canonical `lib/` helper checks that the user has credentials for at least one of the 7 providers the CLI's `auth` stores (`src/vidbyte_cli/types/provider.py:12-21`: openai, claude, grok, deepseek, glm, muse, gemini); otherwise a typed error explains that one of these 7 keys is required and how to add one. A provider outside the 7, or one of the 7 without a key, is refused; there is no Vidbyte-paid generation fallback and no other key source. This gate is its own PR (C1) and the Jev run uses it (C4).
- **D-P6 max_spend architecture (Q7, "figure out the best way").** The SDK already prices every model call in USD (`UsageTracker`, `UsageRollup.cost` in `vidbyte/lib/dataclasses/sessions.py:127-135`; per-model rates in `vidbyte/lib/registries/pricing.py`). Bring-your-own-key spend never reaches the vidbyte backend, so the backend alone cannot see it — rejected as the sole source. Chosen: the SDK meters and enforces (R3: a USD cap on `AgentLoopSettings`, checked by the loop against the run's live priced usage), the CLI owns the universal `--max-spend` option, maps it to each agent's enforcement point (SDK loop cap; existing backend caps such as research `max_cost_cents`; refusing a fixed-price admission above the cap; gateway-metered pre-checks), and records each run's spend in its result and in the runs ledger. An agent whose spend cannot be capped mid-run is capped at the strongest point available and that is stated as a limitation.
- **D-P7 Clarification protocol for agent callers (Q8).** When Jev's `clarity` preflight stops a run, `agents jev run` stops, emits the questions (with suggested answers and a resumable run id) on stdout as an `agents.jev.clarification` record — in JSONL mode as a streamed event — and exits with a distinct status. The calling agent answers with a second CLI call that names the run id and supplies the answers; the CLI re-runs the saved request with the answers. *Why not wait on stdin:* coding agents (Claude Code, Codex) run a shell command to completion and cannot type into a waiting process. The clarification gate runs before the generative agent starts, so re-running loses no work.
- **D-P8 `--send-to` content (Q9):** the run output plus a one-line done-check summary.
- **D-P9 Reasoning effort (Q10):** added in the SDK (R2) to `BaseAgent` and `JevAgentSettings`, then exposed in the CLI (C5). Until C5, the jev command must not silently ignore a non-empty universal `--reasoning-effort`.
- **D-P10 Settings discovery:** only an explicit `--settings FILE`; no auto-discovered project file.

### Rejected alternatives
- Backend-only spend tracking — cannot see bring-your-own-key provider spend.
- Waiting on stdin for clarification answers — agent callers cannot write to a running process.
- Vidbyte-paid generation fallback when the user lacks a provider key — the user said "I dont want them to be able to use a key outside of this".
- Read-only toolsets in v1 — the user said "I dont want writes to be denied".
- A recommended Jev bundle on by default — the user said "just run the jev agent with no parameters".
- Named settings profiles stored in config.json — breaks the argv-only configuration rule (universal-agent-options NG-6).

### Constraints and assumptions
- vidbyte-cli imports only top-level `vidbyte` names listed in `lint/contracts/sdk-public-api.json` (C028), only from `services/*/sdk.py` adapters inside a guarded function-level import (C011).
- vidbyte-cli main now pins `vidbyte-sdk[codex]>=0.3.1,<0.4` (pyproject.toml:50,57) and its vendored contract is 0.3.1; 0.3.1 is not on PyPI, so local CLI gates need `PIP_FIND_LINKS=C:/Users/422mi/vidbyte-repos/.wheels/vidbyte-sdk-0.3.1`.
- vidbyte-sdk merges need `gh pr merge --squash --admin` (ci.yml automatic triggers paused; dispatched CI does not attach to PRs). vidbyte-cli remote Actions fail on account billing; the local `python scripts/run_ci.py` is the real gate there.
- `vidbyte-sdk` and `vidbyte` treat `docs/` as opaque except files a briefing names.

### Terminology
- **Jev** — Vidbyte's decision model, reached only through the Vidbyte-managed gateway; it answers fixed questions (preflight presets, done checks, compute choices). It never generates the reply.
- **Preflight preset** — a fixed-question check Jev runs before the main agent (`JevPreflightPreset`: clarity, tool_selector, run_state_relation, bulk_work, read_only).
- **Done check** — a fixed-question check at each finish attempt that can send the agent back to work (`JevDoneCheck`, 24 members).
- **The 7 providers** — the provider kinds `vidbyte-cli auth` stores keys for (`Provider` StrEnum, `src/vidbyte_cli/types/provider.py`).
- **Universal option** — an option every catalog agent command accepts through `AgentCommand` (`src/vidbyte_cli/commands/agents/agent_command.py`; today `--instructions`, `--model`, `--reasoning-effort`, `--send-to`).

### Implementation hints
- Model a CLI agent command on `src/vidbyte_cli/commands/agents/bug_finder/` (group, `run.py`, `prompts/library.py`) and its service on `src/vidbyte_cli/services/bug_finder/{service,sdk}.py`.
- Credentials: `context.require_provider_credentials(Provider.OPENAI)` already exists (`src/vidbyte_cli/commands/runtime/persistence.py:138`); secrets resolve environment → keyring → restricted file (`src/vidbyte_cli/lib/auth/resolver.py`, `provider_resolver.py`).
- Do not copy `src/vidbyte_cli/services/mcp/sdk.py` (deep SDK imports; baseline lint findings).
- vidbyte-sdk placement: dataclasses in `vidbyte/lib/dataclasses/<domain>.py`, enums in `vidbyte/lib/enums/<domain>.py` (exported from `vidbyte/lib/enums/__init__.py`), agent settings in `vidbyte/agents/settings/` or the agent's `settings.py`; `contracts/sdk-public-api.json` is generated by `scripts/generate-sdk-public-api.py`.

### Open questions
- Exact CLI default model per provider, and the default system prompt text for `agents jev run`.
- Unit and spelling of `--max-spend` (USD amount assumed) and what a run returns when the cap stops it.
- The exact second-call shape for answering clarifications (a dedicated `answer` subcommand vs a `run --resume` flag).

## D. Weighted words

- "all the setting/things that are possible to be tweaked/customized through the jevAgent I want to add to the vidbyte-cli/" — Prompt 1
- "Can you give me a checklist of all the basic/required commands" — Prompt 1
- "I dont want writes to be denied." — Prompt 3
- "just run the jev agent with no parameters ... whatever these defaults are they will run." — Prompt 3
- "I want to make sure that the user has one of the 7 provider keys." — Prompt 3
- "I dont want them to be able to use a key outside of this" — Prompt 3
- "a helper class that runs before the core logic runs" — Prompt 3
- "you can raise an error with a message explaining that they need 1 of these 7 api providers" — Prompt 3
- "make "max_spend" a universal command in the cli" — Prompt 3
- "i want every agent to be tracking usage" — Prompt 3
- "if there are clarifying questions the JevAgent will stop, stream these questions back to the main agent running the cli, and then the main agent has a way to "input" the answer to the questions back into the run." — Prompt 3
- "JevAgent should have a reasoning effort" — Prompt 3
- "you can just auto merge that applies this change and updates the version" — Prompt 3
