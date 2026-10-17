# S0 Scout report: BrowserAgent code map

- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-browser-agent`, HEAD `08f67e7f4a6fb3e0c524d476965f82d28d89e941`.
- What I did not do: no commits, no installs, no gate runs, no pytest or lint runs, no `import vidbyte`, and no reads under `docs/` except `docs/spec/browser-agent/request.md`.
- Output: `docs/spec/browser-agent/context/code-map.md`, with four `## ` headings (checked with `grep -c "^## "`, which returned 4).
- Every `path:line` below is in a file I opened in this worktree. Anything I did not open is marked `unverified`.

## 1. Planned read list (step 3)

The files are grouped by why each is on the list. The last group was added during reading.

- **Rules and gates:**
  - `AGENTS.md`, `REPO_MAP.md`, `scripts/run_ci.py`, `lint/run.py`, `lint/rules/` (the listing plus the docstrings of the rules that bite), `scripts/generate-sdk-public-api.py`, `pyproject.toml`;
  - the field guide `init.md` and its topic files;
  - `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`.
- **Sibling agent the new package is modeled on (Jev):**
  - `vidbyte/agents/jev/{agent,runtime,settings,usage,response,README.md,__init__}`;
  - `vidbyte/agents/jev/continuation/{__init__,base,fresh}.py`;
  - `vidbyte/agents/jev/done/reviewer.py`;
  - `vidbyte/lib/jev/decision.py`.
- **Second sibling (InfiniteMemory, the newest specialized runtime):**
  - `vidbyte/agents/infinite/{agent,runtime,settings,launch,README.md,__init__}`;
  - `vidbyte/tools/toolsets/infinite.py`;
  - `vidbyte/lib/{dataclasses,enums,constants,registries}/infinite.py`;
  - the prompt family `vidbyte/prompts/prompts/infinite_memory/`;
  - the test pack `tests/features/infinite_memory_agent/`.
- **Loop and hooks:**
  - `vidbyte/agents/base.py`, `vidbyte/agents/runtime.py`, `vidbyte/agents/fork.py`, `vidbyte/agents/mixins.py`;
  - `vidbyte/agents/settings/{__init__,loop}.py`;
  - `vidbyte/agents/runtimes/__init__.py`;
  - `vidbyte/agents/multi/agent.py` (the `on_event` region).
- **Registration rows and exports:**
  - `vidbyte/lib/enums/{agent_runtime,__init__,prompts,structured_output,infinite}.py`;
  - `vidbyte/lib/registries/{runtimes,__init__,prompts,structured_output,infinite}.py` and `vidbyte/lib/registries/README.md`;
  - `vidbyte/lib/constants/{__init__,infinite,delegation}.py`;
  - `vidbyte/lib/dataclasses/{validation,prompts,infinite,agents(grep),middleware(grep)}.py`;
  - `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `contracts/sdk-public-api.json`;
  - `vidbyte/agents/README.md`, `vidbyte/prompts/README.md`.
- **MCP:**
  - `vidbyte/tools/mcp/{types,attach,bridge,client,presets,transport,__init__}.py` and `vidbyte/tools/mcp/README.md`;
  - `vidbyte/lib/config/mcp_presets.py`;
  - `vidbyte/lib/dataclasses/mcp.py`;
  - `vidbyte/lib/errors/base.py`.
- **Tools:**
  - `vidbyte/tools/{function_tool,decorators,base,types,catalog,agent_tool,__init__}.py`;
  - `vidbyte/tools/toolsets/{__init__,infinite,coding}.py`.
- **Context and middleware:**
  - `vidbyte/context/{compaction,window,manager}.py`;
  - `vidbyte/middleware/builtins/{token_budget,context_compaction,delegation_limits,cost_budget}.py`;
  - `vidbyte/middleware/compaction/{context_compaction,engine,strategies}.py`;
  - `vidbyte/lib/util/text.py`.
- **Prompts:**
  - `vidbyte/prompts/{catalog,__init__}.py` and `vidbyte/prompts/README.md`;
  - `vidbyte/lib/dataclasses/prompts.py`;
  - the families `goals/`, `jev_continuation/`, `infinite_memory/`.
- **Tests and fakes:**
  - `tests/features/infinite_memory_agent/*`;
  - `tests/test_mcp_bridge.py`, `tests/test_mcp_attachment.py`, `tests/agent_test_support.py`;
  - the `git grep "class Fake|class Stub|class Recording"` hits in `tests/`.
- **Added while reading:**
  - `vidbyte/lib/usage_ledger.py` (how worker usage reaches the parent);
  - `vidbyte/lib/dataclasses/coding.py` and `vidbyte/tools/toolsets/coding.py` (the key-holding settings sibling and the native fetch tools);
  - `vidbyte/middleware/compaction/strategies.py` (sliding-window semantics).

## 2. Files actually read (step 4)

"Full" means read to the last line. Large files were read in ranges after `wc -l`. "Ranges" lists what was read. "Grep" means line-located only.

| File | Lines | Read |
| --- | --- | --- |
| `AGENTS.md` | 81 | full |
| `docs/spec/browser-agent/request.md` | 168 | full (twice) |
| `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md` | 38 | full |
| field guide `init.md` | 28 | full |
| field guide `local-ci-verification.md` | 64 | full |
| field guide `runtime-boundaries.md` | 50 | full |
| field guide `prompt-families.md` | 8 | full |
| field guide `prebuilt-agents.md` | 15 | full |
| field guide `model-facing-tool-contracts.md` | 22 | full |
| field guide `comment-format.md` | 8 | full |
| field guide `strict-config-dataclasses.md` | 73 | full |
| field guide `class-bound-helpers.md` | 64 | full |
| field guide `blocking-lint-invariants.md` | 66 | full |
| field guide `declarative-config-resolution.md` | 43 | full |
| field guide `review-scope.md` | 16 | full |
| field guide `jev-capability-layout.md` | 210 | full |
| `REPO_MAP.md` | 423 | full |
| `scripts/run_ci.py` | 287 | full |
| `lint/run.py` | 75 | full |
| `scripts/generate-sdk-public-api.py` | 152 | full |
| `lint/rules/{a001,a002,a003,a005,a006,a007,a009,c001,c002,c008,c011,c015,c016,s008,s015,s020,s024,s025,s060}*.py` | 81, 106, 132, 94, 194, 170, 86, 88, 106, 364, 460, 362, 216, 36, 123, 89, 115, 312, 87 | module docstrings, plus a001 `REQUIRED_FIELDS` :24-32, a002 :23-24, c011 :26-34 |
| `pyproject.toml` | — | full |
| `vidbyte/lib/enums/agent_runtime.py` | 55 | full |
| `vidbyte/lib/registries/runtimes.py` | 69 | full |
| `vidbyte/agents/base.py` | 1830 | full (5 ranges), re-read 80-86, 866-890, 1460-1486 |
| `vidbyte/agents/runtime.py` | 2304 | full (5 ranges), re-read 736-760, 1085-1101, 1935-1965 |
| `vidbyte/agents/fork.py` | 252 | full |
| `vidbyte/agents/mixins.py` | 388 | full |
| `vidbyte/agents/jev/agent.py` | 132 | full |
| `vidbyte/agents/jev/runtime.py` | 293 | full |
| `vidbyte/agents/jev/usage.py` | 94 | full |
| `vidbyte/agents/jev/response.py` | 157 | full |
| `vidbyte/agents/jev/settings.py` | 417 | full |
| `vidbyte/agents/jev/README.md` | 55 | full |
| `vidbyte/agents/jev/__init__.py` | 281 | full |
| `vidbyte/agents/jev/continuation/{__init__,base,fresh}.py` | 16, 40, 129 | full |
| `vidbyte/agents/jev/done/reviewer.py` | 73 | full |
| `vidbyte/lib/jev/decision.py` | 64 | full |
| `vidbyte/agents/infinite/{agent,runtime,settings,launch,README.md,__init__}` | 123, 118, 208, 380, 115, 26 | full |
| `vidbyte/agents/runtimes/__init__.py` | 64 | full |
| `vidbyte/agents/settings/{__init__,loop}.py` | 22, 235 | full |
| `vidbyte/agents/multi/agent.py` | — | lines 40-110 only |
| `vidbyte/tools/mcp/{types,attach,bridge,client,presets,transport,__init__}.py` | 71, 105, 133, 173, 502, 507, 187 | full |
| `vidbyte/tools/mcp/README.md` | 169 | full |
| `vidbyte/lib/dataclasses/mcp.py` | 27 | full |
| `vidbyte/lib/config/mcp_presets.py` | 1833 | ranges 1-155, 953-984, 1693-1701 (the browser, search and fetch presets and `ALL_PRESETS`); the other ~1,600 lines are non-browser presets |
| `vidbyte/lib/errors/base.py` | 615 | full |
| `vidbyte/prompts/catalog.py` | 198 | full |
| `vidbyte/prompts/__init__.py` | 35 | full |
| `vidbyte/lib/registries/prompts.py` | 8 | full |
| `vidbyte/lib/dataclasses/prompts.py` | 70 | full |
| `vidbyte/lib/enums/prompts.py` | 218 | full |
| `vidbyte/lib/enums/structured_output.py` | 35 | full |
| `vidbyte/lib/registries/structured_output.py` | 107 | full |
| `vidbyte/prompts/prompts/goals/{goals.json,goal_prompt.md}` | 11, 27 | full |
| `vidbyte/prompts/prompts/jev_continuation/{jev_continuation.json,continue_prompt.md}` | 11, 29 | full |
| `vidbyte/prompts/prompts/infinite_memory/infinite_memory.json` | 167 | full |
| `vidbyte/prompts/prompts/infinite_memory/{root_system_prompt,launch_tool_description,map_header,result_card}.md` | 72, 15, 1, 7 | full |
| `vidbyte/tools/{function_tool,decorators,types,base}.py` | 263, 44, 41, 181 | full |
| `vidbyte/tools/catalog.py` | 164 | full |
| `vidbyte/tools/agent_tool.py` | 100 | full |
| `vidbyte/tools/__init__.py` | 82 | full |
| `vidbyte/tools/toolsets/{__init__,infinite}.py` | 26, 53 | full |
| `vidbyte/tools/toolsets/coding.py` | 138 | header and imports (1-56) |
| `vidbyte/lib/dataclasses/coding.py` | 325 | lines 40-130 |
| `vidbyte/lib/registries/{infinite,__init__}.py` | 54, 56 | full |
| `vidbyte/lib/registries/README.md` | 78 | full |
| `vidbyte/lib/enums/infinite.py` | 70 | full |
| `vidbyte/lib/enums/__init__.py` | 304 | full |
| `vidbyte/lib/constants/{__init__,infinite,delegation}.py` | 167, 195, 22 | full |
| `vidbyte/lib/dataclasses/infinite.py` | 189 | full |
| `vidbyte/lib/dataclasses/validation.py` | 262 | full |
| `vidbyte/lib/dataclasses/agents.py` | 478 | grep (`AgentStopReason` :61-80, `ProviderKeys` :211, `AgentInput` :361-367, `AgentMessage` :385-396, `AgentForkSettings` :423) |
| `vidbyte/lib/dataclasses/middleware.py` | — | grep (`MiddlewareDecision.continue_` :94, `abort` :120, `deny_tool` :134, `DelegationLimits` :240) |
| `vidbyte/lib/usage_ledger.py` | 57 | grep (:23-48) |
| `vidbyte/lib/util/text.py` | — | lines 60-110 |
| `vidbyte/context/{compaction,window,manager}.py` | 17, 38, 372 | full |
| `vidbyte/context/runtime.py`, `vidbyte/context/primitives/documents.py` | — | ranges (`ContextWindowPlacement` :30-36, `TextContextItem` :56-65) |
| `vidbyte/middleware/builtins/{token_budget,context_compaction,delegation_limits,cost_budget}.py` | 116, 15, 74, 96 | full |
| `vidbyte/middleware/compaction/context_compaction.py` | 562 | lines 111-262 |
| `vidbyte/middleware/compaction/engine.py` | 474 | lines 40-75, 200-225 |
| `vidbyte/middleware/compaction/strategies.py` | — | lines 663-705 |
| `vidbyte/agents/__init__.py` | — | lines 80-92, plus grep for the `__all__` rows |
| `vidbyte/__init__.py` | — | lines 10-14 and 104-112, plus grep for the enum import and `__all__` rows |
| `contracts/sdk-public-api.json` | — | lines 246-257 |
| `vidbyte/agents/README.md` | 405 | the InfiniteMemory section :151-181 and Key Modules :394 (not the rest) |
| `vidbyte/prompts/README.md` | 484 | quick-reference rows :60-70, the family section :229-250 and Key Modules :473-478 (not the rest) |
| `tests/features/infinite_memory_agent/README.md` | 30 | full |
| `tests/features/infinite_memory_agent/FEATURE.md` | 128 | full |
| `tests/features/infinite_memory_agent/infinite_memory_fixtures.py` | 556 | full |
| `tests/features/infinite_memory_agent/test_infinite_memory_contract.py` | 493 | test list and the cited test bodies |
| `tests/features/infinite_memory_agent/test_infinite_memory_{acceptance,context,delegation,resume,verification,workspace}.py` | 180, 85, 609, 392, 308, 671 | not read beyond names and line counts |
| `tests/test_mcp_bridge.py` | 318 | lines 1-80, plus test names |
| `tests/test_mcp_attachment.py` | 640 | lines 1-135 |
| `tests/agent_test_support.py` | 73 | grep (`OfflineTestAgent` :48, `bind_test_runner` :62, `build_test_agent` :68) |

**Not read, or not read in full:**
- `vidbyte/lib/dataclasses/{tools,__init__}.py`;
- `vidbyte/lib/constants/jev.py` (794 lines) and `vidbyte/lib/enums/jev.py` (362);
- `vidbyte/agents/jev/continuation/done.py` (738), `vidbyte/lib/jev/done/{done,state}.py`, `vidbyte/agents/jev/done/{run_state,handoff}.py` (grep only);
- `vidbyte/tools/builtins/operations/fetch.py` (seen only through the imports at `vidbyte/tools/toolsets/coding.py:29-36`);
- the rest of `vidbyte/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/agents/README.md` and `vidbyte/prompts/README.md`;
- the six Infinite test files listed above, as bodies.

Not one of these changes a fact recorded in the code map. Where a fact depends on one of them, it is marked "unverified".

## 3. Where the areas hint and vidbyte-gates.md are wrong or incomplete

- **The PYTHONPATH split.** vidbyte-gates.md gives the local gate as `python scripts/run_ci.py`. AGENTS.md agrees, under "## Repository Map". Neither mentions the worktree split from field guide `local-ci-verification.md`: run `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` without `PYTHONPATH`.
- **Three other omissions in vidbyte-gates.md:**
  - semgrep scans only git-tracked files, so `git add -A` comes first;
  - the pin `semgrep==1.170.1`;
  - `scripts/generate-sdk-public-api.py --check`, and the fact that the generator refuses to write while its inputs differ from HEAD.
- **Where BrowserAgentTools lives.** The areas hint puts it at `vidbyte/agents/browser/tools.py`. Field guide `prebuilt-agents.md` puts `<Agent>Tools(Tools)` in `vidbyte/tools/toolsets/<agent>.py`, which is where Infinite and Coding keep theirs.
- **Events siblings.** The request and the hint name `InfiniteEvents` as the events sibling. It is not on main, and neither is any `JevEvents` (Q K).
- **README sections.** The request expects a folder README with "a File Index and `## Notes for agents`" modeled on Jev. Jev's README has neither. Infinite's has both.
- **Screenshots and keys.** The request assumes screenshots reach the worker as images, and that a missing key may be supplied through `os.environ`. The code contradicts both (Q B, Q F).
- **A correction to my own earlier draft.** I first wrote that the field guide has no "quick checks". The briefing's "quick check" is each entry's **Check:** line. Code-map §1.7 now quotes the **Check:** line of every applicable entry.
- **What I could not do as asked.** The briefing asked for "the exact install, lint, test … commands as AGENTS.md states them". AGENTS.md states only `python scripts/run_ci.py`. The other commands in the code map are attributed to the files they come from.

## 4. Answers to Questions A–N

### Q A: fakes for MCP transport and model calls

- **Attaching a fake MCP server to an agent.**
  - Patch the class `attach.py` constructs: `@patch("vidbyte.tools.mcp.attach.McpStdioTransport", MockMcpStdioTransport)` (`tests/test_mcp_attachment.py:119`).
  - `MockMcpStdioTransport` (`tests/test_mcp_attachment.py:49-106`) takes `command`, `env`, `request_timeout`, `shutdown_timeout` and `stderr_max_bytes`. It implements `start()`, then `request(method, params)` for `initialize`, `tools/list` (one tool, `remote_<command[0]>`) and `tools/call` (text `mocked_response`), then `close()`. It records every instance.
  - A test then calls `await agent.attach_mcp_server(command=["myserver"])` on `build_test_agent(name=…, system_prompt=…, runner=DoneRunner())` (`tests/agent_test_support.py:68`).
  - `TwoToolMcpTransport(MockMcpStdioTransport)` (`tests/test_agent_fork_isolation.py:119`, patched at :382) is used the same way, and so is `tests/test_fork_tool.py:466`.
- **Client and bridge level.** `FakeTransport` (`tests/test_mcp_bridge.py:30`) implements `async request(method, params)`. It is used as `McpClient(FakeTransport())` and `await McpToolBridge(registry, client, permission=ToolPermission.READ).bridge()` (:165-166). `RaisingFakeTransport` and `PagedFakeTransport` cover errors and pagination.
- **Model fakes.**
  - `ScriptedTree.install()` (`tests/features/infinite_memory_agent/infinite_memory_fixtures.py:287-295`) patches `BaseAgent._runner_for_model` for every agent and routes scripts by `agent.name`.
  - Also: `FakeRunner` and `RecordingRunner` (`tests/test_agent_runtime.py:61`, `:67`); `FakeRunner` (`tests/test_agent_tool.py:35`); `RecordingRunner` (`tests/test_jev_compute_clone.py:35`); `RecordingTracer(TracerBase)` (`tests/test_agent_fork_isolation.py:131`); `RecordingModel` (`tests/features/system_prompt_presets/fakes.py:39`); `DoneRunner` (`tests/test_mcp_attachment.py`, before :119).
- There is no `tests/conftest.py` and no `tests/features/conftest.py`.

### Q B: how MCP image content flows into context

- `McpClient.call_tool` (`vidbyte/tools/mcp/client.py:90-115`) converts the raw result:
  ```python
  text = self._content_to_text(result)
  if len(text) > self.max_output_chars:
      text = text[: self.max_output_chars] + "\n...[truncated]"
  ...
  return ToolResult.success(name, text, metadata={"remote_error": False})
  ```
  These lines are at :109-115. `isError` gives `ToolResult.error(name, text, metadata={"remote_error": True})` (:112-114). A protocol exception gives `ToolResult.error(name, output, metadata={"error": "mcp_error"})` (:108).
- `_content_to_text` (:124-173) turns `image` and `audio` blocks into `f"[{item.get('type')}: {mime}, {size} base64 chars omitted]"` (:136-143, `@intent mcp-binary-content-stays-out-of-prompts`). `max_output_chars=8000` is set at :31.
- `McpBridgedTool.execute` (`vidbyte/tools/mcp/bridge.py:61-69`) passes the `ToolResult` through.
- The loop stores a provider-formatted `dict`: `_append_tool_result_message` (`vidbyte/agents/runtime.py:1935-1953`) calls `ToolsFormatter.format_tool_result(call, visible_result, provider)` and `messages.append(dict(formatted))`. History is `list[dict[str, Any]]`.
- **Answer:** text only. The base64 is dropped in the client. The transport reads lines of up to 64 MiB (`transport.py:65-68`), so the drop is not a wire limit.

### Q C: prompt families; is `goals/` reusable

- **The loader.**
  - `Prompts._load` (`vidbyte/prompts/catalog.py:85-126`) finds `*.json` at the top level or one directory deep (`_json_assets` :128-138).
  - Each JSON needs `name`, `description`, `key` and a non-empty `prompts` (:147-157).
  - Each leaf is `{path: "<leaf>.md", source_url}`; any other suffix is a `ConfigurationError` (:166-181).
  - The enum value is `"<family_key>.<leaf>"`. An unknown value fails the import (:107-111), and every `Prompt` member must have an asset (:189-193).
  - `vidbyte/prompts/__init__.py:22-27` generates module-level string exports. `vidbyte/lib/registries/prompts.py` re-exports `PromptRecord, Prompts`.
  - Call shape: `Prompts().get(Prompt.X)` (:34-38).
- **The enum.** `Prompt(str, Enum)` is at `vidbyte/lib/enums/prompts.py:65-206`, with hand-kept counts at :7-8 and :45-46.
- **Packaging.** `pyproject.toml` package-data `"vidbyte.prompts.prompts" = ["*.json", "*.md", "*/*.json", "*/*.md"]` ships a new family directory without a pyproject edit (C015).
- **Where a family must be listed.** The prompts README quick reference table (`vidbyte/prompts/README.md:65`, `:67`) and a per-family section (:229-250). The infinite pack also has a leaf-count contract test (`test_infinite_memory_contract.py:172`).
- **Is `goals/` reusable?** No. `goals/goal_prompt.md` (27 lines) is a general Codex `/goal` emulation system prompt with no placeholders and nothing about a verdict. Its first line includes "You do not claim to have Codex's native /goal tool". It is keyed `Prompt.GOALS_GOAL_PROMPT` (`vidbyte/lib/enums/prompts.py:161`). Unverified: which code consumes it.
- **Other families.** `jev_continuation/continue_prompt.md` (29 lines) takes `{request}{run_state}{handoff}{failed}{focus}`. `infinite_memory/` has 40 leaves: role prompts, the task, verifier and resume prompts, the result card, the map header, and one leaf per tool and per parameter description.

### Q D: finish-attempt hook and per-iteration injection

- **The hook.** `AgentRuntime._continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool` (`vidbyte/agents/runtime.py:917-923`) returns False. It is called at :598 (final text answer) and :673 (isDone). Returning True continues the loop with whatever was appended to `messages`.
- **After each tool iteration.** `_after_tool_iteration(self, state, messages) -> None` (:925-931) is called at :700.
- **How Jev uses them.**
  - Jev overrides both: `_continue_finish_attempt` at `vidbyte/agents/jev/runtime.py:252-279` (`if should_continue: continue_`) and `_after_tool_iteration` at :282-290.
  - Jev wraps the loop in `arun` (:86-102), which runs `_arun_metered` (:104-155) inside `self.usage.scope()`. `_arun_metered` calls `response.start` (:118), `super().arun` (:145) and `response.finished(result, self.usage.settle())` (:155).
  - The contract is `JevContinuation(ABC)` (`continuation/base.py:24-37`). The fresh-context example is `JevFreshContinuation` (`continuation/fresh.py:31-126`, appends a user message at :85-86).
- **Per-iteration injection.** Infinite's `_after_tool_iteration` (`vidbyte/agents/infinite/runtime.py:104-110`) re-upserts `_map()` (:112-115) as a `TextContextItem` with a fixed `primitive_id` at `ContextWindowPlacement.TOP_OF_CONTEXT`, so the item is replaced in place. The context manager is rendered into the system string by `_build_system_string` (`runtime.py:1668-1677`).

### Q E: MCP attachment, partition, and sharing

- **Attaching.** `attach_mcp_servers(servers) -> self` (`vidbyte/agents/mixins.py:97-145`) attaches all or nothing and raises `McpAttachmentError`. Connection is lazy, in `_ensure_mcp_connected` (:200-244), awaited from `base.py:916`.
- **Handles.** `mcp_servers() -> tuple[McpServerHandle, ...]` (:264-266). `McpServerHandle(config, client, transport, bridged_tools)` (`vidbyte/tools/mcp/types.py:50-71`) is the object that maps a bridged tool back to its server.
- **One server.** `attach_mcp_server(config)` (`vidbyte/tools/mcp/attach.py:35-105`) maps READONLY to `ToolPermission.READ` and bridges nothing for DISABLED. On failure it closes the transport (:95-98).
- **Sharing with a second agent.**
  - `BaseAgent._own_tool` (`base.py:473-493`) passes `McpBridgedTool` objects through unchanged, so a second `BaseAgent(tools=[…handle.bridged_tools…])` calls the same client with no new subprocess.
  - A fork is different. `fork.py:98-99` re-queues the configs, which means new subprocesses, and `_tool_items` (:176-188) drops the parent's MCP tools.
- **Lifetime.**
  - `run()` (`base.py:1107-1114`) goes through `_run_releasing_mcp` (`mixins.py:246-262`), which closes the servers after every sync run. `arun()` (`base.py:1098`) keeps them open.
  - `__aexit__` closes them (`mixins.py:387-388`). `close_mcp_servers` is at :292-305.
  - The transport is bound to its event loop (`transport.py:152-170`).
- Unverified: whether concurrent calls from two agents on one stdio client are safe.

### Q F: `McpPresetRegistry` API, presets, missing-env error

- **Registry API.**
  - `McpPresetRegistry.get(name)` (`vidbyte/tools/mcp/presets.py:370-374`) raises `McpPresetNotFoundError` (:100).
  - `list_presets(category=None)` (:377-381).
  - `build_config(preset_name, env=None, permission=McpToolPermission.EXECUTE, timeout=30.0, extra_args=None) -> McpServerConfig` (:384-421) merges `default_env` with `env`.
  - A missing variable raises `McpPresetConfigurationError(f"Preset '{preset_name}' requires the following environment variables: {', '.join(missing_vars)}")` (:400-404, class at :104). It does not read `os.environ`.
- **Config record.** `McpServerConfig(command, name=None, permission=McpToolPermission.EXECUTE, env=None, timeout=30.0)` (`types.py:39-47`) is frozen and has no validation.
- **Subprocess environment.** The child gets only allowlisted variables plus `env` (`transport.py:34-62`, `build_child_env` :80-89).
- **Presets** (`vidbyte/lib/config/mcp_presets.py`; definition shape at :25-35):

  | Preset | Lines | Command | `required_env` |
  | --- | --- | --- | --- |
  | `puppeteer` | :81-87 | `npx -y @modelcontextprotocol/server-puppeteer` | none |
  | `playwright` | :89-95 | `python -m mcp_server_playwright` | none |
  | `browserbase` | :961-967 | `npx -y @browserbase/mcp-server` | `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID` |
  | `firecrawl` | :105-111 | — | `FIRECRAWL_API_KEY` |
  | `jina_reader` | :113-119 | — | `JINA_API_KEY` |
  | `brave_search` | :41-47 | — | `BRAVE_API_KEY` |
  | `tavily` | :57-63 | — | `TAVILY_API_KEY` |
  | `exa` | :65-71 | — | `EXA_API_KEY` |
  | `duckduckgo` | :73-79 | — | none |
  | `apify` | :953-959 | — | `APIFY_API_TOKEN` |

  `zenrows` (:969-975) and `scrapingbee` (:977-983) also exist. `ALL_PRESETS` is at :1693. The registry's class attributes are at `presets.py:120-129` and `:255-256`.

### Q G: structured output

- **On BaseAgent.**
  - `BaseAgent(output_schema=…)` (`base.py:91-310`) feeds `_output_contract_with_schema` (`base.py:1486-1494`).
  - The runtime adds `response_format` (`runtime.py:1616-1617`), and `_final_result` (`runtime.py:1703-1735`) fills `AgentResult.structured`.
  - The reply is `AgentMessage(…, structured=…)` (`base.py:1000-1006`). A miss raises `OutputSchemaViolationError` (`base.py:1060-1076`; class at `vidbyte/lib/errors/base.py:178-186`).
- **Provider tiers.** `StructuredOutputRegistry.resolve(provider, model)` (`vidbyte/lib/registries/structured_output.py:45-54`) resolves to `NATIVE_SCHEMA | STRICT_TOOLS | JSON_MODE | PROMPT_ONLY` (`vidbyte/lib/enums/structured_output.py:22-32`).
- **Worked example.** `JevReviewer(BaseAgent)` (`vidbyte/agents/jev/done/reviewer.py:26-70`) does six things:
  - passes `output_schema=JevReviewPayload` (:44) and `system_prompt_presets=()` (:48);
  - clears history (:54);
  - runs `await self.arun(AgentInput(prompt=request, context_manager=window))` (:57);
  - checks `isinstance(reply.structured, …)` (:58);
  - fails open on `VidbyteSdkError` (:67-70);
  - records usage via `self.get_usage()` (:64).
- Other `output_schema=` users, grep only: `vidbyte/agents/jev/done/run_state.py:288` and `handoff.py:168`.

### Q H: runtime registration

- **The enum.** `AgentRuntimeType` (`vidbyte/lib/enums/agent_runtime.py:43-52`) has `JEV = "jev"` (:51) and `INFINITE_MEMORY = "infinite_memory"` (:52).
- **The registry.** `RuntimeRegistry.resolve` (`vidbyte/lib/registries/runtimes.py:30-56`) imports from the package `__init__`s inside the method and holds one `_registry` dict with `AgentRuntimeType.JEV: JevRuntime` and `AgentRuntimeType.INFINITE_MEMORY: InfiniteMemoryRuntime`. It raises `ConfigurationError` for an unknown type.
- **BaseAgent.**
  - `_LINEAR_LOOP_RUNTIMES` (`base.py:83`) is read at :243, :1435 and :1478.
  - `_runtime()` (:1408-1461) merges `_runtime_extension_kwargs()` (:1463-1465) with `output_contract`, `usage_tracker`, `speed_tracker`, `fallback` and `agent_catalog`.
- **Refusals.**
  - Jev refuses at `vidbyte/agents/jev/runtime.py:60-74`: "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev')."
  - Infinite refuses at `vidbyte/agents/infinite/runtime.py:54`. Its contract test is `test_runtime_type_resolves_and_refuses_outside_its_agent` (`tests/features/infinite_memory_agent/test_infinite_memory_contract.py:209`).

### Q I: Jev decomposition and README shapes

- **Line counts:** `agent.py` 132, `runtime.py` 293, `settings.py` 417, `response.py` 157, `usage.py` 94.
- **`JevAgent(BaseAgent).__init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings | None = None)`** (`agent.py:35-106`):
  - refuses with "JevAgent requires a JevAgentSettings instance." (:39-40);
  - builds `JevResponse()` (:47);
  - calls `super().__init__(…, runtime=AgentRuntimeType.JEV, …)` (:91-106);
  - exposes `response` as a property (:108-111);
  - returns its collaborators from `_runtime_extension_kwargs` (:127-129).
- **`JevRuntime(AgentRuntime).__init__(*, runtime_settings=None, preflight=None, run_state=None, continuation=None, compute=None, response=None, bulk_work=None, skill_preload=None, **kwargs)`** (`runtime.py:43-84`).
- **`JevUsageAccount(tracker, agent_name)`** (`usage.py:25-91`) fails closed through four methods:
  - `scope()` (:33-37) wraps `usage_ledger_scope`;
  - `require_accounted()` (:39-58) raises `UsageAccountingError` on failures, including unpriced calls (:74-84);
  - `report()` (:60);
  - `settle()`.
- **`JevResponse`** (`response.py:44-154`) is the one writer: `start`, one method per event, then `finished(result, usage)`.
- **`JevAgentSettings`** is frozen and slotted (`settings.py:131-239`). `api_keys = field(default_factory=ProviderKeys, repr=False)` (:139), `vidbyte_api_key … repr=False` (:149), `ProviderKeyMatcher.match(…, field_name="JevAgentSettings.api_keys")` (:166).
- **READMEs.** Jev's (55 lines) has no File Index and no Notes. Infinite's (115 lines) has `## File Index` (:91-101) and `## Notes for agents` (:103-115).

### Q J: tools, loop limits, errors

- **Function tools.**
  - `FunctionTool(func, *, name=None, description=None, permission=ToolPermission.SAFE, output_schema=None)` (`vidbyte/tools/function_tool.py:24-143`) validates arguments in pydantic JSON mode (:194-203) and keeps a `ToolExecutionError`'s kind (:78-90).
  - It rejects `*args`, `**kwargs` and positional-only parameters (:151-154). Its spec metadata is `{"source": "function"}` (:138-142).
  - The decorator `@tool` is at `vidbyte/tools/decorators.py:23-37`.
  - `BaseTool` is at `vidbyte/tools/base.py:30-116`. `vidbyte/tools/types.py` re-exports `ToolSpec`, `ToolParameter`, `ToolResult` and the rest from `vidbyte/lib/dataclasses/tools.py`.
- **Field-guide rules.** 6–9 meaningful fields, 4–5 sentence descriptions, no examples, and categorical values as enums under `vidbyte/lib/enums` (`model-facing-tool-contracts.md`). S025 enforces the description depth.
- **Loop limits.**
  - `AgentLoopSettings` (`vidbyte/agents/settings/loop.py:46-235`) is a plain class, not a dataclass. Its fields are at :49-67 (`max_iterations`, `max_tokens`, `max_tool_calls`, `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens`, `allowed_tools`, `tool_error_policy`, `tool_settings`, `output_contracts`, `max_contract_rejections=3`).
  - The positive-int guard is at :102-110. Messages name `AgentLoopSettings.<field>`.
- **Errors.**
  - `ConfigurationError(VidbyteSdkError)` (`vidbyte/lib/errors/base.py:289-290`) has no packet. `VidbyteSdkError(message, *, details=None)` is at :68-75.
  - The A003 packet `DIAGNOSTIC_FIELDS = ("error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests")` appears on `ReasoningTraceArgumentError` (:86-123) and seven other classes.
  - The file header says to add one type per remediation category and export it from `errors/__init__` (:6).
  - Record validators raise `ConfigurationError(…, details={"field": field_name})` (`vidbyte/lib/dataclasses/validation.py:37-259`).

### Q K: events on main

- On main there is no `InfiniteEvents`, no `JevEvents`, and no `on_event` on `JevAgent` or `InfiniteMemoryAgent` (git grep over `vidbyte/`).
- The only callback is `MultiAgent.__init__(…, on_event: MultiAgentEventCallback | None = None, …)` (`vidbyte/agents/multi/agent.py:65`), stored at :93 and validated at :88-89. Grep also finds it at `vidbyte/agents/multi/ledger_controller.py:162-167` and `vidbyte/workflows/contracts.py:514`.
- `InfiniteJournalEvent` (`vidbyte/lib/enums/infinite.py:53-59`) is the enum for journal records.
- Jev's observable surface is the `JevResponse` writer.

### Q L: context size and compaction

- **Measuring.**
  - `TokenEstimate` (`vidbyte/lib/util/text.py:88`) provides `count` (:92), `cut` (:97) and `cap(text, max_tokens, marker)` (:104), using `TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4` (:68).
  - `AgentRuntime._approx_output_tokens` is `ceil(chars/4)` (`runtime.py:2169-2172`).
- **Compacting.**
  - `MessageHistoryCompactionMiddleware` (`vidbyte/middleware/compaction/context_compaction.py:111`) has these constructors:
    - `trim_with_provider_boundaries(max_messages=None, max_tokens=None, token_counter=None)` (:163);
    - `trim_to_token_budget` (:158);
    - `tool_output_sliding_window(keep_recent=2, window_mode=TRUNCATE_TOOL_RESULTS, max_chars=600)` (:173);
    - `clear_tool_results_except(exclude_tools)` (:178);
    - `scrub_bloat` (:188);
    - `clear_except_system_and_log`, and others.
  - Its `before_model_call` (:217-229) rewrites only the outgoing call's messages. `_apply_before_model_call_transform` is at `runtime.py:1085-1094` and the compaction count at :747-748.
  - The engine is `ContextCompactionEngine` (`vidbyte/middleware/compaction/engine.py:40`), re-exported by `vidbyte/context/compaction.py`. The sliding window keeps N results per tool name (`strategies.py:683-695`).
- **Budget abort.** `TokenBudgetMiddleware(*, max_tokens, abort_reason="token_budget_exceeded", allow_final_response_over_budget=False)` (`vidbyte/middleware/builtins/token_budget.py:40-113`) aborts the run.
- **Context manager.** `ContextManager.copy` (`vidbyte/context/manager.py:62-70`), `upsert(item, *, placement=END_OF_CONTEXT)` (:72-90; needs a `primitive_id`), `remove_by_id` (:157-161) and `render_primitives_zone` (:208-217).
- **What Infinite does.** Workers use `trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS)` (`vidbyte/agents/infinite/launch.py:277-291`; constant `90_000` at `vidbyte/lib/constants/infinite.py:72`). The root's map is upserted every iteration (`infinite/runtime.py:104-115`).
- **Gap.** `AgentLoopSettings.compaction_trigger_tokens`, `compaction_target_tokens` and `context_window_budget` are stored and exported (`base.py:317-323`, `:630-631`, `:671-673`, `:762-763`). No consumer turned up in `vidbyte/agents/runtime.py` or `vidbyte/middleware/`; outside `loop.py`, git grep for `compaction_trigger` hits only `base.py`, `fork.py` and `lib/constants/codex.py`.

### Q M: constants, exports, `REPO_MAP` row shape

- **Constants.**
  - The pattern is one module per domain, `vidbyte/lib/constants/<domain>.py`. The listing includes `codex, coding, cot_events, delegation, failure, infinite, jev, native_threads, outputs, pricing, reasoning_strategies, runners, skills, speed, trace`.
  - `vidbyte/lib/constants/infinite.py` (195 lines) has a docstring header (PURPOSE / ROLE / ARCHITECTURE NOTE with the cap arithmetic / FUNCTION INVENTORY / COMMON MODIFICATION / WHAT NOT TO DO / KNOWN EDGE CASES / RELATED DOCS / TESTS) and commented groups of `INFINITE_*` names. For example `INFINITE_HISTORY_MAX_TOKENS = 90_000` (:72), `INFINITE_RESERVED_TOOL_NAMES` (:104-109) and `INFINITE_MAP_PRIMITIVE_ID` (:126). Its `__all__` is at :138-195.
  - `vidbyte/lib/constants/__init__.py` (167 lines) re-exports only codex, cot_events, failure, reasoning_strategies, runners and speed. Infinite and jev are not re-exported.
- **Enum exports.** `vidbyte/lib/enums/__init__.py` has one import block per domain (Infinite at :80-86; `AgentRuntimeType` imported at :40) and an alphabetical `__all__` (`AgentRuntimeType` :183; Infinite :223-228).
- **Agent exports are eager.**
  - `vidbyte/agents/__init__.py:84-89` imports `InfiniteMemoryAgent`, `InfiniteMemoryAgentSettings`, `InfiniteMemoryRuntime` and `InfiniteWorkspaceSettings` from `vidbyte.agents.infinite`, and `:90` begins the import from `vidbyte.agents.jev`. The `__all__` rows are at :392-397.
  - `vidbyte/__init__.py` lists the agent exports in its header (:12), imports eagerly (:104-112) plus the enum `InfiniteMemoryPreset` (:472), and has `__all__` rows at :758-764 (starting at :731).
  - `contracts/sdk-public-api.json` (:246-257) must be regenerated after a commit.
  - The lib registry imports the runtime lazily, through the package `__init__` (`runtimes.py:33-34`).
- **REPO_MAP row shape.** `##### \`vidbyte/agents/infinite/\`` followed by one paragraph of 5–6 sentences: what it is, how it works, its limits and where they are enforced, resume, and "Its records, enums, constants, and prompt text live lower in the shared substrate, and its preset tools in the toolsets folder" (`REPO_MAP.md:83-85`; Jev at :87-89). The toolsets row says "It holds three such bundles" (:361). The constants row is at :187-189. The JEV File Locations table is at :383-423.

### Q N: feature test pack layout and commands

- **Packs on main.** `tests/features/` holds 21 packs: `agent_output_connectors, coding_agent, harness_threads, infinite_memory_agent, jev_bulk_work, jev_claims, jev_input_exhaustion, jev_input_set_coverage, jev_output_extent, jev_problem_repair, jev_read_only, jev_required_actions, jev_skills_preload, sdk_loop_settings, sdk_managed_text, sdk_middleware_limits, sdk_model_catalog, sdk_model_usage, sdk_operation_costs, sdk_provider_keys, system_prompt_presets`.
- **Layout of `tests/features/infinite_memory_agent/`:**
  - `README.md` (30 lines; Folder Description / Intent, File Index, Run, Logs);
  - `FEATURE.md` (128 lines; Contract, Invariants, Known Failure Modes, Test Suite Map, Omitted Testing Strategies, …);
  - `infinite_memory_fixtures.py` (556 lines);
  - `test_infinite_memory_<area>.py` for acceptance, contract, context, delegation, resume, verification and workspace.
  - The names follow area, not unit, integration or acceptance tiers, except the one `_acceptance` file that runs the spec's usage snippet.
- **Markers.** Only `@pytest.mark.parametrize` and one `@pytest.mark.asyncio` (`test_infinite_memory_delegation.py:95`). No custom markers; `--strict-markers` is on. No conftest.
- **Commands** (`tests/features/infinite_memory_agent/README.md:24`):
  - `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`;
  - one file: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_resume.py -q`.
- **Is the pack layout mandated?** AGENTS.md does not mandate `tests/features/` packs or any test layout; it names no test command. The packs are a convention on main, not a written rule.
- **Contract-test checklist the infinite pack pins** (`test_infinite_memory_contract.py`): exports :141, prompt leaf count :172, enum values :188, runtime refusal :209, session refusal :225, defaults :234, invalid settings :282-296, tool schemas :393, `TokenEstimate` :427, prompt text :452, and the complexity budget :471 (≤ 8 modules, ≤ 400 lines each after the header).

## 5. Notes for the orchestrator

- **Files created.** Only `docs/spec/browser-agent/context/code-map.md` and `docs/spec/browser-agent/reports/S0-scout.md`. Nothing else was modified, and no commit was made.
- **A commit will be needed later.** `scripts/generate-sdk-public-api.py` refuses to regenerate `contracts/sdk-public-api.json` while `vidbyte/__init__.py` or `pyproject.toml` differ from HEAD. The implementer must commit the export change, regenerate, and commit again, with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. C016 fails until this is done.
- **Correction to my earlier draft.** `McpClient.call_tool` spans `client.py:90-115`; the conversion lines are :109-115.
