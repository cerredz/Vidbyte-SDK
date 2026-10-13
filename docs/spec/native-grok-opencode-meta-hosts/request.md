---
slug: native-grok-opencode-meta-hosts
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-13 01:24 UTC
flags: none
---

# Request: GrokHost, OpencodeHost, MuseHost (Meta Muse Code), and GLM / DeepSeek backend profiles, with exhaustive error handling

## A. Every user prompt in this conversation, verbatim and in order

Two local `/effort` commands were also run. They are settings changes, not prompts.

**Prompt 1** (opening message, 2026-10-12 21:22 UTC):

````text
Can you view our "herdr-claude 2" claude code sessionsannd view the "CodexHost and ClaudeHost" session, understand what we are talking about implementing in the vidbyte-sdk/, and then come up with a list of 1) other native harnesses to integrate this with (grok, glm, deepseek, meta, opencode, etc), and then 2) an in-depth function list of every function that we can implement with these native harnesses
````

The assistant answered with a harness roster and a function catalog of about 480 functions. The parts that bind this run are copied verbatim in §C, "The catalog the user accepted", and the catalog's closing decision list is in §B.2.

**Prompt 2** (2026-10-13 01:24 UTC; the `/spec-pipeline` invocation, whose whole argument string was this text):

````text
great, can you focus on implementing grok, glm, deepseek, meta, and opencode harnesses for now. Make sure to extensively handle errors for every single function.
````

## B. Handoff block and decision ledger (verbatim, if present)

There is no `## HANDOFF` block. Two ledgers bind this run.

### B.1 Upstream "CodexHost and ClaudeHost" session: Re-entry card (verbatim)

Prompt 1 asked the assistant to read and follow this session. It is the design source this run extends. Two other pipelines are implementing it right now (see §C "Constraints and assumptions").

**Re-entry · harness-thread vocabulary**

Decided:
- **Where it lives:** in the SDK. Functions go in `vidbyte/harnesses/native/<host>/`, one tool per function in `vidbyte/tools/builtins/<host>/`, bundled in `toolsets/<host>.py`, and exposed over MCP through `mcp_server/`. Both hosts use their official SDK (openai-codex, claude-agent-sdk); features that only exist in a CLI run the CLI.
- **One host class per harness:** each owns its live processes and handles. Spawn returns a handle immediately, settings are spawn-request fields, and the existing Codex settings are reused.
- **Shared vocabulary:** shared verbs for cross-harness code, plus one `<host>.<problem>` error vocabulary with next steps. Tools return error results instead of raising.
- **Budgets:** Codex uses a goal budget plus our interrupt; Claude uses its built-in `max_budget_usd`, `max_turns`, `task_budget` and thinking budget.
- **⚑ group:** the TypeScript-only Claude controls are reachable from Python only through a private method (decision pending, below).

Open:
- The verify items above.
- The policy on plan-backed (subscription) usage in a paid product, for both OpenAI and Anthropic.

Needs you:
1. Should the ⚑ functions wait until the Python SDK exposes them? Building them now means using the private call under an exact pin plus contract tests. Default: leave them out of the first PRs.
2. Should PR 1 contain only CodexHost's ★ set, with PR 2 adding ClaudeHost's ★ set and extracting the shared pieces (error envelope, tool base, handle registry)? Default: yes.
3. Should both hosts default to the user's installed binary (`codex_bin` / `cli_path`, with a minimum-version check) instead of the SDK's bundled one? Default: yes.

*Reply "go" to accept all defaults.*

Next: on "go", I write the HANDOFF for PR 1: CodexHost's 14 ★ functions, their tools, the error mapper and contract tests.

The user answered that card in the upstream session with a request for two parallel PRs, one for CodexHost and one for ClaudeHost, accepting defaults 1 and 3. The codex-host pipeline recorded that answer as:
- Q1, the ⚑ functions: left out.
- Q2: superseded by "two PRs in parallel, no shared base module".
- Q3: the host defaults to the user's installed binary, with a minimum-version check.

### B.2 This conversation's catalog "Decisions for you" (verbatim) and the user's reply

**To check before any PR:**
1. Where Grok reports usage: summary.json, ACP `usage_update`, or only OTEL?
2. Does an opencode revert restore files? Does `prompt_async` on a busy session queue the message or reject it?
3. Does Amp's `--stream-json-input` steer mid-turn?
4. Which ACP agents actually use the client's fs and terminal?
5. The undocumented quota endpoints (Z.ai, Copilot's internal one).

**Decisions for you:**
1. **Build `AcpHost` right after Codex and Claude, with Grok as its first profile?** My default is yes: Grok is installed and ACP-native, and the same class then covers Gemini, Kimi, Qwen, Copilot, Goose and the rest.
2. **Should opencode be the next dedicated host after that?** My default is yes. It has the richest local API, reports dollars, and is the most complete native route to GLM, DeepSeek, Kimi and Llama.
3. **Ship GLM and DeepSeek as backend profiles on ClaudeHost, and skip ZCode and `dsh` for now?** My default is yes.

The user's reply is Prompt 2. It begins "great", which accepts the catalog with its three defaults. It then narrows the work: "focus on implementing grok, glm, deepseek, meta, and opencode harnesses for now". §C "Key decisions" records how that narrowing is applied.

## C. Structured conversation notes

### Key decisions

- **The five targets are three hosts and two backend profiles.** This follows Prompt 2 and the catalog's tiers.
  - **grok → `GrokHost`**, driving Grok Build (xAI's coding CLI), in `vidbyte/harnesses/native/grok/`.
  - **opencode → `OpencodeHost`**, in `vidbyte/harnesses/native/opencode/`.
  - **meta → `MuseHost`**, driving Meta's Muse Code CLI (`muse`), in `vidbyte/harnesses/native/muse/`. The catalog says "Llama has no coding CLI", so "meta" means Muse Code.
  - **glm and deepseek → backend profiles, not hosts**, in `vidbyte/harnesses/native/backends/`. These are model endpoints that existing harnesses point at. The catalog's decision 3 (default yes, accepted by "great") ships them as profiles and skips Z.ai's ZCode and DeepSeek's `dsh` harness. ZCode's headless mode is undocumented and `dsh` is an early preview.
  - Why: each of these is "a harness the user can drive" or "a model the user can point a harness at", matching the catalog's Tier A and Tier D.

- **Placement and shape follow the upstream ledger (§B.1), unchanged.**
  - Functions go in `vidbyte/harnesses/native/<host>/`.
  - Each function gets one tool in `vidbyte/tools/builtins/<host>/`. Copy the `builtins/sessions/` layout: `_base.py` with shared state, one file per group of tools, and `descriptions.py`.
  - Tools are bundled in `vidbyte/tools/toolsets/<host>.py`.
  - Tools are exposed over MCP through the existing `vidbyte/mcp_server/`. Add code there only if it cannot already serve a toolset.

- **One host class per harness.**
  - It is an async context manager that owns its live processes, servers and handles.
  - Each function is a method on it. Module-level functions wrap the one-shot ones.
  - Spawn returns a handle immediately, and `wait_<host>_turn` collects the result.
  - Settings are fields of the spawn request, never one function per setting.
  - Names follow `<verb>_<host>_<noun>`, mirroring the CodexHost and ClaudeHost names so cross-harness code can share verbs (catalog §2.1).

- **First-PR scope is the catalog's ★ set for each target.** This applies Prompt 2's "for now" the same way the upstream Codex PR did ("PR 1: CodexHost's 14 ★ functions"). Non-★ functions are follow-ups. See Q-1.
  - **GrokHost, 10 functions:** `check_grok_ready`, `list_grok_models`, `spawn_grok_session`, `run_grok_once`, `continue_grok_session`, `fork_grok_session`, `list_grok_sessions`, `search_grok_sessions`, `wait_grok_turn`, `interrupt_grok_turn`.
  - **OpencodeHost, 18 functions:**
    - Readiness and providers: `check_opencode_ready`, `list_opencode_models`, `list_opencode_providers`, `get_opencode_provider_auth`.
    - Session lifecycle: `spawn_opencode_session`, `continue_opencode_session`, `fork_opencode_session`, `revert_opencode_session`, `unrevert_opencode_session`.
    - Session reads: `list_opencode_sessions`, `get_opencode_session`, `get_opencode_session_messages`, `get_opencode_message`, `get_opencode_session_diff`.
    - Turn control and extras: `wait_opencode_turn`, `interrupt_opencode_turn`, `track_opencode_session_usage`, `add_opencode_mcp_server`.
  - **MuseHost, 12 functions:**
    - Readiness and models: `check_muse_ready`, `list_muse_models`.
    - Sessions: `spawn_muse_session`, `continue_muse_session`, `fork_muse_session`, `list_muse_sessions`, `read_muse_session`, `page_muse_session`.
    - Turn control and usage: `steer_muse_turn`, `interrupt_muse_turn`, `wait_muse_turn`, `track_muse_session_usage`.
  - **Backend profiles, for GLM (Z.ai) and DeepSeek only:**
    - The ★ set: `list_harness_backends`, `build_claude_backend_env`, `check_backend_ready`, `check_backend_compat`, `get_deepseek_balance`.
    - Plus `build_opencode_backend_provider`, a non-★ function pulled in by the orchestrator. Why: Prompt 2 asks to "implement" GLM and DeepSeek. ClaudeHost is not on `main` yet, so OpencodeHost is the only host in this PR that can actually run a GLM or DeepSeek model. Without this function, the profiles would have no runnable route.
    - Kimi, MiniMax, Qwen, the Meta Model API and xAI profiles are follow-ups.
  - The tool tags (R / W / int) come from the catalog tables below.

- **Grok transport.** Live sessions use ACP over stdio (`grok agent stdio`). `run_grok_once` uses `grok -p --output-format json`. Admin reads (models, sessions list or search) use the CLI where ACP has no method.
  - Per the catalog, accepted by "great", decision 1 builds an `AcpHost` with Grok as its first profile. Prompt 2 says to focus on Grok "for now", and the upstream ledger rejected "a shared base class in PR 1: it would have only one implementation; extract it once [a second host] exists".
  - So the orchestrator's reading is: the ACP client code in this PR is protocol-generic, with no Grok names in the message layer. It is not exported as a public `AcpHost`, and the generic `*_acp_*` functions from catalog §2.8 are follow-ups. See Q-3 for where the code sits.

- **opencode transport:** HTTP to `opencode serve`, using `httpx`, which is already a required dependency in `pyproject.toml` (`httpx>=0.27`). The PyPI Python client for opencode is a stale alpha, so it is not used.

- **Muse transport:** MSP, Muse's JSON-RPC over stdio from `muse serve`, which is shaped like Codex's app-server. On this machine, Muse runs inside WSL (see "Research facts"). The official Python SDK `muse-code-sdk` is the alternative (Q-2).

- **GLM / DeepSeek routes:**
  - `build_claude_backend_env(backend, model)` returns the environment mapping Claude Code needs to use that endpoint. It imports nothing from ClaudeHost, which is not on `main`; a later ClaudeHost consumes the mapping.
  - `build_opencode_backend_provider(backend)` returns the opencode provider configuration that OpencodeHost applies when it starts its server.
  - `check_backend_compat` rejects request features that the endpoint silently ignores, before any money is spent.

- **Errors are the user's explicit requirement in both sessions.**
  - Prompt 2 here: "Make sure to extensively handle errors for every single function."
  - Upstream Prompt 2, as recorded by the codex-host pipeline: "return semantic error messages if something goes wrong, each funciton shoulllld make sure to handle errors".
  - The vocabulary is `<host>.<problem>` (`grok.*`, `opencode.*`, `muse.*`, `backend.*`). Each code carries a next step the caller is told. Shared problems reuse the upstream names exactly (see "The shared error vocabulary" below).
  - Tool wrappers return an error `ToolResult` instead of raising, matching the session tools' convention.
  - Checks run before any money is spent (upstream ledger and catalog §2.13).

- **Tool permissions:** each tool declares the R (READ) or W (WRITE) shown in the catalog. The default `PermissionPolicy` allows only SAFE and READ, so WRITE (spending) tools need an explicit opt-in. "int" functions are not tools.

- **Never expose these as tools**, in any form, including a spawn-request field a tool can set:
  - Grok `--always-approve`, the ACP `_meta.yoloMode`, and permission mode `bypassPermissions`.
  - opencode `--dangerously-skip-permissions`.
  - Muse `--yolo`.
  - Any equivalent "approve everything" setting.
  - This comes from catalog §2.13. Python-level access is Q-12.

### Rejected alternatives
- **A public generic `AcpHost` with the `*_acp_*` functions in this PR.** Prompt 2 narrows the scope to five targets "for now", and the upstream ledger rejects a base class with one implementation. It stays a follow-up. The protocol code is still written so it can be lifted later.
- **ZCode and `dsh` as hosts.** Rejected in catalog decision 3: one has an undocumented headless mode and the other is a preview.
- **GLM and DeepSeek as hosts.** They are endpoints, not harnesses.
- **The PyPI opencode Python client.** It is a stale alpha; plain HTTP via the existing `httpx` is used instead.
- **A function per setting.** Settings are spawn-request fields (upstream ledger).
- **A blocking spawn.** Spawn returns a handle (upstream ledger). `CodexHarnessAgent` already cancels its own custom-tool calls after 300 s, which is the evidence the codex-host pipeline cited.
- **Kimi, MiniMax, Qwen, Meta Model API and xAI backend profiles, and the Kilo or MiMo opencode profiles.** These are follow-ups, outside "grok, glm, deepseek, meta, and opencode … for now".

### Constraints and assumptions

- **Three parallel PRs touch the same new folder.**
  - The codex-host pipeline (worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host`) and the claude-host pipeline (worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host`) both started from `678136bd4358bcf9f120504cecd818d36a3d46fe` and are still running.
  - This PR starts from `aa8c380c4cd1d5791526dd545f5ef1020b28a5cc` (origin/main, 2026-10-12).
  - No PR may depend on another PR or reference code only another PR creates. In particular, nothing here imports `vidbyte.harnesses.native.codex` or `vidbyte.harnesses.native.claude`.
  - Whichever PR merges later catches up by merging `origin/main` into its branch. Never rebase after the first push, and never force-push.

- **Shared-file contract.** This PR obeys the contract the codex-host and claude-host pipelines both follow, so the later merges stay trivial.

  - **`vidbyte/harnesses/native/__init__.py`.**
    - Create it with exactly the content of the fenced block below, without the fence lines. That means LF line endings, a final newline after the closing `"""`, and nothing else: no imports and no `__all__`.
    - The file's SHA-256 must be `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`. The orchestrator checks it.
    - Copy it byte for byte; do not reword, rewrap or reorder it. The module text says "wrapping that harness's official SDK"; leave that wording alone even where a host here uses HTTP or raw JSON-RPC.
    - If a gate rejects these bytes, report BLOCKED with the rule ID and output.
    - Host classes are imported from their own subpackage, for example `vidbyte.harnesses.native.grok`.

`````python
"""FILE: vidbyte/harnesses/native/__init__.py

PURPOSE: Marks vidbyte/harnesses/native as the package of native coding-harness hosts: one subpackage per coding harness, each wrapping that harness's official SDK in small, atomic functions on a host class.
ROLE IN CODEBASE: A parent package only. Callers import a host from its own subpackage, never from this module, so this module imports nothing and names no harness.
ARCHITECTURE NOTE: Each harness subpackage owns its host class, its vendor SDK import, and its errors. Nothing here imports a vendor SDK, so importing this package never requires an optional extra.
COMMON MODIFICATION PATTERNS: A new harness adds its own subpackage beside the existing ones and leaves this module unchanged.
KNOWN EDGE CASES: None; the module defines no names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: None of its own; each harness subpackage has its own tests.
"""
`````

  - **No `vidbyte/harnesses/native/README.md`.** The codex-host scout verified that no lint rule requires a README in every folder: A009 only caps README size, and C015 forbids shipping a README in the wheel.

  - **No shared test files.**
    - Tests live only in files or folders whose names contain this PR's own targets, for example `tests/features/grok_host/`, `tests/features/opencode_host/`, `tests/features/muse_host/` and `tests/features/native_backends/`.
    - Feature packs under `tests/features/` have no `__init__.py`.
    - Every new test `.py` needs its own A001 header.

  - **`vidbyte/lib/enums/failure.py`.**
    - The Codex PR appends its `CODEX_*` members immediately after the last existing `CODEX_*` member.
    - The Claude PR adds one `CLAUDE_*` block that is not adjacent to the end of the `CODEX_*` block. Its own request suggests "directly before the first existing `CODEX_*` member".
    - This PR adds its blocks (`GROK_*`, `OPENCODE_*`, `MUSE_*`, backend codes) somewhere that touches neither of those two spots. The scout reports the candidate positions.

  - **Export lists and indexes are append-only:** `vidbyte/lib/enums/__init__.py`, `vidbyte/__init__.py`, `vidbyte/tools/builtins/__init__.py`, `vidbyte/tools/toolsets/__init__.py`, `REPO_MAP.md`, `vidbyte/harnesses/README.md`, `contracts/sdk-public-api.json`, and any failure-classification table. Expect a small conflict at the later merges.

  - **`pyproject.toml`.** Only the Claude PR changes it, by adding a `claude` extra. This PR leaves it unchanged unless Q-2 resolves otherwise with evidence.

- **The user's machine** (verified 2026-10-12):
  - **Grok Build 1.0.13** is at `C:/Users/422mi/.grok/bin/grok.exe`.
  - **opencode 1.18.31** is installed via scoop and found with `shutil.which("opencode")`. Kilo 7.5.6 is also installed but out of scope.
  - **Muse Code 1.0.1** runs inside the WSL distro `MuseUbuntu1`.
    - `C:/Users/422mi/.local/bin/muse.cmd` contains `wsl.exe -d MuseUbuntu1 -- /usr/local/bin/muse %*`.
    - Git Bash's `muse` lookup does not find the `.cmd` shim; `cmd //c` or `wsl.exe` directly does.
  - **Latest releases are newer:** Grok 1.0.13 is current, opencode 1.19.0, Muse 1.4.6. Muse 1.4 adds methods that 1.0.1 lacks.

- **Live calls spend money or plan quota.**
  - Automated tests make no live model calls, and CI has no vendor credentials. Tests use fake transports: a fake ACP or MSP peer process, or `httpx.MockTransport`. They also use recorded fixtures.
  - Read-only protocol handshakes that start no model turn may be run by S1 and S2 to verify facts and record fixtures. Allowed:
    - ACP `initialize`, `session/list`, and `grok models`;
    - `opencode serve` bound to 127.0.0.1, plus GET reads (health, providers, session list);
    - MSP `initialize`, `model/list` and `session/list`.
  - Never send a prompt in those handshakes: no `session/prompt`, `turn/start`, `prompt_async`, `POST …/message`, `grok -p`, `opencode run` or `muse exec`.
  - Scrub every secret, token and absolute user path before committing a fixture.

- **Secrets:**
  - Never read or print `~/.grok/auth.json`, opencode's `auth.json`, Muse credentials, or any `*_API_KEY` value.
  - Tokens and keys never go on argv. Pass them through environment variables or stdin.
  - Error messages, logs and fixtures never contain a secret.

- **Do not send the user's account email** to any external service.

- **Draft PR only.** Never merge, never mark ready.

- **AGENTS.md binds every change:**
  - The placement rules.
  - The five coding principles.
  - `docs/` is opaque.
  - The full local gate `python scripts/run_ci.py` must pass before anything is called complete.

### Clarifications and answers
- **Q (catalog decision 1):** "Build `AcpHost` right after Codex and Claude, with Grok as its first profile?" A (Prompt 2): "great, can you focus on implementing grok, …". The orchestrator applies this as described in "Key decisions → Grok transport".
- **Q (catalog decision 2):** "Should opencode be the next dedicated host after that?" A: "great". Yes, `OpencodeHost`.
- **Q (catalog decision 3):** "Ship GLM and DeepSeek as backend profiles on ClaudeHost, and skip ZCode and `dsh` for now?" A: "great". Yes. They are profiles; ClaudeHost consumes `build_claude_backend_env` later, and OpencodeHost consumes `build_opencode_backend_provider` now.
- **Q (catalog, "To check before any PR"):** These five items were never answered by the user. The ones that bind this PR are Q-6, Q-7 and Q-10.

### Terminology
- **host:** the class (`GrokHost`, `OpencodeHost`, `MuseHost`) that owns one harness's live processes or server and the sessions or turns it started.
- **native harness:** the vendor's coding-agent executable (`grok`, `opencode`, `muse`), as opposed to the SDK's own `Harness` run envelope in `vidbyte/harnesses/`.
- **backend profile:** a `HarnessBackend` record that points an existing harness at a model endpoint: base URL, which env var holds the key, which model fills each slot, the compaction window, the timeout, unsupported features and allowed harnesses. GLM and DeepSeek are profiles.
- **handle:** what spawn returns right away. It names a running turn inside the host that started it.
- **★ / ✗ / R / W / int:** the catalog legend.
  - ★ = first PR.
  - ✗ = a plain function that must never be a tool.
  - R / W = the tool's READ or WRITE permission.
  - int = internal, not a tool.
- **ACP:** Agent Client Protocol, JSON-RPC 2.0 over stdio. Grok speaks it via `grok agent stdio`.
- **MSP:** Muse Server Protocol, JSON-RPC over stdio via `muse serve`. It is shaped like Codex's app-server.
- **session / turn:** Grok, opencode and Muse all say "session". A turn is one prompt and its response; one turn runs at a time per session.
- **next step:** the one-line instruction carried by every error code that tells the caller what to do (install, log in, wait until a reset time, pick from a list, and so on).

### Implementation hints

- **Nearest siblings to copy:**
  - `vidbyte/agents/codex/` (`CodexHarnessAgent`): transport isolation, error translation, and the 300 s custom-tool cancel.
  - `vidbyte/tools/builtins/sessions/`: tool layout, `_base.py` binding shared state, `descriptions.py`.
  - `vidbyte/tools/toolsets/coding.py`: the toolset, and the exact A001 header form at lines 1-12.
  - `vidbyte/tools/mcp/transport.py`: stdio JSON-RPC to a child process (the MCP client), and the Windows launcher precedent, `shutil.which` at lines 197-201. It may be reusable for ACP and MSP framing (Q-3).
  - `vidbyte/lib/dataclasses/codex.py` and `vidbyte/lib/enums/codex.py`: validated frozen, slotted settings records.
  - `vidbyte/lib/enums/failure.py`: `FailureCode`.
  - `vidbyte/lib/constants/codex.py:95-174`: failure classification rows. Each new `FailureCode` may need a row in a table like this; the scout must find what is required.

- **Existing key names to reuse** (`vidbyte/lib/registries/models.py:90-107`):
  - `ModelProvider.DEEPSEEK` → `DEEPSEEK_API_KEY`, endpoint `https://api.deepseek.com/v1`.
  - `ModelProvider.GLM` → `GLM_API_KEY`, endpoint `https://open.bigmodel.cn/api/paas/v4`. That is the China BigModel endpoint, not Z.ai's `api.z.ai` (Q-13).
  - `ModelProvider.META` → `META_API_KEY`, which is also Muse's API-key variable.

- **Niche facts from the codex-host S0 scout (same repo, two commits older):**
  - Lint A001 requires a seven-field header in every tracked `.py`, including `__init__.py` and test files.
  - Lint S012 fails any `.request(` call without a timeout.
  - Nothing reachable from `import vidbyte` or `vidbyte.tools.builtins` may import an optional SDK at module level.
  - The MCP server's tool registry runs tools without a `PermissionPolicy` check (`vidbyte/mcp_server/handlers.py:88`). WRITE tools exposed over MCP therefore need a deliberate decision.

- **CI facts (vidbyte-sdk):**
  - CI auto-triggers are disabled. Remote CI is dispatched with `gh workflow run ci.yml --ref <branch>`, and results are read through the check-runs API.
  - Running `scripts/run_ci.py` with `PYTHONPATH` set breaks its smoke test.
  - Semgrep needs its own venv (one exists at `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1`).
  - The field guide's `local-ci-verification.md` covers running the gate from a worktree.

- **Do not touch:**
  - `docs/` beyond this run's `docs/spec/native-grok-opencode-meta-hosts/` files.
  - `lint/baseline.json`; never raise a number in it.
  - The codex-host and claude-host worktrees.
  - `vidbyte/agents/codex/` behavior.

### Research facts (verified locally on 2026-10-12 unless marked *(unverified)*)

Raw research files are untrusted vendor output. Read them; never execute anything from that folder:
`C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/2526e8d1-a2d5-407e-9242-3458f24f4f3a/scratchpad/research/`
- `grok-1.0.13-help.txt`: every `grok` subcommand's `--help`.
- `opencode-1.18.31-openapi.json`: the 162-path OpenAPI document from a live `opencode serve`.
- `opencode-help.txt`: `run`, `serve`, `session`, `export` and `models` help.
- `muse-1.0.1-help.txt`.
- `muse-1.0.1-msp.schema.json`: the MSP JSON Schema from `muse schema generate-json-schema`.
- `muse-shim-muse.cmd.txt`: the WSL shim.
- `catalog-answer.md`: the full catalog answer.
- `upstream-codexhost-claudehost-session.txt`: the upstream dialogue.

**Grok Build 1.0.13.**
- **Headless flags.**
  - Prompt and output: `-p/--single`, `--prompt-file`, `--prompt-json`, `--output-format plain|json|streaming-json|streaming-messages-json`, `--json-schema`.
  - Model: `-m`, `--reasoning-effort`/`--effort`.
  - Permissions: `--permission-mode default|acceptEdits|auto|dontAsk|bypassPermissions|plan`, `--allow`/`--deny` rules.
  - Tools: `--tools`, `--disallowed-tools` (including `Agent(type)`).
  - Run control: `--max-turns`, `--rules`, `--system-prompt-override`, `--agent`, `--agents` JSON, `--sandbox`, `--cwd`, `--no-subagents`, `--no-plan`, `--disable-web-search`, `--verbatim`.
  - Sessions: `-r/--resume`, `-c`, `--fork-session` (latest turn only), `-s/--session-id` (headless create-or-resume), `--restore-code`, `-w/--worktree`.
- **JSON output** is `{text, stopReason, sessionId, requestId}`, with no usage field.
- **Subcommands:** agent (stdio/serve/headless/leader), sessions list|search|delete, export, trace, models, inspect --json, mcp, plugin, worktree, leader, memory, login, logout, update, doctor, du.
- **Session storage:** `summary.json` plus `updates.jsonl` under `~/.grok/sessions`. Where usage is reported is *(unverified)* (Q-6).

**ACP** (schema v1.25.0, 2026-10-09; wire `protocolVersion` 1).
- **Agent methods:**
  - initialize, authenticate, logout.
  - session/new, load, resume, list, close, delete, prompt.
  - session/cancel (a notification).
  - session/set_mode, session/set_config_option.
  - Unstable: session/fork, providers/*, systemPrompt.
  - `session/set_model` was removed from the schema on 2026-06-01, but many agents still answer it.
- **Client methods:** session/request_permission, fs/read_text_file, fs/write_text_file, terminal/*, elicitation/create.
- **`session/update` variants:** agent_message_chunk, agent_thought_chunk, tool_call, tool_call_update, plan, available_commands_update, current_mode_update, config_option_update, session_info_update, usage_update{used,size,cost}, notice, compaction_update.
- **Error codes:** -32000 auth required, -32601 method not found, -32800 request cancelled, -32002 resource not found.
- **Stop reasons:** end_turn, max_tokens, max_turn_requests, refusal, cancelled.
- **Grok specifics:** Grok's ACP entry point is `grok agent stdio`, and `session/new` accepts `_meta.yoloMode`, which is never exposed.
- **Python SDK:** PyPI `agent-client-protocol` 0.12.1 (`import acp`, `spawn_agent_process`); it is not installed.

**opencode 1.18.31.**
- **Server:** `opencode serve`, with basic auth via `OPENCODE_SERVER_USERNAME`/`OPENCODE_SERVER_PASSWORD`.
- **v1 endpoints** (all present in the dump):
  - Sessions: `POST /session`, `GET /session`, `GET /session/status`, `GET /session/{id}`.
  - Turns and history: `POST /session/{id}/prompt_async`, `POST …/fork`, `POST …/abort`, `POST …/revert`, `POST …/unrevert`, `GET …/message`, `GET …/diff`.
  - Server-wide: `GET /event` (SSE), `GET /global/health`, `GET /config/providers`, `GET /provider/auth`, `POST /mcp`.
- **v2 endpoints:** `/api/session/{id}/wait`, `/interrupt`, `/compact`, `/model`, `/agent`, `/context`, `/prompt`, `/permission…`, `/question…`, and `/revert/stage|commit|clear`.
- **Cost and tokens:** Session and AssistantMessage objects carry `cost` and `tokens`.
- **`opencode run --format json` events:** step_start, step_finish (with cost and tokens), text, reasoning, tool_use, error.
- **Unverified behaviour:**
  - Whether revert restores files *(unverified)*.
  - Whether `prompt_async` on a busy session queues or rejects *(unverified)* (Q-7).
- **Versions:** latest is 1.19.0. Kilo is an API-identical fork, out of scope.

**Meta Muse Code 1.0.1 (MSP).**
- **Entry points:** `muse serve` (stdio JSON-RPC).
  - Official Python SDK: `muse-code-sdk` (`spawn_msp_connection`, `.command(method, params)`), not installed.
  - One-shot: `muse exec --json`, with `--output-schema` (Meta provider only), `--approval-mode`, `--reasoning-effort`, `--disable-write`, `--disable-shell`, `--max-model-steps` and `--session-id`.
- **Auth:** `META_API_KEY` or `muse login`.
- **MSP 1.0.1 methods:**
  - approval/decide, approval/listPending.
  - model/list.
  - session/start, resume, fork, list, read, compact, setModel, setApprovalMode, userShell.
  - subagent/close, followupTask, interrupt, readResult, reopen, resume, sendMessage, stop.
  - turn/start, cancel, interrupt, steer, unqueue.
  - userInput/answer, cancel, clarify.
  - view/page, unsubscribe.
- **MSP 1.0.1 notifications:**
  - session/tokenUsage, contextUsage, goalChanged, todoListChanged, modelChanged, approvalModeChanged, branchChanged.
  - turn/started, completed, retracted, retryScheduled, unqueued.
  - item/started, delta, completed, updated.
  - approval/requested, resolved, updated.
  - userInput/requested, settled.
  - view/gap.
- **Muse 1.4 additions:** usage/read, session/rename, setReasoningEffort, sideChat, workflow/*, skill/*, plugin/*, goal/*.
- **WSL caveats:**
  - Paths must be translated (`C:\` ↔ `/mnt/c`).
  - Killing `wsl.exe` may not kill the `muse` process inside the distro, so the host needs an MSP interrupt and close before the kill, or a kill inside WSL.

**GLM (Z.ai).**
- **Endpoints:** Anthropic-compatible `https://api.z.ai/api/anthropic`; OpenAI-compatible `https://api.z.ai/api/coding/paas/v4`.
- **Claude Code environment:**
  - `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `API_TIMEOUT_MS=3000000`.
  - `ANTHROPIC_DEFAULT_OPUS_MODEL` and `ANTHROPIC_DEFAULT_SONNET_MODEL` = `glm-5.3[1m]`; `ANTHROPIC_DEFAULT_HAIKU_MODEL` = `glm-5.3-flash[1m]`.
  - `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.
- **Quota endpoint:** `GET https://api.z.ai/api/monitor/usage/quota/limit` is undocumented and out of scope.
- **Coding Plan restriction:** the plan may be used only in these tools: ZCode, Claude Code, Codex, OpenCode, Pi, Cursor, Cline, TRAE, Qoder, Droid, Kilo, Roo, Crush, Goose and Eigent. Grok and Muse are not listed. That is what `backend.harness_not_allowed` exists for.

**DeepSeek.**
- **Endpoint:** Anthropic-compatible `https://api.deepseek.com/anthropic`.
- **Models:** `deepseek-flash` (V4.1-Flash, 1M context) and `deepseek-v4-pro`. On the Anthropic-compatible endpoint, `claude-opus*` maps to v4-pro and sonnet and haiku map to flash.
- **Claude Code environment:** `ANTHROPIC_MODEL=deepseek-flash[1m]`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432`.
- **Silently ignored fields:** mcp_servers, cache_control, container, top_k, service_tier, anthropic-beta (except Files), disable_parallel_tool_use, thinking.budget_tokens, and `is_error` on tool results.
- **Unsupported content:** document and search_result blocks.
- **Balance:** `GET https://api.deepseek.com/user/balance` with a Bearer key returns `{is_available, balance_infos[{currency,total_balance,granted_balance,topped_up_balance}]}`.

### The shared error vocabulary (from the upstream design; this PR reuses the names exactly)

Each code is `<host>.<problem>`, so cross-harness code can branch on the problem without caring which host raised it. Upstream table (codex-host `request.md`, "One error vocabulary for both hosts"):
- not_installed, version_unsupported, not_signed_in, auth_mode_unsupported.
- usage_limited, billing_error, model_unknown.
- session_not_found, session_busy, budget_exhausted, api_error, permission_denied.
- mcp_server_failed, checkpointing_disabled, sandbox_not_ready, schema_violation.
- process_exited, protocol_mismatch.

Host-specific additions already named upstream or in the catalog: `turn_timed_out`, `capability_missing` (for example fork when the peer lacks it; must fail before money is spent), `server_unreachable` (opencode) and `wsl_unavailable` (Muse). For backends: `feature_unsupported` and `harness_not_allowed`.

The catalog §2.13 (verbatim below) used four different names for problems the upstream table already names. The upstream names win:

| Catalog name | Upstream name used here |
|---|---|
| `binary_missing` | `not_installed` |
| `binary_unsupported` | `version_unsupported` |
| `host_exited` | `process_exited` |
| `protocol_changed` | `protocol_mismatch` |

ACP wire errors map onto `grok.<problem>` codes, not onto an `acp.*` namespace, because there is no AcpHost in this PR:

| ACP wire error | Grok code |
|---|---|
| -32000 | `grok.not_signed_in` |
| -32601 | `grok.capability_missing` |
| -32800 | the interrupt path |
| -32002 | `grok.session_not_found` |

The spec author may add a problem only when no listed one fits, and must say why.

### The catalog the user accepted (verbatim excerpts from the answer to Prompt 1)

**The five targets, as presented:**

| You said | What exists in Oct 2026 | How to integrate it |
|---|---|---|
| **grok** | **Grok Build 1.0.13, installed.** It's ACP-native (`grok agent stdio`) and copies Claude Code on purpose: the same `--permission-mode` values, `--fork-session`, `--json-schema` and `Bash(cmd:*)` rules. | A `GrokHost` that drives live sessions over ACP and one-shot runs with `grok -p --output-format json` |
| **glm** | Z.ai has its own harness, **ZCode 3.15** (open-sourced in September; its headless mode is undocumented). Z.ai's documented route is the GLM Coding Plan through Claude Code, Codex, opencode, Pi, Droid or Kilo. | A **backend profile**, not a host (§2.11). Revisit ZCode later. |
| **deepseek** | **DeepSeek Harness `dsh`** is an early preview with no documented headless mode. The real route is the Anthropic-compatible endpoint, `api.deepseek.com/anthropic`. | A backend profile, plus a guard for the features that endpoint silently ignores (MCP servers, `cache_control`, documents) |
| **meta** | **Muse Code (`muse`)**, launched 2026-08. **It's installed here: 1.0.1, running inside WSL (`MuseUbuntu1`).** Its protocol (MSP) is shaped like Codex's app-server, and it has an official Python SDK, `muse-code-sdk`. Llama has no coding CLI. | A `MuseHost` that copies the CodexHost pattern |
| **opencode** | **1.18.31, installed.** `opencode serve` exposes about 180 HTTP endpoints. Kilo 7.5.6 (also installed) and Xiaomi MiMo Code are forks of it. | An `OpencodeHost` over HTTP, with a Kilo profile |

**§2.1 cross-host matrix:**

| Verb | Codex | Claude | Grok | opencode / Kilo | Pi | Droid | Amp | Muse | ACP (generic) |
|---|---|---|---|---|---|---|---|---|---|
| Live transport | app-server | SDK, 1 process per session | ACP stdio | HTTP, 1 server per directory | RPC JSONL, 1 process per session | stream-jsonrpc / `droid-sdk` | stream-json in and out | MSP | ACP |
| One-shot | `exec --json` | `-p` json | `-p --output-format json` | `run --format json` | `-p --mode json` | `exec -o json` | `-x --stream-json` | `exec --json` | n/a |
| Typed output | `output_schema` | `--json-schema` | `--json-schema` | validate locally | validate locally | validate locally | validate locally | `--output-schema` (Meta models only) | per agent |
| Resume | ✓ | ✓ | `-r`, or `-s` (creates if missing) | ✓ | `--session` | `-s` | `threads continue` | `session/resume` | `session/resume` or `load` |
| **Fork** | from any turn | from any message, offline | latest turn only | `fork(messageID)` | `fork(entryId)`, `clone` | `fork` | **✗** | `session/fork` | `session/fork` (unstable) |
| **Rewind** | conversation | conversation + files | ✗ (TUI only) | `revert` / `unrevert` (+ staged revert, v2) | tree navigation | `rewind(restore files)` | ✗ | (1.4) | ✗ |
| Steer mid-turn | `turn/steer` | queue | ✗ | `prompt_async` while busy *(verify)* | `steer` + `follow_up` | *(verify)* | `--stream-json-input` *(verify)* | `turn/steer` | ✗ |
| Interrupt | ✓ | ✓ | `session/cancel` | `abort` | `abort` | `interrupt` | ✓ | `turn/interrupt` | `session/cancel` |
| Usage in $ | tokens only | **$** | *(verify)* | **$** + tokens | **$** + tokens | tokens + credits | credits | tokens (cost in 1.4) | `usage_update` |
| Quota windows | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | `amp usage` | 1.4 `usage/read` | Kiro, Kimi extensions |
| Control the host's own subagents | config only | `--agents` | `--agents`, personas | child sessions (read) | extensions | **`--mission`** | n/a | **`subagent/*` (full control)** | `subagent_update` (unstable) |
| Ask-user channel | approvals | `canUseTool` | permission requests | **`question.*`** + permissions | extension UI | `droid.ask_user` | n/a | **`userInput/*`** | elicitation |
| Hermetic switch | `--ignore-user-config` | `--bare` | `--system-prompt-override` *(verify)* | `--pure` | `-nc -ne -ns -np` | `--settings` | `--settings-file` | `-c` | per agent |

**§2.2 GrokHost** (only ★ rows are in scope; the rest are follow-ups):

Live sessions use ACP through the generic base class. One-shot runs use `grok -p`. Admin functions use the CLI.

**Spawn request fields:**
- Prompt: `prompt` / `prompt_file` / `prompt_json` (content blocks), `verbatim`
- Model: `model`, `reasoning_effort` (`none` through `max`, or `deep`)
- Permissions: `permission_mode` (default, acceptEdits, auto, dontAsk, bypassPermissions, plan), `allow` / `deny` rules
- Tools: `tools` (allowlist), `disallowed_tools` (including `Agent(type)`), `disable_web_search`, `no_subagents`, `no_plan`
- Instructions: `rules` (appended), `system_prompt_override`, `agent` (profile), `agents` (inline subagents JSON)
- Run: `json_schema`, `max_turns`, `sandbox` profile, `cwd`, `session_id` (UUID)

| Function | Backed by | Tool |
|---|---|---|
| ★ `check_grok_ready()`: binary, version, login, ACP `authMethods` | `grok --version`, `inspect --json`, `initialize` | R |
| `get_grok_version()`, `run_grok_doctor()`, `get_grok_disk_usage()` | `version`, `doctor`, `du` | R |
| `inspect_grok_config(cwd)`: AGENTS.md, skills, MCP, imported Claude config | `grok inspect --json` | R |
| ★ `list_grok_models()` | `grok models` | R |
| `login_grok`, `logout_grok`, `update_grok(version)`, `setup_grok_managed_config` | `login`, `logout`, `update`, `setup` | ✗ |
| ★ `spawn_grok_session(request)` | ACP `session/new` + `session/prompt` (`_meta.yoloMode`) | W |
| ★ `run_grok_once(request)` → `{text, stopReason, sessionId, requestId}` | `grok -p --output-format json` | W |
| ★ `continue_grok_session(id_or_title, prompt)` | `-r` / ACP `session/load` | W |
| `continue_latest_grok_session(cwd)` | `-c` | W |
| `run_grok_named_session(key, prompt)`: create-or-resume, safe to retry (e.g. key `pr-123-review`) | `-s <id>` | W |
| ★ `fork_grok_session(id, prompt, new_id)` | `--resume --fork-session [--session-id]` | W |
| `restore_grok_session_code(id, worktree)`: brings back the repo snapshot, not just the chat | `--resume --restore-code --worktree` | W |
| ★ `list_grok_sessions(cwd)`, `search_grok_sessions(query)` | `sessions list` / `search` / ACP `session/list` | R |
| `read_grok_session_summary(id)`: title, model, counts, parent, recap | `~/.grok/sessions/…/summary.json` | R |
| `read_grok_session_log(id)` | `updates.jsonl` | R |
| `export_grok_transcript(id)` → Markdown | `grok export` | R |
| `export_grok_trace(id)` → tar.gz, local only | `grok trace --local --json` | R |
| `delete_grok_session(id)` | `sessions delete` | ✗ |
| ★ `wait_grok_turn(h)`, ★ `interrupt_grok_turn(h)`, `stream_grok_session(h)`, `get_grok_plan(h)` | ACP prompt result, `session/cancel`, `session/update` | R / W |
| `set_grok_mode(h, mode)`, `set_grok_model(h, model)` | `session/set_mode`, `set_config_option` | W |
| `answer_grok_permission(h, option)` | `session/request_permission` handler | int |
| `track_grok_session_usage(id)` *(verify the source: summary.json, `usage_update` or OTEL)* | session token counts | R |
| `configure_grok_native_subagents(agents, personas, blocked_types)` | `--agents`, `.grok/personas`, `Agent(type)` | option on spawn |
| `list_grok_agents_and_personas()`, `list_grok_subagent_sessions(parent)` | `.grok/agents`, `personas`, summary.json parent link | R |
| `list_grok_mcp_servers()`, `diagnose_grok_mcp()` | `mcp list`, `mcp doctor` | R |
| `add`/`remove`/`enable`/`disable_grok_mcp_server` | `grok mcp …` | ✗ |
| `list_grok_plugins()`, `get_grok_plugin_details(name)`, `validate_grok_plugin(path)` | `plugin list`, `details`, `validate` | R |
| `install`/`uninstall`/`update`/`enable`/`disable_grok_plugin` | `grok plugin …` | ✗ |
| `list_grok_worktrees()`, `show_grok_worktree(name)` | `worktree list`, `show` | R |
| `gc_grok_worktrees()`, `salvage_grok_worktree()`, `remove_grok_worktree()` | `worktree gc`, `salvage`, `rm` | ✗ |
| `list_grok_leaders()`, `kill_grok_leaders()` (the shared leader process) | `leader list|info`, `leader kill` | R / ✗ |
| `clear_grok_memory(scope)` | `memory clear` | ✗ |
| `grok_otel_env(endpoint)` → environment for external OTEL usage metrics | `GROK_EXTERNAL_OTEL`, `OTEL_*` | int |
| `serve_grok_agent(bind)`: WebSocket server for remote or shared use | `grok agent serve` | int |

**§2.3 OpencodeHost** (only ★ rows are in scope; Kilo extras omitted):

The host owns one `opencode serve` per working directory, bound to 127.0.0.1 with basic auth. The routes below come from that server's OpenAPI document.

**Spawn request fields:**
- `parts` (text, file, agent, subtask)
- `model` (`provider/model`), `variant` (effort), `agent`
- `system`, `tools` (on/off map), `permission` rules
- `title`, `parent_id`, `directory`

**Readiness, providers and models**

| Function | Backed by | Tool |
|---|---|---|
| ★ `check_opencode_ready()` | `GET /global/health`, `/provider/auth`, `/config/providers` | R |
| ★ `list_opencode_models(provider)`, `list_opencode_providers()`, `get_opencode_provider_auth()` | `/config/providers`, `/api/model`, `/provider` | R |
| `get_opencode_capabilities()`, `get_opencode_paths()` | `/experimental/capabilities`, `/path` | R |
| `set_opencode_provider_key`, `remove_opencode_provider_key`, `start_opencode_provider_oauth`, `upgrade_opencode` | `PUT`/`DELETE /auth/{id}`, `/provider/{id}/oauth/*`, `/global/upgrade` | ✗ |

**Sessions**

| Function | Backed by | Tool |
|---|---|---|
| ★ `spawn_opencode_session(request)`: returns right away | `POST /session` + `POST /session/{id}/prompt_async` | W |
| `run_opencode_once(request)` | `opencode run --format json`, or the blocking `POST …/message` | W |
| ★ `continue_opencode_session(id, prompt)` | `POST …/prompt_async` | W |
| ★ `fork_opencode_session(id, message_id)` | `POST …/fork` | W |
| ★ `revert_opencode_session(id, message_id, part_id)`, `unrevert_opencode_session(id)` (files restored through snapshots *(verify)*) | `POST …/revert`, `…/unrevert` | W |
| `stage_opencode_revert`, `commit_opencode_revert`, `clear_opencode_revert`: preview a revert before applying it | v2 `/api/session/{id}/revert/stage|commit|clear` | W |
| `run_opencode_command(id, name, args)`: slash commands | `POST …/command` | W |
| `run_opencode_session_shell(id, cmd)`: output is saved in the session history | `POST …/shell` | W |
| `init_opencode_agents_md(id)` | `POST …/init` | W |
| `compact_opencode_session(id)` | `POST …/summarize`, v2 `/compact` | W |
| `rename_opencode_session(id, title)` | `PATCH /session/{id}` | W |
| `delete_opencode_message`, `edit_opencode_part`, `delete_opencode_part`: edit a session's context directly | `DELETE …/message/{m}`, `PATCH`/`DELETE …/part/{p}` | W |
| `background_opencode_session(id)` | `/experimental/session/{id}/background` | W |
| `share_opencode_session`, `unshare_opencode_session` (publishes outside the machine) | `POST`/`DELETE …/share` | ✗ |
| `delete_opencode_session(id)` | `DELETE /session/{id}` | ✗ |
| ★ `list_opencode_sessions(dir)`, `get_opencode_session(id)` (includes cost, tokens, parent) | `GET /session`, `/session/{id}` | R |
| `get_opencode_session_status()`: which sessions are busy | `GET /session/status` | R |
| ★ `get_opencode_session_messages(id)`, `get_opencode_message(id, m)` | `GET …/message` | R |
| `list_opencode_child_sessions(id)`: subagent sessions | `GET …/children` | R |
| `get_opencode_session_todo(id)` | `GET …/todo` | R |
| ★ `get_opencode_session_diff(id)` | `GET …/diff` | R |
| `export_opencode_session(id, sanitize)` | `opencode export` | R |
| `import_opencode_session(file_or_url)` | `opencode import` | ✗ |

**Live turn control**

| Function | Backed by | Tool |
|---|---|---|
| ★ `wait_opencode_turn(id, timeout)` | v2 `POST /api/session/{id}/wait`, or SSE `session.idle` | R |
| ★ `interrupt_opencode_turn(id)` | `POST …/abort`, v2 `/interrupt` | W |
| `steer_opencode_session(id, text)` *(verify that it queues)* | `prompt_async` while busy | W |
| `stream_opencode_events(filter)`: 89 event types | `GET /event` (SSE), v2 `/api/session/{id}/event` | R |
| `switch_opencode_model(id, model)`, `switch_opencode_agent(id, agent)` | v2 `…/model`, `…/agent` | W |
| `get_opencode_context(id)` | v2 `…/context` | R |
| `list_opencode_pending_permissions()` | `GET /permission` | R |
| `answer_opencode_permission(req, reply)` | `POST /permission/{id}/reply` | int |
| `list_opencode_questions()` | `GET /question` | R |
| `answer_opencode_question(req, answer)`, `reject_opencode_question(req)`: the harness's built-in way to ask the user | `/question/{id}/reply|reject` | W |
| ★ `track_opencode_session_usage(id)`: dollars and tokens per message | Session and AssistantMessage `cost` / `tokens` | R |
| `get_opencode_stats(days, models, project)` | `opencode stats` | R |

**Operations that don't need a model turn**

| Function | Backed by | Tool |
|---|---|---|
| `find_opencode_symbols(query)`: LSP workspace symbols | `GET /find/symbol` | R |
| `find_opencode_text(pattern)`, `find_opencode_files(query)` | `/find`, `/find/file` | R |
| `get_opencode_vcs_status()`, `get_opencode_vcs_diff(raw)` | `/vcs/status`, `/vcs/diff` | R |
| `apply_opencode_patch(patch)` | `POST /vcs/apply` | W |
| `get_opencode_lsp_status()`, `get_opencode_formatter_status()` | `/lsp`, `/formatter` | R |
| `create_opencode_pty(cmd)`, `list`/`get`/`update`/`remove_opencode_pty`: long-lived dev servers and watchers | `/pty*` | W |
| `list_opencode_worktrees()` | `GET /experimental/worktree` | R |
| `create`/`reset`/`remove_opencode_worktree` | `POST /experimental/worktree`, `…/reset`, `DELETE` | W |

**Config and extensions**

| Function | Backed by | Tool |
|---|---|---|
| `get_opencode_config()` | `GET /config`, `/global/config` | R |
| `update_opencode_config(patch)` | `PATCH /config` | ✗ |
| `list_opencode_agents()`, `list_opencode_skills()`, `list_opencode_commands()`, `list_opencode_tools()` | `/agent`, `/skill`, `/command`, `/experimental/tool` | R |
| `get_opencode_mcp_status()` | `GET /mcp` | R |
| ★ `add_opencode_mcp_server(config)`: attach Vidbyte's per-run tool server while opencode is running | `POST /mcp` | W |
| `connect_opencode_mcp(name)`, `disconnect_opencode_mcp(name)` | `/mcp/{n}/connect|disconnect` | W |
| `start_opencode_mcp_oauth(name)` | `/mcp/{n}/auth*` | ✗ |
| `list_opencode_projects()`, `get_current_opencode_project()` | `/project`, `/project/current` | R |
| `install_opencode_plugin(module)`, `install_opencode_github_agent()` | `opencode plugin`, `opencode github` | ✗ |
| `checkout_opencode_pr(n)`: check out the PR branch and start there | `opencode pr <n>` | W |

**Driving a person's open TUI.** This lets an agent type into, submit to, or notify a terminal UI someone is already using.

| Function | Backed by | Tool |
|---|---|---|
| `append_opencode_tui_prompt(text)`, `submit_opencode_tui_prompt()` | `/tui/append-prompt`, `/tui/submit-prompt` | W |
| `show_opencode_tui_toast(msg)`, `select_opencode_tui_session(id)`, `execute_opencode_tui_command(cmd)` | `/tui/*` | W |

**§2.7 MuseHost** (only ★ rows are in scope):

Talks MSP through `muse-code-sdk`. On this machine every call goes through `wsl.exe -d MuseUbuntu1`, so the host must translate paths (`C:\` ↔ `/mnt/c`) and kill the process tree inside WSL. The methods come from `muse schema generate-json-schema`.

**Spawn request fields:**
- Model: `model`, `reasoning_effort` (`none` through `ultra`)
- Approval and sandbox: `approval_mode` (untrusted, on-request, never), `sandbox_network`, `disable_write` / `disable_shell` (read-only)
- Workspace and limits: `workspace`, `max_model_steps`
- Output: `output_schema` (Meta models only)
- `config` overrides

| Function | Backed by | Tool |
|---|---|---|
| ★ `check_muse_ready()`: binary, WSL distro, auth | `--version`, MSP `initialize` | R |
| ★ `list_muse_models()` | `model/list` | R |
| ★ `spawn_muse_session(request)` | `session/start` + `turn/start` | W |
| `run_muse_once(request)` | `muse exec --json` | W |
| ★ `continue_muse_session(id, prompt)` | `session/resume` + `turn/start` | W |
| ★ `fork_muse_session(id)` | `session/fork` | W |
| ★ `list_muse_sessions()`, `read_muse_session(id)`, `page_muse_session(id, cursor)` | `session/list|read`, `view/page` | R |
| `compact_muse_session(id)` | `session/compact` | W |
| `rename_muse_session(id, title)` | `session/rename` (1.4) | W |
| `run_muse_session_shell(id, cmd)` | `session/userShell` | W |
| `export_muse_session(id)` | `muse export` | R |
| ★ `steer_muse_turn(h, text)`, ★ `interrupt_muse_turn(h)`, `cancel_muse_turn(h)`, `unqueue_muse_message(h, id)` | `turn/steer|interrupt|cancel|unqueue` | W |
| ★ `wait_muse_turn(h)`, `stream_muse_session(h)` | `turn/completed`, `item/*` | R |
| `set_muse_model(h, model)`, `set_muse_reasoning_effort(h, effort)` | `session/setModel`, `setReasoningEffort` (1.4) | W |
| `set_muse_approval_mode(h, mode)` | `session/setApprovalMode` | ✗ |
| `list_muse_pending_approvals()` | `approval/listPending` | R |
| `decide_muse_approval(id, decision)` | `approval/decide` | int |
| `answer_muse_user_input(id, answer)`, `clarify_muse_user_input(id)`, `cancel_muse_user_input(id)` | `userInput/answer|clarify|cancel` | W |
| `send_muse_subagent_message(id, text)`, `assign_muse_subagent_followup(id, task)` | `subagent/sendMessage|followupTask` | W |
| `interrupt_muse_subagent`, `stop_muse_subagent`, `resume_muse_subagent`, `reopen_muse_subagent`, `close_muse_subagent` | `subagent/*` | W |
| `read_muse_subagent_result(id)` | `subagent/readResult` | R |
| ★ `track_muse_session_usage(id)` | `session/tokenUsage`, `contextUsage`; cost via `usage/read` (1.4) | R |
| `get_muse_goal`, `set_muse_goal` | `goal/*` (1.4); 1.0.1 only notifies `session/goalChanged` | R / W |
| `run_muse_workflow(name, args)` | `workflow/*` (1.4) | W |
| `import_claude_skills_into_muse()` | `muse skills import --from claude` | ✗ |

**§2.8 AcpHost** (reference for the ACP calls GrokHost makes; no `*_acp_*` function is in scope):

Built on `agent-client-protocol` (PyPI; `import acp`). Per-vendor wrappers are thin partials, for example `spawn_kimi_session = partial(new_acp_session, agent=AcpAgent.KIMI)`.

**Connecting**

| Function | Backed by | Tool |
|---|---|---|
| ★ `discover_acp_agents()` | registry `cdn.agentclientprotocol.com/registry/v1/latest/registry.json` | R |
| ★ `resolve_acp_launch(agent)`: npx / uvx / binary command and env per platform | registry manifest | int |
| ★ `connect_acp_agent(agent, cwd, env)` | `acp.spawn_agent_process` + `initialize` | int |
| ★ `get_acp_capabilities(agent)`: `loadSession`, `sessionCapabilities.*`, prompt and MCP capabilities | `initialize` result | R |
| `authenticate_acp_agent(method_id)`, `logout_acp_agent()` | `authenticate`, `logout` | ✗ |

**Sessions**

| Function | Backed by | Tool |
|---|---|---|
| ★ `new_acp_session(cwd, mcp_servers, extra_dirs, system_prompt)` | `session/new` (system prompt is unstable) | W |
| ★ `prompt_acp_session(id, blocks)` → stop reason and usage | `session/prompt` | W |
| ★ `resume_acp_session(id)`, `load_acp_session(id)` (load replays history) | `session/resume`, `session/load` | W |
| ★ `fork_acp_session(id)` | `session/fork` (unstable; 10 agents) | W |
| ★ `list_acp_sessions(cwd, cursor)` | `session/list` | R |
| `close_acp_session(id)` | `session/close` | int |
| `delete_acp_session(id)` | `session/delete` | ✗ |
| ★ `cancel_acp_turn(id)`, `cancel_acp_request(req)` | `session/cancel`, `$/cancel_request` | W / int |
| `set_acp_session_mode(id, mode)` | `session/set_mode` | W |
| `set_acp_config_option(id, key, value)`, `set_acp_model(id, model)` (falls back to the old `set_model`, which 16 agents still use) | `session/set_config_option` | W |
| `list_acp_modes(id)`, `list_acp_config_options(id)`, `list_acp_commands(id)` | session result, `available_commands_update` | R |
| `run_acp_slash_command(id, name, input)` | prompt `/name` | W |
| ★ `stream_acp_session(id)`, `get_acp_plan(id)` | `session/update`, `plan` | R |
| `get_acp_session_usage(id)`: tokens used, window size, cost | `usage_update`, prompt `usage` | R |
| `list_acp_providers()` | `providers/list` (unstable) | R |
| `set_acp_provider(id, api_type, base_url, headers)`: point an agent at GLM or DeepSeek at runtime | `providers/set` (unstable) | ✗ |
| `call_acp_extension(method, params)` | `_vendor/*` methods | per method |

**Client-side handlers.** These are policies Vidbyte plugs in, not tools.

| Function | Backed by | Tool |
|---|---|---|
| `acp_permission_policy(rules)` | `session/request_permission`: allow once or always, reject once or always | int |
| `acp_fs_bridge(root, audit)`: send every file read and write through Vidbyte | `fs/read_text_file`, `fs/write_text_file` | int |
| `acp_terminal_bridge(sandbox)`: run every shell command in Vidbyte's process tree | `terminal/create|output|wait_for_exit|kill|release` | int |
| `acp_elicitation_handler(ask_parent)`: send the agent's questions to the parent agent | `elicitation/create` (form or URL) | int |

**§2.11 Backend profiles** (GLM and DeepSeek rows and the ★ functions are in scope, plus `build_opencode_backend_provider`):

These go in `vidbyte/harnesses/native/backends/`. A `HarnessBackend` record holds:
- `base_url` and the auth environment variable
- which model fills each slot (opus, sonnet, haiku, subagent)
- the compaction window and timeout
- `unsupported` features
- `allowed_harnesses`: for example, the GLM plan may only be used in the tools Z.ai lists

| Function | Backed by | Tool |
|---|---|---|
| ★ `list_harness_backends()` | the registry | R |
| ★ `build_claude_backend_env(backend, model)` | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_DEFAULT_*_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, `API_TIMEOUT_MS` | int |
| `build_opencode_backend_provider(backend)`, `build_pi_backend_args(backend)`, `apply_acp_backend(session, backend)` | opencode provider config, `pi --provider`, ACP `providers/set` | int |
| ★ `check_backend_ready(backend)`: key present plus a one-token test call | the endpoint | R |
| ★ `check_backend_compat(backend, request)`: reject features the endpoint silently ignores (DeepSeek ignores `mcp_servers`, `cache_control` and documents) | `unsupported` list | int |
| ★ `get_deepseek_balance()` (documented) | `GET api.deepseek.com/user/balance` | R |
| `get_zai_coding_plan_quota()`: 5-hour and weekly percentages *(undocumented endpoint)* | `GET api.z.ai/api/monitor/usage/quota/limit` | R |
| `get_minimax_quota()`, `get_kimi_code_quota()` | `mmx quota`; `kimi web` `/api/v1/oauth/usage` | R |
| `list_backend_models(backend)`, `price_backend_usage(backend, tokens)` | OpenAI-compatible `/models`; the SDK price list | R / int |

**§2.13 Shared error codes and the never-a-tool list** (with the name reconciliation above):

These extend `FailureCode` with the same pattern for every host, `<host>.<code>`:
- `binary_missing`, `binary_unsupported` (the version floors above)
- `not_signed_in`, `auth_mode_unsupported`, `usage_limited`, `model_unknown`
- `capability_missing`: for example, fork on Amp or Gemini, or an ACP agent without `sessionCapabilities.fork`. This must fail before any money is spent.
- `session_not_found`, `session_busy`, `turn_timed_out`, `host_exited`, `schema_violation`
- `protocol_changed`: the parser didn't find fields it relies on
- `server_unreachable`: opencode, `kimi web`, `qwen serve`
- `wsl_unavailable`: Muse

Plus `backend.feature_unsupported`, `backend.harness_not_allowed`, `acp.auth_required` (-32000), `acp.method_not_found` (-32601) and `acp.cancelled` (-32800).

**Never expose these as tools.** The flags that turn off approvals:
- `--dangerously-skip-permissions` (opencode 1.19, CodeBuddy, agy)
- `--skip-permissions-unsafe` (Droid)
- `--yolo` / `--always-approve` (Grok, Gemini, Muse, Vibe)
- `dangerously_allow_all` (Amp)
- `--dangerously-unauthenticated` (Goose serve)

The research agents' reports set off an injection-pattern filter because they mention these flags. They were only quoting vendor docs, but it's the right list for the guard.

### Open questions

The spec author resolves each of these as a D- or Q-item. The default shown applies unless the spec gives evidence otherwise.

- **Q-1 Scope.** Ship only the ★ set per target listed under "Key decisions" (plus `build_opencode_backend_provider`), or the full catalog section per host? **Default: ★ only.**
  - Why: it mirrors the upstream first PR, and about 46 functions plus tools is already a large PR.

- **Q-2 Dependencies.** Add no new dependency, or add optional extras (`agent-client-protocol` for Grok's ACP; `muse-code-sdk` for MSP)? **Default: no new dependency.**
  - opencode uses the already-required `httpx`.
  - ACP and MSP are newline-delimited JSON-RPC 2.0 over stdio, which the SDK can speak with asyncio subprocesses.
  - Reasons:
    - `pyproject.toml` is reserved to the Claude PR under the shared-file contract.
    - `agent-client-protocol` is pre-1.0.
    - `muse-code-sdk` would have to spawn through `wsl.exe` on Windows, which is unverified.
    - The upstream "use the official SDK" rule had an official Python SDK for both Codex and Claude; here only Muse has one.
  - If the spec chooses an extra, it must name the exact pin and the conflict it creates.

- **Q-3 Where the JSON-RPC stdio framing lives.** The options, in order of preference:
  1. Reuse `vidbyte/tools/mcp/transport.py`, if the layer rules allow `vidbyte/harnesses/` to import it.
  2. Put one private module under `vidbyte/harnesses/native/` that Grok and Muse share. It has two users, so it is not a one-implementation base. It must not change `native/__init__.py`.
  3. One copy per host.

  **Default: decide on the scout's evidence; prefer 1, then 2.**

- **Q-4 Approval and permission requests during a live turn** (ACP `session/request_permission`, opencode permission requests, MSP `approval/requested` and `userInput/requested`). No ★ function answers them. **Default:**
  - The host answers from the spawn request's own policy: deny unless the request's rules allow it.
  - Every denial is recorded in the turn result.
  - A turn never hangs waiting for an answer nobody will send.
  - Grok's ACP client advertises no fs or terminal capabilities.

- **Q-5 opencode server lifecycle.** **Default:**
  - `OpencodeHost` starts and owns one `opencode serve` per working directory, bound to 127.0.0.1 on a free port.
  - It uses a random per-host password passed through the environment, never argv.
  - It stops the server on exit, on every path, including cancellation.
  - An optional `base_url` plus credentials attaches to an existing server instead.

- **Q-6 Grok usage in `wait_grok_turn`.** **Default:**
  - Report ACP `usage_update` or prompt-response usage when Grok sends it.
  - Otherwise report usage as unknown (None), never zero.
  - `summary.json` and OTEL sources are follow-ups. The S1 author may verify with a no-prompt handshake.

- **Q-7 `continue_opencode_session` on a busy session.** **Default:** refuse with `opencode.session_busy` after checking `GET /session/status`, before sending anything. Steering is not in scope for opencode.

- **Q-8 Muse through WSL.** How does `MuseHost` find and launch `muse`, translate paths, and guarantee no orphaned process inside the distro? **Default:**
  - Accept an explicit launcher (`wsl_distro` plus the in-distro `muse` path, or a full argv prefix), with detection on Windows.
  - Translate paths with a pure function, and test that function directly.
  - On exit, send MSP interrupt and close, then kill the process tree, then kill inside the distro.
  - Report `muse.wsl_unavailable` when WSL or the distro is missing.

- **Q-9 Version floors.** **Default:** the installed versions (grok 1.0.13, opencode 1.18.31, muse 1.0.1). Muse 1.4-only methods are not called; where a ★ function would need one, it reports `muse.capability_missing`.

- **Q-10 `check_backend_ready`.** The catalog says "key present plus a one-token test call". **Default:**
  - Use non-spending checks: the key env var is present; for DeepSeek, `GET /user/balance`.
  - Do not make a test call on a GLM Coding Plan key, because the plan may be used only inside the tools Z.ai lists, and a direct call from Vidbyte is not one of them.
  - Any spending test call is opt-in.

- **Q-11 Live smoke tests behind an environment flag.** **Default: no.**

- **Q-12 "Approve everything" settings at the Python level.** **Default:** not exposed in this PR at all, as a tool or as a Python field. Examples: Grok `bypassPermissions` or yoloMode, opencode allow-all, Muse `--yolo` or approval mode `never` when it means "approve everything".

- **Q-13 Which GLM endpoint and key.** Z.ai's international `api.z.ai` or BigModel's `open.bigmodel.cn`, which is the SDK's existing `ModelProvider.GLM` default? **Default:**
  - Use the Z.ai Anthropic-compatible endpoint from the catalog.
  - Read the key from the existing `GLM_API_KEY`.
  - Document the difference.

## D. Weighted words

- "Make sure to extensively handle errors for every single function." — Prompt 2.
  - The spec turns this into testable invariants:
    - Every public function and every tool has its own error table, listing each `<host>.<problem>` it can produce, with a next step.
    - No raw vendor, `httpx`, `json`, `OSError`, `asyncio.TimeoutError` or `KeyError` exception escapes a public function.
    - Every I/O has a timeout.
    - Every process and server is reaped on every exit path, including cancellation.
    - Inputs are validated before any process starts or any money is spent.
    - Secrets never appear in argv or errors.
    - Every listed error code has a test that produces it.
- "focus on implementing grok, glm, deepseek, meta, and opencode harnesses for now" — Prompt 2. Scope boundary: these five targets only; "for now" defers the rest.
- "an in-depth function list of every function that we can implement" — Prompt 1. This scoped the catalog, not this PR.
- Carried from the upstream session (codex-host `request.md` §A, Prompt 2): "return semantic error messages if something goes wrong, each funciton shoulllld make sure to handle errors".
