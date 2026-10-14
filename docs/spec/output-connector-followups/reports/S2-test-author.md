# S2 test author report: output-connector-followups

Status: DONE. The tests are written red from spec r3 and committed in three commits (not pushed).

## Inputs read

- `spec.md` r3 (all sections), `request.md`, `context/code-map.md`, `pipeline.md`.
- `docs/spec/agent-output-connectors/spec.md`, only its §9.2(b) catalog and §17, which AC-35 checks.
- AGENTS.md.
- The existing pack `tests/features/agent_output_connectors/*`.
- The production modules the tests drive, read only: `vidbyte/lib/outputs/{text,base,delivery,telegram}.py`, `vidbyte/lib/dataclasses/outputs.py`, `vidbyte/lib/http/transport.py`, `vidbyte/lib/tools/filesystem/backends/local.py`, and `vidbyte/lib/errors/base.py`.

## Failure inventory

The full list is in `tests/features/agent_output_connectors/FEATURE.md` under "Follow-ups → Failure Inventory", grouped as rendering, webhook options, comments and modes, new destinations, and update in place. Each item is input + state → wrong output, and each maps to a row of the `test-plan.md` coverage map.

## Pruned candidates

These are in `test-plan.md` under "Tests deliberately NOT written":

- the Q-1 to Q-8 fallbacks and Google Chat Markdown, which are not built;
- the live checks;
- the documented limits EC-35 to EC-38, EC-42, EC-45, and EC-46;
- vendor rejections, which `http_failures.py` already maps;
- constant getters;
- gates that are not pytest;
- property generators;
- `OutputHttp.read` of a JSON object, which the spec leaves ambiguous (see below).

## Fixtures added or extended

- **`factories.py`:**
  - five new `CONNECTOR_CASES` rows, with Confluence on `acme-wiki.atlassian.net` and the job-summary path in a missing `S3CRET` directory under the system temp dir;
  - 14 `HTTP_DESTINATION_KEYS` and `ALL_DESTINATION_KEYS` with `github_job_summary`;
  - 16 `OUTPUT_ENV_VARS`;
  - new placeholder constants `GITLAB_KEY`, `CONFLUENCE_KEY`, `TYPEFULLY_KEY`, and `HUBSPOT_KEY`, with no `TOKEN` or `SECRET` name segment;
  - `HttpxRequests.routes` may now hold a callable that builds the response from the request, for a host that gets a GET and then a PATCH.
- **`conftest.py`:** only the `output_api` comment ("24 public names").
- **`FEATURE.md` and `README.md`:**
  - a Follow-ups section with the boundary, the inventory, the strategies selected and omitted, and the suite map;
  - the HMAC Non-Goal removed;
  - the `content=` transport exception noted;
  - "eleven" changed to "sixteen";
  - the File Index and a Logs entry.
- **No new fixture.** The job-summary thread check uses a module-level Python audit hook (`sys.addaudithook`) in `test_output_connectors_new_destinations.py`. It records which thread opens a uniquely named file. It is added once per process and filters by file name, so it cannot affect other tests.

## First-batch expectations changed (spec §13 exception)

Exactly the §13 list, row by row, in `test-plan.md` under "First-batch expectations updated". One mechanical consequence is logged there: `CONNECTOR_NAMES = ROOT_NAMES[7:]` became `[8:]`, because inserting `TypefullyPlatform` after `OutputDestination` would otherwise put an enum into the connector slice. §13 requires the slice to "still hold only connectors". No unlisted expectation was changed. `factories.py` is committed together with these edits in the first commit, because the edited `WIRE_ROWS` import its new constants and §13 lists it among the first-batch files to change. The first commit therefore imports cleanly on its own.

## Red run

Before implementation:

- **Full pack:** `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q tests/features/agent_output_connectors` → `334 failed, 326 passed in 6.33s`.
  - 279 failures are in the 7 new files.
  - 55 are in existing files: the cases that the larger factory tables and the §13 changes turn red, listed in `test-plan.md`.
  - 12 new cases pass by design. They are regression guards for behavior the spec says must not change: the 10 AC-34 header cases, the Slack 12,001-character escaped-text case, and the `OutputRequest` list-body refusal.
- **Transport neighbour:** `tests/test_web_operation_client_retry.py` → `3 passed`.
- **Lint:** `python lint/run.py` → `SDK-LINT: PASS`. `--rule A001/A002/S001/S017/S025/S051/S054/S060/S061/S062/S063/S064 --all` shows no finding in any new or edited test file. With `--all`, set `PYTHONIOENCODING=utf-8` on Windows, or the report crashes on `→` under cp1252.
- **Failure causes:** every new failure is a `TypeError` for an unknown keyword, an `AttributeError` for a missing class or method, or an `AssertionError` on today's request shape or docs. None comes from test setup.
- **Off-loop check (scratch, not committed):** the job-summary off-loop check was exercised against three local variants: a single-worker executor passes, `asyncio.to_thread` fails the one-thread assertion, and an on-loop write fails the loop-thread assertion.

## Spec defects and hard-to-test items

1. **EC-14 against INV-2 and D-10.** EC-14 says a lone `- ` becomes a "`-` paragraph", which implies trailing whitespace is stripped. INV-2 and D-10 say plain lines give "the same paragraphs as today", and today keeps a line's trailing whitespace. The ADF table compares paragraph text after `rstrip`, so either reading passes. The implementer should pick one and keep it consistent.
2. **`OutputHttp.read` of a JSON object.** FR-30 says `read` returns the parsed JSON. §9.2(c) lists "a JSON value that is not a list of objects" among read failures. No test pins which layer refuses an object. The sticky and keyed tests pin the observable `invalid_response` either way.
3. **Record error type.** §9.1 does not name the exception for `OutputRequest` and `OutputRead` validation. The tests expect `ConfigurationError` naming the field, as every record in `vidbyte/lib/dataclasses/outputs.py` raises through `_require` today.
4. **Job-summary serialization** is proven with large concurrent appends. A wrong two-thread implementation is caught whenever the two writes overlap, which 200,000-character bodies make the usual case, but this is not guaranteed on every run. The off-loop half of the check is deterministic.
5. **`test_output_connectors_security.py:110`.** The wire-secret scan joins `url`, `headers`, and `json_body`, but not `content` (spec §13). It was not edited, because the default webhook case is unsigned. Secret hiding for signed webhooks is proven in `test_output_connectors_webhook_options.py`.

## S3 follow-up (2026-10-14)

- **Defect.** S3 reported, and the orchestrator verified, a defect in `test_job_summary_concurrent_appends_run_off_the_loop_one_after_the_other`: no implementation could pass it. The test read the file back with `path.read_text` before its thread assertions. That read runs on the loop thread, and the audit hook recorded it as a third open, so the test always saw `3 == 2`.
- **Why my scratch check missed it.** The red-run check called the hook harness directly and never read the file back, so it was not the committed test.
- **Fix** (commit `3d974a1f`, this test only): the test takes `appends = list(opened)` right after the `gather` and runs the three thread assertions on that snapshot before reading the file. They are as strict as before: exactly 2 opens, never the loop thread, one thread. The content assertion follows unchanged. The file header's KNOWN EDGE CASES now mentions the snapshot.
- **Mutation proof.** Two scratch runs, not committed, used a throwaway pytest plugin. It replaced `GitHubJobSummaryOutput.send` at runtime, so no production file was edited, and `git status --short` showed only the test file.
  - Appending on the loop thread → FAILED, "the append ran on the event-loop thread".
  - `asyncio.to_thread` → FAILED, "the appends ran on more than one thread, so they could interleave".
  - In both runs, the single-send append test still passed, so each wrong variant still wrote correctly.
- **Results after the fix:** the file is `67 passed`, the pack is `660 passed`, and `python lint/run.py` gives `SDK-LINT: PASS`.
