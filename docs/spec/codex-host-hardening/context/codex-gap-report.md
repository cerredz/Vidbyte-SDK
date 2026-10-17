# Codex feature and settings gap report for PR #1055 (CodexHost)

Date: 2026-10-17. PR head `ea473f63271b54de32a024dd358fb21bfa1a383e`, base `f7f32b19dc32e1cca766361445b959ce710bd5f8`.
Ground truth: installed `codex-cli 0.163.0`. Supporting evidence: the installed `openai-codex 0.162.1`, the `rust-v0.163.0` tag of github.com/openai/codex, and the official docs (now served from learn.chatgpt.com).

## 0. Headline findings

1. **Mechanical coverage.** Codex 0.163.0 exposes **172 ClientRequest methods** (105 stable, 67 experimental-only). CodexHost's 27 functions cover them as follows:
   - **10** fully;
   - **9** partially;
   - **3** only internally;
   - **51** deferred by the PR's own spec (the unstarred rows of the R3 catalog);
   - **99** missed, meaning they are not in the catalog at all. 67 of these are experimental, and 32 are stable (mostly fs/*, plugin sharing and marketplaces, gateway OAuth, and import).
2. **Fast mode is reachable, but it is neither discoverable nor validated.**
   - `CodexThreadSettings.service_tier` and `CodexTurnSettings.service_tier` are free strings. The live model catalog's Fast tier id is **`priority`**, with name "Fast", and `fast` is accepted as an alias.
   - `CodexModelInfo` drops `serviceTiers` and `defaultServiceTier`, so a caller cannot find the tier id.
   - `serviceTierForTurn`, which sets the tier for one turn only, is not exposed.
   - The agent tools never expose the tier. That is reasonable: Fast costs 2.5x.
3. **Reasoning effort is a closed enum that is out of date.**
   - `CodexReasoningEffort` has none, minimal, low, medium, high and xhigh. It lacks `max` and `ultra`.
   - Every current catalog model advertises `max`, and most advertise `ultra`.
   - The protocol now types `ReasoningEffort` as an open string, and `effort: "ultra"` replaces the deprecated `multiAgentMode` for proactive multi-agent work.
4. **Plan mode (`/plan`) is impossible today, for three separate reasons:**
   - (a) `collaborationMode` is an experimental `TurnStartParams` field. The PR never sends it, and its validate-then-dump step through openai-codex's stable-only pydantic models, which use `extra="ignore"`, would silently drop it.
   - (b) `collaborationMode/list` is not wrapped.
   - (c) Plan mode asks questions through the server request `item/tool/requestUserInput`. The host router answers every non-approval request with `{}`, which violates the required `answers` field.

   The same `{}` answer also breaks `mcpServer/elicitation/request` (required `action`) and `item/permissions/requestApproval` (required `permissions`).
5. **No mid-thread settings change.** `thread/settings/update` and `turn/settings/update` are not wrapped. These two experimental methods are how the TUI's `/model`, `/fast`, `/plan`, `/permissions` and `/cd` change settings without starting a turn.
6. **Goal runs silently drop turn settings.** A goal run sends no `turn/start` (spec section 9.2, line 892). `request.turn.*` (model, effort, service_tier, sandbox, summary), `output_schema` and `disabled_plugin_ids` therefore never reach Codex. No rule refuses them, which contradicts the PR's own INV-27 ("no setting is silently ignored").
7. **`disabled_plugin_ids` is a no-op in 0.163.** The app-server README says that saving the selection "does not yet filter plugin capabilities".
8. **TUI-only or client-side features.** `/worktree` is implemented client-side, with the `codex_worktree` crate and TUI-injected dynamic tools, and has no app-server method. `/app` is an OS deep link (`codex://threads/<id>`). `/side` is a composite: an ephemeral `thread/fork`, side developer instructions, then `thread/inject_items` with a boundary prompt.

## 1. Method and sources (what was run, and how each claim is verified)

| Source | What was done | Artifact (scratch dir `.../scratchpad/codex-research/`) |
|---|---|---|
| CLI 0.163.0 | `codex --help` and the help of every subcommand; `codex features list`; `codex debug models` (read-only) | `../models-catalog.json` |
| Protocol schema | `codex app-server generate-json-schema --experimental --out schema-exp`; the same without `--experimental` into `schema-stable`; `generate-ts --experimental --out ts-exp` | `schema-exp/`, `schema-stable/`, `ts-exp/` |
| Method lists | `scripts/methods.py` parses `ClientRequest.json`, `ServerRequest.json`, `ServerNotification.json`, and diffs experimental against stable | `methods.txt` |
| Coverage matrix | `scripts/matrix.py` iterates every schema method and assigns PR status from a hand-built map of PR call sites. It asserts that no mapped name is missing from the schema (it reported none). | `coverage-matrix.md` (appended below) |
| Field dumps | `scripts/fields.py` dumps each params type and marks the fields absent from the stable bundle as [EXP] | (inline below) |
| SDK skew | `scripts/skew.py` compares the openai-codex `generated/v2_all.py` classes and fields with the 0.163 schema. The 0.163.0 wheel was downloaded with `pip download --no-deps` and not installed. | `sdk-0.163.0-wheel/` |
| Codex source | Sparse clone of tag `rust-v0.163.0`; TUI slash-command enum, dispatch, side, worktree, memories, service tiers, plan template | `codex-src/`, `src-0.163.0/` |
| Docs | learn.chatgpt.com: developer-commands (CLI), config-reference, app-server, speed, memories. The developers.openai.com URLs 308-redirect there. | cited by URL |
| PR | `git show ea473f63:<path>` only; the working tree was not touched | cited as `ea473f63:path:line` |

Citation keys used below:
- `S:Type` means `schema-exp/codex_app_server_protocol.v2.schemas.json`, definition `Type`.
- `TUI:file:line` means `codex-src/codex-rs/tui/src/file` at `rust-v0.163.0`.
- `PR:file:line` means the PR head.

## 2. The user's 11 named features

| Feature | What it is | Kind | Exact programmatic route | PR #1055 coverage |
|---|---|---|---|---|
| `/fast` | Toggles the model's "Fast" service tier. It is a **dynamic** slash command generated from the current model's catalog tiers, not an enum variant (TUI:chatwidget/service_tiers.rs:75-98, 119-123). It appears only when the model advertises a tier named Fast. | **Setting.** Config `service_tier = "fast"` plus `[features].fast_mode = true` (docs: learn.chatgpt.com/docs/agent-configuration/speed; config-reference). Protocol `serviceTier` string. | `thread/start` / `thread/resume` / `thread/fork` `serviceTier`; `turn/start` `serviceTier` (sticky) or `serviceTierForTurn` (one turn only; `"default"` = standard); `thread/settings/update.serviceTier` [EXP] (`null` clears); `turn/settings/update.serviceTier` [EXP]. The catalog tier id is `priority` (`codex debug models`: every model lists `('priority','Fast')`). `fast` is an accepted alias (`ServiceTier::from_request_value`, codex-rs/protocol/src/config_types.rs). Ultrafast is the separate flag `features.ultrafast_mode`. | **Partial.** Free-text `CodexThreadSettings.service_tier` and `CodexTurnSettings.service_tier` (PR:agents/codex/config.py `_thread_common`, `turn_kwargs`) are sent on spawn, continue, launch and skill runs, and on fork through the thread. Gaps: no tier discovery (`CodexModelInfo` drops `serviceTiers`), no validation, no `serviceTierForTurn`, no change without a turn, ignored at turn level on goal runs, and none on review. |
| `/memories` | Chooses whether Codex uses existing memories and whether it generates new ones. | **Setting plus methods.** Feature flag `features.memories` (stable, **off by default**: `codex features list`); config `memories.use_memories`, `memories.generate_memories` and more (config-reference). | Global: `config/batchWrite` of `memories.use_memories` and `memories.generate_memories` (what the TUI does: TUI:app/config_persistence.rs:929-975). Per thread: `thread/memoryMode/set {threadId, mode: enabled\|disabled}` [EXP] (TUI:app/config_persistence.rs:993-1013). Status: `memory/status {minConsolidatedThreads?}` → `{v2ConsolidatedThreads, v2Ready}` [EXP]. Wipe: `memory/reset` [EXP]. Per spawn: `thread.config["features.memories"]=True`. | **Missed** (none of the methods are in the R3 catalog). It is reachable only untyped, through `CodexThreadSettings.config`. |
| `/review` | Reviews uncommitted changes, a base branch, a commit, or custom instructions. | **App-server method.** Config `review_model` sets the review model (config-reference). | `review/start {threadId, target, delivery}` (S:ReviewStartParams, S:ReviewTarget) | **Covered.** `start_codex_review(thread_id, target, delivery)`. Notes: `delivery=DETACHED` is **deprecated in 0.163**. It emits `deprecationNotice` and is unsupported for paginated parents (S:ReviewStartParams.delivery; app-server docs). There is no `review_model` knob other than the process-wide `CodexClientSettings.config_overrides`. |
| `/fork` | Branches the chat into a new thread. | **App-server method.** | `thread/fork {threadId, lastTurnId? \| beforeTurnId?[EXP], ephemeral, excludeTurns, deferGoalContinuation?[EXP], …settings}` (S:ThreadForkParams) | **Covered (partial).** `fork_codex_thread(thread_id, from_turn_id, exclude_turns, overrides)` sends `lastTurnId` only, and only through a *completed* turn. The protocol forbids only in-progress turns, so this is stricter (D-29). It lacks `beforeTurnId` and `deferGoalContinuation`. |
| `/worktree` | Starts or continues a chat in a managed Git worktree. | **Client-side or TUI-only.** No app-server method exists. The TUI runs `codex_worktree::WorktreeManager::create` locally (TUI:app/managed_worktree_creation.rs:121-140) and gives the model TUI-hosted dynamic tools `create_worktree`, `get_worktree_creation_status` and `list_worktrees` (TUI:managed_worktree_tool_specs.rs). Feature flag `worktrees` (stable, on). | The CLI flags `codex --worktree` and `codex exec --worktree`. Programmatically: create a git worktree yourself, then call `thread/start` (or fork) with `cwd` set to the worktree. | **Missed.** It is reachable only by hand, with git plus `CodexThreadSettings.cwd`. |
| `/app` | Continues the current session in the Desktop app (macOS or Windows only). | **TUI-only, as an OS deep link.** | Open `codex://threads/<thread_id>` (TUI:app/history_ui.rs:287-297; Windows uses a PowerShell launch script, line 438+). No protocol call. | Not covered. A trivial helper is possible (P2). |
| `/compact` | Summarizes earlier turns to free context. | **App-server method.** Config `compact_prompt`, `model_auto_compact_token_limit`. | `thread/compact/start {threadId}` | **Covered.** `compact_codex_thread`. Its completion is not tracked (helpers NG-12, deferred by spec). |
| `/plan` | Plan mode: non-mutating exploration, then a `<proposed_plan>`. It asks questions through `request_user_input` (src `collaboration-mode-templates/templates/plan.md` lines 13, 64, 75). | **Turn or thread param** [EXP] plus a **server request**. Config `plan_mode_reasoning_effort`. | `turn/start.collaborationMode = {mode: "plan", settings: {model, reasoning_effort?, developer_instructions: null}}` (S:CollaborationMode, S:ModeKind = plan\|default, S:Settings), or `thread/settings/update.collaborationMode`. Presets come from `collaborationMode/list` [EXP]. Questions arrive as the server request `item/tool/requestUserInput`, whose response requires `answers` (S:ToolRequestUserInputResponse). The output is a `plan` ThreadItem (`item/plan/delta`). | **Missed.** No field, the pydantic validation would drop it, and the router's `{}` answer breaks the questions. The PR's serializer does keep `plan` items (PR:lib/constants/codex.py:67-86). |
| `/side` (`/btw`) | Starts a side chat in an **ephemeral fork**, so the main transcript is untouched. | **Composite of app-server methods.** | `thread/fork {threadId, ephemeral: true, developerInstructions: <existing> + SIDE_DEVELOPER_INSTRUCTIONS}` (TUI:app_server_session.rs:1001-1020; TUI:app/side.rs:44, 609-611), then `thread/inject_items` with a boundary user message (TUI:app/side.rs:28, 780), then `turn/start`. | **Partial.** `fork_codex_thread(overrides=CodexSpawnRequest(thread=CodexThreadSettings(ephemeral=True), developer_instructions=…))` then `continue_codex_thread` gets close. `thread/inject_items` (the boundary) is not wrapped (deferred catalog row). Resuming an ephemeral fork through `thread/resume` is UNVERIFIED. |
| `/mcp` | Lists MCP tools and auth; `/mcp verbose`; `/mcp login <name>`. | **App-server methods.** Config `mcp_servers.*`. | `mcpServerStatus/list {threadId?, serverName?, detail?, cursor?, limit?}`; `mcpServer/oauth/login {name, scopes?, threadId?, timeoutSecs?}`; `config/mcpServer/reload`; `mcpServer/tool/call {threadId, server, tool, arguments}`; `mcpServer/resource/read` | **Deferred by spec** (R3 catalog rows; NG-1). Nothing is wrapped. |
| `/plugins` (the user wrote `/plugin`; the CLI subcommand is `codex plugin`) | Browses, inspects, enables and manages plugins. | **App-server methods plus a config key.** Config `plugins.<name@marketplace>.enabled`. | `plugin/list {cwds?, forceRefetch?, marketplaceKinds?}`, `plugin/read`, `plugin/installed`, `plugin/install`, `plugin/uninstall`, `marketplace/add\|remove\|upgrade`; enable or disable through `config/value/write`. Per turn: `turn/start.disabledPluginIds`. | **Mostly deferred by spec.** `plugin/installed`, `plugin/search`, `plugin/reconcile` and `marketplace/*` were missed. `CodexSpawnRequest.disabled_plugin_ids` is sent but is a **no-op** in 0.163 (app-server README "Thread plugin settings"). |

## 3. Every TUI slash command (0.163.0)

The enum `SlashCommand` (TUI:slash_command.rs:12-88) has **64 variants**:
- `/rollout` and `/test-approval` are visible only in debug builds (lines 309-317).
- `/debug-m-drop` and `/debug-m-update` are stubs described as "DO NOT USE".

In addition, **dynamic service-tier commands** such as `/fast` are generated from the model catalog.

Legend:
- **C** = covered by the PR; **P** = partial; **D** = deferred by the spec; **M** = missed; **T** = TUI-only.

| Command | Programmatic route | PR |
|---|---|---|
| /model | `model/list`; `turn/start.model,effort`; `thread/settings/update` [EXP] | P: model and effort on spawn or continue; enum lacks max and ultra; no change without a turn |
| /fast (dynamic) | `serviceTier` = catalog id (`priority`) | P (section 2) |
| /daybreak | `thread/start.daybreakEnabled` [EXP], `thread/metadata/update.daybreakEnabled` [EXP] | M (P2) |
| /ide | IDE selection context | T |
| /permissions | `permissionProfile/list`; `thread/settings/update {approvalPolicy, approvalsReviewer, sandboxPolicy, permissions}` | P: approvals and a sandbox preset at spawn or continue; no named profiles, no granular policy, no sandbox sub-options; the list is D |
| /keymap, /vim, /tui, /raw, /theme, /pets, /title, /statusline, /copy | UI | T |
| /setup-default-sandbox | `windowsSandbox/setupStart` | D |
| /experimental | `experimentalFeature/list`, `experimentalFeature/enablement/set` | D |
| /approve | `thread/approveGuardianDeniedAction {threadId, event}` | D (✗ in the catalog) |
| /memories | section 2 | M |
| /skills | `skills/list`, `skills/config/write` | P: list and run covered; the enable toggle is D |
| /import | `externalAgentConfig/detect`, `externalAgentConfig/import` | M (P2) |
| /hooks | `hooks/list` (trust goes through config writes) | D |
| /review | `review/start` | C |
| /rename | `thread/name/set` | P: at spawn or fork only; standalone rename is D (helpers NG-1) |
| /new, /clear | `thread/start` | C (spawn) |
| /archive | `thread/archive` / `thread/unarchive` | D (helpers NG-1) |
| /delete | `thread/delete` | C (`delete_codex_thread`, plain function) |
| /resume | `thread/resume` | P: only together with a new turn (`continue_codex_thread`); no attach-only resume |
| /fork | `thread/fork` | C (partial fields) |
| /worktree | client-side git plus `cwd` | M or T |
| /app | `codex://threads/<id>` | T |
| /init | a canned prompt (`tui/assets/prompt_for_init_command.md`) | C through spawn with that prompt (no named wrapper) |
| /compact | `thread/compact/start` | C |
| /config | settings UI over `config/batchWrite` | T (the writes are D) |
| /recap | temporary ephemeral `thread/start` with tools disabled, plus a structured turn (TUI:temporary_structured_request.rs:51-160; TUI:app/recap.rs) | M (P2; composable from spawn) |
| /plan | section 2 | M |
| /voice | `thread/realtime/*` [EXP] | M (P2) |
| /goal | `thread/goal/set\|get\|clear` | P: get and run; pause, resume, edit and clear are D (helpers NG-3) |
| /agents | UI over `thread/list` (shared daemon) | P (list helpers) |
| /subagents | `thread/list` with `sourceKinds` or `parentThreadId` [EXP] | P: `list_codex_threads(source_kinds=…)`; parent filter M; `list_codex_subagent_threads` D (helpers NG-2) |
| /side, /btw | section 2 | P |
| /export | rendered from `thread/turns/list` | P: `list_codex_turns`; `export_codex_transcript` D |
| /diff | local `git diff`; protocol `turn/diff/updated` notification | M: the notification is not surfaced (`get_codex_turn_diff` D) |
| /mention | `mention` UserInput | C (`CodexMentionInput`) |
| /status | config plus token usage | P (`track_codex_thread_usage`) |
| /daemon | CLI `codex app-server daemon …` | T |
| /warnings | `warning`, `configWarning`, `guardianWarning` and `deprecationNotice` notifications | M: none are surfaced |
| /cd | `thread/settings/update.cwd` [EXP] or `turn/start.cwd` | P (`turn.cwd` on continue) |
| /pwd | UI | T |
| /usage | `account/usage/read`, `account/rateLimitResetCredit/consume` | D and M |
| /debug-config | `config/read {includeLayers}`, `configRequirements/read` | D |
| /mcp | section 2 | D |
| /apps | `app/list`, `app/read`, `app/installed` | D |
| /plugins | section 2 | D or M |
| /logout | `account/logout` | D (✗) |
| /quit, /exit | UI | T |
| /feedback | `feedback/upload` | M (P2) |
| /rollout | `Thread.path` (debug) | T |
| /ps | `thread/backgroundTerminals/list` [EXP] | M (P1) |
| /stop (/clean) | `thread/backgroundTerminals/clean` [EXP] | M (P1) |
| /test-approval, /debug-m-drop, /debug-m-update | debug and stubs | T |

The docs table (learn.chatgpt.com/docs/developer-commands?surface=cli) matches the enum, except that it omits `/daybreak`, `/voice`, `/config` and the debug commands, and it lists `/fast` explicitly.

## 4. App-server ClientRequest coverage (summary; the full 172-row matrix is in the appendix)

| Status | Stable | Experimental | Total |
|---|---|---|---|
| COVERED | 10 | 0 | 10 |
| PARTIAL | 9 | 0 | 9 |
| INTERNAL (used, not exposed) | 3 | 0 | 3 |
| DEFERRED by spec (R3 unstarred / helpers NG) | 51 | 0 | 51 |
| MISSED (not in the catalog) | 32 | 67 | 99 |

- **Covered.** `account/rateLimits/read`, `windowsSandbox/readiness`, `thread/read`, `thread/turns/list`, `thread/compact/start`, `thread/delete`, `thread/goal/get`, `turn/steer`, `turn/interrupt`, `review/start`.
- **Partial.** `model/list`, `thread/start`, `thread/resume`, `thread/fork`, `thread/name/set`, `thread/list`, `thread/goal/set`, `turn/start`, `skills/list`.
- **Internal only.** `initialize`, `account/read`, `thread/goal/clear`. The last is used only inside openai-codex `start_goal_operation`.
- **Missed and worth wrapping**, in priority order:
  - `thread/settings/update`, `collaborationMode/list` (P0);
  - `turn/settings/update`, `thread/memoryMode/set`, `thread/queue/add\|list\|start`, `thread/search`, `thread/unsubscribe`, `thread/backgroundTerminals/list\|clean`, `plugin/installed` (P1);
  - `memory/status`, `memory/reset`, `marketplace/*`, `externalAgentConfig/*`, `feedback/upload`, `thread/realtime/*`, `process/spawn`, `environment/info`, `project/*`, `thread/readState/update`, `thread/items/read`, `account/rateLimitResetCredit/consume` (P2).
- **Missed and not recommended.** These are admin, internal, test or platform plumbing:
  - `server/diagnostics`;
  - `userVerification/*`, `remoteControl/*`, `account/bedrock/*`, `account/gatewayOAuth/*`;
  - `thread/prediction/request`, `thread/increment_elicitation`, `thread/decrement_elicitation`;
  - `rollout/compress`, `mock/experimentalMethod`;
  - `plugin/share/*`, `fs/*`, `fuzzyFileSearch/session*`, `mcpServer/event/stream/*`;
  - `thread/attachmentOwner/list`, `thread/timeline/list`, `thread/searchOccurrences`, `account/workspaceMessages/read`, `account/sendAddCreditsNudgeEmail`, `externalAgentConfig/import/{recordHistory,readHistories}`.

### Server requests (11) and notifications (85)

- **Server requests.** The router (`PR:harnesses/native/codex/connection.py` `CodexServerRequestRouter.handle`, around lines 119-137) handles three groups:
  - It answers the two approval methods with `{"decision":"accept"}`.
  - It dispatches `item/tool/call` to dynamic tools.
  - It answers **every other request with `{}`**.

  `{}` is schema-invalid for:
  - `item/tool/requestUserInput`, which requires `answers` (S:ToolRequestUserInputResponse; used by plan mode and by `request_user_input`);
  - `mcpServer/elicitation/request`, which requires `action` (S:McpServerElicitationRequestResponse; `tool_call_mcp_elicitation` and `auth_elicitation` are stable and on);
  - `item/permissions/requestApproval`, which requires `permissions` (S:PermissionsRequestApprovalResponse).

  `{}` is also likely invalid for `account/chatgptAuthTokens/refresh`, `attestation/generate` and `currentTime/read` [EXP] (UNVERIFIED). The runtime effect of a schema-invalid answer is UNVERIFIED; most likely the tool call fails.
- **Notifications.** The host reads only `turn/started`, `turn/completed`, `item/completed`, `thread/tokenUsage/updated`, `thread/goal/updated` and `thread/goal/cleared` (PR:lib/constants/codex.py, "Notification names the turn watchers read"). It never surfaces the rest:
  - streaming (`item/agentMessage/delta`, `item/reasoning/*Delta`, `item/plan/delta`);
  - progress (`turn/plan/updated`, `turn/diff/updated`, `item/commandExecution/outputDelta`);
  - settings echoes (`thread/settings/updated`);
  - safety and rerouting (`model/rerouted`, `model/verification`, `guardianWarning`);
  - `warning`, `configWarning`, `deprecationNotice`, `mcpServer/startupStatus/updated`, `hook/started`, `hook/completed`.

  The stream, diff and plan rows are deferred by the spec (R3 rows `stream_codex_turn`, `get_codex_turn_diff`, `get_codex_turn_plan`).

## 5. Settings matrix (protocol field × CodexHost function)

Legend:
- **Y** = sent;
- **R** = refused with ConfigurationError (INV-27);
- **I** = silently ignored (accepted but never sent);
- **N** = not expressible;
- **–** = not applicable;
- **cfg** = reachable only untyped, through `CodexThreadSettings.config` (sent as `ThreadStartParams.config`, which the TUI itself uses with dotted keys such as `"features.apps": false`: TUI:temporary_structured_request.rs:65-100, 156).

Columns:
- **spawn** = `spawn_codex_thread`;
- **cont** = `continue_codex_thread` (thread/resume + turn/start);
- **fork** = `fork_codex_thread`;
- **subag** = `launch_codex_subagents`;
- **goal** = `run_codex_goal` or spawn with a goal;
- **skill** = `run_codex_skill` / `run_codex_openai_docs`;
- **review** = `start_codex_review`.

Sources: PR:harnesses/native/codex/wire.py:192-250, PR:agents/codex/config.py (`_thread_common`, `thread_*_kwargs`, `turn_kwargs`), and PR:harnesses/native/codex/preflight.py:51-80 (REJECTED_FIELDS).

### Thread-level fields (thread/start, thread/resume, thread/fork)

| Field (S:ThreadStartParams / ResumeParams / ForkParams) | spawn | cont | fork | subag | goal | skill | review |
|---|---|---|---|---|---|---|---|
| model, modelProvider, cwd, baseInstructions, developerInstructions | Y | Y | Y | Y | Y | Y | N |
| serviceTier (Fast = `priority`) | Y | Y | Y | Y | Y | Y | N |
| sandbox (SandboxMode preset) | Y | Y | Y | Y | Y | Y | N |
| approvalPolicy: untrusted / on-request / never | Y | Y | Y | Y | Y | Y | N |
| approvalPolicy: **granular** {sandbox_approval, rules, mcp_elicitations, request_permissions, skill_approval} | N | N | N | N | N | N | N |
| approvalsReviewer (USER refused by design, D-16) | Y | Y | Y | Y | Y | Y | N |
| config (raw overrides) | Y | Y | Y | Y | Y | Y | N |
| ephemeral | Y | R | Y | Y | R if true | R if true | – |
| personality (deprecated, no style effect) | Y | Y | R | Y | Y | Y | – |
| threadSource | Y | R | Y | Y | Y | Y | – |
| serviceName, sessionStartSource | Y | R | R | Y | Y | Y | – |
| dynamicTools [EXP] | Y | R | R (inherits parent's handler) | Y | Y | Y | – |
| permissions (named profile) [EXP] | N | N | N | N | N | N | N |
| runtimeWorkspaceRoots, environments [EXP] | N | N | N | N | N | N | N |
| projectId, historyMode, allowProviderModelFallback, daybreakEnabled, selectedCapabilityRoots [EXP] | N | – | – | N | N | N | – |
| fork: lastTurnId | – | – | Y (completed turns only) | – | – | – | – |
| fork: beforeTurnId, deferGoalContinuation, experimentalPredictionMode [EXP] | – | – | N | – | – | – | – |
| resume: initialTurnsPage [EXP] | – | N | – | – | – | – | – |
| subagent config (`config.agents.*`) | Y | Y | Y | Y | Y | Y | N |
| name (→ `thread/name/set`) | Y | R | Y | Y (the same name on every thread) | Y | Y | N |

### Turn-level fields (turn/start)

| Field (S:TurnStartParams) | spawn | cont | fork | subag | goal | skill | review |
|---|---|---|---|---|---|---|---|
| model, cwd, summary | Y | Y | R | Y | **I** | Y | N |
| effort | Y, but the **enum lacks max and ultra** | same | R | same | **I** | same | N |
| serviceTier (sticky) | Y | Y | R | Y | **I** | Y | N |
| **serviceTierForTurn** (stable) | N | N | – | N | N | N | N |
| sandboxPolicy (type only) | Y | Y | R | Y | **I** | Y | N |
| sandboxPolicy sub-fields: networkAccess, writableRoots, excludeSlashTmp, excludeTmpdirEnvVar, externalSandbox | N | N | – | N | N | N | N |
| approvalPolicy / approvalsReviewer per turn | only through `turn.approval_mode` | same | R | same | **I** | same | N |
| outputSchema | Y | Y | R | Y | **I** (never sent to Codex) | Y | N |
| disabledPluginIds (no-op in 0.163) | Y | Y | R | Y | **I** | Y | N |
| **collaborationMode** (plan) [EXP] | N | N | – | N | N | N | – |
| clientUserMessageId, parentTurnId, rootTurnId, turnTrigger (stable) | N | N | – | N | N | N | – |
| additionalContext, permissions, environments, runtimeWorkspaceRoots, cyberAccessProgram, responsesapiClientMetadata [EXP] | N | N | – | N | N | N | – |
| UserInput: text, image url, localImage, skill, mention | Y | Y | – | Y | – | Y | – |
| UserInput: image `fileId`, localImage `detail`, `audio`, `localAudio`, `text_elements` | N | N | – | N | – | N | – |
| Vidbyte caps (max_output_tokens, timeout_seconds) | Y | Y | R | Y | Y | Y | none |

- **steer.** `steer_codex_turn` sends `{threadId, expectedTurnId, input}`. It does not expose `clientUserMessageId` or `additionalContext` [EXP] (S:TurnSteerParams).
- **Agent tools.** The spawn tool lets the model set only prompt, goal, model, effort (the same closed enum), name, caps and output_schema (PR:tools/builtins/codex/threads.py:107-138). The service tier, sandbox and approvals stay with the developer's `spawn_defaults`. That is correct for cost and safety, and it should stay that way for Fast.

## 6. Proposed functions and settings (ranked)

Every signature is async and follows the PR's style. Records are frozen dataclasses with slots in `vidbyte/lib/dataclasses/codex_host.py`. "Tool" gives the agent-tool class.

### P0: core features users expect

1. **Fix the effort enum (setting).** Add `MAX="max"` and `ULTRA="ultra"` to `CodexReasoningEffort`. Better, validate against the selected model's `supportedReasoningEfforts` (the open-string protocol type S:ReasoningEffort) in preflight, the same way models are checked today.
   - Maps to `turn/start.effort`, `thread/settings/update.effort`, and `config.model_reasoning_effort`.
   - Failure: the model does not advertise the value. Raise `codex.model_unknown`-style with the list of supported values.
   - Tool: the spawn tool's `effort` choice grows the same way.
2. **Fast mode as a first-class setting.**
   - Add `CodexServiceTier(id: str, name: str, description: str)`, and add `CodexModelInfo.service_tiers: tuple[CodexServiceTier, ...]` and `default_service_tier: str`, read from S:Model.serviceTiers and defaultServiceTier.
   - Add `CodexTurnSettings.service_tier_for_turn: str`, mapped to `turn/start.serviceTierForTurn`.
   - Add a convenience constant `CODEX_FAST_TIER_NAME = "Fast"`, and a helper `resolve_codex_fast_tier(model) -> str` that returns the tier id (`priority` today).
   - Preflight: refuse a tier the model does not list (`codex.model_unknown`). Surface the managed-requirements refusal (`features.fast_mode=true violates managed requirements`, TUI:config_update_tests.rs:307).
   - Docs: Fast needs a ChatGPT sign-in for the subscription multiplier; API keys use API pricing.
   - Tool: keep it developer-only (2.5x, or 8x for Ultrafast).
3. **`update_codex_thread_settings(thread_id: str, update: CodexThreadSettingsUpdate) -> CodexThreadSettingsSnapshot`.**
   - Maps to `thread/settings/update` [EXP] with the fields model, effort, summary, serviceTier (`None` clears, omission keeps), cwd, approvalPolicy, approvalsReviewer, sandboxPolicy, permissions, collaborationMode and disabledPluginIds. The snapshot is read from the response or from the `thread/settings/updated` notification.
   - Failure modes:
     - the thread is not loaded on this host (resume first, or refuse with `session_not_found`);
     - `experimental_api=False`;
     - `permissions` combined with `sandboxPolicy`;
     - a USER reviewer (keep D-16 and D-32);
     - an unknown model, effort or tier (preflight).
   - The update applies to *subsequent* turns, so allow it while a turn is running.
   - Tool: WRITE, with a restricted variant (model, effort, collaboration mode). Never let a model widen approvals or the sandbox.
4. **Plan mode.**
   - `CodexCollaborationMode(mode: CodexModeKind, model: str = "", reasoning_effort: CodexReasoningEffort = PROVIDER_DEFAULT, developer_instructions: str | None = None)`.
   - `CodexTurnSettings.collaboration_mode: CodexCollaborationMode | None`, which `turn/start.collaborationMode` must add **after** pydantic validation, as `dynamicTools` is (PR:wire.py:203-205). Otherwise `extra="ignore"` drops it.
   - `list_codex_collaboration_modes() -> tuple[CodexCollaborationModeInfo, ...]`, mapped to `collaborationMode/list` [EXP] (S:CollaborationModeMask: name, mode, model, reasoning_effort).
   - `run_codex_plan(prompt: str, request: CodexSpawnRequest | None = None, answer_policy: CodexUserInputPolicy = AUTO_DEFER) -> CodexTurnHandle`. It is a spawn whose turn carries the plan mask. The snapshot exposes the final `plan` item text.
   - Failure modes:
     - no plan preset for the model (`collaborationMode/list` has none);
     - experimental API off;
     - the model asks questions (see item 5);
     - the turn ends without a `plan` item (`codex.response_invalid`).
   - Tool: WRITE (it spends), but it is non-mutating by design, so it is a good READ-ish delegation tool.
5. **Schema-valid answers to every server request (correctness fix plus an optional callback).** `CodexClientSettings.user_input_handler: Callable[[CodexUserInputRequest], Awaitable[CodexUserInputAnswer]] | None` (an analogue of Claude Agent SDK `can_use_tool`, a comparison). Defaults:
   - `item/tool/requestUserInput` → `{"answers": {}}`, or a configured "proceed with stated assumptions" answer per question id;
   - `mcpServer/elicitation/request` → `{"action": "decline"}`;
   - `item/permissions/requestApproval` → grant nothing (the `permissions` shape from S:GrantedPermissionProfile; exact empty value UNVERIFIED);
   - `currentTime/read` → the local clock.

   Failure modes: the handler raises or times out. Answer with the safe default, and never let an exception escape on the reader thread (keep the router's single-try rule). Not a tool.
6. **Refuse or apply turn settings on goal runs.**
   - Either add `RUN_CODEX_GOAL` (and spawn when `goal` is set) to REJECTED_FIELDS for `turn`, `output_schema` and `disabled_plugin_ids`,
   - or, better, apply them first with `thread/settings/update` (model, effort, serviceTier, summary, sandboxPolicy, collaborationMode) before `start_goal_operation`.

   Mapping: `thread/settings/update` then the existing goal start.
7. **`list_codex_mcp_servers(thread_id: str = "", server: str = "", detail: CodexMcpDetail = FULL) -> tuple[CodexMcpServerStatus, ...]`.**
   - Maps to `mcpServerStatus/list` (pages walked until the cursor repeats).
   - Failure modes: an unknown server; a startup still pending (`mcpServer/startupStatus/updated`).
   - Tool: READ. It is a deferred catalog row, ranked P0 because `/mcp` is the most-used inspection command after `/model`.

### P1: valuable

- **`start_codex_side_chat(thread_id: str, question: str | CodexRunInput, request: CodexSpawnRequest | None = None) -> CodexTurnHandle`** (`/side`).
  - Maps to `thread/fork {ephemeral: true, developerInstructions: parent + side instructions}`, then `thread/inject_items [boundary user message]`, then `turn/start`.
  - Failure modes: the parent has no completed turn; the parent is in review mode; nested side chats; goal continuation (use `deferGoalContinuation` [EXP]).
  - Tool: WRITE, but force a read-only sandbox.
- **`create_codex_worktree(cwd: str, ref: str = "", name: str = "") -> CodexWorktree`, plus `spawn_codex_thread(request.thread.cwd=worktree.path)`** (`/worktree`).
  - There is no app-server method. Implement it with `git worktree add` under a Vidbyte-owned root, mirroring `codex_worktree` (default root UNVERIFIED). Alternatively shell out to `codex exec --worktree`.
  - Failure modes: not a git repo; the ref is missing; the branch exists; Windows long paths; dirty-state rules.
  - Tool: WRITE. Removal is never a tool.
- **Memories.**
  - `set_codex_thread_memory_mode(thread_id, enabled: bool) -> None` → `thread/memoryMode/set` [EXP].
  - `get_codex_memory_status(min_consolidated_threads: int | None = None) -> CodexMemoryStatus` → `memory/status` [EXP] (range 1..4096).
  - `reset_codex_memories() -> None` → `memory/reset` [EXP]. Plain function, never a tool.
  - Typed `CodexThreadSettings.memories: CodexMemorySettings(use: bool | None, generate: bool | None)` mapped to config keys.
  - Failure: `features.memories` is off by default, so warn when it is off.
  - Tools: READ for status; WRITE for mode.
- **`update_codex_turn_settings(handle, model="", effort=…, service_tier: str | None = UNSET, summary=…, approvals_reviewer=…) -> None`** → `turn/settings/update {threadId, turnId, …}` [EXP]. Failure: the turn has already ended. Tool: WRITE, restricted.
- **Fork completeness.** Add `before_turn_id: str = ""` (mutually exclusive with `from_turn_id`) and `defer_goal_continuation: bool = False` to `fork_codex_thread`. Both are [EXP], so add them after validation.
- **Goal management** (deferred, helpers NG-3).
  - `pause_codex_goal` / `resume_codex_goal` → `thread/goal/set {status: paused|active}`;
  - `edit_codex_goal(thread_id, objective="", token_budget=None)` → `thread/goal/set`;
  - `clear_codex_goal` → `thread/goal/clear`.
  - Tool: WRITE.
- **Thread housekeeping** (deferred): `rename_codex_thread`, `archive_codex_thread`, `unarchive_codex_thread`, `revert_codex_thread(thread_id, before_turn_id)` (history only; "doesn't change local files"), `inject_codex_items`.
- **`release_codex_thread(thread_id)`** → `thread/unsubscribe`. Missed. It lets long-lived hosts unload threads, with a 30-minute grace period per the app-server docs.
- **Queue.** `queue_codex_message(thread_id, input) -> str`, `list_codex_queue`, `start_codex_queued_message` → `thread/queue/add|list|start` [EXP]. `codex queue` in the CLI is the same feature.
- **Background terminals.** `list_codex_background_terminals(thread_id)` and `stop_codex_background_terminals(thread_id)` → `thread/backgroundTerminals/list|clean` [EXP] (`/ps`, `/stop`).
- **`search_codex_thread_content(query, archived=False, source_kinds=(), limit=None)`** → `thread/search` [EXP]. It is full text, whereas `search_codex_threads` matches titles only.
- **`list_codex_child_threads(thread_id, recursive=False)`** → `thread/list {parentThreadId | ancestorThreadId}` [EXP] (`/subagents`).
- **Deferred inspection rows:** `read_codex_config(cwd, include_layers)`, `list_codex_features(thread_id)`, `list_codex_permission_profiles(cwd)`, `list_codex_plugins` and `list_installed_codex_plugins`, `get_codex_account_usage`, `exec_in_codex_sandbox`, `call_codex_mcp_tool`, `reload_codex_mcp_servers`, `add_codex_skill_roots`. All are READ, except exec, call and reload, which are WRITE.
- **Permissions settings.**
  - `CodexThreadSettings.permissions: str` (named profile [EXP]);
  - `CodexApprovalPolicy` granular, as `CodexGranularApprovals(sandbox_approval, rules, mcp_elicitations, request_permissions, skill_approval)`;
  - sandbox sub-options `network_access` and `writable_roots`.
- **`stream_codex_turn(handle) -> AsyncIterator[CodexTurnEvent]`** (deferred). It carries deltas, `turn/plan/updated`, `turn/diff/updated` and item events. Every comparable SDK streams (comparison).

### P2: niche

- `open_codex_thread_in_app(thread_id)`: opens `codex://threads/<id>`, as `/app` does.
- `run_codex_recap(thread_id)`.
- Voice: `thread/realtime/*`.
- Apps: `app/*`. Hooks: `hooks/list`.
- Import: `externalAgentConfig/*`.
- `feedback/upload`, `memory/reset`, `marketplace/*`.
- Daybreak: `thread/start.daybreakEnabled`, `thread/metadata/update`.
- Projects, sections and attachments.
- UserInput `fileId`, `audio` and `localImage.detail`.
- `account/rateLimitResetCredit/consume` (`/usage`; never a tool).
- `process/spawn`: unsandboxed, never a tool.

## 7. TUI-only (cannot be driven through the app-server protocol)

- **Pure UI:** `/ide`, `/keymap`, `/vim`, `/tui`, `/raw`, `/theme`, `/pets`, `/title`, `/statusline`, `/copy`, `/pwd`, `/quit`, `/exit`, `/config` (the UI; its writes go through `config/batchWrite`), `/agents` (the UI; its data comes from `thread/list`), the `/mention` picker, and the `toggle_fast_mode` keybinding.
- **Client-side:**
  - `/worktree`: the `codex_worktree` crate plus TUI-hosted dynamic tools `create_worktree`, `get_worktree_creation_status` and `list_worktrees`. These tools exist only in the TUI.
  - `/app`: OS deep link.
  - `/diff`: local `git diff`.
  - `/export`: rendering.
  - `/daemon`: CLI daemon management.
  - `/warnings`: retained notifications.
- **Debug or stub:** `/rollout`, `/test-approval`, `/debug-m-drop`, `/debug-m-update`.

Each of these has either a CLI flag (`--worktree`) or a plain reproduction (git, a URL opener). Only the TUI's *dynamic worktree tools for the model* cannot be reached without re-implementing them as Vidbyte dynamic tools.

## 8. Version skew and deprecations

- **CLI 0.163.0 vs SDK pin.** The SDK pin is `openai-codex>=0.162.1,<0.163.0` (PR:pyproject.toml:43), while CLI 0.163.0 is installed. PyPI has **openai-codex 0.163.0**.
  - The hand-written modules (client, api, async_client, _goal, _runtime_requirements) are **byte-identical** between the two versions.
  - `generated/v2_all.py` differs by 120 lines: thread read-state types and `ThreadListParams.excludedThreadIds`.
  - Bumping the pin is low-risk.
- **The SDK's generated models are stable-only.**
  - 62 experimental ClientRequest params types are absent, for example ThreadSettingsUpdate, TurnSettingsUpdate, CollaborationModeList, MemoryStatus, ThreadMemoryModeSet, ThreadQueue*, ThreadSearch and ThreadBackgroundTerminals*.
  - Experimental fields are absent from `ThreadStartParams` (permissions, environments, runtimeWorkspaceRoots, historyMode, projectId and others), from `TurnStartParams` (collaborationMode, permissions, additionalContext and others) and from `ThreadForkParams` (beforeTurnId, deferGoalContinuation).
  - Pydantic's default `extra="ignore"` means the PR's `model_validate(values).model_dump()` silently drops any of these fields. Every [EXP] field must be added after validation, as `dynamicTools` is.
- **Deprecated or changed in 0.163, and still exposed by the PR:**
  - `CodexPersonality` FRIENDLY and PRAGMATIC are no longer a style (README "Deprecated thread personality setting"; S:Personality).
  - `CodexReviewDelivery.DETACHED` is deprecated (S:ReviewStartParams.delivery).
  - `disabledPluginIds` does not yet filter anything (README).
  - `multiAgentMode` is ignored; use effort `ultra` (S:TurnStartParams.multiAgentMode).
  - Full-history hydration through `thread/read includeTurns` is deprecated for paginated threads (S:ThreadReadParams.includeTurns). `fork_codex_thread`, review read-back and `read_codex_thread(include_turns=True)` all rely on it.
  - `CodexApprovalsReviewer.GUARDIAN_SUBAGENT` is a legacy alias.
  - `thread/rollback` was removed (use `thread/revert`).
- **ReasoningEffort** is now an open string in the protocol, and SDK 0.162.1 already has `max` and `ultra`. The PR's enum lags both.

## 9. Docs vs binary disagreements (the binary wins)

| Topic | Docs | Binary (0.163.0) |
|---|---|---|
| `/fast` | A listed command | No enum variant. It is a dynamic `ServiceTierCommand` from catalog tiers named "Fast" (TUI:chatwidget/service_tiers.rs:75-123) |
| `/memories` scope | "controls the current chat only … doesn't change global settings" (learn.chatgpt.com/docs/customization/memories) | Writes global `memories.use_memories` and `memories.generate_memories` through `config/batchWrite` **and** sets `thread/memoryMode/set` on the current thread (TUI:app/config_persistence.rs:929-1013) |
| `thread/search` | "Not a method; use thread/list searchTerm" (app-server docs) | It exists as an experimental ClientRequest (S:ThreadSearchParams, `searchTerm` required) |
| User-input request name | `tool/requestUserInput` | `item/tool/requestUserInput` (ServerRequest.json) |
| `approval_policy = "untrusted"` | "unsupported" (config-reference) | Still in S:AskForApproval, and in PR `CodexApprovalPolicy.UNTRUSTED` |
| `plugin/install` | "under development; don't call from production" | Listed as a stable method |
| Memory methods | Not documented | `memory/status`, `memory/reset` and `thread/memoryMode/set` [EXP] |
| Fast tier value | `service_tier = "fast"` "maps to request value `priority`" | The catalog tier id is `priority`, and `from_request_value` accepts `fast` and `priority` |

## 10. UNVERIFIED

- The runtime effect of the router's `{}` answer on `item/tool/requestUserInput`, `mcpServer/elicitation/request` and `item/permissions/requestApproval`. The schema says it is invalid; the server's reaction was not run.
- Whether `serviceTier: "fast"`, as opposed to `"priority"`, is accepted on the wire for `thread/start` and `turn/start`. It is likely, given `ServiceTier::from_request_value`.
- Whether `CodexThreadSettings.config` overrides apply on `thread/resume` of a thread that is already loaded.
- Whether `review_model` is honoured from the thread config or only from process config.
- Whether `thread/resume` works on an ephemeral fork within the same process, which matters for side chats.
- The managed-worktree default root path.
- The exact empty value of `GrantedPermissionProfile`.
- The Claude Agent SDK and OpenAI Agents SDK facts in section 11 were taken from prior knowledge of their published APIs and not re-fetched this session.

## 11. Comparison with other agent SDKs (a comparison, not Codex evidence)

- **Claude Agent SDK.** Exposes:
  - `resume`, `fork_session` and `continue_conversation` options;
  - `permission_mode`, including `"plan"`;
  - `can_use_tool` approval callbacks and `hooks`;
  - streaming partial messages;
  - client methods `interrupt()`, `set_model()` and `set_permission_mode()`.
- **OpenAI Agents SDK.** Exposes:
  - streamed runs;
  - sessions and `max_turns`;
  - human-in-the-loop tool approvals as interruptions.
- **What programmatic users therefore expect from CodexHost:**
  - `set_model` / `set_permission_mode`, which maps to `update_codex_thread_settings`;
  - plan mode, which maps to `collaborationMode`;
  - an approval and question callback, which maps to section 6, P0 item 5;
  - streaming, which maps to `stream_codex_turn`.

  CodexHost already matches resume, fork and interrupt.

## 12. The larger move

The TUI uses a **shared local app-server daemon** by default: `codex --no-daemon` opts out, and `codex agents` "browse[s] all agent sessions on the shared local app-server daemon". CodexHost starts its own stdio app-server, so it sees the user's live TUI threads as `notLoaded`, and it can neither steer them nor queue into them.

`codex app-server proxy` ("Proxy stdio bytes to the running app-server control socket") suggests that a CodexHost could attach to that daemon through `launch_args_override=("codex","app-server","proxy")`. That would turn Vidbyte from "a second Codex" into "a programmatic co-pilot of the user's running Codex": queueing (`thread/queue/*`), `/side`-style forks and settings changes on sessions the human is watching. UNVERIFIED: openai-codex's `initialize` handshake over the proxy, and how ownership and approval routing work with a human client attached.

## Appendix A: full ClientRequest coverage matrix (generated by `scripts/matrix.py` from `schema-exp/ClientRequest.json`)

| # | Method | Stability | Status | PR function | Proposed | Pri |
|---|---|---|---|---|---|---|
| 1 | `initialize` | stable | INTERNAL | CodexHost.__aenter__ (version check only) | get_codex_version (deferred catalog row) | P2 |
| 2 | `server/diagnostics` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 3 | `userVerification/status` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 4 | `userVerification/enroll` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 5 | `userVerification/delete` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 6 | `userVerification/verify` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 7 | `userVerification/cancel` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 8 | `thread/start` | stable | PARTIAL | spawn_codex_thread, launch_codex_subagents, run_codex_goal, run_codex_skill, run_codex_openai_docs | see settings matrix | P0 |
| 9 | `thread/resume` | stable | PARTIAL | continue_codex_thread, compact_codex_thread (load) | resume_codex_thread (attach without a turn) | P1 |
| 10 | `thread/fork` | stable | PARTIAL | fork_codex_thread (lastTurnId only) | before_turn_id, defer_goal_continuation, start_codex_side_chat | P1 |
| 11 | `thread/archive` | stable | DEFERRED (spec) | - | archive_codex_thread | P1 |
| 12 | `thread/delete` | stable | COVERED | delete_codex_thread (plain fn, no tool) |  |  |
| 13 | `thread/unsubscribe` | stable | MISSED | - | release_codex_thread (unload after use) | P1 |
| 14 | `thread/increment_elicitation` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 15 | `thread/decrement_elicitation` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 16 | `thread/name/set` | stable | PARTIAL | spawn/fork via request.name only | rename_codex_thread | P1 |
| 17 | `thread/prediction/request` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 18 | `thread/goal/set` | stable | PARTIAL | run_codex_goal / spawn goal (objective+active, tokenBudget) | set/pause/resume/edit goal | P1 |
| 19 | `thread/goal/get` | stable | COVERED | get_codex_goal |  |  |
| 20 | `thread/goal/clear` | stable | INTERNAL | only inside openai-codex start_goal_operation | clear_codex_goal | P1 |
| 21 | `thread/queue/add` | EXPERIMENTAL | MISSED | - | queue_codex_message (codex queue) | P1 |
| 22 | `thread/queue/list` | EXPERIMENTAL | MISSED | - | list_codex_queue | P1 |
| 23 | `thread/queue/update` | EXPERIMENTAL | MISSED | - | update_codex_queued_message | P2 |
| 24 | `thread/queue/delete` | EXPERIMENTAL | MISSED | - | delete_codex_queued_message | P2 |
| 25 | `thread/queue/reorder` | EXPERIMENTAL | MISSED | - | reorder_codex_queue | P2 |
| 26 | `thread/queue/start` | EXPERIMENTAL | MISSED | - | start_codex_queued_message | P1 |
| 27 | `thread/metadata/update` | stable | DEFERRED (spec) | - | set_codex_thread_git_info | P2 |
| 28 | `thread/attachment/add` | stable | DEFERRED (spec) | - | attach_to_codex_thread | P2 |
| 29 | `thread/attachment/list` | stable | DEFERRED (spec) | - | list_codex_thread_attachments | P2 |
| 30 | `thread/attachmentOwner/list` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 31 | `thread/attachment/remove` | stable | DEFERRED (spec) | - | detach_from_codex_thread | P2 |
| 32 | `thread/section/move` | stable | DEFERRED (spec) | - | move_codex_thread_to_section | P2 |
| 33 | `thread/settings/update` | EXPERIMENTAL | MISSED | - | update_codex_thread_settings (/model, /fast, /plan, /permissions, /cd without a turn) | P0 |
| 34 | `thread/memoryMode/set` | EXPERIMENTAL | MISSED | - | set_codex_thread_memory_mode (/memories, per thread) | P1 |
| 35 | `memory/status` | EXPERIMENTAL | MISSED | - | get_codex_memory_status | P2 |
| 36 | `memory/reset` | EXPERIMENTAL | MISSED | - | reset_codex_memories (never a tool) | P2 |
| 37 | `rollout/compress` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 38 | `thread/unarchive` | stable | DEFERRED (spec) | - | unarchive_codex_thread | P1 |
| 39 | `thread/compact/start` | stable | COVERED | compact_codex_thread (completion not tracked, NG-12) |  |  |
| 40 | `thread/shellCommand` | stable | DEFERRED (spec) | - | run_codex_thread_shell (unsandboxed; never a tool) | P2 |
| 41 | `thread/approveGuardianDeniedAction` | stable | DEFERRED (spec) | - | approve_codex_guardian_denied (/approve) | P2 |
| 42 | `thread/backgroundTerminals/clean` | EXPERIMENTAL | MISSED | - | stop_codex_background_terminals (/stop) | P1 |
| 43 | `thread/backgroundTerminals/list` | EXPERIMENTAL | MISSED | - | list_codex_background_terminals (/ps) | P1 |
| 44 | `thread/backgroundTerminals/terminate` | EXPERIMENTAL | MISSED | - | terminate_codex_background_terminal | P2 |
| 45 | `thread/revert` | stable | DEFERRED (spec) | - | revert_codex_thread | P1 |
| 46 | `thread/list` | stable | PARTIAL | list_codex_threads and the list_recent/since/search helpers | parent/ancestor filters, excludedThreadIds, modelProviders, sectionId | P1 |
| 47 | `project/list` | EXPERIMENTAL | MISSED | - | list_codex_projects | P2 |
| 48 | `project/read` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 49 | `project/create` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 50 | `project/import` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 51 | `project/update` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 52 | `project/move` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 53 | `project/delete` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 54 | `threadSection/list` | stable | DEFERRED (spec) | - | list_codex_sections | P2 |
| 55 | `threadSection/create` | stable | DEFERRED (spec) | - | create_codex_section | P2 |
| 56 | `threadSection/update` | stable | DEFERRED (spec) | - | update_codex_section | P2 |
| 57 | `threadSection/delete` | stable | DEFERRED (spec) | - | delete_codex_section | P2 |
| 58 | `thread/search` | EXPERIMENTAL | MISSED | - | search_codex_thread_content (full text) | P1 |
| 59 | `thread/searchOccurrences` | EXPERIMENTAL | MISSED | - | find_codex_thread_occurrences | P2 |
| 60 | `thread/loaded/list` | stable | DEFERRED (spec) | - | list_loaded_codex_threads | P2 |
| 61 | `thread/read` | stable | COVERED | read_codex_thread, get_codex_thread_lineage, preflight |  |  |
| 62 | `thread/readState/update` | EXPERIMENTAL | MISSED | - | mark_codex_thread_read | P2 |
| 63 | `thread/turns/list` | stable | COVERED | list_codex_turns, run_codex_skill read-back |  |  |
| 64 | `thread/items/list` | stable | DEFERRED (spec) | - | list_codex_items | P2 |
| 65 | `thread/items/read` | EXPERIMENTAL | MISSED | - | read_codex_items | P2 |
| 66 | `thread/inject_items` | stable | DEFERRED (spec) | - | inject_codex_items | P1 |
| 67 | `skills/list` | stable | PARTIAL | list_codex_skills (one cwd, no forceReload) | force_reload, many cwds | P2 |
| 68 | `skills/extraRoots/set` | stable | DEFERRED (spec) | - | add_codex_skill_roots | P1 |
| 69 | `hooks/list` | stable | DEFERRED (spec) | - | list_codex_hooks | P2 |
| 70 | `marketplace/add` | stable | MISSED | - | add_codex_marketplace (never a tool) | P2 |
| 71 | `marketplace/remove` | stable | MISSED | - | remove_codex_marketplace | P2 |
| 72 | `marketplace/upgrade` | stable | MISSED | - | upgrade_codex_marketplace | P2 |
| 73 | `plugin/list` | stable | DEFERRED (spec) | - | list_codex_plugins (/plugins) | P1 |
| 74 | `plugin/search` | EXPERIMENTAL | MISSED | - | search_codex_plugins | P2 |
| 75 | `plugin/installed` | stable | MISSED | - | list_installed_codex_plugins | P1 |
| 76 | `plugin/reconcile` | stable | MISSED | - | reconcile_codex_plugins | P2 |
| 77 | `plugin/read` | stable | DEFERRED (spec) | - | read_codex_plugin | P2 |
| 78 | `plugin/skill/read` | stable | DEFERRED (spec) | - | read_codex_plugin_skill | P2 |
| 79 | `plugin/share/save` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 80 | `plugin/share/updateTargets` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 81 | `plugin/share/list` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 82 | `plugin/share/checkout` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 83 | `plugin/share/delete` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 84 | `app/read` | stable | DEFERRED (spec) | - | read_codex_app | P2 |
| 85 | `app/list` | stable | DEFERRED (spec) | - | list_codex_apps | P2 |
| 86 | `app/installed` | stable | DEFERRED (spec) | - | list_installed_codex_apps | P2 |
| 87 | `fs/readFile` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 88 | `fs/writeFile` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 89 | `fs/createDirectory` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 90 | `fs/getMetadata` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 91 | `fs/readDirectory` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 92 | `fs/remove` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 93 | `fs/copy` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 94 | `fs/watch` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 95 | `fs/unwatch` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 96 | `skills/config/write` | stable | DEFERRED (spec) | - | set_codex_skill_enabled | P2 |
| 97 | `plugin/install` | stable | DEFERRED (spec) | - | install_codex_plugin (never a tool; docs say not for prod yet) | P2 |
| 98 | `plugin/uninstall` | stable | DEFERRED (spec) | - | uninstall_codex_plugin (never a tool) | P2 |
| 99 | `turn/start` | stable | PARTIAL | spawn/continue/launch/skill | see settings matrix | P0 |
| 100 | `turn/settings/update` | EXPERIMENTAL | MISSED | - | update_codex_turn_settings (change the running turn) | P1 |
| 101 | `turn/steer` | stable | COVERED | steer_codex_turn |  |  |
| 102 | `turn/interrupt` | stable | COVERED | interrupt_codex_turn, close, Vidbyte caps |  |  |
| 103 | `thread/realtime/start` | EXPERIMENTAL | MISSED | - | start_codex_voice (/voice) | P2 |
| 104 | `thread/realtime/appendAudio` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 105 | `thread/realtime/appendText` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 106 | `thread/realtime/appendSpeech` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 107 | `thread/realtime/stop` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 108 | `thread/timeline/list` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 109 | `thread/realtime/listVoices` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 110 | `review/start` | stable | COVERED | start_codex_review (DETACHED delivery is deprecated in 0.163) |  |  |
| 111 | `model/list` | stable | PARTIAL | list_codex_models (drops serviceTiers, defaultServiceTier, inputModalities, upgrade) | extend CodexModelInfo with service tiers | P0 |
| 112 | `account/gatewayOAuth/read` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 113 | `account/gatewayOAuth/login` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 114 | `account/gatewayOAuth/cancel` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 115 | `modelProvider/capabilities/read` | stable | DEFERRED (spec) | - | get_codex_provider_capabilities | P2 |
| 116 | `experimentalFeature/list` | stable | DEFERRED (spec) | - | list_codex_features | P1 |
| 117 | `permissionProfile/list` | stable | DEFERRED (spec) | - | list_codex_permission_profiles | P1 |
| 118 | `experimentalFeature/enablement/set` | stable | DEFERRED (spec) | - | set_codex_features (process-wide; never a tool) | P2 |
| 119 | `remoteControl/enable` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 120 | `remoteControl/disable` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 121 | `remoteControl/status/read` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 122 | `remoteControl/pairing/start` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 123 | `remoteControl/pairing/status` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 124 | `remoteControl/client/list` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 125 | `remoteControl/client/revoke` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 126 | `collaborationMode/list` | EXPERIMENTAL | MISSED | - | list_codex_collaboration_modes (/plan presets) | P0 |
| 127 | `mock/experimentalMethod` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 128 | `environment/add` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 129 | `environment/info` | EXPERIMENTAL | MISSED | - | get_codex_environment | P2 |
| 130 | `environment/status` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 131 | `mcpServer/oauth/login` | stable | DEFERRED (spec) | - | login_codex_mcp_oauth (/mcp login; never a tool) | P2 |
| 132 | `config/mcpServer/reload` | stable | DEFERRED (spec) | - | reload_codex_mcp_servers | P1 |
| 133 | `mcpServerStatus/list` | stable | DEFERRED (spec) | - | list_codex_mcp_servers (/mcp) | P0 |
| 134 | `mcpServer/resource/read` | stable | DEFERRED (spec) | - | read_codex_mcp_resource | P2 |
| 135 | `mcpServer/event/stream/start` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 136 | `mcpServer/event/stream/stop` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 137 | `mcpServer/tool/call` | stable | DEFERRED (spec) | - | call_codex_mcp_tool | P1 |
| 138 | `windowsSandbox/setupStart` | stable | DEFERRED (spec) | - | setup_codex_windows_sandbox | P1 |
| 139 | `windowsSandbox/readiness` | stable | COVERED | check_codex_ready, preflight |  |  |
| 140 | `account/login/start` | stable | DEFERRED (spec) | - | login fns (catalog: never a tool) | P2 |
| 141 | `account/bedrock/discover` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 142 | `account/bedrock/setup` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 143 | `account/bedrock/checkGovCloudRequirements` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 144 | `account/login/cancel` | stable | DEFERRED (spec) | - | cancel_codex_login | P2 |
| 145 | `account/logout` | stable | DEFERRED (spec) | - | logout_codex | P2 |
| 146 | `account/rateLimits/read` | stable | COVERED | get_codex_rate_limits, preflight |  |  |
| 147 | `account/rateLimitResetCredit/consume` | stable | MISSED | - | use_codex_rate_limit_reset (/usage; never a tool) | P2 |
| 148 | `account/usage/read` | stable | DEFERRED (spec) | - | get_codex_account_usage | P1 |
| 149 | `account/workspaceMessages/read` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 150 | `account/sendAddCreditsNudgeEmail` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 151 | `feedback/upload` | stable | MISSED | - | upload_codex_feedback (/feedback) | P2 |
| 152 | `command/exec` | stable | DEFERRED (spec) | - | exec_in_codex_sandbox | P1 |
| 153 | `command/exec/write` | stable | DEFERRED (spec) | - | write_codex_exec_stdin | P2 |
| 154 | `command/exec/terminate` | stable | DEFERRED (spec) | - | terminate_codex_exec | P2 |
| 155 | `command/exec/resize` | stable | DEFERRED (spec) | - | resize_codex_exec | P2 |
| 156 | `process/spawn` | EXPERIMENTAL | MISSED | - | spawn_codex_process (UNSANDBOXED; never a tool) | P2 |
| 157 | `process/writeStdin` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 158 | `process/kill` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 159 | `process/resizePty` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 160 | `config/read` | stable | DEFERRED (spec) | - | read_codex_config | P1 |
| 161 | `externalAgentConfig/detect` | stable | MISSED | - | detect_codex_import_sources (/import) | P2 |
| 162 | `externalAgentConfig/import` | stable | MISSED | - | import_codex_agent_config | P2 |
| 163 | `externalAgentConfig/import/recordHistory` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 164 | `externalAgentConfig/import/readHistories` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 165 | `config/value/write` | stable | DEFERRED (spec) | - | write_codex_config (never a tool) | P1 |
| 166 | `config/batchWrite` | stable | DEFERRED (spec) | - | write_codex_config_batch (never a tool) | P1 |
| 167 | `configRequirements/read` | stable | DEFERRED (spec) | - | read_codex_config_requirements | P2 |
| 168 | `account/read` | stable | INTERNAL | check_codex_ready, preflight | get_codex_account (deferred catalog row) | P2 |
| 169 | `fuzzyFileSearch` | stable | DEFERRED (spec) | - | fuzzy_find_codex_files | P2 |
| 170 | `fuzzyFileSearch/sessionStart` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 171 | `fuzzyFileSearch/sessionUpdate` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 172 | `fuzzyFileSearch/sessionStop` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |

Counts: {'INTERNAL': 3, 'MISSED': 99, 'PARTIAL': 9, 'DEFERRED (spec)': 51, 'COVERED': 10} total 172
By stability: {('INTERNAL', 'stable'): 3, ('MISSED', 'EXPERIMENTAL'): 67, ('PARTIAL', 'stable'): 9, ('DEFERRED (spec)', 'stable'): 51, ('COVERED', 'stable'): 10, ('MISSED', 'stable'): 32}
Mapped names not in schema (typos): []

## Appendix B: ServerRequest, ServerNotification and ClientNotification lists (from the 0.163.0 schema; X = experimental-only)

```
=== ServerRequest: 11 exp, 10 stable
  item/commandExecution/requestApproval -> #/definitions/CommandExecutionRequestApprovalParams | NEW APIs Sent when approval is requested for a specific command execution. This request is used for Turns started via turn/start.
  item/fileChange/requestApproval -> #/definitions/FileChangeRequestApprovalParams | Sent when approval is requested for a specific file change. This request is used for Turns started via turn/start.
  item/tool/requestUserInput -> #/definitions/ToolRequestUserInputParams | EXPERIMENTAL - Request input from the user for a tool call.
  mcpServer/elicitation/request -> #/definitions/McpServerElicitationRequestParams | Request input for an MCP server elicitation.
  item/permissions/requestApproval -> #/definitions/PermissionsRequestApprovalParams | Request approval for additional permissions from the user.
  item/tool/call -> #/definitions/DynamicToolCallParams | Execute a dynamic tool call on the client.
  account/chatgptAuthTokens/refresh -> #/definitions/ChatgptAuthTokensRefreshParams | 
  attestation/generate -> #/definitions/AttestationGenerateParams | Generate a fresh upstream attestation result on demand.
X currentTime/read -> #/definitions/CurrentTimeReadParams | Read the current time from an external clock owned by the client.
  applyPatchApproval -> #/definitions/ApplyPatchApprovalParams | DEPRECATED APIs below Request to approve a patch. This request is used for Turns started via the legacy APIs (i.e. SendUserTurn, SendUserMessage).
  execCommandApproval -> #/definitions/ExecCommandApprovalParams | Request to exec a command. This request is used for Turns started via the legacy APIs (i.e. SendUserTurn, SendUserMessage).
=== ServerNotification: 85 exp, 85 stable
  error -> #/definitions/ErrorNotification | NEW NOTIFICATIONS
  thread/started -> #/definitions/ThreadStartedNotification | 
  thread/status/changed -> #/definitions/ThreadStatusChangedNotification | 
  thread/readState/changed -> #/definitions/ThreadReadStateChangedNotification | 
  thread/archived -> #/definitions/ThreadArchivedNotification | 
  thread/deleted -> #/definitions/ThreadDeletedNotification | 
  thread/unarchived -> #/definitions/ThreadUnarchivedNotification | 
  thread/closed -> #/definitions/ThreadClosedNotification | 
  thread/reverted -> #/definitions/ThreadRevertedNotification | 
  skills/changed -> #/definitions/SkillsChangedNotification | 
  thread/name/updated -> #/definitions/ThreadNameUpdatedNotification | 
  thread/attachment/updated -> #/definitions/ThreadAttachmentUpdatedNotification | 
  thread/goal/updated -> #/definitions/ThreadGoalUpdatedNotification | 
  thread/prediction/updated -> #/definitions/ThreadPredictionUpdatedNotification | 
  thread/goal/cleared -> #/definitions/ThreadGoalClearedNotification | 
  thread/queue/changed -> #/definitions/ThreadQueueChangedNotification | 
  project/changed -> #/definitions/ProjectChangedNotification | 
  thread/project/updated -> #/definitions/ThreadProjectUpdatedNotification | 
  thread/environment/connected -> #/definitions/EnvironmentConnectionNotification | 
  thread/environment/disconnected -> #/definitions/EnvironmentConnectionNotification | 
  thread/settings/updated -> #/definitions/ThreadSettingsUpdatedNotification | 
  thread/tokenUsage/updated -> #/definitions/ThreadTokenUsageUpdatedNotification | 
  turn/started -> #/definitions/TurnStartedNotification | 
  hook/started -> #/definitions/HookStartedNotification | 
  turn/completed -> #/definitions/TurnCompletedNotification | 
  hook/completed -> #/definitions/HookCompletedNotification | 
  turn/diff/updated -> #/definitions/TurnDiffUpdatedNotification | 
  turn/plan/updated -> #/definitions/TurnPlanUpdatedNotification | 
  item/started -> #/definitions/ItemStartedNotification | 
  item/autoApprovalReview/started -> #/definitions/ItemGuardianApprovalReviewStartedNotification | 
  item/autoApprovalReview/completed -> #/definitions/ItemGuardianApprovalReviewCompletedNotification | 
  autoApprovalReview/strictReviewRequired -> #/definitions/StrictReviewRequiredNotification | 
  item/completed -> #/definitions/ItemCompletedNotification | 
  item/agentMessage/delta -> #/definitions/AgentMessageDeltaNotification | 
  item/plan/delta -> #/definitions/PlanDeltaNotification | EXPERIMENTAL - proposed plan streaming deltas for plan items.
  command/exec/outputDelta -> #/definitions/CommandExecOutputDeltaNotification | Stream base64-encoded stdout/stderr chunks for a running `command/exec` session.
  process/outputDelta -> #/definitions/ProcessOutputDeltaNotification | Stream base64-encoded stdout/stderr chunks for a running `process/spawn` session.
  process/exited -> #/definitions/ProcessExitedNotification | Final exit notification for a `process/spawn` session.
  item/commandExecution/outputDelta -> #/definitions/CommandExecutionOutputDeltaNotification | 
  item/commandExecution/terminalInteraction -> #/definitions/TerminalInteractionNotification | 
  item/fileChange/outputDelta -> #/definitions/FileChangeOutputDeltaNotification | Deprecated legacy apply_patch output stream notification.
  item/fileChange/patchUpdated -> #/definitions/FileChangePatchUpdatedNotification | 
  serverRequest/resolved -> #/definitions/ServerRequestResolvedNotification | 
  item/mcpToolCall/progress -> #/definitions/McpToolCallProgressNotification | 
  mcpServer/oauthLogin/completed -> #/definitions/McpServerOauthLoginCompletedNotification | 
  mcpServer/startupStatus/updated -> #/definitions/McpServerStatusUpdatedNotification | 
  mcpServer/event/stream/notification -> #/definitions/McpServerEventStreamNotification | 
  account/updated -> #/definitions/AccountUpdatedNotification | 
  account/gatewayOAuth/changed -> #/definitions/GatewayOAuthChangedNotification | 
  account/rateLimits/updated -> #/definitions/AccountRateLimitsUpdatedNotification | 
  app/list/updated -> #/definitions/AppListUpdatedNotification | 
  remoteControl/status/changed -> #/definitions/RemoteControlStatusChangedNotification | 
  externalAgentConfig/import/progress -> #/definitions/ExternalAgentConfigImportProgressNotification | 
  externalAgentConfig/import/completed -> #/definitions/ExternalAgentConfigImportCompletedNotification | 
  fs/changed -> #/definitions/FsChangedNotification | 
  item/reasoning/summaryTextDelta -> #/definitions/ReasoningSummaryTextDeltaNotification | 
  item/reasoning/summaryPartAdded -> #/definitions/ReasoningSummaryPartAddedNotification | 
  item/reasoning/textDelta -> #/definitions/ReasoningTextDeltaNotification | 
  thread/compacted -> #/definitions/ContextCompactedNotification | Deprecated: Use `ContextCompaction` item type instead.
  model/rerouted -> #/definitions/ModelReroutedNotification | 
  model/verification -> #/definitions/ModelVerificationNotification | 
  modelProvider/authRecoveryStarted -> #/definitions/AuthRecoveryNotification | 
  modelProvider/authRecoveryCompleted -> #/definitions/AuthRecoveryNotification | 
  turn/moderationMetadata -> #/definitions/TurnModerationMetadataNotification | 
  model/safetyBuffering/updated -> #/definitions/ModelSafetyBufferingUpdatedNotification | 
  warning -> #/definitions/WarningNotification | 
  guardianWarning -> #/definitions/GuardianWarningNotification | 
  deprecationNotice -> #/definitions/DeprecationNoticeNotification | 
  configWarning -> #/definitions/ConfigWarningNotification | 
  fuzzyFileSearch/sessionUpdated -> #/definitions/FuzzyFileSearchSessionUpdatedNotification | 
  fuzzyFileSearch/sessionCompleted -> #/definitions/FuzzyFileSearchSessionCompletedNotification | 
  thread/realtime/started -> #/definitions/ThreadRealtimeStartedNotification | 
  thread/realtime/itemAdded -> #/definitions/ThreadRealtimeItemAddedNotification | 
  thread/realtime/item/started -> #/definitions/ThreadRealtimeItemStartedNotification | 
  thread/realtime/item/transcript/delta -> #/definitions/ThreadRealtimeItemTranscriptDeltaNotification | 
  thread/realtime/item/completed -> #/definitions/ThreadRealtimeItemCompletedNotification | 
  thread/realtime/transcript/delta -> #/definitions/ThreadRealtimeTranscriptDeltaNotification | 
  thread/realtime/transcript/done -> #/definitions/ThreadRealtimeTranscriptDoneNotification | 
  thread/realtime/outputAudio/delta -> #/definitions/ThreadRealtimeOutputAudioDeltaNotification | 
  thread/realtime/sdp -> #/definitions/ThreadRealtimeSdpNotification | 
  thread/realtime/error -> #/definitions/ThreadRealtimeErrorNotification | 
  thread/realtime/closed -> #/definitions/ThreadRealtimeClosedNotification | 
  windows/worldWritableWarning -> #/definitions/WindowsWorldWritableWarningNotification | Notifies the user of world-writable directories on Windows, which cannot be protected by the sandbox.
  windowsSandbox/setupCompleted -> #/definitions/WindowsSandboxSetupCompletedNotification | 
  account/login/completed -> #/definitions/AccountLoginCompletedNotification | 
=== ClientNotification: 1 exp, 1 stable
  initialized -> None | 
```
