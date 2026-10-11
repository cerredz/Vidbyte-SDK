VERDICT: NEEDS REWORK — The wire contracts, credential handling and reply-path insertion point are sound. But the spec's headline decision puts the `OutputConnector` abstraction and nearly all agent-to-provider linking logic in `vidbyte/lib/outputs/`, which inverts the user's settled placement and rests on an overstated A006 claim. Four correctness gaps (posted stop notices, Jev specialist double delivery, multi-line truncated titles, the Jira link check) also need fixing before tests are written.

## WHAT THE SPEC GETS RIGHT

- **The delivery point is right.**
  - It sits between `_assert_schema_satisfied` (base.py:931) and the drain (base.py:932).
  - It writes to the same `metadata` dict the reply holds. `AgentMessage.metadata` is not copied (lib/dataclasses/agents.py:276), so receipts really do land on `reply.metadata`.
  - Clearing the queue and calling `_notify_session_exception` matches the handoff block.
  - It honestly accepts drained-reply failures as EC-20.
- **The HTTP choices match `HttpTransport`'s real behavior.**
  - Header keys are lowercase, because `_send_once` calls `setdefault("content-type", …)` on a plain dict.
  - `retry_status_codes=(429,)` is set explicitly, with a local guard key that never goes on the wire.
  - `follow_redirects=False` and `max_response_bytes` are both set.
- **The Jev and Coding wiring respects the pinned tests.**
  - `JevAgentSettings.outputs` follows AGENTS.md "New JEV code" and leaves tests/test_jev_agent.py:504-509 intact.
  - `CodingAgent` takes `outputs` through `**kwargs`, so `EXPECTED_SIGNATURE` stays intact.
  - Forks pass `outputs=()` at fork.py:53-81.
- **Credential and receipt handling are sound.**
  - Credentials resolve as explicit argument, then environment variable, then `ConfigurationError`, copying `resolve_api_key` (registries/models.py:151-161).
  - The repr is masked, secret fields are `repr=False`, error codes follow the token grammar, and connectors are never serialized.
  - The 17 root exports follow the existing root re-export precedent.

## FINDINGS

### R-1 [Blocker] [L1] §8.1 D-2 (also TL;DR, D-1, §12.2, §12.3 rows 4–6 and 20–22) — The spec places "this abstraction" and the agent-linking logic in `lib/`, the opposite of the user's settled placement, and justifies it with a lint claim that does not hold

**Evidence:**
- **The user's sentence has three clauses.** Prompt 4 (§0.1):
  1. "this abstraction to live inside of the vidbyte-sdk/vidbyte/agents/output folder";
  2. provider-specific logic "can either go in the lib folder of the repo or the provider folder";
  3. "our output folder and be responsible for the core logic kind of linking the provider and agent logic".

  D-2 quotes none of them.
- **The spec moves both the abstraction and most of the linking logic to `lib/`.**
  - `lib/outputs/base.py` (row 5) holds the `OutputConnector` ABC and its `deliver()` template: skip, then render or shape, then type-check, then `_send`.
  - `lib/outputs/content.py` (row 6) holds the reply-to-content rules: `is_deliverable`, `content`, `structured_field`, `first_line` and `structured_json`.
  - `agents/output/` gets one logic file: `OutputDispatcher`, which gathers, collects receipts and raises (row 21). It also gets re-exports (row 20).
  - The TL;DR calls this "the decision that matters most". Clause 1 is inverted, and most of clause 3 moves to lib.
- **D-2 overstates A006.** It says "A006: lib code cannot import `vidbyte.agents`, even inside a function". In fact A006 keeps an edge only when the target is a concrete module. `__init__.py` files are not graph nodes (lint/rules/a006_directed_dependency_graph.py:54, 67, 77). That is why `lib/enums/model_provider.py:61` can import the `vidbyte.agents.pricing` package at call time without a finding.
  - The rule that actually binds is AGENTS.md Style 3 (line 31): "nothing in `vidbyte/lib/` may import from a layer above it". It only stops lib from importing upward. It does not require the agent-facing contract or the reply-shaping rules to live in lib.
- **D-2's runner-up is a false choice.** It describes "a Protocol in lib plus an abstract base in agents/output, giving two contracts and two classes per platform". But the spec's own `_send(reply, content)` is already the provider half. Suppose the lib class carries only that half, and the agent-facing `OutputConnector` contract is a `typing.Protocol` in `agents/output/`. Lib classes then satisfy the Protocol structurally, with no import, and each platform is still one class.
- **Repo guidance points the same way:**
  - REPO_MAP.md:157: "Anything genuinely foundational and used across multiple domains belongs here".
  - REPO_MAP.md:161: "Anything that can legitimately live in the agent layer instead should be moved there".
  - Field guide `class-bound-helpers.md:10`: "Separate shared abstraction translation from provider serialization".

**Failure:**
- The PR ships the layout the user explicitly asked against.
- `agents/output/` becomes a two-file shim.
- Agent-only rules (the stop-reason skip, title-from-first-line, structured-field shaping) land in the shared substrate, where nothing else uses them.
- The row-22 README teaches future contributors a false A006 rationale.

**Smallest fix:** Re-cut at the provider boundary. This keeps one class per platform and the same public names.
- **`vidbyte/lib/outputs/` keeps provider work only:**
  - each connector's constructor, credential resolution and masked repr;
  - a public `send(reply, content) -> DeliveryReceipt` (today's `_send`), with `render` stored as a read-only attribute;
  - `OutputArguments`, `OutputHttp`, `OutputSmtp`;
  - the pure text helpers `truncate`, `single_line` and `chat_text`.
- **`vidbyte/agents/output/` gains the abstraction and the linking:**
  - `OutputConnector` as a `typing.Protocol` with `destination`, `render` and `send`;
  - the skip rule;
  - `content`, `structured_field`, `first_line` and `structured_json`;
  - the `render` call and the `OutputContent` type check. These are today's `deliver` steps 1–4, run per connector by `OutputDispatcher`.
- **Update the surrounding text:**
  - Rewrite D-2 and the TL;DR to quote all three clauses and cite AGENTS.md Style 3, not A006.
  - Point AC-24, EC-42 and the README resend example at the dispatcher entry point.
  - Adjust §8.4 (about one more module), §12.2, and rows 4–6 and 20–22.

Any other cut that puts the contract and the linking logic in `agents/output/`, with no upward lib import, also satisfies the decision.

### R-2 [Major] [L5] §6.1 INV-9 — The skip rule lets SDK-written budget-stop notices through, so a capped run posts "Agent runtime stopped after reaching max_iterations." as if it were the answer

**Evidence:**
- INV-9 skips only blank content and `stop_reason == "middleware_abort"`.
- For other stops, the runtime returns SDK-written text as the reply's `output`, through `_stopped_result` (vidbyte/agents/runtime.py:1882; metadata `stop_reason` at :1911):
  - "Agent runtime stopped after reaching max_iterations." (:1848)
  - "…max_tokens." (:497, :1856)
  - "…max_tool_calls." (:1677, :1866)
  - "…timeout_seconds." (:1874)
- `AgentStopReason` (lib/dataclasses/agents.py:51-70) has 15 reasons other than `final_response` and `is_done`.
- EC-9's own rationale applies equally: "Without the guard, the abort notice would be posted to the channel".
- With an `output_schema`, the schema check raises first. Without one, the notice reaches every connector.

**Failure:** Consider a scheduled agent with `GitHubIssueOutput` and `EmailOutput` that hits `max_iterations`. It opens an issue titled "Agent runtime stopped after reaching max_iterations." and emails the same text. With Slack, it posts the notice to the channel. This repeats on every capped run.

**Smallest fix:**
- Skip when `reply.metadata.get("stop_reason")` is set and is neither `final_response` nor `is_done`. When the key is absent, deliver. Jev code never sets `stop_reason`, so EC-38 still holds.
- Update INV-9, AC-8 and EC-9, and add an EC for a budget stop.
- If the author prefers to deliver stop notices, record that as an accepted EC instead.

### R-3 [Major] [L5] §6.1 INV-16 (also NG-5, EC-21) — "Jev specialists never deliver" is false: user agents that run un-forked inside other agents deliver on their own, post twice, and turn `OutputDeliveryError` into `AgentExecutionError`

**Evidence:**
- INV-16 lists "Jev specialist and child agents" among agents with `outputs == ()`. NG-5 lists delivery from Jev specialists as a non-goal. Nothing enforces either.
- `JevSpecialist.agent` is the user's own `BaseAgent` (lib/dataclasses/jev.py:659-663). The runtime runs it directly: `reply = await self.preflight.specialist.agent.arun(message)` (vidbyte/agents/jev/runtime.py:187).
- That reply then becomes the JevAgent's reply, which `_generate_reply` delivers again.
- The same un-forked direct calls exist for AggregateAgent proposers and its aggregator (vidbyte/agents/aggregation.py:113-114, 144).
- Pipeline stages (pipelines/base.py:67), workflow stages (workflows/stages.py:109) and the MCP handler (mcp_server/handlers.py:149) also run the user's own agent. There, delivering is arguably correct, but it is undocumented.
- Only the fork-based paths hold:
  - agent_tool.py:59;
  - MultiAgent workers (`binding.fork()`);
  - jev/bulk_work.py:49;
  - the fresh-continuation `partial`;
  - Session restore (session.py:459).

**Failure:**
- **Double posts.** A specialist and `JevAgentSettings` that both carry a `SlackOutput` post twice per run. An AggregateAgent whose three proposers have outputs posts three drafts plus the final answer.
- **Lost error type.** base.py:887-890 wraps a specialist's delivery failure into a generic `AgentExecutionError`. So `except OutputDeliveryError` around `jev.arun()` never fires, and `err.receipts` is lost.

**Smallest fix:**
- Rescope INV-16 and D-7 to agents the SDK builds:
  - `fork()` children and `as_tool()` children;
  - MultiAgent workers;
  - Jev bulk-work and continuation agents;
  - Session rebuilds.
- **Add EC rows:**
  - A user agent with outputs, used as a `JevSpecialist` or as an AggregateAgent proposer or aggregator, delivers on its own run, and its error is wrapped.
  - Pipeline stages, workflow stages and MCP-served agents deliver once per run.
- **Add footguns** to the README rows 19, 22 and 33: the cases above, plus the fact that `Session.resume` and `fork_from` return agents with `outputs=()` (Q-4).
- **Optional Q-8 [scope-adding]:** have `JevAgentSettings` validation reject a `JevSpecialist` whose agent has `outputs`. Default: not built.

### R-4 [Major] [L9] §12.3 row 6 (`single_line`) — Collapsing and then calling `truncate` appends a two-newline marker, so every long title becomes multi-line and email and Jira fail, contradicting INV-15 and AC-10

**Evidence:**
- Row 6 says `single_line` "joins `text.split()` with single spaces, then truncates". `truncate` appends `OUTPUT_TRUNCATION_MARKER = "\n\n[truncated]"` (row 2).
- INV-15 and AC-10 require one line: "The GitHub `title` is exactly 250 characters with no newline".
- INV-13 takes the title from the body's first non-empty line. Any reply whose first paragraph runs past 250 characters, which is common for LLM output, takes this path.
- Verified locally: setting `EmailMessage()["Subject"] = "a\n\n[truncated]"` raises `ValueError: Header values may not contain linefeed or carriage return characters`.
- `single_line` calling `truncate` is also a helper calling a helper, which row 6's Style 1 note does not list.

**Failure:**
- **Email:** `EmailOutput._send` raises, giving FAILED `unexpected:ValueError` and then `OutputDeliveryError` on every such reply.
- **Jira:** `summary` receives newlines, which Jira's single-line summary field rejects, giving `http_400`.
- **GitHub, Linear and Notion:** titles end in a blank line plus "[truncated]".
- **Tests:** AC-10 cannot pass if row 6 is followed.

**Smallest fix:** Define `single_line(text, limit)` as `" ".join(text.split())[:limit]`, or append a one-line marker constant (for example `OUTPUT_TITLE_TRUNCATION_MARKER = "…"`). Either way, it must not call `truncate`.

### R-5 [Major] [L9] §8.1 D-21 (also §12.3 row 7 `_link`) — Checking for `https://` before applying `link_prefix` turns every successful Jira create into FAILED `invalid_response`

**Evidence:**
- D-21 says: "When a non-empty `link_path` is missing or not an `https://` string in a 2xx response, the receipt is FAILED `invalid_response`."
- Jira's `link_path` is `("key",)` (row 16). Jira returns 201 `{id, key, self}` (§9.2 row a-9), where `key` looks like `PROJ-123`. That is not an `https://` string.
- Row 7 says `_link` "keeps only `https://` strings, with `link_prefix` prepended", which does not settle the order.
- AC-17 expects the receipt URL `https://{site}/browse/{key}`.

**Failure:** With the literal order, Jira creates every issue and then reports it FAILED, raising `OutputDeliveryError`. A caller who resends the failed pairs (AC-24) creates duplicate issues.

**Smallest fix:** State the order in D-21 and row 7:
1. Read the value at `link_path`.
2. Require a non-blank `str`.
3. Prepend `link_prefix`.
4. Require `https://`.

### R-6 [Major] [L11] §11 Commands (also §12.4) — "Typecheck: N/A" is false: the lint gate runs package-wide mypy as ratchet S009

**Evidence:**
- lint/core/mypy.py:56 runs `[sys.executable, "-m", "mypy", "--config-file", "lint/mypy.ini", "vidbyte"]`.
- S009 (lint/rules/s009_staged_mypy_contracts.py) ratchets the error count, with a baseline of 350 (lint/baseline.json).
- lint/mypy.ini sets `check_untyped_defs = True` and `disallow_any_generics = True`.
- `python lint/run.py` runs inside `scripts/run_ci.py`, so the full gate type-checks every new module.
- The spec misses this in three places:
  - §11's baseline list omits S009.
  - §12.4 has no typing line.
  - §8.5 shows an unannotated `render=None` on every connector.

**Failure:** The implementer and the test author treat typing as optional. Any of these adds mypy errors, so S009 reports REGRESSED and the gate fails late:
- a bare `Mapping`, `tuple`, `Callable` or `dict` annotation;
- an untyped `render` parameter.

**Smallest fix:**
- Replace "N/A" with the S009 command and its baseline (350).
- Add a §12.4 line covering three points:
  - every new annotation is fully parameterized (`disallow_any_generics`);
  - `render` is typed `Callable[[AgentMessage], OutputContent] | None`;
  - `python lint/run.py --rule S009` stays at 350.

### R-7 [Minor] [L8] §12.3 rows 5, 7, 16, 21 (also §12.4) — The per-row lint obligations miss two A002 sites and the S003, S002 and A007 details that will fail ratchets

**Evidence:**
- **A002.** The rule scans the function name plus every Name and Attribute in the body (lint/rules/a002_intent_comments.py:69-75), and its tokens include `send` and `request`.
  - `OutputConnector.deliver` calls `self._send`.
  - `OutputHttp._link(response, request)` reads `request.link_path`.
  - Both therefore need `# @intent`. Rows 5 and 7 list only `credential`, `_send`, `post`, `send` and `_client`.
  - §12.4's wording, "identifiers contain", reads as if only names count.
- **S003** (B905, baseline 9). The dispatcher pairs connectors with gather results, but `zip(..., strict=True)` is not stated.
- **S002** (B904, baseline 0). A `raise ConfigurationError` inside an `except` needs `from exc` or `from None`. Likely sites are the not-iterable check in `connectors` and a `uuid.UUID` parse in `identifier`.
- **A007** (a007_operational_constants.py:23-38, 96-106). The inline Jira ADF `"version": 1` sits in the same expression as `OutputText.truncate`, whose name matches an A007 token, so the `1` needs a named constant.

**Failure:** Each miss raises a ratchet count, giving REGRESSED at the first gate run. Each is cheap to fix but avoidable.

**Smallest fix:**
- Add `deliver` and `_link` to the A002 lists.
- Reword §12.4 to "the function name or any name used in its body".
- Add one §12.4 line each for:
  - `zip(strict=True)`;
  - `raise … from` inside `except`;
  - `JIRA_ADF_VERSION = 1` in row 2.

### R-8 [Minor] [L9] §8.1 D-17 — The five "implemented when all hold" criteria are not the real rule: table (b) marks 16 destinations "Qualifies, deferred"

**Evidence:**
- D-17 says "A destination is implemented when all five hold".
- Table (b) marks 16 rows "Qualifies, deferred": GitLab Issues, GitHub Gists, Asana, ClickUp, Todoist, Trello, Webex, Matrix, Pushover, ntfy, Datadog, Splunk, Feishu, DingTalk, WeCom and the Zulip webhook.
- PagerDuty and Mastodon are marked as technically qualifying.
- GitLab even has the same shape as `GitHubIssueOutput`.

**Failure:** A reader, or the user comparing this against another model's output, cannot tell why these eleven were chosen. D-17's "Revisit" trigger and the §8.4 budget rest on a cut that is never stated.

**Smallest fix:** Add the actual sixth criterion to D-17, for example "user-named, or the top one or two per category by adoption, within the §8.4 budget". In table (b), say "qualifies; below the cut".

### R-9 [Minor] [L7] §8.1 D-18 (also INV-12, §10 T-2) — Notion's `markdown` parameter takes enhanced markdown, not plain text, so model output can create user mentions

**Evidence:**
- D-18 lists "Notion's `markdown` parameter" under "Plain text everywhere".
- T-2 claims mentions are suppressed per destination.
- The `markdown` body parameter takes Notion's enhanced markdown, which includes mention tags such as `<mention-user url="…"/>`.
- INV-12 neutralizes nothing for Notion.

**Failure:** Prompt-injected text that contains a mention tag notifies a workspace member. That is an INV-12 gap for one destination.

**Smallest fix:** Either neutralize `<mention-` in Notion bodies, the same way Google Chat neutralizes `<users/` (one constant pair), or list it as an accepted limitation under T-2 and A-6.

### R-10 [Minor] [L9] §6.3 EC-28 (also §15 A-14) — Dropped receipt markers appear in every later automatic checkpoint, not only in a manual one

**Evidence:**
- `record_turn` persists before delivery (session.py:182-188).
- The next turn's checkpoint serializes the whole history through `message_to_dict`, then `_scrub_metadata`, then `_safe` (serialization.py:111-119, 188-195). That turns every earlier reply's receipts into `{"__dropped__": "DeliveryReceipt"}`.
- `export_state()` does the same (base.py:533).
- EC-28 mentions only "a later manual checkpoint", and A-14 frames the markers as an "If wrong" case.

**Failure:** A test author who pins "checkpoints never contain `__dropped__`" writes a test that fails from turn 2 onward. Users who inspect checkpoints see markers with no explanation.

**Smallest fix:** Reword EC-28 and A-14: "From the next turn on, every checkpoint and `export_state()` holds earlier receipts as `{"__dropped__": "DeliveryReceipt"}`. Harmless; accepted (D-15, Q-6)."

### R-11 [Minor] [L9] §12.3 row 7 `_client` (also §9.2 row a-6) — Amazon SES's second implicit-TLS port, 2465, is treated as STARTTLS

**Evidence:**
- `_client` uses `SMTP_SSL` only when `port == SMTP_IMPLICIT_TLS_PORT` (465).
- SES documents implicit TLS on ports 465 and 2465, and STARTTLS on ports 25, 587 and 2587.
- SES is in catalog row a-6.

**Failure:** `EmailOutput(port=2465)` opens a plain connection to a TLS listener. It fails as FAILED `network` after the 10-second timeout, with no hint why.

**Smallest fix:** Add one footgun line to the row-19 README: "SES: use 465 or 587; 2465 is not supported". Optional Q-9 [scope-adding]: an `implicit_tls` flag. Default: not built.

## VERIFIED CLAIMS

**Held (repo, at base `db3988ff`)**

- **Insertion point** (INV-26, D-3). In base.py:
  - the handoff block is at 920-927;
  - `_notify_session(reply)` is at 928;
  - `_assert_schema_satisfied` is at 931;
  - the drain is at 932-933.

  The `metadata` dict is the reply's own object.
- **Drain contract** (EC-20). base.py:1073-1107 catches `Exception`, writes `queued_prompt_error`, notifies the session and clears the queue.
- **Transport** (§12.4, D-5). In transport.py:
  - `_send_once` calls `setdefault("content-type", …)` on a plain dict (59-66);
  - a POST retry requires `idempotency_key` (`_require_idempotency_guard`), and the key is never sent;
  - `follow_redirects` defaults to False;
  - backoff starts at 0.5 s and doubles.
- **JevAgent** (D-8).
  - `JevAgentSettings` is frozen and slotted, with `api_key` as `field(repr=False)`.
  - `_validate_agents` provides the tuple-normalization pattern.
  - The `JevAgent(settings, runtime_settings=None)` signature is pinned by tests/test_jev_agent.py:504-509.
  - `super().__init__` takes an explicit keyword list.
- **CodingAgent** (D-9). It forwards `**kwargs`, and its contract test forbids new keywords.
- **Fork paths** (D-7, for those paths only).
  - fork.py:53-81 calls `BaseAgent(...)` with explicit keywords.
  - agent_tool.py:59 runs `self._agent.fork()`.
  - MultiAgent workers come from `binding.fork()`.
  - jev/bulk_work.py:49 builds its agent with no outputs.
- **Credential and masking precedents** (D-11). `resolve_api_key` is at registries/models.py:151-161, and `FallbackModel.__repr__` masks the key (lib/dataclasses/agents.py:224).
- **Sessions.**
  - `SessionSerializer._safe` turns non-pydantic objects into `{"__dropped__": TypeName}`.
  - `Session.resume` and `fork_from` call `BaseAgent.restore(...)` without outputs (session.py:459).
  - `Session.arun` re-notifies on any exception, but `FailureRouter.capture_exception` dedups by id, so `_deliver_outputs`'s notify does not double-count.
- **`AgentStopReason.MIDDLEWARE_ABORT.value`** is `"middleware_abort"` (lib/dataclasses/agents.py:65).
- **A-13.** Every runtime goes through `_run_direct`, then `_runtime()`, then `RuntimeRegistry`, inside `_generate_reply`.
- **D-1.** `vidbyte/providers/` is the model-vendor layer (REPO_MAP.md:269), and REPO_MAP uses `#####` folder headings.
- **Smaller precedents:**
  - the `asyncio.to_thread` precedent at fetch.py:223;
  - the "Retrieved" date in the clients README;
  - the A001 header in speed.py;
  - the C016 generator refuses while `vidbyte/__init__.py` has uncommitted changes;
  - `SDK-LINT: PASS` is the last line of the lint report (lint/core/report.py:58);
  - the Semgrep commands;
  - setuptools package discovery picks up the new subpackages;
  - `test_custom_exception_constructors` does not iterate over error classes, so the keyword-only constructor is safe;
  - §13's `_send_once` and `asyncio.sleep` patch seams.
- **Baseline counts match lint/baseline.json:** A001 643, A002 703, A006 34, A007 255.

**Did not hold**

- **§11 "Typecheck: N/A":** S009 runs mypy (R-6).
- **INV-16 and NG-5 for Jev specialists and AggregateAgent:** these agents run un-forked (R-3).
- **D-2 "A006 … even inside a function":** this is true for concrete modules but not for package `__init__` targets (a006:54/67/77; model_provider.py:61). The real rule is AGENTS.md Style 3 (R-1).
- **Row 6 `single_line` against INV-15 and AC-10:** the marker contains "\n\n" (R-4).
- **D-21 and row 7 `_link` order for Jira** (R-5).
- **INV-9 completeness:** budget-stop notices are not skipped (R-2).
- **EC-28 "a later manual checkpoint":** every later checkpoint carries the markers (R-10).

**Web spot-checks** (2026-10-11, official docs)

- **GitHub:** API version `2026-03-10` exists, and create-issue returns 201 with `html_url`. Held.
- **Notion:** `Notion-Version: 2026-03-11` and the `markdown` body parameter on `POST /v1/pages` are both documented. Held. Enhanced markdown includes mention tags (R-9).
- **Linear:** a personal API key goes in `Authorization` with no `Bearer`, and `issueCreate` returns `issue { url }`. GraphQL errors can arrive with HTTP 200. Held.
- **Jira Cloud v3:** create returns 201 `{id, key, self}` with no web URL, `description` must be ADF, and auth is Basic `email:token`. Held.
- **Gmail:** SMTP with an app password needs 2-Step Verification. Held.
- **Teams:** Office 365 connectors are retired, and Workflows webhooks take an Adaptive Card attachment envelope. The 28 KB card limit is consistent with A-4. The meaning of the 202 response is only community-documented, as A-2 states honestly. Held.
- **Amazon SES:** implicit TLS on 465 and 2465 (R-11).
