---
slug: agent-swarm-v2
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2
branch: feat/agent-swarm
base_commit: 39ce8b20baf28690a3dc74b8fbdca9530119fdef
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1174
until: none
started: 2026-10-19 17:19
---

# Pipeline: AgentSwarm revision (PR #1174 updated in place)

This run revises an existing feature branch. `base_commit` is the PR head at the start of the run, not `origin/main` (merge-base with `origin/main` is `845a4d9b`; the branch is 63 commits ahead). The previous run's artifacts live at `docs/spec/agent-swarm/` (spec r5) and are the baseline; this run's artifacts live at `docs/spec/agent-swarm-v2/`. The last stage edits PR #1174's title and body and resolves its four review threads; it never opens a second PR.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-19 17:19 | 2026-10-19 21:50 | reports/S0-scout.md, reports/S0-compaction-researcher.md | base_commit 39ce8b20; code-map.md (~60 files); compaction-research.md |
| S1 spec + review | running | 2026-10-19 21:52 | | reports/S1-spec-author.md, reports/S1-spec-review.md | spec r1 at 57c20f68 (18 FR, 25 AC, 35 EC, 40 INV, 18 D, 7 Q; 57 §12.3 rows; budget 16 new files = 2 .py + 14 .md); review round 1 running |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-19 17:19 — Worktree created on the existing branch `feat/agent-swarm` (synced to origin at 39ce8b20) instead of a new `feat/<slug>` branch from `origin/main` — the user asked for PR #1174 to be updated in place, not replaced.
- 2026-10-19 17:19 — New spec folder `docs/spec/agent-swarm-v2/` instead of revising `docs/spec/agent-swarm/` in place — the old folder holds the previous run's pipeline state and reports, which this run must not overwrite; the r5 spec there is the named baseline subagents may read.
- 2026-10-19 17:19 — S0 launches a second agent, a compaction researcher, in parallel with the scout — the user asked for best-in-class prebuilt compaction to be researched and integrated ("Compaction is very important"); the spec author needs that research as an input, and the scout's job must stay small.
- 2026-10-19 17:19 — Defaults applied to the unanswered halves of the alignment questions (recorded in request.md §C "Clarifications and answers"): thoroughness sections live in the shared system prompt; members keep name/provider/model and lose `system_prompt`; no web-search provider selected means no web-search tool, a selected provider with no key is refused at settings time; events always-on with no cap; offline scripted tests only.

- 2026-10-19 21:29 — Both S0 agents hit the account session limit at ~17:40 (reset 21:10) before writing any file; resumed via SendMessage from their saved transcripts at 21:29 rather than relaunched fresh, so their reading is not repeated.

- 2026-10-20 15:19 — The S1 spec author hit the session limit at ~23:30 on 10-19 (reset 02:10) after reading but before writing anything; resumed via SendMessage from its transcript at 15:19 rather than relaunched, with the instruction to re-open any file it cites.

## User replies (verbatim)
- 2026-10-19 17:15 — the ten alignment answers; verbatim in request.md §A Prompt 5.

## Niche facts accumulated (carried into every later briefing)
- CI on this repo runs only by manual dispatch (`gh workflow run ci.yml --ref feat/agent-swarm`; Static policy is `static-policy.yml`); `gh pr checks` stays empty; read results with `gh run list --branch feat/agent-swarm`. — *source:* previous PR body (docs/spec/agent-swarm/pr-body.md)
- Lint TID251/S039 bans `asyncio.Lock`; a one-slot `asyncio.Semaphore()` is the accepted mutex. — *source:* previous PR body
- Lint C012 accepts only `ModelProvider(value)` as proof of a valid provider, not `RecordFieldConverter.to_enum`. — *source:* previous PR body
- mypy rejects `Callable` as an `isinstance` target; use `callable()`. — *source:* previous PR body
- `vidbyte/lib/enums/prompts.py` has a header count of prompts and families that must be updated with every added key (previous run: 139 in 35 → 149 in 36). — *source:* previous PR body
- `contracts/sdk-public-api.json` is regenerated with `python scripts/generate-sdk-public-api.py` and checked with `--check`. — *source:* previous PR body
- Three local pytest failures in `tests/features/harness_threads/test_harness_threads_surface.py` are inherited (they compare the branch with main's exports); CI skips them in its shallow clone. — *source:* previous PR body
- The shared loop `vidbyte/agents/runtime.py` is a non-goal to touch; the swarm uses only `_after_tool_iteration`, `review_finish`, `after_tool_call`, and a tool. — *source:* request.md §C
- No `Summarizer` implementation exists in the SDK, only the Protocol at `vidbyte/middleware/compaction/base.py:42-47`; the summarize modes raise at `context_compaction.py:121-124` and `:261-264`. Any summarizing compaction needs a new runner-backed summarizer. — *source:* S0 compaction researcher
- `before_model_call` middleware transforms never persist (`vidbyte/agents/runtime.py:1085-1125`, snapshot copy at `:1196`); the only persistence seam that leaves the shared loop untouched is `AgentSwarmMemberRuntime._after_tool_iteration` (`member.py:60`), which may rewrite the live `messages` list. Splice a summary BEFORE mail is appended there, never with an open tool call. — *source:* S0 compaction researcher
- `compaction_trigger_tokens` / `compaction_target_tokens` already exist on `BaseAgent.__init__` (`base.py:105-106`), `AgentLoopSettings`, the config whitelist (`:674-675`) and serialization (`:632-633`, `:764`), but nothing in the runtime reads them; make them live for members rather than adding knobs. — *source:* S0 compaction researcher
- Real context size per call: `after_model_response` ctx carries `model_usage=usage_record.usage` (`runtime.py:470-500`; `input_tokens`, `output_tokens`, cache fields). `AgentSwarmTurnMiddleware` today implements only `after_tool_call` and `review_finish` (`agent_swarm_turn.py:34,40`). The engine's own estimate is chars/4 (`strategies.py:61`). — *source:* S0 compaction researcher
- The task prompt is NOT in `messages` (spliced at the run boundary via `prompt_index`, `runtime.py:1596-1662`) and the system prompt is `call_options["system"]`, so compacting `messages` cannot lose the goal. — *source:* S0 compaction researcher
- Engine summarize strategies emit `ContextMessage(role="assistant", kind="summary")` (`strategies.py:334-400`); Codex and LangChain splice a USER message with a fixed prefix; prefer the user-role prefix form for provider safety. Reuse `ContextCompactionEngine.compact_provider_messages` + `_repair_tool_pairing`; `ContextCompactionTool` (`compact_context`, 24 modes, needs a `ContextState` adapter) is not wired anywhere. — *source:* S0 compaction researcher
- Provider-native compaction is NOT a drop-in: the SDK formatter flattens text-only assistant replies to a string (`formatter.py:388-396`) so a returned compaction block is lost; the OpenAI encrypted item cannot roundtrip through `_responses_items` without new code; Anthropic threshold compaction "might fail when tools are defined". Anthropic on-demand compaction needs beta header `anthropic-beta: compact-2026-09-04` on the compaction request and every later request; precedent for a beta header: `vidbyte/agents/skills/anthropic.py:37` + `vidbyte/lib/constants/skills.py:92`. — *source:* S0 compaction researcher
- `CompactCodexThreadTool` / `vidbyte/tools/builtins/codex/thread_helpers.py` do NOT exist on this branch (they exist on main only); request.md §C names them in error. — *source:* S0 compaction researcher
- Offline testability: `ScriptedSwarm` patches `BaseAgent._runner_for_model` (`tests/features/agent_swarm/agent_swarm_fixtures.py:248-280`, `_ScriptedRunner.arun(prompt, **options)`), so a summarizer that calls the member's own runner (`TextRunner.arun(prompt, *, system, messages, ...)`, `text.py:69`) can be scripted. — *source:* S0 compaction researcher
- Placement for new compaction code under AGENTS.md: summarizer + compactor in `vidbyte/agents/agent_swarm/` (not `vidbyte/lib/`, which cannot import runners or tools); enums in `vidbyte/lib/enums/agent_swarm.py`; dataclasses in `vidbyte/lib/dataclasses/agent_swarm.py`; constants in `vidbyte/lib/constants/agent_swarm.py`; add the compaction tool's name to `AGENT_SWARM_RESERVED_TOOL_NAMES`. — *source:* S0 compaction researcher
- `after_tool_call` (`runtime.py:1788-1799`) sees the RAW `ToolResult`; the swarm's character cap is applied afterwards via `_append_tool_result_message` (`:1812`) → `ToolSettings.truncate` (`settings/tool.py:64-79`). — *source:* S0 scout
- The trim runs in `before_model_call`, first in the member's middleware tuple (`member.py:126`); `pipeline._apply_transform` (`:170-186`) passes post-trim `provider_messages` to later middleware but not the trim's before/after metadata, so a `history_trimmed` observer must count messages itself. — *source:* S0 scout
- `ctx.model_usage` is a `ProviderUsage` (not `UsageRecord`), may be None, and its `input_tokens/output_tokens/total_tokens` may each be None; `cost_usd` needs a `ModelPricing`. `on_model_error` gets `error=exc`; returning CONTINUE leaves the loop's retry untouched. — *source:* S0 scout
- Tool metadata verbatim: write_text success `{"path": <resolved>, "encoding"}`; patch_file `{"changed": True, "file_path": <raw model argument>}`; bash returns `ToolResult.success` even on a non-zero exit with `{"exit_code", "truncated"}`; a bash timeout is `ToolResult.error` with `{"error": "timeout", "truncated"}`. — *source:* S0 scout
- Every new event field must be listed in `_KIND_FIELDS`/`_OPTIONAL_FIELDS` (`vidbyte/lib/dataclasses/agent_swarm.py:33-43`) and in `AgentSwarmEvents.record`'s keyword surface (`events.py:38-58`); `AgentSwarmResult.__post_init__` requires `swarm_ended` last; each runtime `record` is followed by an awaited `flush`. — *source:* S0 scout
- No swarm-wide token budget exists today; `RecordFieldValidator.require_number` needs a `maximum` and `require_int` a `minimum` (`validation.py:93-107`), so there is no "unbounded" option: every limit needs a ceiling. `AgentLoopSettings.max_tokens` is per agent and unset by the member. — *source:* S0 scout
- `AgentSwarmMember.system_prompt` is required (`dataclasses/agent_swarm.py:56,66`); `_build_member` prefixes it to the swarm prompt (`runtime.py:245-249`) and the loop appends the agentic prompt. The contract tests pin own→swarm→loop order, 4–5-sentence descriptions, no digits or role words, 8 kinds, 10 leaves, 7 package modules including settings.py, ≤400 lines each, and every constant value: S2 must rewrite those. — *source:* S0 scout
- The prompt catalog has no "section" mechanism (`catalog.py:166-174`, one `.md` per leaf); sections of one system prompt are headings inside one leaf, or several leaves joined by the runtime. `vidbyte/lib/enums/prompts.py:7` header counts (149/36) are hand-maintained. — *source:* S0 scout
- Lint rules most likely to bite: A006 (`vidbyte/lib` may not import `vidbyte.tools`, even function-locally), S060 (no `dict[str, Any]` in lib dataclass signatures), C016 (regenerate the contract after root exports change), A009 README length (~7k chars headroom left in `vidbyte/prompts/README.md`, ~8.5k in `vidbyte/agents/README.md`), S020 File Index parity in REPO_MAP. — *source:* S0 scout
- AGENTS.md exception 1 allows settings in `vidbyte/agents/`, and its "Existing code" paragraph says moving code to lib "belongs in its own pull request"; the user's "7) lib folder." decision overrides both for `AgentSwarmSettings`; record it as a user decision with that tension named. Precedent for a lib settings record that must not import tools: `CodingAgentSettings` in `vidbyte/lib/dataclasses/coding.py` (keys as `str|None` with `repr=False`, tools as `tuple[object, ...]`). `settings.py:39-40` imports `IS_DONE_TOOL_NAME` and `BaseTool`, both forbidden in lib. — *source:* S0 scout
- No search-provider enum exists and `ProviderKeyMatcher` binds only `ModelProvider` members, so a web-search key cannot ride in `api_keys`; 3 of the 8 search tools in `vidbyte/tools/builtins/operations/search.py` have no client module (see code-map.md §2 for which). — *source:* S0 scout
- The dev install command is `python -m pip install -e ".[dev]"` from `CONTRIBUTING.md:34-35` (not AGENTS.md); gates from a worktree need `PYTHONPATH=$(pwd)` for the source stage and no `PYTHONPATH` for the package stage (field guide `local-ci-verification.md`); semgrep scans tracked files only, so `git add -A` first. — *source:* S0 scout
- `workplace.prepare()` returns only the `Path` with `exist_ok=True` (`workplace.py:33-42`); `workplace_prepared` needs it to report created-vs-existed. `REPO_MAP.md:365` "three such bundles" is stale (four toolsets). — *source:* S0 scout
- Contract names from spec r1 §8.5: `AgentSwarmMember(name, provider, model_name)` (no `system_prompt`); `AgentSwarmSettings` in `vidbyte/lib/dataclasses/agent_swarm.py` with `web_search: AgentSwarmWebSearch | str | None` (brave, browserbase, exa, parallel, tavily) + `web_search_api_key`; limits 2–500 agents, 100,000 turns, 10,000,000,000 `max_tokens` (new stop reason `max_tokens`), 86,400 s default / 2,592,000 s ceiling; `compact(focus?)` tool; `AgentSwarmHandoffSummarizer`; `AgentSwarmTrimMiddleware`; `AgentSwarmObserverMiddleware`; member middleware order (Trim, Turn, Observer); `prepare() -> bool`; `AgentSwarmRuntime(settings, root, *, workplace_created)`; 24 event kinds (16 new), 8 new typed fields. — *source:* S1 author
- `CompactionStats` (`context/compaction/base.py:54-62`) has no `changed` field; the trim middleware computes `changed` itself (`context_compaction.py:226-228`) and `_apply_transform` drops transform metadata, so `history_trimmed` must come from the trim subclass's own stats. — *source:* S1 author
- `AgentRuntime.arun(message, *, handle, ...)` (`runtime.py:273`) never stores the `RunnerHandle`; the summarizer side call goes through `BaseAgent._runner_for_model` (`base.py:1661`) / `_invoke_runner` (`base.py:1519`), which `ScriptedSwarm.install()` patches (fixtures `:276-281`). — *source:* S1 author
- Side-call metering precedent: `_invoke_and_count_side_call` + `token_usage_from_response` (`vidbyte/lib/token_usage.py`); the summary call is recorded as `model_called` and counted against `max_tokens`. — *source:* S1 author
- `SummarizeRangeCompaction(summarizer, keep_last)` rounds `keep_last` up to whole provider groups (`strategies.py:334-366`) and returns messages unchanged when no middle exists; its summary is an assistant-role `kind="summary"` message (spec A-1, under review). — *source:* S1 author
- Web-search clients with modules: Brave, Browserbase, Exa, Parallel, Tavily (`vidbyte/tools/builtins/operations/__init__.py:20-26`); Firecrawl is a fetch, not a search; no Linkup/OpenAlex/SemanticScholar client, hence the five-member enum. — *source:* S1 author
- Summarizer prompt precedent is a flat leaf `vidbyte/prompts/prompts/trajectory_checkpoints_agentic_summarizer.md`; the shared system prompt is nine `system_*` leaves the runtime joins, `system_thoroughness` holding eight `##` subsections; Prompt enum header count becomes 162/36. — *source:* S1 author
- Subagents report the working directory is not the worktree after a resume; briefings must say to use absolute paths or `git -C`. — *source:* S1 author
