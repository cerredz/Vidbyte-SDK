# S1 spec author report: agent output connectors

- **Stage:** S1 spec author
- **Date:** 2026-10-11
- **Spec:** `docs/spec/agent-output-connectors/spec.md`, revision r1
- **Commit:** `6248fc96`

This stage wrote and committed only `spec.md`, plus this report, which is not committed. It created no source, test, or stub files. It ran no gate and installed nothing.

## What I read

### Pipeline inputs (read in full)

- `docs/spec/agent-output-connectors/request.md`
- `context/code-map.md`
- `reports/S0-scout.md`
- the spec template
- `house-style.md`
- the orchestrator briefing

### Repo guidance

- `AGENTS.md`
- `REPO_MAP.md`, for these entries:
  - the `vidbyte/agents/` subtree
  - `vidbyte/lib/` and its subfolders
  - `vidbyte/providers/`
  - `vidbyte/lib/http/`
- folder READMEs:
  - `vidbyte/agents/README.md`
  - `vidbyte/agents/jev/README.md`
  - `vidbyte/lib/README.md`
  - `vidbyte/tools/builtins/operations/clients/README.md`

### Field guide (`field-guide/vidbyte-sdk/`)

- `comment-format.md`
- `class-bound-helpers.md`
- `strict-config-dataclasses.md`
- `provider-api-contracts.md`
- `blocking-lint-invariants.md`
- `jev-capability-layout.md`
- `prebuilt-agents.md`
- `local-ci-verification.md`
- `agents-md-map.md`
- `review-scope.md`

### Source (read in the sections cited by the spec)

**Agents**

- `vidbyte/agents/base.py`:
  - `__init__`
  - the runtime rejections at 128–162
  - `_generate_reply` at 896–934
  - `_assert_schema_satisfied` at 947–963
  - `_notify_session_exception`
  - `_drain_queued_prompts` at 1073–1107
  - `restore`
  - `run` and `arun`
- `vidbyte/agents/fork.py`: lines 53–81
- `vidbyte/agents/jev/settings.py` and `vidbyte/agents/jev/agent.py`: lines 90–102
- `vidbyte/agents/coding.py`
- `vidbyte/agents/runtime.py`: `_middleware_abort_result` and `_runtime_metadata`
- `vidbyte/agents/codex/agent.py`: lines 100–178
- `vidbyte/tools/agent_tool.py`: line 59

**Lib**

- `vidbyte/lib/http/transport.py`: `request`, and `_send_once` at 59–66
- `vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`
- `vidbyte/lib/registries/models.py`: lines 151–161
- `vidbyte/lib/dataclasses/agents.py`: `AgentStopReason` and `AgentMessage`
- `vidbyte/lib/dataclasses/config.py`: lines 23–29
- `vidbyte/lib/enums/__init__.py`
- `vidbyte/lib/constants/speed.py`

**Other**

- `vidbyte/sessions/session.py`: `record_turn` at 182–188, and line 459
- `vidbyte/tools/builtins/operations/clients/_base.py` and `brave.py`
- `vidbyte/tools/builtins/operations/fetch.py`: line 223
- `.semgrep/typed-mapping-boundary-policy.yml`
- `pyproject.toml`

I re-verified every `path:line` reference in the spec against this worktree before committing.

### Platform research

Three parallel research agents ran on 2026-10-11:

- chat and messaging
- trackers, docs, and storage
- email, alerting, and automation

Their findings are cited row by row, with official URLs, in spec §9.2 tables (a) and (b). I spot-checked these myself:

- Notion's `markdown` parameter: `markdown_version` defaults to v1, and the parameter is mutually exclusive with children.
- Notion's page-parent shape.
- X `POST /2/tweets` and LinkedIn sharing are OAuth-only.
- The Gmail API needs OAuth.

## Approaches weighed

**Chosen: the contract plus one class per destination in a new `vidbyte/lib/outputs/`, with the linking dispatcher in `vidbyte/agents/output/` (D-1, D-2).**

The user placed "the abstraction" in `agents/output/` and the provider logic in lib or providers. Lint rule A006 forbids any lib or providers module from importing `vidbyte.agents`, and it counts function-local imports. So a connector in lib cannot subclass a base class that lives in `agents/output/`. Moving the contract down to lib is what AGENTS.md prescribes ("move the contract down"). It keeps each platform to one class. `agents/output/` keeps the part the user described as "linking the provider and agent logic": the dispatcher, plus the public re-export package.

**Rejected placements and shapes**

- **A `Protocol` in lib plus an abstract base in `agents/output/`.** Every platform would need two classes and the codebase would carry two contracts.
- **`vidbyte/providers/outputs/`.** REPO_MAP defines `providers/` as the model-vendor layer. Its `__init__` eagerly imports every model adapter, and its README covers model contracts only. The user allowed either folder, so purpose decided it.
- **A delivery loop inline in `BaseAgent`.** `base.py` is already 1,694 lines. This also contradicts the user's placement of the linking logic.
- **Smaller designs (§8.3):**
  - Slack plus a webhook only. This fails the user's request for a list of platforms.
  - One templated generic webhook. Mentions, caps, auth forms, and link extraction differ for every destination, so the templates would grow into a DSL.
  - No `OutputContent` record. That means 11 copies of the shaping rule.
  - Per-connector `*Settings` records. That means 10 one- to three-field records; the checks are already single-sourced in `OutputArguments`.

## Where I disagreed with the scout or the request (with evidence)

1. **Registry name.** The request names `ModelRegistry.resolve_api_key`, but the class is `ProviderModelRegistry` (`vidbyte/lib/registries/models.py:151-161`). The spec cites the real symbol.
2. **Forks versus `as_tool`.** The request says forks drop outputs and also that `as_tool` delivers on every call. Those contradict each other, because `AgentTool.execute` runs on `self._agent.fork()` (`vidbyte/tools/agent_tool.py:59`). I chose "forks never deliver" (D-7) and recorded the other option as Q-2, default no. Both lines were proposals by the assistant, not decisions by the user.
3. **Per-kind payload dataclasses.** The request's implementation hints suggested payloads per kind (chat, email, issue). Every one of the 11 destinations needs only a title and a body per reply. Labels are per-connector configuration in the approved snippet (`labels=("bug",)`). One `OutputContent` record replaces them (D-10), and the flip condition is recorded.
4. **JevAgent wiring.** The request said "bolt it on JevAgent". `tests/test_jev_agent.py:504-509` pins the constructor, and AGENTS.md routes new capabilities to `JevAgentSettings` fields. So outputs arrive as `JevAgentSettings.outputs` (D-8).
5. **Blank-content skip.** The request's skip rule covered only aborted replies. I added "blank content" as well: Slack answers 400 `no_text` and Discord rejects an empty `content`, so a blank reply would turn into false failures. This is guarded by INV-9. The assumption it rests on is A-12: valid structured replies always carry non-blank JSON content.
6. **Teams.** The conversation treated Teams like Slack. Two things change that. Office 365 connector webhooks stopped working in May 2026, and Workflows URLs accept only Adaptive Card envelopes. A 202 response means "accepted", not "posted" (A-2). Only "Anyone" flows avoid OAuth. All of this is recorded in EC-30 and catalog row a-3.
7. **Notion.** The conversation assumed block conversion would be needed. `POST /v1/pages` accepts a `markdown` body parameter, so no converter is required (D-18, A-6).
8. **Gmail.** Gmail has no separate connector. Without OAuth it is reachable only over SMTP with an app password. It is a configuration of `EmailOutput` (D-12). The Gmail API itself goes in table (b) as OAuth-only.
9. **Retries.** The request allowed full retries where a provider idempotency key exists. None of the 11 destinations offers a documented replay-safe key. Linear's `IssueCreateInput.id` rejects a duplicate rather than replaying it. So retries are 429-only (D-5).
10. **Lint result line.** The gates reference expects `AGENT-LINT: PASS`, but `lint/core/report.py:58` prints `SDK-LINT: PASS`. The spec uses the real line.
11. **Placement of the handoff sibling.** The S0 map treats the handoff as a post-reply sibling. In fact `_run_auto_handoff` runs *before* `_notify_session` and `_assert_schema_satisfied` (`base.py:920-931`). Delivery therefore follows the schema-check precedent instead, sitting between line 931 and the drain (D-3, INV-26).

## Assumptions I am least sure of

- **A-6, Notion `markdown`.** That Notion's `markdown` handles typical LLM markdown under `2026-03-11`. If it does not, the fallback is the block route, which is a larger change.
- **A-1, GitHub limits.** That GitHub's 65,536-character body limit and its title limit hold. Both were observed in practice and are not documented.
- **A-2 and A-3, Teams.** That Teams 202 semantics behave as described, and that a plain TextBlock cannot mention anyone. Both come from community reports and card docs, not a contract.
- **A-5, Google Chat mentions.** That only `<users/…>` mentions people in Google Chat webhook text.
- **A-7, Jira tokens.** That unscoped Jira API tokens over Basic auth keep working. Atlassian is pushing scoped tokens, which need the `api.atlassian.com` route (NG-12).
- **A-11, GitHub API version.** That GitHub API version `2026-03-10` keeps the create-issue fields unchanged.
- **A-13, runtime coverage.** That every `AgentRuntimeType` replies through `_generate_reply`. This is taken from code-map §4 and was not re-traced for the MCTS and actor runtimes.

## Self-check (Stage E)

- **Section headings** match the template exactly (verified with a diff).
- **IDs:** every referenced ID is defined, and none is duplicated. The counts:

  | ID | Count | ID | Count |
  |---|---|---|---|
  | G | 4 | D | 21 |
  | NG | 12 | W | 12 |
  | INV | 28 | T | 5 |
  | AC | 26 | A | 14 |
  | EC | 42 | Q | 7 (0 blocking) |
  | FR | 20 | | |
  | NFR | 8 | | |

- **Traceability:** every FR maps to an INV or AC, every AC appears in a W row, and every §12.3 row names a standard and what it serves.
- **File budget:** the §12.3 new-file count is 22, which equals the §8.4 budget.
- **Corrections during the check:**
  - The §8.4 class count was 25 and is now 24, across 18 modules.
  - One weighted-word quote lost its original double space; it is restored.
- **Verbatim text:** the Prompt 4 text in §0.1 is verbatim from request.md.
- **No test cases** appear anywhere in the spec.
