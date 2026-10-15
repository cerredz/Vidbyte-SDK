VERDICT: SOUND WITH FIXES — The R-1 re-cut honors all three placement clauses, is cycle-free, and resolves R-1 to R-11 in the text; what remains is two Major gaps (validators that AC-20 needs but §8.5 does not provide, and a new two-hop call chain in `BaseAgent`) plus five Minor accuracy fixes, none of which changes the architecture.

## WHAT THE SPEC GETS RIGHT

- **The r2 layout is correct and should not be collapsed further.**
  - The `OutputConnector` Protocol lives in `vidbyte/agents/output/`, and the lib classes satisfy it with no upward import.
  - I simulated the exact §12.2/§12.3 import edges in memory. Stub modules carried every new edge: constants → `lib.dataclasses.agents`, `lib/errors/base.py` → `lib.enums.outputs`, `agents/output/__init__` → `lib.outputs`, base.py and jev/settings.py → `agents.output.connector`/`dispatcher`, and root → `agents.output`. `import vidbyte` loads cleanly whether base.py's two new imports sit early (after `vidbyte.agents.mixins`) or late (after `vidbyte.tools.types`). No cycle forms, and there is no lib → agents edge.
  - Two types (the Protocol plus `BaseOutput`) is the minimum. A single contract would have to live in lib, which inverts clause 1, or would need eleven hand-written masked reprs, which puts INV-4 at risk. §8.3 states this correctly.
- **The R-1 to R-11 fixes are actually in the text.**
  - R-2: `OUTPUT_DELIVERABLE_STOP_REASONS` equals the repo's `NORMAL_STOP_REASONS` (evals/behavior/stop.py:32).
  - R-4: `single_line` no longer calls `truncate`.
  - R-5: D-21 orders the steps parse, walk, str, prefix, then `https://`.
  - R-6: the S009 command and its baseline of 350 are verified.
  - R-7: the A002 site list matches how the rule scans identifiers (a002:69-75).
  - R-8 to R-11 are reflected in D-17 (f), the Notion constants, EC-28, and EC-46.
  - Removed r1 symbols (`OutputConnector.deliver`, `_send`, `content.py`, `OutputText.is_deliverable`, `.content`, `.structured_json`) appear only in the §16 rename table.
- **EC-44's Jev error claim is exactly right.** base.py:879-890 wraps every `Exception` except `UsageAccountingError` and `FailureRaisedError` in `AgentExecutionError(...) from exc`. A specialist's `OutputDeliveryError`, raised from `jev/runtime.py:187` inside the JevAgent's runtime call, therefore surfaces as `AgentExecutionError` with the original as `__cause__`.
- **The counts reconcile.**
  - §8.4's 23 new files are §12.3 rows 1–23 (21 `.py` and 2 READMEs), with 26 classes in 19 modules and 13 modified files.
  - The 17 root exports follow the root precedent: `vidbyte/__init__.py:458-479` exports 16 middleware builtins.
  - Every lint baseline number in §11 matches `lint/baseline.json`.

## FINDINGS

R-12 [Major] [L9] §8.5 `OutputArguments` (also §12.3 rows 13, 14, 16; §12.4; AC-20) — Four AC-20 inputs have no validator in the designed API, and the `to` check would name the wrong parameter
  Evidence:
  - §12.4 says: "Connector constructors contain no `raise` themselves. Every check lives in `OutputArguments` or in a record's `__post_init__`."
  - §8.5's `OutputArguments` has `credential`, `https_url`, `text`, `texts`, `identifier`, and `optional_callable`. None of them checks:
    - an `owner/name` repo (row 14: "exactly one `/` … made of `[A-Za-z0-9_.-]`");
    - a bare host ending in `.atlassian.net` (row 16 `site`);
    - an address containing `@` (row 16 `email`).
  - Row 13 sends `to` through `OutputArguments.texts`, which checks only non-blank. The address check then happens in `SmtpSettings.recipients`, whose `__post_init__` "raises `ConfigurationError` naming the field", and that field is `recipients`.
  - AC-20 (P0) requires `repo="acme"`, `site="https://acme.atlassian.net"`, and `to="not-an-address"` each to raise a `ConfigurationError` that "names the offending parameter".
  Failure: A fresh implementer has two bad options.
  - Write an inline `raise` in the `GitHubIssueOutput` and `JiraIssueOutput` constructors, which breaks the spec's own §12.4 checklist and draws a review comment.
  - Invent `OutputArguments` methods that §8.5 does not list, which §14 makes an ask-first change.

  Either way, `EmailOutput(to="not-an-address")` raises an error naming `recipients`, so a blind test asserting that the message names `to` fails.
  Smallest fix: Add two static methods to §8.5 and use them in rows 13, 14, and 16:
  - `OutputArguments.matching(value: object, pattern: str, *, parameter: str) -> str`, a full-match check whose error names `parameter`;
  - `OutputArguments.address(value: object, *, parameter: str) -> str`, which requires `@` and rejects whitespace, CR, LF, and commas.

  Add `GITHUB_REPO_PATTERN` and `JIRA_SITE_PATTERN` to row 2. Rows 13, 14, and 16 then call these with `parameter="to"` (per item), `"repo"`, `"site"`, and `"email"`. `SmtpSettings` keeps its own checks as record validation. The class count does not change.

R-13 [Major] [L4] §12.3 row 27 (also §8.5 `_deliver_outputs`, §5 node G, the §12.4 Style 1 line) — The PR's one new `BaseAgent` helper calls another same-class helper, a two-hop chain that AGENTS.md Style 1 forbids in new code
  Evidence:
  - AGENTS.md Style 1: "a function may call another of its own functions, but that second function should not call a third … lift that call up into the main function."
  - Row 27: `_generate_reply` calls `await self._deliver_outputs(reply, metadata)`. Then `_deliver_outputs`, in its `except BaseException`, "runs `self._queued_prompts.clear()` and `self._notify_session_exception(exc)`". That second call is a `BaseAgent` method (base.py:965).
  - The handoff precedent the spec cites does its `try`/`except BaseException` inline in `_generate_reply` (base.py:920-927).
  - §12.4 asserts "Call chains are at most one hop of same-class delegation."
  Failure: The shape contradicts both AGENTS.md and the spec's own checklist, and a reviewer applying Style 1 to new code flags it. It is Major, not Blocker, because `_assert_schema_satisfied` and `_close_failed_reply` already have this shape on main. AGENTS.md says existing code is not precedent.
  Smallest fix: Delete `_deliver_outputs`. After base.py:931, add the following, mirroring 920-927 (about 7 lines, within NFR-3's 25):

  ```python
  if self.outputs:
      try:
          await OutputDispatcher.deliver(self.outputs, reply, metadata)
      except BaseException as exc:
          # @intent failed-run-leaves-no-queued-prompts
          self._queued_prompts.clear()
          self._notify_session_exception(exc)
          raise
  ```

  Update §5 node G, the §8.5 `BaseAgent` block, W-9, row 27, the §12.4 narration and A002 site lists, INV-7, and the §2 wording.

R-14 [Minor] [L7] §6.1 INV-12 (also §10 T-2) — "No delivered text can trigger a mention" overclaims: per-user mentions still notify on GitHub and Telegram
  Evidence:
  - INV-12's headline promises no mention can be triggered, but T-2 accepts only "GitHub `@org/team` mentions in issue bodies".
  - GitHub notifies any `@username` named in an issue body, not only teams.
  - Telegram's Bot API detects `@username` in plain text as a `mention` entity, and the named group member is notified. Leaving out `parse_mode` does not change that.
  - request.md §C settled on suppressing only *mass* mentions.
  Failure:
  - A prompt-injected "@alice @bob" in a public-repo issue or a Telegram group pings those people from the user's token or bot. That is a shorter path to harm than T-2 traces.
  - A test author bound to INV-12's headline writes a GitHub or Telegram `@user` neutralization test that the design never satisfies.
  Smallest fix:
  - Reword INV-12 to "No delivered text can trigger a channel-wide or mass mention", keeping the per-destination bullets.
  - Extend T-2's accepted limitation and the row-19 footguns to "GitHub `@user`/`@org/team` and Telegram `@username` notify the named person".
  - Optional Q-10 [scope-adding]: neutralize `@` in GitHub and Telegram text. Default: not built.

R-15 [Minor] [L9] §6.1 INV-9, EC-38, EC-44 (also README rows 19, 23, 34) — The Jev and Aggregate sub-agent paths are partly misdescribed
  Evidence:
  - **INV-9** says "A reply with no `stop_reason` key is delivered; JevAgent replies are an example (Jev code sets none)." But:
    - `JevRuntime` subclasses `AgentRuntime` (jev/runtime.py:40) and calls `super().arun` (:137).
    - `AgentRuntime._runtime_metadata` writes `"stop_reason": stop_reason.value` (runtime.py:1911).
    - `JevResponse.finished` keeps that metadata (jev/response.py:150).
    - `JevResponse.delegated` copies the specialist's whole `reply.metadata` (response.py:131).
    - Only the preflight `stopped` result (response.py:136) carries no `stop_reason`.
  - **AggregateAgent:** proposers run under `gather(return_exceptions=True)` (aggregation.py:89). An exception result goes to `failed_labels`, and too few candidates raise `AggregateExecutionError` (aggregation.py:116-132).
  Failure:
  - (a) A normal JevAgent reply carries `final_response` and is delivered. The outcome is right but the stated reason is wrong, so a test asserting "Jev replies have no `stop_reason`" fails.
  - (b) A JevAgent without outputs that delegates to a specialist with outputs returns `metadata["deliveries"]` holding the specialist's receipts, so AC-21's "no deliveries key" does not hold on that path. When the JevAgent has outputs of its own, its receipts silently replace the specialist's.
  - (c) An AggregateAgent proposer whose webhook was revoked did write a draft, but it is counted as a failed proposer and its draft is dropped. If every proposer fails delivery, the aggregate raises `AggregateExecutionError`. Neither EC-44 nor the footguns say this.
  Smallest fix:
  - In INV-9, replace the example with "the JevAgent clarification stop (`JevResponse.stopped`); normal Jev finishes carry the inner runtime's `final_response` or `is_done`".
  - Add consequences (b) and (c) to EC-44 and to the footgun lines in rows 19, 23, and 34.

R-16 [Minor] [L4] §8.1 D-1 — The deciding reason misstates `vidbyte/providers/` and skips its closest sibling, `vidbyte/providers/tracing/`
  Evidence:
  - D-1 says `vidbyte/providers/`'s "README covers model contracts only". But `vidbyte/providers/README.md:46` lists "`tracing/`: provider-backed trace adapters".
  - `vidbyte/providers/tracing/{langfuse,langsmith,phoenix}.py` are non-model adapters. Each sends agent data to a third-party platform with a pasted credential (an explicit argument, else an environment variable: langsmith.py:38, langfuse.py:40-41) and implements a lib contract (`TracerBase`).
  - The eager-import reason is weak too. Root `vidbyte/__init__.py:504` already imports `vidbyte.providers`.
  Failure: The user's clause 2 explicitly offered "the provider folder". The spec turns it down on a false premise, so a reader comparing designs sees an unweighed precedent. The lib choice itself is allowed and should stay.
  Smallest fix: Rewrite D-1's deciding reason so it names `providers/tracing/` as the precedent for the runner-up. Then decide on the real differentiators:
  - `lib/outputs/` sits beside `lib/http/`, which every connector uses.
  - It keeps destination classes out of the model-vendor namespace.

  The runner-up (`vidbyte/providers/outputs/`) and the flip condition stay.

R-17 [Minor] [L11] §12.4 "Import order passes …" — The S051 check cannot hold as written
  Evidence:
  - On this base, `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` prints "Found 222 errors".
  - `vidbyte/agents/base.py` already has three unsorted blocks (24:1, 422:9, 450:9).
  - S051 is a ratchet, baselined at 259.
  - Field guide `local-ci-verification.md:38-42` says to filter the output to your own paths and to check that S051 returns to its baseline.
  Failure: An implementer told the command must "pass" either chases 222 unrelated findings or runs `--fix` over base.py's whole import block. That reorders untouched lines, which `review-scope.md` and NG-11 forbid.
  Smallest fix: Reword to: "S051 is not REGRESSED. The I001 output, filtered to the new files and to `jev/settings.py`, `errors/base.py`, `errors/__init__.py`, and `enums/__init__.py`, is empty. In `base.py`, add the two imports without re-sorting the existing block."

R-18 [Minor] [L5] §7 NFR-2 (also §10 T-5) — "Bounded added latency" holds only per httpx phase, so a trickling endpoint can hold `run()` far past the conversation's "about 10 s"
  Evidence:
  - request.md §C: "a per-connector timeout constant (about 10 s) bounds the added latency".
  - NFR-2: "each with `OUTPUT_TIMEOUT_SECONDS` per httpx phase".
  - `HttpTransport` passes the timeout to `httpx.AsyncClient(timeout=…)` (transport.py:46), and httpx applies its read timeout per read. `_send_bounded` keeps streaming until `max_response_bytes` (1,000,000) is reached.
  - T-5 names the hostile endpoint as an attacker.
  Failure: A compromised webhook receiver that sends one byte every 9 s keeps one `agent.run()` waiting for up to about 1,000,000 × 9 s, with no receipt and no error. Because the sends are gathered, every other connector's receipt waits too.
  Smallest fix: Choose one:
  - (a) In `_deliver_one`, wrap `connector.send(...)` in `asyncio.wait_for(..., OUTPUT_DELIVERY_DEADLINE_SECONDS)` and map `TimeoutError` to FAILED `network`. Size the constant above the 429 path (3 attempts plus 1.5 s of backoff). As EC-19 already says, an SMTP thread keeps running.
  - (b) Record the per-phase limit as an accepted edge case under T-5 and NFR-2.

  Option (a) is not scope-adding, because the conversation set the bound.

## VERIFIED CLAIMS

Held (repo at base `db3988ff`; worktree clean before and after):
- **Reply path.** `_notify_session` is at base.py:928, `_assert_schema_satisfied` at :931, and the drain at :932-933. The `except Exception` wrapping is at :879-890 and the `except BaseException` at :891 (D-3 says the `try` is at :832; it is at :831, which is trivial). `self.middleware` is at :231, and `export_state` history is at :533. The runtime rejections A-13 cites are at :128-134.
- **Stop reasons.**
  - `AgentStopReason` has 17 members (lib/dataclasses/agents.py:51-70).
  - `FINAL_RESPONSE` and `IS_DONE` are set at runtime.py:539 and :608, `_stopped_result` is at :1882, and `stop_reason.value` is written into metadata at :1911.
  - `NORMAL_STOP_REASONS` is at evals/behavior/stop.py:32.
  - `CONTRACT_UNSATISFIED` is set at runtime.py:514 and :593.
  - Codex sets `stop_reason` only on its schema error (codex/result.py:225), never in reply metadata.
- **Import graph** (in-memory simulation, no files written, `PYTHONDONTWRITEBYTECODE=1`).
  - Every new edge in §12.2/§12.3 loads with both base.py import placements.
  - `lib/errors/base.py` imports nothing from vidbyte today, and no `lib/enums/*` module imports `lib.errors`, so the new errors → `enums.outputs` edge is safe.
  - A006 has no layering within lib (a006:23-35), and it excludes `__init__.py` targets (:65-67).
- **Protocol semantics.**
  - `isinstance(SlackOutput, OutputConnector)` (the class itself) is True and `object()` is False, so the spec's `isinstance(item, type)` check that runs first is needed.
  - mypy 2.3.1 accepts §8.5's `destination: OutputDestination` annotation on `BaseOutput` with subclasses assigning it.
  - It rejects a `ClassVar[...]` declaration: "Protocol member OutputConnector.destination expected instance variable, got class variable".
- **§11 commands.**
  - `lint/core/mypy.py:56` runs `mypy --config-file lint/mypy.ini vidbyte`, and `lint/mypy.ini` sets `check_untyped_defs` and `disallow_any_generics`.
  - `lint/run.py` has `--rule` and `--update-baseline`.
  - `run_ci.py --stage` accepts all, source, and package.
  - `SDK-LINT: PASS` is printed at report.py:58, and the generator's `--check` and its refusal on uncommitted changes are as described.
  - Baselines A001 643, A002 703, A003 36, A006 34, A007 255, S002 0, S003 9, S009 350, S011 0, S012 0, S015 13, S019 5, S024 25, S046 0, S052 0, S063 4, C016 0, and A009 0 all match.
- **Sub-agent paths.**
  - Forks: fork.py:53-81 and agent_tool.py:59.
  - Jev: jev/agent.py:62-76 and :90-102. clone.py:29-45 and swarm.py:41-57 build with explicit keywords and no outputs, and jev/runtime.py:187 runs the specialist.
  - Others: aggregation.py:113-114 and :144; pipelines/base.py:67; workflows/stages.py:109 and :121; mcp_server/handlers.py:149.
  - Sessions: session.py:182-188 and :459.
  - The drain contract at base.py:1073-1107 matches EC-20.
- **Pinned tests.** tests/test_jev_agent.py:504-509 and the coding contract's `EXPECTED_SIGNATURE` and `PARITY_KEYWORDS` match. No test pins `BaseAgent.__init__`, `restore`, or the `JevAgentSettings` field list; test_jev_done.py:1028 only asserts that `done` is absent.
- **Transport.**
  - The async `request` accepts `max_response_bytes` and `follow_redirects`.
  - Network errors are never retried (transport.py:43-56).
  - A POST retry requires `idempotency_key` (:22-25), and `setdefault("content-type")` is at :65.
- **§13 seams.**
  - test_web_operation_client_retry.py:39-40 patches `_send_once` and the transport's `asyncio.sleep`.
  - agent_test_support.py has `build_test_agent`, `bind_test_runner`, and `OfflineTestAgent`.
  - The coding_agent conftest has `script_model` and `fake_provider_http` with the "(200, 401)" note.
  - There is no `tests/conftest.py`.
- **Precedents.**
  - `SessionStore` is a runtime-checkable Protocol (sessions/store.py:29-30).
  - `ProviderModelRegistry.resolve_api_key` is at registries/models.py:151-161.
  - `FallbackModel.__repr__` masks the key (agents.py:224).
  - `JevAgentSettings.api_key` is `field(repr=False)`, and `_validate_agents` is the pattern.
  - `outputs` belongs on `JevAgentSettings` per field guide jev-capability-layout.md:63-65.
- **Packaging and docs.**
  - C015 exempts folder READMEs that no package-data pattern ships, so the two new READMEs are safe.
  - No lint rule requires a folder README per phase.
  - The touched folder READMEs have no `## Notes for agents` sections.
  - Nothing gates `llms.txt` or `artifacts/file_index.md`.

Did not hold:
- INV-9 and EC-38 say JevAgent replies carry no `stop_reason`. Normal and delegated Jev replies do carry it (R-15).
- D-1 says the `vidbyte/providers/` README covers model contracts only. README:46 lists `tracing/` adapters (R-16).
- §12.4 says the I001 command "passes". It reports 222 findings on the base (R-17).
- AC-20 expects `to="not-an-address"` to raise an error naming `to`. Under rows 13 and 3 the error names `recipients`, and `repo`, `site`, and `email` have no validator home (R-12).
- §12.4 says call chains are at most one hop. `_deliver_outputs` calls `_notify_session_exception`, which is two hops (R-13).
