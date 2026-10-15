LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — All 36 §12.3 rows are built as written and the §4 snippet prints exactly what the spec shows, but a caller-written connector with a non-enum `destination` gets past construction and then breaks INV-6, INV-7, INV-8 and INV-21 at delivery time.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The §4 snippet works exactly as the spec shows. I extracted it from spec.md and ran it verbatim with `exec`, scripting only the model runner and `HttpTransport._send_once`. It prints `slack sent None\ngithub_issue sent https://github.com/acme/shop/issues/412\n`, which is byte-equal to the §4 text block. Slack receives `"<title>\n\n<body>"`. GitHub receives `{title, body, labels:["bug"]}`.
- The row-27 wiring in `vidbyte/agents/base.py:935-959` matches the r5 design exactly:
  - `if self.outputs:` guards the call, so an agent without outputs adds no await (INV-22).
  - `_deliver_outputs` catches `BaseException`, clears `_queued_prompts`, notifies the session, then re-raises. `_queued_prompts` is the context-var-scoped run queue (base.py:396-399), so INV-7's "the list the run claimed" holds.
  - `_generate_reply` measures 10 / 9 / 50, identical to db3988ff, so S008 is unchanged.
- Placement and layering follow Prompt 4 to the letter:
  - The Protocol, `OutputShaping` and `OutputDispatcher` are in `vidbyte/agents/output/`.
  - All provider work is in `vidbyte/lib/outputs/`.
  - No lib module imports a higher layer, and `agents/output` imports only `vidbyte.lib.*` and itself (grep is empty).
  - No OAuth, MCP, CLI, YAML or keyring code was added.
- Every per-destination wire body and header in §9.2, every constant in row 2, and every constructor signature in §8.5 matches field for field. No extra knobs were added, and the INV-9 allowlist is exactly `stop_reason is None or in {final_response, is_done}`.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Major] [every-path / INV-21] vidbyte/agents/output/dispatcher.py:45 (also :57, :94, :102) — A connector whose `destination` is not an `OutputDestination` passes construction and then breaks delivery after the model call
  Evidence:
  - `connectors()` checks only `isinstance(item, OutputConnector)` (line 45). That is a runtime-checkable Protocol, so it checks that the attributes exist, not their types.
  - Every receipt the dispatcher builds itself uses `DeliveryReceipt(connector.destination, ...)` (lines 57, 94, 102). `DeliveryReceipt.__post_init__` rejects a non-enum destination (`vidbyte/lib/dataclasses/outputs.py:62`).
  - I ran the probe script `scratchpad/probe_edges.py`. Its first case passes a connector with `destination = "pagerduty"` plus a valid `WEBHOOK` connector:
    ```
    1. connectors() accepts str destination: ACCEPTED at construction
    2. deliver with str destination: ConfigurationError | destination must be an OutputDestination, got 'pagerduty'. | deliveries key present: False
    3. skip path with str destination: ConfigurationError | destination must be an OutputDestination, got 'pagerduty'.
    4. send returns None: OutputDeliveryError | 1 of 1 outputs failed: webhook (unexpected:NoneType) | cause: None
    ```
  Failure:
  - `Agent(outputs=[MyPagerDutyOutput()])`, where `destination = "pagerduty"`, builds without error. `OutputConnector` is a root export and FR-5 documents caller-written connectors.
  - After the whole model run, `_deliver_outputs` re-raises a bare `ConfigurationError`. The valid connector's SENT receipt is lost, no `"deliveries"` key is written, and no `OutputDeliveryError` carries `.reply` or `.receipts`. This breaks INV-6, INV-7 and FR-10.
  - A skipped run (budget or middleware stop) also raises instead of returning normally. This breaks INV-8 and AC-8's "nothing is raised".
  - Related path: a custom `send` that returns a non-receipt (for example `None`) becomes `unexpected:NoneType`. That falls outside INV-11's `unexpected:<ExceptionTypeName>` form, and the error has no `__cause__`.
  Smallest fix:
  - In `OutputDispatcher.connectors`, inside the existing loop, also require `isinstance(item.destination, OutputDestination)`, raising `ConfigurationError(f"outputs[{index}].destination must be an OutputDestination ...")`. The message names `outputs`, as AC-20 requires.
  - In `_deliver_one`, check the value returned by `send` the same way the render result is checked: raise `ConfigurationError` unless it is a `DeliveryReceipt`. It then becomes FAILED `unexpected:ConfigurationError` and is chained, which is valid INV-11 grammar.
  - Two small edits in one file, with no new class or knob. Re-measure S008 on `connectors()` after the change.
  Spec IDs: INV-21 ("before any model call"; "does not satisfy `OutputConnector`", whose member is typed `destination: OutputDestination`), INV-6, INV-7, INV-8, INV-11, AC-8, FR-5, FR-10

R-C2 [Minor] [spec wording vs AC] docs/spec/agent-output-connectors/spec.md:197 vs vidbyte/agents/output/dispatcher.py:88-90 — INV-2's "exactly once unless the reply is skipped" cannot hold together with AC-11(e) and EC-16
  Evidence:
  - INV-2 says every connector's `send` is called "exactly once unless the reply is skipped (INV-9)".
  - `_deliver_one` raises before `send` when `render` raises or returns a non-`OutputContent`. The test `test_render_that_returns_anything_but_output_content_fails_only_its_connector` asserts `fake_http.sends_to("api.github.com") == []`, as AC-11(e) requires.
  Failure: a GitHub connector built with `render=lambda r: "x"`, on a finished reply, gets zero sends on a reply that is not skipped. That literally violates INV-2's weighted "exactly once". The code is correct per AC-11(e), EC-16 and Q-5. The spec contradicts itself.
  Smallest fix: no code change. Reword INV-2 to "exactly once unless the reply is skipped (INV-9) or its content cannot be built (AC-11 e, EC-16)".
  Spec IDs: INV-2, AC-11, EC-16, Q-5

VERIFIED CLAIMS:
- S3: "313/313 feature tests pass". HELD (313 passed).
- S3: "source stage 3516 passed, 12 skipped". HELD for pytest: the full suite gives 3516 passed, 12 skipped (pytest only; I did not run run_ci).
- S3 and r5: "`_generate_reply` measures 10 / 9 / 50, same as base". HELD. Ruff with limits of 1 gives C901 10, PLR0912 9, PLR0915 50 on both 9463c348 and db3988ff.
- S3: "base.py +29/−4 against a limit of 35". HELD (numstat `29 4`).
- §8.4 budget. HELD:
  - 23 new files (21 `.py` and 2 READMEs);
  - 26 classes (25 in the new modules plus `OutputDeliveryError`);
  - 0 dependencies (pyproject diff is empty);
  - 17 root exports, and `vidbyte.agents.output.__all__` has 18 names with `OutputDispatcher` the only non-root one;
  - the largest new module is 149 lines.
- S3: "Files outside §12.3: none". HELD. The name-status listing shows 23 A and 13 M under vidbyte/, REPO_MAP.md and contracts/, exactly rows 1–36. `coding.py`, `agents/__init__.py`, `codex/*`, `transport.py` and `sessions/*` are untouched.
- §14 Never-list. HELD:
  - `git diff origin/main...9463c348 -- lint/baseline.json` is empty;
  - `git diff 72fc2002..9463c348 -- tests/` is empty, and no test outside the new pack was touched;
  - no `noqa`, `type: ignore`, `nosemgrep` or `pragma` was added;
  - every code commit cites a W-, FR- or AC- ID.
- AC-1 (§4 snippet run literally). HELD (see the first bullet of "gets right"). The acceptance test runs the same text. Its only addition is `bind_test_runner` between construction and `run`, the same seam my exec used.
- AC-22 contract. HELD: `generate-sdk-public-api.py --check` reports current at 839e8e33, 623 exports.
- INV-9 allowlist. HELD: `connector.py` `is_deliverable` matches row 21 exactly. Every runtime writes `stop_reason.value`, never the enum (runtime.py:1911, reflexion.py:160), so membership in the str frozenset is sound. MCTS writes no `stop_reason` and is delivered, as INV-9 says.
- INV-16 and D-7. HELD:
  - fork.py passes `outputs=()`;
  - nothing in vidbyte copies an agent (no `copy`, `deepcopy` or `type(agent)(...)` of an agent);
  - the Jev fresh-continuation, bulk, clone, swarm and `JevClarificationAgent` constructions pass no `outputs`.
- FR-1 "accepted for every AgentRuntimeType". HELD: linear, mcts_search and the three actor types all construct with `outputs` and store them. Jev goes through JevAgent.
- FR-2 / AC-14, FR-3 / AC-13 and D-9 / AC-15. HELD. Settings validates through `OutputDispatcher.connectors` and its error contains "outputs". `JevAgent.__init__` keeps `(settings, runtime_settings)`. `restore(outputs=)` passes the value through. The CodingAgent contract suite passes unmodified (202 passed, 11 skipped across the pinned suites).
- §12.4 "comments ≤ 72 cols" and "no numeric literals". HELD: no added comment line is over 72 columns, and no numeric literal appears in `lib/outputs` or `agents/output`.
- Briefing item "README catalog with researched exclusions". README PART HELD; EXCLUSIONS NOT A DEFECT.
  - `vidbyte/lib/outputs/README.md` has 11 dated rows with links and least-privilege notes (AC-26).
  - The researched exclusions (§9.2 b) live only in the spec. That is where Prompt 4 asked for them ("What i also want you to do in the spec is come up with a list of popular platforms") and where FR-19 places them, so this is not a finding.
- Weighted words (request.md §D). HELD:
  - "1 line using a key": `SlackOutput()` reads `SLACK_WEBHOOK_URL`.
  - "deterministically pass the structured output": the destination and credential are fixed at construction, and the structured `title`/`body` fields shape the content.
  - "provider specific logic … lib folder": held.
  - "bolt the parameter on our BaseAgent": held, plus Jev and CodingAgent.
  - "no oauth": held.
  - "not overengineered": the counts match §8.4 exactly. No registry, plugin system or per-destination payload types.
- §5 diagram vs code. HELD node for node from `_assert_schema_satisfied` to `OutputDeliveryError`. Two cosmetic divergences:
  - node C→D omits the pre-existing handoff block and the moved `_record_last_trace`;
  - `render` runs outside the `wait_for` deadline. The diagram's edge label is consistent with this, but it is not stated.
- S3 deviations 1–5 (spec §17). Each is necessary or harmless and recorded. I found no unreported deviation that changes behavior. The private module helpers in `lib/dataclasses/outputs.py` are an implementation detail, owned by the conventions lens.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors -p no:cacheprovider` → `313 passed in 2.34s`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/test_jev_agent.py tests/features/coding_agent tests/test_restore_output_schema.py tests/test_agent_tool.py tests/test_agent_fork_isolation.py tests/test_custom_exception_constructors.py tests/test_readme_size_limit.py` → `202 passed, 11 skipped in 6.57s`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -x` → `3516 passed, 12 skipped in 25.83s`
- `python scratchpad/run_spec_snippet.py <worktree>` (spec §4 extracted and exec'd verbatim; runner and `_send_once` scripted) → `MATCH: True`
- `python scratchpad/probe_edges.py <worktree>` → the 4 lines quoted in R-C1
- `python -m ruff check vidbyte/agents/base.py --no-cache --isolated --select C901,PLR0912,PLR0915 (limits 1)` → `_generate_reply ... (10 > 1)`, `(9 > 1)`, `(50 > 1)`. The same command on `git show db3988ff:vidbyte/agents/base.py` gives the identical 10 / 9 / 50.
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 839e8e33... (vidbyte-sdk 0.2.1, 623 exports).`
- `git diff origin/main...9463c348 -- lint/baseline.json | wc -l` → `0`. `git diff 72fc2002..9463c348 --stat -- tests/` → empty. `git diff ... -- pyproject.toml | wc -l` → `0`. The suppression grep over the vidbyte, tests and contracts diff → empty.
- `git diff --numstat origin/main...9463c348 -- vidbyte/agents/base.py` → `29 4`
- An FR-1 probe constructing `BaseAgent(..., runtime=rt, outputs=[WebhookOutput(...)])` for 5 runtime types → `ok True` ×5
- Not run, per the briefing: `python lint/run.py` and `scripts/run_ci.py`. The conventions reviewer owns lint.
