# Design Doc: Tri-CLI Agent Synthesis Prompt

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-21
**Last Updated:** 2026-06-21

---

## 1. Overview

Add a new Vidbyte SDK prompt catalog family that helps a host agent run one user prompt through Codex, Claude Code, and opencode as separate non-interactive CLI calls, collect their answers, and synthesize a final answer in the original conversation. The catalog entry will store a Markdown-backed orchestration prompt and a companion PowerShell runner script in the same prompt family folder, then update the human prompt catalog and the local mirrored `vidbyte-prompts` skill collection with a link to the new prompt.

---

## 2. Goals & Non-Goals

### Goals

- Create a new prompt family under `vidbyte/prompts/prompts/tri_cli_agent_synthesis/`.
- Add a Markdown-backed prompt that instructs a host agent to run the user's prompt through Codex, Claude Code, and opencode independently, consume their outputs, and compose a final response.
- Add a companion PowerShell runner script in the same folder with default model and thinking settings:
  - Codex: `gpt-5.5`, high thinking
  - Claude Code: `opus-4.8`, xhigh thinking
  - opencode: `glm-5.2`, max thinking
- Register the new prompt in the `Prompt` enum so `Prompts().get(...)` and direct imports expose it.
- Update the human catalog in `vidbyte/prompts/README.md` so the prompt has a stable GitHub link.
- After catalog implementation, add the new GitHub prompt link to every existing mirrored local `vidbyte-prompts` skill file.

### Non-Goals

- Build a new SDK runtime, pipeline, provider adapter, or hosted service for executing the three CLIs.
- Replace the existing `multi_provider_aggregator` prompt family, which remains SDK-internal and provider-agnostic.
- Guarantee that future model names such as `gpt-5.5`, `opus-4.8`, or `glm-5.2` are available from the user's local CLI credentials.
- Persist agent outputs to a database or trace store.
- Add or modify tests in this no-tests workflow.

---

## 3. Background & Context

The Vidbyte SDK prompt catalog stores plain repository-backed prompt assets under `vidbyte/prompts/prompts/`. Markdown-backed prompt families use a JSON descriptor with `name`, `description`, `key`, and `prompts`, where each leaf prompt maps to a local Markdown file and a GitHub `source_url`. `vidbyte.prompts.catalog.Prompts` automatically scans root and one-level nested JSON descriptors, validates that every prompt value maps to a `Prompt` enum member, reads Markdown assets, and generates direct import names by replacing dots with underscores.

The existing `multi_provider_aggregator` family already handles model-output synthesis in a provider-agnostic SDK context. The requested feature is different: it is a personal workflow prompt that coordinates external local CLIs (`codex`, `claude`, and `opencode`) and then asks the current host conversation to synthesize their answers. Local inspection confirms the three CLI commands exist on this machine, with non-interactive modes available through `codex exec`, `claude --print`, and `opencode run`.

The personal `vidbyte-prompts` skill does not store prompt bodies. It stores links to prompt files listed in `vidbyte/prompts/README.md`, then mirrors that elected-link block across Codex, Claude Code, opencode, and Antigravity CLI skill files when those files exist.

---

## 4. Requirements

### Functional Requirements

1. The new catalog family must be named `Tri-CLI Agent Synthesis` with family key `tri_cli_agent_synthesis`.
2. The family must include a Markdown-backed leaf prompt named `orchestrator`, producing enum value `tri_cli_agent_synthesis.orchestrator`.
3. The Markdown prompt must tell the host agent to pass the same user prompt separately to Codex, Claude Code, and opencode.
4. The Markdown prompt must tell the host agent to treat the three CLI answers as candidate responses and synthesize a single final answer for the original conversation.
5. The Markdown prompt must explain that the companion script emits structured Markdown sections for `codex`, `claude_code`, and `opencode`.
6. The companion script must live in the same prompt family folder as the Markdown prompt.
7. The companion script must define default model and thinking settings in one obvious configuration block.
8. The companion script must accept a user prompt and optional working directory.
9. The companion script must run each CLI as a separate non-interactive invocation, not as one shared conversation.
10. The companion script must write the three raw answers to stdout in a stable format the host agent can paste back into context and synthesize.
11. The `Prompt` enum must include `TRI_CLI_AGENT_SYNTHESIS_ORCHESTRATOR = "tri_cli_agent_synthesis.orchestrator"`.
12. `vidbyte/prompts/README.md` must list the new family in the quick reference table and descriptions section with a direct link to `orchestrator.md`.
13. The local mirrored `vidbyte-prompts` skill files that exist on this machine must receive a new elected prompt entry linking to the GitHub `orchestrator.md` file.

### Non-Functional Requirements

- Performance: The runner script may execute the three CLIs sequentially to keep stdout deterministic; total runtime depends on external CLI latency.
- Scalability: N/A - this is a local workflow prompt and script, not a server.
- Security: The script must not inject untrusted prompt text into shell command strings. It should pass prompt content via stdin or argument arrays rather than string-built commands.
- Observability: The script stdout must clearly label each agent's answer and surface failures per agent without hiding successful outputs from other agents.
- Reliability / error tolerance: If one CLI fails, the script should still return any successful answers and include the failed agent's exit code and stderr summary.

---

## 5. High-Level Design

The implementation will add one new prompt family directory under the existing catalog asset tree. The JSON descriptor registers the prompt family, the Markdown prompt provides the host-agent operating procedure, and the PowerShell script provides the executable helper the prompt can reference. Because `Prompts._json_assets()` already discovers one-level nested JSON descriptors, no catalog loader changes are required.

The runner script remains a companion artifact rather than a loaded prompt value. The SDK prompt catalog will expose the `orchestrator.md` text through `Prompts().get(...)`; users who want the script can inspect the same catalog folder in the repository. To package the script with source distributions, `pyproject.toml` will extend prompt package data to include `*/*.ps1`.

```text
[User prompt]
    |
    v
[Host agent reads tri_cli_agent_synthesis.orchestrator]
    |
    v
[run_tri_cli_agent_synthesis.ps1]
    |-- codex exec    -> Codex answer
    |-- claude --print -> Claude Code answer
    `-- opencode run  -> opencode answer
    |
    v
[Structured stdout returned to host conversation]
    |
    v
[Host agent synthesizes final answer]
```

The personal prompt collection update is intentionally separate from the SDK commit. Once the catalog file exists at its stable GitHub path, the local `vidbyte-prompts` skill will add the link inside each existing mirrored elected-prompt block.

---

## 6. Detailed Design

### 6.1 Prompt Descriptor

**File(s):** `vidbyte/prompts/prompts/tri_cli_agent_synthesis/tri_cli_agent_synthesis.json`
**Type:** New file

#### What it does

Registers the `tri_cli_agent_synthesis` family and maps the `orchestrator` leaf prompt to `orchestrator.md`.

#### Interface / API

```json
{
  "name": "Tri-CLI Agent Synthesis",
  "description": "Prompt assets for running one request through Codex, Claude Code, and opencode as separate local CLI calls before synthesizing a final answer in the host conversation.",
  "key": "tri_cli_agent_synthesis",
  "prompts": {
    "orchestrator": {
      "path": "orchestrator.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/tri_cli_agent_synthesis/orchestrator.md"
    }
  }
}
```

#### Logic / Algorithm

1. `Prompts._json_assets()` discovers the descriptor in the nested family directory.
2. `Prompts._load()` reads the `orchestrator` prompt object.
3. `_resolve_prompt_text()` loads `orchestrator.md`.
4. `_validate_enum_sync()` verifies the enum contains `tri_cli_agent_synthesis.orchestrator`.

#### Edge Cases & Error Handling

- Missing `orchestrator.md` will raise the existing `ConfigurationError`.
- Missing enum registration will raise the existing `ConfigurationError`.
- The script is not referenced from the JSON descriptor because the prompt loader only accepts inline strings or Markdown prompt objects.

---

### 6.2 Orchestrator Prompt

**File(s):** `vidbyte/prompts/prompts/tri_cli_agent_synthesis/orchestrator.md`
**Type:** New file

#### What it does

Provides host-agent instructions for collecting independent Codex, Claude Code, and opencode answers and synthesizing a final answer for the current conversation.

#### Interface / API

```text
Prompt key: tri_cli_agent_synthesis.orchestrator
Direct import: tri_cli_agent_synthesis_orchestrator
Expected placeholder: {user_prompt}
Companion script: run_tri_cli_agent_synthesis.ps1
```

#### Logic / Algorithm

1. Preserve the user's original prompt exactly as the task input.
2. Run the companion script with that prompt.
3. Read the structured output sections for Codex, Claude Code, and opencode.
4. Treat each output as fallible candidate material.
5. Produce one final answer that integrates the strongest correct content and resolves contradictions.
6. Do not expose raw candidate answers unless the user explicitly asks for them.

#### Edge Cases & Error Handling

- If one agent fails, synthesize from the successful agents and mention that one backend failed only if relevant to the user.
- If all three agents fail, report the failure rather than fabricating a synthesized answer.
- If candidate outputs conflict, the host agent must use its judgment and local context instead of blindly voting.

---

### 6.3 Companion PowerShell Runner

**File(s):** `vidbyte/prompts/prompts/tri_cli_agent_synthesis/run_tri_cli_agent_synthesis.ps1`
**Type:** New file

#### What it does

Runs the user's prompt through the three local CLIs with default model and thinking settings, then prints stable Markdown sections containing each answer or failure.

#### Interface / API

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string]$Prompt,
  [string]$WorkingDirectory = (Get-Location).Path,
  [string]$CodexModel = "gpt-5.5",
  [string]$CodexThinking = "high",
  [string]$ClaudeModel = "opus-4.8",
  [string]$ClaudeThinking = "xhigh",
  [string]$OpencodeModel = "glm-5.2",
  [string]$OpencodeThinking = "max"
)
```

#### Logic / Algorithm

1. Validate that `codex`, `claude`, and `opencode` are available with `Get-Command`.
2. Invoke Codex non-interactively with `codex exec`, the configured model, a reasoning-effort config if supported, and prompt input via stdin.
3. Invoke Claude Code non-interactively with `claude --print --model <model> --effort <thinking>`.
4. Invoke opencode non-interactively with `opencode run --model <model> --variant <thinking>`.
5. Capture stdout, stderr, and exit code for each invocation independently.
6. Print a Markdown report with a summary table and fenced answer blocks.

#### Edge Cases & Error Handling

- If a CLI binary is missing, print a failed section for that agent and continue to the next one.
- If a CLI exits non-zero, preserve stderr in that agent's section and continue.
- Prompt text must not be interpolated into a command string.
- The exact Codex reasoning config key must be verified during implementation because `codex exec --help` exposes `-c key=value` but not the concrete thinking-effort key.

---

### 6.4 Prompt Enum

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds the enum member needed for prompt loader validation and typed SDK access.

#### Interface / API

```python
class Prompt(str, Enum):
    TRI_CLI_AGENT_SYNTHESIS_ORCHESTRATOR = "tri_cli_agent_synthesis.orchestrator"
```

#### Logic / Algorithm

1. Add the enum member near the other prompt family members.
2. Direct import generation automatically exposes `tri_cli_agent_synthesis_orchestrator`.

#### Edge Cases & Error Handling

- If the enum value differs from the JSON family and prompt key, catalog loading fails.

---

### 6.5 Package Data

**File(s):** `pyproject.toml`
**Type:** Modified

#### What it does

Ensures the companion PowerShell script is included with packaged prompt assets.

#### Interface / API

```toml
[tool.setuptools.package-data]
"vidbyte.prompts.prompts" = ["*.json", "*/*.json", "*/*.md", "*/*.ps1"]
```

#### Logic / Algorithm

1. Extend the existing package-data list with `*/*.ps1`.
2. Leave Markdown and JSON packaging unchanged.

#### Edge Cases & Error Handling

- If this is omitted, editable installs still see the script, but built packages may omit it.

---

### 6.6 Human Prompt Catalog

**File(s):** `vidbyte/prompts/README.md`
**Type:** Modified

#### What it does

Adds the new prompt family to the canonical human catalog consumed by the personal `vidbyte-prompts` skill.

#### Interface / API

```markdown
| Tri-CLI Agent Synthesis | `tri_cli_agent_synthesis` | orchestrator | [tri_cli_agent_synthesis/orchestrator.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/tri_cli_agent_synthesis/orchestrator.md) |
```

#### Logic / Algorithm

1. Add a quick-reference table row.
2. Add a matching descriptions section with the direct Markdown prompt link.
3. Update catalog count text if needed.

#### Edge Cases & Error Handling

- The link must be the direct Markdown prompt file, not the JSON descriptor, so the personal prompt skill can store the prompt link.

---

### 6.7 Local Vidbyte Prompt Collection

**File(s):** `C:\Users\422mi\.claude\skills\vidbyte-prompts\SKILL.md`, `C:\Users\422mi\.codex\skills\vidbyte-prompts\SKILL.md`, `C:\Users\422mi\.config\opencode\commands\vidbyte-prompts.md`, `C:\Users\422mi\.codeium\windsurf\skills\vidbyte-prompts\SKILL.md`
**Type:** Modified outside the SDK repository when each file exists

#### What it does

Adds the new prompt link to the elected prompt block in each local mirrored personal prompt collection.

#### Interface / API

```markdown
- **Tri-CLI Agent Synthesis / orchestrator** (`tri_cli_agent_synthesis.orchestrator`) - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/tri_cli_agent_synthesis/orchestrator.md
```

#### Logic / Algorithm

1. Check each mirror path for existence.
2. Insert the entry inside the `ELECTED-PROMPTS` block if the link is not already present.
3. Skip missing paths without failing the SDK implementation.

#### Edge Cases & Error Handling

- This change is intentionally local and will not be committed to the SDK repository branch.
- The local opencode command file may use Markdown command formatting rather than full skill frontmatter; only the elected-prompt block should be changed.

---

## 7. Data Model Changes

N/A - This change adds static prompt assets, an enum member, package-data configuration, and local skill links. No database schemas, Pydantic models, or persistent SDK data models are changed.

---

## 8. API Changes

N/A - No HTTP endpoints are added, modified, or deprecated. The SDK prompt API gains one enum value and one generated direct import through the existing prompt catalog mechanism.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/tri_cli_agent_synthesis/tri_cli_agent_synthesis.json` | Register the new prompt family |
| CREATE | `vidbyte/prompts/prompts/tri_cli_agent_synthesis/orchestrator.md` | Host-agent prompt for tri-CLI answer collection and synthesis |
| CREATE | `vidbyte/prompts/prompts/tri_cli_agent_synthesis/run_tri_cli_agent_synthesis.ps1` | Companion local runner script referenced by the prompt |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Register `tri_cli_agent_synthesis.orchestrator` |
| MODIFY | `pyproject.toml` | Package the companion PowerShell script with prompt assets |
| MODIFY | `vidbyte/prompts/README.md` | Add the new family to the canonical prompt catalog |
| MODIFY | `C:\Users\422mi\.claude\skills\vidbyte-prompts\SKILL.md` | Add local elected prompt link if the file exists |
| MODIFY | `C:\Users\422mi\.codex\skills\vidbyte-prompts\SKILL.md` | Add local elected prompt link if the file exists |
| MODIFY | `C:\Users\422mi\.config\opencode\commands\vidbyte-prompts.md` | Add local elected prompt link if the file exists |
| MODIFY | `C:\Users\422mi\.codeium\windsurf\skills\vidbyte-prompts\SKILL.md` | Add local elected prompt link if the file exists |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Codex CLI | Local `codex.ps1` | Runs the Codex candidate answer | CLI config key for high thinking must be verified |
| Claude Code CLI | Local `claude.exe` 2.1.183.0 | Runs the Claude Code candidate answer | Requested model alias may not exist locally |
| opencode CLI | Local `opencode.exe` | Runs the opencode candidate answer | Requested model string may require provider prefix |
| GitHub prompt URL | `https://github.com/cerredz/Vidbyte-SDK/blob/main/.../orchestrator.md` | Stored in catalog and local prompt skill | Link is stable only after the PR merges to `main` |

---

## 11. Rollout & Deployment

- The SDK change is additive and non-breaking.
- Implementation must happen in an isolated worktree after this design doc is approved.
- The SDK branch should be pushed as a draft PR targeting `main`.
- The local `vidbyte-prompts` skill update can happen after the catalog files exist, but the GitHub link will only resolve publicly after merge.
- Rollback is to revert the SDK prompt catalog commit and remove the local elected-prompt entry from mirrored skill files.

---

## 12. Open Questions

- [ ] Should the companion script use a Windows-first PowerShell implementation only, or should a POSIX shell equivalent be added later for non-Windows environments?
- [ ] What exact Codex CLI config key should represent "high thinking" for `codex exec` in the currently installed Codex CLI?
- [ ] Should opencode's default model be exactly `glm-5.2` as requested, or does the user's opencode provider configuration require a provider-prefixed model like `provider/glm-5.2`?
- [ ] Should the script run the three CLIs sequentially for deterministic output, or concurrently for latency? The proposed design uses sequential execution.

---

## 13. Alternatives Considered

### Alternative 1: Only Add A Markdown Prompt Without A Script

- What: Store all orchestration instructions in `orchestrator.md` and require the host agent to build commands manually each time.
- Why rejected: The original request explicitly asked for a script with model defaults defined in the script and located in the same folder.

### Alternative 2: Extend `multi_provider_aggregator`

- What: Add Codex, Claude Code, and opencode CLI behavior to the existing `multi_provider_aggregator` family.
- Why rejected: That family is provider-agnostic SDK prompt material for an aggregation pattern. The requested feature is a local CLI orchestration workflow and would add unrelated operational assumptions to an existing reusable family.

### Alternative 3: Build A First-Class SDK Runtime

- What: Add Python runtime code that shells out to the three CLIs and returns a structured SDK object.
- Why rejected: The user asked for a catalog prompt and script, not a new SDK execution abstraction. A runtime would need tests, public API design, and more error-surface commitments than this no-tests prompt-catalog change needs.
