# S3 implementer report: output-connector-followups

Status: BLOCKED on one frozen test (details under "Blocker"); every §12.3
row is built, committed, and pushed to `feat/agent-output-connectors`
(PR #882, still a draft).

Start HEAD `a286bdb4`, BASE_COMMIT `336d6c78`, tests frozen at S2_HEAD
`f0167c13`. No drift: `git rev-list --count HEAD..origin/main` was 0.

## Rows (spec §12.3)

| Row | Phase | Status | Commit |
|---|---|---|---|
| 1, 2 | P1 | done | a5a50002 |
| 3 | P1 | done | c0ef21d4 |
| 4 | P1 | done | e5b24010 |
| 5 | P1 | done | e2f51913 |
| 6 | P1 | done | 20da9505 (I001 wrap in 1be7319e, comment width in b0c5624e) |
| 7 | P1 | done | 9a9079a8 |
| 8 | P2 | done | 559d9b53 |
| 9 | P2 | done | 2d27dca2 |
| 10 | P2 | done | 6f8ed664 (comment width in b0c5624e) |
| 11 | P2 | done | 75c18943 |
| 12 | P2 | done | 3cfec3d9 |
| 13 | P3 | done | 1ec32e82 |
| 14 | P3 | done | a72e463a (mypy fix in 4991370c) |
| 17 | P3 | done | 5f2fec01 |
| 18 | P3 | done | 5fef133b |
| 15 | P4 | done | f3313095 |
| 16 | P4 | done | d702a7c7 |
| 19 | P5 | done | f54aa3dd |
| 20 | P5 | done | 36ec0929 |
| 21 | P5 | done | aa5b0d0c |
| 22 | P5 | done | 812ab380 |
| 23 | P5 | done | 69343d7d |
| 24, 25, 26 | P6 | done | 88e50eca (I001 wrap of row 25 in 1be7319e) |
| 27 | P6 | done | eadefa3f |
| 28 | P6 | done | d421b6b9 (`--check` current) |
| 29 | P7 | done | b73d77b1 (comment width fix unrelated) |
| 30 | P7 | done | 61c00e58 |
| 31, 32 | P7 | done | c89c001d |
| 33 | P7 | done | 95ecb862 |

§12.4: every box holds (checked below). §12.5: docs, exports, contract,
and gates done; the seven NFR-6 rule checks are clean; `ci.yml` and
`static-policy.yml` dispatch is left to the orchestrator (see Open items).
`llms.txt` and `artifacts/file_index.md` were not touched (§12.5 says no
action).

Spec bookkeeping: frontmatter `status: implemented` (8e51f8ab); §17 row
`r3 | 2026-10-14 | S3 implement` plus an "Implementation deviations" list
(8f1fc73e). §6.2 had no blank Proof cell, so none was filled.

## Data flow, as built

- A connector's `send` builds one or more `OutputRequest`s and hands each to
  `OutputHttp` (`post`, `patch`, or `read`). `post` and `patch` share one
  private `_write(destination, request, method)`: 429-only retries, the
  idempotency key, `HttpTransport.request(json_body=…)` or `content=…`
  (exact bytes; both together raise before any I/O). `read` is a GET with no
  body, `OUTPUT_MAX_READ_BYTES`, 429-only retries, and returns
  `OutputRead(data=…)` or `OutputRead(failure=receipt)`.
- `OutputResponses.error_code` and `.link` moved unchanged out of
  `OutputHttp`, so `_write` calls them one level deep (R-9).
- GitHub: `send` picks one of four mode methods; each builds requests with
  `GitHubRequests`, reads with `OutputHttp.read`, parses with
  `GitHubResponses`, then makes exactly one write. Sticky pages stop at the
  first marked comment or a short page, at most 10 pages.
- Webhook `secret=`: `json.dumps(body).encode("utf-8")` is both signed
  (`"{id}.{ts}." + bytes`, HMAC-SHA256 with the decoded key) and sent as
  `content=`, so a 429 retry repeats the same bytes and headers.
- Job summary: `_append` runs on the module's `ThreadPoolExecutor(max_workers=1)`
  through `LocalFileSystemBackend.append_text(..., create_parents=False)`;
  `OSError` becomes FAILED `file_error`.
- Jira descriptions and comments and Confluence bodies go through
  `OutputAdf.document`.

## Implementation deviations (none changes a public name or a tested behavior)

- Row 11: removed the now-dead `TELEGRAM_TEXT_MAX_CHARS` constant (the only
  user was the old `sendMessage` path).
- `OutputHttp.read` ignores any body on the request and returns any parsed
  JSON value; the list-of-objects check lives in `GitHubResponses.items`
  (invalid → FAILED `invalid_response`).
- `OutputAdf`: a paragraph keeps its raw line (INV-2 byte identity); the
  patterns run on the `rstrip()`ed line; blank lines add no node, so an
  empty fence between two items of one list kind keeps one list.
- Inline literals kept rather than constants (none sits next to an
  operational name, A007 clean): the marker separator `"\n\n"` in
  `GitHubRequests.body`, GitHub query words `open`/`created`/`asc`, Slack's
  three escape characters, the header-value forbidden characters
  `"\r\n\x00"`, and HubSpot's `"+00:00"` → `"Z"`.
- Discord `forum_tags` without `forum=True` is an inline
  `ConfigurationError` in `discord.py`, not a new `OutputArguments` helper.
- `GitHubRequests.issue` single-lines the title itself.
- `OutputArguments.signing_key` strips surrounding whitespace before the
  `whsec_` prefix and base64 decoding.
- Extra `@intent` blocks on the GitHub mode methods and a few helpers, so
  A002 stays clean.
- `WebhookOutput.send` declares `body: object` before the payload check so
  mypy (S009) does not regress; behavior is unchanged.
- Two touched import blocks (`agents/output/__init__.py`, `delivery.py`)
  were wrapped for I001; untouched blocks were left alone.

## Files outside §12.3

None. `docs/spec/output-connector-followups/pipeline.md` is the
orchestrator's and was never staged.

## Budget (§8.4)

- New files: 7 of 7 (`adf.py`, `github_api.py`, `gitlab.py`,
  `github_job_summary.py`, `confluence.py`, `typefully.py`, `hubspot.py`).
- New classes: 12 of 12 (`OutputMethod`, `TypefullyPlatform`, `OutputRead`,
  `OutputResponses`, `OutputAdf`, `GitHubRequests`, `GitHubResponses`, and
  the five connectors).
- Dependencies: 0. Environment variables: 5 of 5.
- Diff: 33 files, +1,708 / −231 (before the spec-status commits).

## Blocker

`tests/features/agent_output_connectors/test_output_connectors_new_destinations.py::test_job_summary_concurrent_appends_run_off_the_loop_one_after_the_other`
cannot pass with any implementation. Its audit hook (`_watch_opens`)
records every `open` of the summary file, including the test's own
`path.read_text(...)` at line 242, which runs on the event-loop thread
before `assert len(opened) == 2` (line 243) and
`assert loop_thread not in opened` (line 244). Observed:
`len([17584, 17584, 7848]) == 3`: both appends on one worker thread
(17584), then the test's read on the loop thread (7848). The
implementation meets D-18, INV-12, and AC-22 (one worker thread, never the
loop, blocks whole). Tests are frozen, so it was not edited.

Options: (a) S2/orchestrator moves the `read_text` after the `opened`
asserts, or snapshots `opened` before it (one-line test fix;
recommended); (b) accept it as a known red test and re-scope AC-22's proof;
(c) change the implementation to avoid `open` (impossible: any append must
open the file).

## Gates (final lines)

All run on the code at 4991370c (the two later commits touch only the
spec).

- Feature pack, `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`:
  `1 failed, 659 passed in 5.24s` (the blocker test; no regression against
  the S2_HEAD pass list).
- `tests/test_web_operation_client_retry.py tests/features/coding_agent`:
  `300 passed, 12 skipped in 14.54s`.
- `scripts/test-async-http-transport.py`: every HttpTransport line `PASS`;
  it then crashes at line 293 on
  `BaseAgent.__init__() got an unexpected keyword argument 'runner'`, the
  same pre-existing crash as on the start commit.
- `python lint/run.py`: `S009 RATCHETED: 350 known finding(s)` …
  `SDK-LINT: PASS`.
- NFR-6 rule checks (`--rule <ID> --all --format json`, compared with the
  S2_HEAD tree): A002 579 (baseline 703), S061 5 (6), S001 56 (59), S017 78
  (79), S025 261 (263), C011 1 (2), C012 23 (24); no finding in a touched
  file that was not already there. S008 19 = baseline 19, no touched-file
  finding (`_generate_reply` untouched). No baseline was updated.
- `ruff check <touched .py> --select I001`: clean after 1be7319e.
- Contract: `contracts/sdk-public-api.json is current at eadefa3f… (vidbyte-sdk 0.2.1, 630 exports).`
- Semgrep `.semgrep/typed-mapping-boundary-policy.yml`:
  `Ran 1 rule on 921 files: 0 findings.` `exit=0`.
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: lint,
  compileall, and the three check scripts pass; pytest ends
  `1 failed, 4674 passed, 13 skipped in 37.16s` then
  `CI failed: Command failed with exit code 1: … -m pytest`. The one failure
  is the blocker test.
- `python scripts/run_ci.py --stage package` (no PYTHONPATH):
  `Installed vidbyte-sdk 0.2.1 passed smoke checks.` `CI passed.`
- Push: `8e51f8ab..8f1fc73e  HEAD -> feat/agent-output-connectors`;
  `gh pr view 882`: `draft=true head=8f1fc73edfa33595291b912b252ed4d7146ceaa3`.

## Open items

- The blocker test above.
- §12.5 asks for `ci.yml` and `static-policy.yml` to be dispatched on the
  branch after the push; left to the orchestrator, because this stage's
  procedure does not include a workflow dispatch. The source job would show
  the same one red test.
- Live checks L-1…L-15 (spec §15) need real credentials; none was run.

## Tricky parts

- `S009` (mypy) regressed by one on `webhook.py` (`dict` vs `Mapping` on the
  payload branch); fixed with a declared `body: object` and the existing
  `isinstance` check.
- The `--rule <ID> --all` text output prints no findings for an IMPROVED
  rule; the seven NFR-6 checks were read from `--format json` and compared
  with the same run on the S2_HEAD tree: every finding in a touched file
  (A002 on `errors/base.py` and `transport.py`, S001 F401 in
  `vidbyte/__init__.py`, S024/A007 in `transport.py`, S062 in
  `errors/base.py`) already existed there, with the same symbols.
- `generate-sdk-public-api.py` only checks its own inputs for a dirty tree,
  so the orchestrator's modified `pipeline.md` did not block it.
