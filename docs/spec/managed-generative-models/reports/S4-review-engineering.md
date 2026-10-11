LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — The code follows r5 on every money path and key path I probed. The one real gap is in the test pack: the S064 cumulative retry deadline (INV-10, EC-38) has no test, and five plausible bugs in it pass all 32 tests.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Raise shape.** `_send` (`vidbyte/lib/http/vidbyte_gateway.py:198-206`) keeps only the exception *type*, never the instance. Every `ProviderRequestError` is raised in `request` after all `except` blocks have closed (`:190`), so no failure path leaves the response body, the inner `response_excerpt`, or exception text reachable. The canary and key scans over `str`, `details` and the formatted traceback all pass, and the "error is truthy" mutation is caught.
- **One key per call.** `TextModelRunner.arun` builds a new `VidbyteGatewayTransport` for each call (`vidbyte/lib/runners/text.py:77-84`), and the key is minted inside `request` (`vidbyte_gateway.py:156`). Concurrent calls therefore never share a key, and retries never change it: the "fresh key per attempt" mutation fails 4 tests. The inner `retry_count` stays at the `HttpTransport` default of 0: the `retry_count=2` mutation fails 6 tests.
- **The deadline loop matches r5 exactly** (`vidbyte_gateway.py:168-184`). Under a fake loop clock, with every attempt answering 502 after `step` seconds:
  - step 0 s → 3 POSTs; 300 s → 3; 600 s → 2; 629.4 s → 2; 629.5 s → 1 (boundary: `>=` stops); 629.8 s → 1.
  - Every attempt gets the full 630.0 s.
  - The messages count re-sends correctly (2/1/0, and "did not re-send" at 0).
  - The `for … else` counting is correct. Do not "simplify" it.
- **Key selection fails closed.** None of these sends a request: a malformed `VIDBYTE_API_KEY`, an `sk-` key placed in `VIDBYTE_API_KEY`, a `vb_live_` key with a custom endpoint, or a `vb_live_` key with an unmanaged provider. Adapters only ever see `VIDBYTE_MANAGED_KEY_PLACEHOLDER`. BYOK is unchanged: the AC-3 goldens pass, and the full suite is also green with `VIDBYTE_API_KEY` set in the environment.

FINDINGS (ranked, most severe first, max 15)

R-E1 [Major] [test quality] tests/features/sdk_managed_text/test_managed_text_failures.py:94-110 (whole pack; code under test vidbyte/lib/http/vidbyte_gateway.py:169,177,182-184) — No test drives the event-loop clock, so the r5 cumulative retry deadline (INV-10, EC-38, §9.2 "Retries" and the "did not re-send" wording) is untested. The deadline branch, the per-attempt "never shortened" rule and the re-send count in messages can all break without any test failing.
  Evidence:
  - `grep -n deadline tests/features/sdk_managed_text/*.py` finds nothing.
  - The pack was written against r4 (test-plan.md header: "Spec … r4"), before r5 added the deadline. Yet test-plan.md:20 lists EC-38 as covered by `test_gateway_errors_raise_credential_safe_errors_after_one_post_or_three_for_a_502`. That test never moves the clock: `BackoffRecorder` sleeps 0.
  - I re-executed mutated module copies in place through a scratch pytest plugin (no worktree edits), then ran `MUT=<m> PYTHONPATH="$(pwd);<scratch>" python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider -p mutplug`. Each of these still reports `32 passed`:
    - `no_deadline`: the `or loop.time() + retry_wait >= deadline` check deleted;
    - `deadline_gt`: `>=` changed to `>`;
    - `deadline_after_first`: the deadline re-taken after the first attempt, which allows a worst case of about 3× the timeout;
    - `resends_off_by_one`: the `for … else` count set to `JEV_DEFAULT_RETRY_COUNT - 1`, so messages say "re-sends in this call: 1" after two re-sends;
    - `shorten_attempt`: retry attempts given `deadline - loop.time()` instead of the full timeout, which INV-10 forbids.
  - `shorten_attempt` survives only because of this host's clock. The assertion `self.assertEqual(request["timeout_seconds"], 630.0)` (`:110`) is meant to catch it, but `time.get_clock_info('monotonic')` here is `GetTickCount64(), resolution=0.015625`. A fast test sees `deadline - loop.time() == 630.0` exactly, so the assertion passes on Windows and would fail only on a high-resolution (Linux) clock.
  - For contrast, the other mutations are caught: `retry_503` (2 failed), `retry_network` (2), `error_truthy` (1), `inner_retry` (6), `fresh_key_per_attempt` (4), `nan_floor_order` (1), `runner_key_placeholder` (8), `fallthrough_any_provider` (1), `env_vb_not_managed` (1).
  Failure: Three outcomes go undetected:
  - **The deadline check is lost.** Lint S064 sees only the comparison's shape, so the check could later be removed or moved. A slow 502 at the gateway's 600 s deadline (EC-38) would then get two re-sends instead of at most one. Each re-send forwards upstream again (the claim was released), so Vidbyte pays the provider up to 3 times and the caller waits about 32 minutes instead of about 21. The suite stays green.
  - **The re-send count is wrong.** The error then misreports how many same-key re-sends a possibly billed call made, and §9.2 rows 3, 5 (409, 502) and 6 bind that number.
  - **An attempt is cut short.** Its timeout fires while the gateway is still finishing a call it bills, which INV-10 exists to prevent. On Windows the pack cannot see this.
  Smallest fix: Add one test to the pack; no existing test needs editing.
  - Patch the gateway module's `asyncio` name with a fake clock: `patch("vidbyte.lib.http.vidbyte_gateway.asyncio", new=SimpleNamespace(get_running_loop=lambda: clock, sleep=clock.sleep))`, where the scripted inner transport advances `clock.t` by `step` on each call.
  - Assert, for a call that answers 502 every time:
    - step 0 → 3 POSTs with message "re-sends in this call: 2";
    - step 600 → 2 POSTs and "re-sends in this call: 1";
    - step 629.5 → 1 POST, no sleep, and the "did not re-send" wording (this is the exact boundary, where `>=` must stop);
    - every attempt has `timeout_seconds == 630.0`.
  - This kills all five surviving mutations on every platform. Then update test-plan.md:20 so EC-38 points to the new test.
  Spec IDs: INV-10, INV-16, EC-38, D-10, §9.2 Retries and rows 3/5/6 (re-send count), AC-27 (per-attempt timeout)

R-E2 [Minor] [failure modes] [scope-adding] vidbyte/lib/http/vidbyte_gateway.py:201 → vidbyte/lib/http/transport.py:46 — The 630 s floor also applies to the TCP connect and pool phases, so an unreachable gateway host makes each managed call hang for 10.5 minutes before failing, even though nothing can have been billed.
  Evidence:
  - `_send` passes the floored `timeout_seconds` to `HttpTransport.request`, which builds `httpx.AsyncClient(timeout=timeout_seconds, …)`.
  - `python -c "import httpx; t=httpx.Timeout(630.0); print(t.connect, t.read, t.write, t.pool)"` prints `630.0 630.0 630.0 630.0`.
  - D-9's reason for the floor ("the gateway may still complete and bill") covers only the read phase. A request that never connected never reached Vidbyte.
  Failure: When the gateway host blackholes packets (a firewall dropping SYNs, a broken corporate proxy, or a dead route during EC-26), every managed call blocks for up to 630 s on connect. It is then raised as row 1, whose message wrongly says Vidbyte "may already have billed the call". BYOK callers who used the 60 s default used to fail in 60 s. Agent stage timeouts of 120 s cancel first, so users see a timeout and not a cause.
  Smallest fix: This is a follow-up outside §12.3. Let `HttpTransport.request` accept an `httpx.Timeout`, or a separate connect timeout, and have the gateway transport pass a short connect timeout with the 630 s read timeout. It needs a new constant and a change to the transport signature, neither of which the spec contains.
  Spec IDs: INV-10 (intent), EC-26; follow-up for the user

R-E3 [Minor] [observability] [scope-adding] vidbyte/lib/http/vidbyte_gateway.py:174-190 — Same-key re-sends of a possibly billed call leave no trace an operator can use: a retried success looks identical to a first-try success, and a failure gives no Idempotency-Key to correlate with the backend's replay and claim rows.
  Evidence:
  - `lib/http` and `lib/runners` have no logger: `grep -rn "logger\|logging.getLogger" vidbyte/lib/http/ vidbyte/lib/runners/` returns nothing.
  - On success the transport returns the last inner response unchanged (`:186-187`), so `HttpResponse.attempts` is 1 even after 3 POSTs.
  - The raised error carries only `provider` and `status_code` (`:190`). The 409 message says the call "may still complete and be billed", but the key needed to look up that claim is discarded.
  Failure: A deploy-time storm of edge pages (EC-15), each re-sent twice, is invisible on the client. When a user disputes a bill after the EC-37 409 error, support cannot match the SDK's error to the backend's claim and replay row.
  Smallest fix: This is a follow-up; INV-12 requires the `HttpResponse` to be returned unchanged, and the spec has no logging or `details` field. Two options: one `logging.getLogger(__name__).info` line per re-send giving status and attempt number (never the key or the body), and `details={"idempotency_key": key}` on managed errors. T-4 makes the key useless to another tenant, because the claim is scoped to the owner.
  Spec IDs: n/a (follow-up for the user)

VERIFIED CLAIMS:
1. S3 report and briefing: "pack 32 passed". HELD: `32 passed in 0.94s`.
2. S3 report: "full suite 3004 passed, 1 skipped". HELD: `3004 passed, 1 skipped in 18.07s`. Also HELD with a valid-format `VIDBYTE_API_KEY` set in the environment (`19.49s`), so no existing test depends on that variable being unset.
3. S3 report: "C017 0, C018 1, C019 0, C020 2, S064 4, SDK-LINT: PASS". HELD. Also S002 0, S019 5 and S008 19 are RATCHETED, and A007 (254) and S009 (345) are IMPROVED.
4. S3 report, deadline scratch check (step 0/300 → 3 POSTs, 600 → 2, 629.8 → 1, with the re-send wording). HELD, reproduced independently with my own fake-clock probe. Extra cases also behave per r5: 629.4 → 2, 629.5 → 1 (exact `>=` boundary), 409×3 → 3 POSTs, 502 then 200 → 2 POSTs and OK, and timeout 900 with step 700 → 2. Every attempt timeout equals the floored value.
5. AC-19 and S3 report: "production .py only under vidbyte/lib/". HELD. `git diff --name-only origin/main...a80f0660 -- '*.py'` lists 9 production files, all under `vidbyte/lib/`. Nothing changed under `vidbyte/providers/` or `vidbyte/agents/`.
6. Test plan row AC-10, test-plan.md:20: "EC-38" covered. DOES NOT HOLD. No pack test advances the clock, and the `no_deadline` mutation survives (R-E1).
7. Test plan row AC-27: "a timeout of 630 on each attempt" catches shortened attempts. HOLDS ONLY ON HIGH-RESOLUTION CLOCKS. The `shorten_attempt` mutation passes on this Windows host, where `resolution=0.015625` (R-E1).
8. Spec D-10 and §9.2: "each attempt leaves the inner retry_count at 0". HELD. The code passes no `retry_count`, and `HttpTransport.request` defaults to `retry_count: int = 0`. The `inner_retry` mutation is caught by 6 tests.
9. INV-10 and AC-9: a NaN timeout resolves to the floor. HELD. `text.py:53` is `max(VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS, config.timeout_seconds)`, and the `nan_floor_order` mutation is caught.
10. EC-24 and AC-20: one key per call, including under concurrency. HELD. A transport is built per call (`text.py:78-84`), and the `fresh_key_per_attempt` mutation is caught by 4 tests.
11. S3 report: "jev.py about 757 lines (< 1,000)". HELD: `wc -l` gives 757.

COMMANDS RUN:
- `git rev-parse --short HEAD`: `a80f0660`. `git status --short`: empty, so the worktree is clean.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider` → `32 passed in 0.94s`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=line` → `3004 passed, 1 skipped in 18.07s`
- `VIDBYTE_API_KEY=vb_live_zzzz…(32) PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=line` → `3004 passed, 1 skipped in 19.49s`
- `PYTHONPATH=$(pwd) python lint/run.py` → `C017 0 0 CLEAN`, `C018 1 1 RATCHETED`, `C019 0 0 CLEAN`, `C020 2 2 RATCHETED`, `S064 4 4 RATCHETED`, `SDK-LINT: PASS`
- Mutation sweep, one run per mutation: `MUT=<m> PYTHONPATH="$(pwd);<scratch>/s4eng" python -W ignore -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider -p mutplug`. The plugin re-executes a string-patched copy of the module source in the module's own namespace; it never writes to the worktree.
  - Survived (`32 passed`): `no_deadline`, `deadline_gt`, `deadline_after_first`, `resends_off_by_one`, `shorten_attempt`.
  - Caught: `retry_503` → `2 failed, 30 passed`; `retry_network` → `2 failed`; `error_truthy` → `1 failed`; `inner_retry` → `6 failed`; `fresh_key_per_attempt` → `4 failed`; `nan_floor_order` → `1 failed`; `runner_key_placeholder` → `8 failed`; `fallthrough_any_provider` → `1 failed`; `env_vb_not_managed` → `1 failed`.
- `PYTHONPATH=$(pwd) python <scratch>/s4eng/deadline_probe.py` (fake loop clock, driving `VidbyteGatewayTransport` directly):
  - `step=0.0 POSTs=3 … (re-sends in this call: 2).`
  - `step=600.0 POSTs=2 … (re-sends in this call: 1).`
  - `step=629.5 POSTs=1 … the SDK did not re-send it, because the call's 630 s timeout left no time for another attempt.`
- `python -c "import time;print(time.get_clock_info('monotonic'))"` → `implementation='GetTickCount64()', resolution=0.015625`
- `python -c "import httpx; t=httpx.Timeout(630.0); print(...)"` → `connect 630.0 read 630.0 write 630.0 pool 630.0` (httpx 0.28.1)
- `git diff --name-only origin/main...a80f0660 -- '*.py' | grep -v '^tests/'` → the 9 files under `vidbyte/lib/`
- `grep -n deadline tests/features/sdk_managed_text/*.py` → no output
- `grep -rn "logger\|logging.getLogger" vidbyte/lib/http/ vidbyte/lib/runners/` → no output
