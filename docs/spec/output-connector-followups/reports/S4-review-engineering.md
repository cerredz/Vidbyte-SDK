LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the delivery paths are correct (reads before one write, signature over the sent bytes, marker and Telegram neutralization, single-worker summary). One Major input-validation gap can fail every send with the secret on the exception chain. Two test-pack gaps let a regression of a security invariant (INV-18) and a P0 invariant (INV-1) pass all 660 tests.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- INV-8 holds end to end. `webhook.py:87-89` serializes once, signs `"{id}.{ts}." + wire`, and sends the same object as `content=`. `_signed_headers` runs once per send, so the 429 retries in `HttpTransport.request` reuse the same bytes and the same three headers. `_send_once` (`transport.py:82-88`) adds no content-type to `content=`.
- INV-1, D-15 and D-16 are correct in `github.py:114-138` and `github_api.py:34-44`. The marker is quoted before the cut and the own marker is appended after it (total ≤ 65,536). Replacing `<!-- vidbyte:` with `<!-- vidbyte-quoted:` cannot create a new occurrence across a boundary. Every read failure returns before any write. The page loop is exactly 1..10.
- Job summary (`github_job_summary.py`): a module-level `ThreadPoolExecutor(max_workers=1)` and `run_in_executor`. When the deadline passes, a queued (not started) append is cancelled through `wrap_future`, and a running one finishes, as EC-46 states. The fixed concurrency test (3d974a1f) is now sound and deterministic: 8/8 repeated passes, and it killed an 8-worker mutation 10/10.
- The `OutputResponses` move is byte-for-byte the base `_error_code`/`_link`. `read` and `_write` both set and reset the ContextVar log guard in `finally`, so a deadline cancel cannot leave the filter on.

FINDINGS (ranked, most severe first, max 15)
R-E1 [Major] [security / error handling] vidbyte/lib/outputs/base.py:170 — `OutputArguments.headers` accepts header values that httpx/h11 cannot send, so the error comes at every send instead of at construction, and one path puts the whole secret on `OutputDeliveryError.__cause__`
  Evidence: the only value check is `if not isinstance(text, str) or any(mark in text for mark in "\r\n\x00"):`. Scratch probe `probe_headers.py` (MockTransport; the error comes from httpx's own header encoding, before any transport): `WebhookOutput(url=…, headers={"Authorization": "Bearer S3CRET-token"})` constructs, then `OutputDispatcher.deliver` → `RAISED OutputDeliveryError [('failed', 'unexpected:UnicodeEncodeError')]`, `S3CRET in repr(cause): True` (same for a smart quote U+2019). Loopback probe `probe_h11.py` through the real httpx/httpcore/h11 stack: a trailing space, `{"authorization": "Bearer S3CRET "}` → `ProviderRequestError | excerpt: Illegal header value b'Bearer S3CRET '`, which `_write` turns into FAILED `network`. `{"content-length": "3"}` → a raw `h11._util.LocalProtocolError: Too much data for declared Content-Length` escapes `HttpTransport.request` (it catches only `httpx.RequestError`) → `unexpected:LocalProtocolError`. The same encoding failure hits the new header-auth credentials: `GitLabIssueOutput(project="acme/shop", token="glpat-S3CRET‑token")` → `[('failed', 'unexpected:UnicodeEncodeError')] | S3CRET in repr(cause): True` (`OutputArguments.credential`, base.py:46-52, checks only non-blank).
  Failure: a key pasted with a non-breaking space or hyphen, a smart quote, or a leading or trailing space (common when copying from rendered docs) builds fine, then fails every run:
  - non-ASCII → `unexpected:<Type>`. The dispatcher reserves that code for connector bugs. The UnicodeEncodeError chained at dispatcher.py:80 (`raise … from first_exception`) carries the full value in `.object`, so `repr(err.__cause__)`, debuggers, and error trackers that serialize exception args show the secret.
  - whitespace → FAILED `network`, which the resend caution says "may already have been delivered", so the user debugs the network.
  - `content-length` / `transfer-encoding` → unexpected / network.
  The INVALID_HEADERS table (`test_output_connectors_webhook_options.py:97`) has none of these cases.
  Smallest fix: in `OutputArguments.headers`, require each value to fully match an ASCII field-value constant, e.g. `OUTPUT_HEADER_VALUE_PATTERN = r"(?:[\x21-\x7e](?:[\x20-\x7e\t]*[\x21-\x7e])?)?"`. Refuse the framing names `content-length`, `transfer-encoding`, `host`, and `connection`. Keep the existing message shape (header name only, never the value). Add rows to INVALID_HEADERS. Optionally refuse non-ASCII in `credential` with a message that names only the parameter.
  Spec IDs: INV-11, INV-3, NFR-5, T-1, AC-10, EC-16

R-E2 [Major] [test quality] tests/features/agent_output_connectors/test_output_connectors_rendering.py:201, :229-238 — INV-18's "every `![`" is checked only with inputs that hold a single `![`, so a first-occurrence-only neutralization passes the whole pack
  Evidence: scratch plugin `mut_plugin.py` (MUT=telegram_media_once) replaces `TelegramOutput.send` at runtime with `.replace(TELEGRAM_MEDIA_PREFIX, TELEGRAM_MEDIA_REPLACEMENT, 1)`. `MUT=telegram_media_once PYTHONPATH="$(pwd);<scratch>" python -m pytest -q -p no:cacheprovider -p mut_plugin tests/features/agent_output_connectors` → `660 passed in 5.09s`. The sanity test confirmed the mutation was live. HOSTILE_BODY and every row of the neutralization table hold exactly one `![` (`!![x]` also holds one).
  Failure: a refactor to `re.sub(..., count=1)` or `str.replace(..., 1)` ships. A reply such as "see ![](https://ok/a.png) and ![](https://evil/b.pdf)" then has its second media block fetched and posted by the bot (T-2(c)), and no test fails. The test plan's row for AC-5/INV-18 claims this risk is covered.
  Smallest fix: add a row to `test_telegram_neutralization_changes_only_tag_starts_and_media_brackets` with two media blocks and two tags, e.g. `"![a](https://e.com/1.png) <b>x</b> ![b](https://e.com/2.pdf)"` → `"!［a](https://e.com/1.png) ＜b>x＜/b> !［b](https://e.com/2.pdf)"`.
  Spec IDs: INV-18, EC-44, T-2(c), AC-5

R-E3 [Minor] [test quality] tests/features/agent_output_connectors/test_output_connectors_update_in_place.py:209-233 — read failures are tested only on the first read, so a sticky send that treats a failed later page as "end of list" and POSTs passes all tests
  Evidence: `MUT=sticky_later_read_failure_ignored`, which replaces `_sticky_comment` so that on page ≥ 2 a failed read does `break` and then POSTs → `660 passed in 5.07s`. Every READ_FAILURES row scripts the failure as the first answer on READ_FRAGMENT.
  Failure: page 1 is full (100 comments), and page 2 (which holds the marked comment) returns 500 or 429×3. The send POSTs a second marked comment and reports SENT, not the page-2 read's FAILED receipt, against INV-1 ("A read failure returns that read's FAILED receipt and makes no write").
  Smallest fix: one more parametrized case that scripts `_page(1)` and then the failure on READ_FRAGMENT, and asserts the receipt code and the wire `["GET", "GET"]` with no POST.
  Spec IDs: INV-1, AC-28, EC-38

R-E4 [Minor] [error handling] vidbyte/lib/outputs/webhook.py:78-87 — a `payload=` that returns a Mapping other than a dict passes the connector's own check, then fails `json.dumps` as `unexpected:TypeError`
  Evidence: `if not isinstance(body, Mapping):` accepts it. Then `json.dumps(body)` (signed path, :87, or `transport.py:85`, unsigned path) raises. Probe `probe_misc.py`: `payload=lambda reply, content: MappingProxyType({"text": content.title})` → `('RAISED', [('failed', 'unexpected:TypeError')], 'TypeError')` for both the unsigned and the signed path.
  Failure: a developer follows the published signature `Callable[[AgentMessage, OutputContent], Mapping[str, object]]` (FR-14, §8.5) and returns a frozen or proxy mapping. Every send is FAILED `unexpected:TypeError`, a code the dispatcher reserves for connector bugs.
  Smallest fix: after the Mapping check, `body = dict(body)`, so a top-level Mapping always serializes. Alternatively, have the TypeError message say "must return a dict".
  Spec IDs: FR-14, EC-18, EC-19

R-E5 [Minor] [error handling] vidbyte/lib/outputs/github_job_summary.py:65-68 — only `OSError` becomes `file_error`, so a reply with a lone surrogate fails the summary as `unexpected:UnicodeEncodeError`
  Evidence: `except OSError:`. Probe `probe_misc.py`: `GitHubJobSummaryOutput(path=<tmp file>)` given the reply `"Report\n\nbad \ud800 char"` → `('RAISED', [('failed', 'unexpected:UnicodeEncodeError')], 'UnicodeEncodeError')`. The HTTP connectors send the same text without error, because `json.dumps` escapes it.
  Failure: a model reply decoded with a lone surrogate (a split emoji) delivers everywhere except the job summary. There it reports an "unexpected" connector bug instead of the documented file outcome.
  Smallest fix: `except (OSError, ValueError):` → FAILED `file_error`. UnicodeEncodeError and "embedded null character" are both ValueError.
  Spec IDs: D-18, EC-30, FR-25

VERIFIED CLAIMS
- S3: "`post` and `patch` share one private `_write`; `json_body` and `content` together raise before any I/O". HELD: `delivery.py:63-73,111-150`; `transport.py:58-59` raises before the client is created; the AC-15 test passes.
- S3: "Sticky pages stop at the first marked comment or a short page, at most 10 pages". HELD: `github.py:123-136` (`range(1, 11)`); AC-29 is an exact 10-GET wire list. By reasoning, a `range(1, 10)` bound and a `range(1, 12)` bound are both caught (exact list; an extra request gets "no scripted response").
- S3: "the signed body is `json.dumps(body).encode()`, sent as `content=`, so a 429 retry repeats the same bytes and headers". HELD: `webhook.py:87-89`. The tests recompute the HMAC over the recorded `content`, so signing re-serialized JSON instead of the sent bytes would be caught.
- S3: "job summary on `ThreadPoolExecutor(max_workers=1)` through `append_text(create_parents=False)`; OSError → file_error". HELD. Non-OSError failures escape (R-E5).
- Brief: "the concurrency test fixed in 3d974a1f is sound and deterministic". HELD: 8/8 repeated runs pass. With `_SUMMARY_EXECUTOR` swapped for 8 workers it failed 10/10. The snapshot is taken before the read-back open.
- S3: "`OutputResponses.error_code`/`.link` moved unchanged". HELD: identical to base `_error_code`/`_link` (`git show 336d6c78:vidbyte/lib/outputs/delivery.py`).
- D-16 test "neutralize before truncation, marker after". HELD by reasoning: appending the marker before the cut fails `endswith(MARKER + STICKY_SUFFIX)`, and quoting after the cut fails `len == 65_536` (`update_in_place.py:194-204`).
- INV-7 "Typefully never sends publish_at/plan_at/share". HELD: `typefully.py:48-50`; the test asserts the whole body.
- Spec INV-11 "every invalid argument raises ConfigurationError at construction". DID NOT HOLD for header values or credentials (R-E1).
- Test plan row AC-5/INV-18 "covered". PARTIALLY: a first-occurrence-only mutation survives (R-E2).
- Test plan AC-28/INV-1 coverage. PARTIALLY: only the first read's failure is exercised (R-E3).
- Orchestrator: "pack 660 passed". HELD: reproduced `660 passed in 5.04s`.

COMMANDS RUN
- `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors </dev/null` → `660 passed in 5.04s`
- `PYTHONPATH=<worktree> python <scratch>/probe_headers.py` → `nbsp-in-value RAISED OutputDeliveryError [('failed', 'unexpected:UnicodeEncodeError')]` / `S3CRET in repr(cause): True | in str(cause): False`. ctrl-0x01, del-0x7f, and content-length-override show `RECEIPTS [('sent', None)]` under MockTransport, which does not validate.
- `PYTHONPATH=<worktree> python -I -c "import h11 …"` → `'Bearer S3CRET\x01x' accepted by h11`; `' lead' h11 refuses: Illegal header value b' lead'`
- `PYTHONPATH=<worktree> python <scratch>/probe_h11.py` (loopback socket only) → `ProviderRequestError | excerpt: Illegal header value b'Bearer S3CRET ' | secret in excerpt: True`
- Same probe with `{"content-length": "3"}` → `h11._util.LocalProtocolError: Too much data for declared Content-Length`, raised from transport.py:67 → :91, not wrapped. With `{"transfer-encoding": "chunked"}` → `ProviderRequestError | excerpt:`
- `PYTHONPATH=<worktree> python <scratch>/probe_cred.py` → `[('failed', 'unexpected:UnicodeEncodeError')] | S3CRET in repr(cause): True`
- `PYTHONPATH=<worktree> python <scratch>/probe_misc.py` → `payload MappingProxyType, unsigned ('RAISED', [('failed', 'unexpected:TypeError')], 'TypeError')`, the same for signed; `job summary lone surrogate ('RAISED', [('failed', 'unexpected:UnicodeEncodeError')], …)`; GitLab hosts `localhost`, `127.0.0.1`, `gitlab.com:65535` accepted, `gitlab.com.` refused
- Mutation 1: `MUT=telegram_media_once … pytest -p mut_plugin tests/features/agent_output_connectors` → `660 passed in 5.09s` (survived)
- Mutation 2: `MUT=sticky_later_read_failure_ignored …` → `660 passed in 5.07s` (survived)
- Mutation 3: `MUT=summary_many_workers …::test_job_summary_concurrent_appends_run_off_the_loop_one_after_the_other`, 10 runs → `survived=0 killed=10`
- Mutation sanity: `pytest -p mut_plugin <scratch>/test_mut_sanity.py` for each MUT → `1 passed`, so each mutation was live
- Determinism: `pytest … test_output_connectors_new_destinations.py -k job_summary`, 8 runs → `pass=8 fail=0`
- `git diff 336d6c78...d5611f25 -- <files>`, `git show 336d6c78:vidbyte/lib/outputs/{delivery,jira}.py` (read-only comparisons)
