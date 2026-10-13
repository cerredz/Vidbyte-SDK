# S4 findings verifier, re-review round 1

**Stage:** S4 findings verifier, scoped to the post-repair re-review round 1 (`reports/S5-rereview.md`).
**Worktree:** `feat/native-grok-opencode-meta-hosts` at HEAD `77e18983`. The code is identical to af3e05e8.
**Spec:** r8.
**Output:** I appended `## Post-repair re-review round 1 — verified findings` to `review.md` and added one sentence to its Verdict line. I made no source edits and no commits.

## Outcome

| Re-review row | Re-reviewer severity | Verdict | review.md row | Spec change needed |
|---|---|---|---|---|
| R-RR1 | Major | **CONFIRMED Major.** It is stronger than reported. | R-16 | no (INV-14 spec.md:261, §8.5 spec.md:1094) |
| R-RR2 | Major | **DOWNGRADED to Minor** (follow-up). | R-M10 | yes, a spec gap (wording below) |
| R-RR3 | Major | **CONFIRMED Major.** | R-17 | no (§9.1 spec.md:1385, INV-6 spec.md:234-236) |
| R-RR4 | Minor | **CONFIRMED Minor** (trivial). The count is slightly higher than reported. | R-M11 | no |

Totals: 0 Blockers, 2 Majors and 2 Minors confirmed; 0 refuted; 1 downgraded.

## Method

I wrote my own scratch tests under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/2526e8d1-a2d5-407e-9242-3458f24f4f3a/scratchpad/s5-rereview-verifier/`:
- One folder per pack: `grok/`, `muse/` and `opencode/`.
- Each folder has a `conftest.py` shim that loads the pack's own `conftest.py` with `importlib.util.spec_from_file_location`, registers it in `sys.modules` before `exec_module`, and re-exports its globals. The real fakes therefore run unchanged: `fake_grok_peer.py` and `fake_muse_peer.py` as child processes, and `FakeOpencodeServer` through `httpx.MockTransport`.
- Every Grok host was built through `make_grok_host`, which always sets `grok_command` to the fake. No real `grok`, `opencode`, `muse` or `wsl.exe` ran. (A real `grok` is on PATH at `/c/Users/422mi/.grok/bin/grok`, and it was never resolved by a host.)
- Each test has a control that shows the check is not vacuous.

The run command, from the worktree root:
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q -s <scratch test>`.

`git status --porcelain` was empty before I wrote to `review.md`. After that it showed only `M docs/spec/native-grok-opencode-meta-hosts/review.md` (and this report).

---

## R-RR1: INV-14 case folding misses vendor-returned ids. CONFIRMED Major (R-16)

### Code read in full
- `hostkit/turns.py`:
  - `reserve` (:47), `bind_session` (:62), `release` (:79), `is_session_busy` (:92) and `_finish` (:105) all key `_busy_sessions` by the exact string.
- `grok/host.py`:
  - `spawn_grok_session` binds `self._wire.parse_session_id(created)` verbatim (:215-216).
  - `continue_grok_session` (:279) and `fork_grok_session` (:322) lower-case the caller's id after `require_uuid`.
  - The fork busy check is `is_session_busy(lower)` (:328).
- `grok/wire.py`: `_SESSION_ID_PATTERN = r"^\S+$"` (:54). `parse_session_id` (:208-213) neither lower-cases nor checks for a UUID.
- `muse/host.py`:
  - spawn binds `session.session_id` verbatim (:243);
  - continue (:275) and fork (:311, :316) lower-case the caller's id.

### Spec reading
INV-14 (spec.md:261) says:
- "every comparison of them ignores letter case, in this busy check";
- "An id and its upper-cased form name the same session".

§8.5 (spec.md:1094) puts the rule on `NativeTurnTable.reserve`: "Grok and Muse session ids match ignoring letter case". §12.3 rows 30 and 41 (spec.md:1914, 1925) repeat it for the busy check.

The implementation folds case only at the entry points that take a caller's id. The spawn bind does not fold, so the invariant holds only if the vendor always returns lower case. The re-reviewer read the spec correctly.

### Execution (`grok/test_v_grok.py`, `muse/test_v_muse.py`)
```
[control] bound=5865db4e-eaaf-4aef-a6ba-20ad07241162 continue(same)=REFUSED grok.session_busy continue(upper)=REFUSED grok.session_busy agent_peers=1
[handle id] handle.session_id=ABCDEF01-2345-4678-89AB-CDEF01234567 continue(handle.session_id)=ACCEPTED second live turn session_id=abcdef01-2345-4678-89ab-cdef01234567 turn_id=0067b07619b64d31804e048335f51f08 agent_peers=2
[handle id] session/resume ids=['abcdef01-2345-4678-89ab-cdef01234567'] session/prompt ids=['ABCDEF01-2345-4678-89AB-CDEF01234567', 'abcdef01-2345-4678-89ab-cdef01234567']
[lower id] continue(abcdef01-2345-4678-89ab-cdef01234567)=ACCEPTED second live turn ... agent_peers=2
[fork] fork_grok_session(handle.session_id)=REFUSED grok.session_not_found
5 passed in 13.01s

[muse control] bound=0192f0c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f continue(upper)=REFUSED muse.session_busy
[muse handle id] handle.session_id=0192F0C4-5B6A-7C8D-9E0F-1A2B3C4D5E6F continue(handle.session_id)=ACCEPTED second live turn session_id=0192f0c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f peers 1->2
3 passed in 12.26s
```

### Where I go further than the re-reviewer
- **The caller does not need to change the id.** The re-reviewer continued with a hand-lower-cased id. Passing back the host's own `handle.session_id` (upper case) also starts a second live turn: continue lower-cases it, and the table holds the upper-case key. This is the ordinary way a caller uses the API.
- **Fork is affected too.** `fork_grok_session(handle.session_id)` passed the busy check and reached the session listing. It failed only because the fake's listing did not contain the id, raising `grok.session_not_found`. Muse fork has the same shape (`muse/host.py:311,316`), which I confirmed by reading the code, not by running it.
- **Both handles of one session carry different strings.** The spawn handle carries `ABCDEF01-…` and the continue handle carries `abcdef01-…`.

### Existing guard
None. Nothing lower-cases the id between `parse_session_id`, or `MuseWire.read_session_result`, and `bind_session`.

### Calibration
I keep it Major. INV-14 is explicit and was written in r8 for this exact failure, R-8, which was itself a confirmed Major: double spend and interleaved history on one session. The trigger depends on the vendor's casing. The fakes return lower case, and whether real Grok or Muse ever returns upper case is unverified. That limits how likely it is, but not whether it is a defect: the invariant should hold by construction, and a reviewer checking the R-8 fix finds the hole.

### Fix (no spec change)
Fold case inside `NativeTurnTable` when `self._harness` is GROK or MUSE. Use `session_id.lower()` as the `_busy_sessions` key in `reserve`, `bind_session`, `release` (from `_reserved`), `is_session_busy`, and `_finish` (from `entry[0].session_id`). opencode keeps exact keys.

Because the handle keeps the vendor's spelling, `lookup` (`entry[0] != handle`) is unaffected. This matches where §8.5 puts the rule and covers spawn, continue, fork and release in one place.

**Runner-up:** lower-case in `GrokWire.parse_session_id` and at the Muse spawn bind (`session.session_id.lower()`). This also satisfies INV-14, but the spawn handle's `session_id` becomes lower case. I would choose it over the table fold only if the spec author wants every handle in lower case.

### Test to add
See the R-16 row of "Tests to add" in review.md. It goes in `test_grok_host_session_id_case.py` (the R-8 file) and `test_muse_host_turns.py` (next to `test_continue_on_the_upper_cased_id_of_a_live_session_is_busy`, :330).

---

## R-RR2: child-session 404 skips the EC-158 abort. DOWNGRADED to Minor (R-M10, follow-up)

### Code read in full (`opencode/turn.py`)
- `_refresh_tree` (:236-256) calls `GET /session/{order[index]}/children` with `not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND` for **every** id it visits, including descendants (:251).
- `_count_failure` (:286-293) re-raises any code that is not counted.
- `abort_before_failing` (:184-198) returns early for any `OPENCODE_SESSION_NOT_FOUND` (:195).
- `OpencodeClient._status_error` (`opencode/client.py:128-155`) maps a 404 to the route's `not_found` code. Without an override it maps a 404 to `opencode.protocol_mismatch` (EC-58).
- `OpencodeHost._drive` (`opencode/host.py:751-766`) calls `abort_before_failing` in both `except` branches.

### Execution (`opencode/test_v_opencode.py`)
```
[child 404] outcome=opencode.session_not_found message='The opencode server does not know the requested session or message.'
[child 404] aborts=[] children walks=['ses_known0001', 'ses_child000']
[child 404] turn's own session still exists=True server status={'type': 'busy'} server turn done=False
[child 404] interrupt_opencode_turn was_running=False; continue again -> REFUSED opencode.session_busy
[control 500] outcome=opencode.api_error aborts=['ses_known0001']
[control EC-86] outcome=opencode.session_not_found aborts=[]
3 passed in 11.79s
```
The mechanism is exactly as described. The consequence is the same as R-6's: an orphaned server-side turn.

### Spec reading: does "the session" mean the turn's own session?
**Yes.**
- EC-86's trigger is "A watcher poll gets 404 for the session, because it was deleted mid-turn". It sits in the `wait_opencode_turn` table, whose handle names one session.
- EC-158's trigger is "a failure the host raised itself, not one the server reported **for the turn**", and its abort targets "the turn's session".
- A descendant's 404 says nothing about the turn's own session, so EC-158's purpose calls for the abort.

The spec does not, however, say which row a descendant's 404 belongs to:
- EC-154 says only "A failed `children` call counts as a failed poll (EC-87)".
- EC-87 says an uncounted failure ends the turn "with its own row's code".
- That row could be EC-86, read loosely, or EC-58: "a 404 on a route whose own table does not give 404 a meaning".

The implementer's reading, "any session_not_found is exempt", is the literal one. This is a **spec gap**.

### Why I downgraded it
1. **The trigger is a narrow race.** It needs a descendant (subagent) session, while the turn's own session survives, to be deleted inside the window of one tree walk. A walk runs only when a pending request names an unknown session. Once a child is deleted it no longer appears in the parent's `children` listing, so a deletion before the walk cannot cause the 404.
   - I assume, without having verified it on opencode 1.18.31, that opencode deletes a session's children before the session itself. If so, the most common deletion during a walk is the user deleting the turn's own session, and the outcome is correct by EC-86: `session_not_found` with no abort.
2. **Whether the server answers 404 at all is unverified.** The 1.18.31 OpenAPI (`scratchpad/research/opencode-1.18.31-openapi.json`) declares a 404 `NotFoundError` for `GET /session/{sessionID}/children`, but not for `…/diff` or `…/abort`, the two routes verified to answer 200 for a missing session. So the 404 is plausible, but the spec records no verified behaviour.
3. **Fixing it needs a design decision first.** One option skips the vanished descendant. The other ends the turn with `protocol_mismatch` and aborts. The second gives the caller the next step "check_opencode_ready", which misleads. Fixing it in the last repair round before the spec decides risks a mismatch between code and spec.
4. **The house style agrees.** It says to calibrate fear and not to spend caution "on theoretical races".

**Flip condition:** promote it to Major if deleting a subagent session during a live turn counts as a supported workflow, for example from the user's TUI on an attached server. The fix is then one site, `turn.py:251`, plus the spec sentence.

### Proposed spec wording (the smallest change that settles it)
- **EC-158 exemption:** replace "or a 404 for the session (EC-86, EC-90)" with "or a 404 for the turn's own session (EC-86, EC-90)".
- **EC-154:** append "A 404 from the `children` call of a descendant, not the turn's own session, means that descendant was deleted during the walk; the watcher leaves it out of the tree and goes on, and the poll does not fail."

**Recommended:** skip the vanished descendant. A deleted subagent session has nothing left to reject, so failing the parent turn for it is the wrong outcome for the caller.

**Runner-up:** "…is EC-58's 404 (`opencode.protocol_mismatch`), so EC-158's abort is sent". In code this is `not_found=… if order[index] == self._session_id else None`, but the next step misleads.

**Test (follow-up):** monkeypatch `fake_opencode.on_session_children` to return `fake_opencode.not_found()` for a child id, as `opencode/test_v_opencode.py::test_child_children_404_fails_the_turn_with_no_abort` does. Under the recommended wording, assert that the turn keeps running and later completes after `release_turn`. Under the runner-up, assert `protocol_mismatch` and one abort for the turn's session.

---

## R-RR3: Grok and Muse approval titles are not scrubbed. CONFIRMED Major (R-17)

### Code read in full
- `grok/turn.py:177`: `title=permission.title[:NATIVE_APPROVAL_TITLE_MAX_CHARS]`.
- `muse/turn.py:211`: `(request.tool_name or request.approval_id)[:cap]`.
- `muse/turn.py:235`: `request.tool_name[:cap]`.
- `opencode/turn.py:268`: `self._errors.scrub(...)[:cap]`.
- Both drivers already hold `self._errors` (`grok/turn.py:50`, `muse/turn.py:61`).
- `NativeErrorFactory.scrub` (`hostkit/errors.py:62-73`):
  - returns blank text unchanged;
  - otherwise runs `HarnessRedactor.safe_error_message` (`vidbyte/harnesses/serialization.py:84-94`), which replaces credential assignments only, so plain titles come back unchanged.
- `MuseApprovalRequest.tool_name` and `GrokPermissionRequest.title` are type-checked only (`lib/dataclasses/muse.py:246`, `lib/dataclasses/grok.py:264`), so any string reaches the title.

### Spec reading
- §9.1 `NativeApprovalDecision` (spec.md:1385): "`title` may be empty, ≤ 200, scrubbed". The record is shared by all three hosts.
- INV-6 (spec.md:234-236): no secret appears in "`ToolResult` output", and "Any vendor text a host surfaces has been through `HarnessRedactor.safe_error_message`".

The finding rests on explicit text.

### Execution
```
[title] recorded title contains secret: True
[title] tool output contains secret: True
[title] scrub(title) = 'Run: export OPENAI_API_KEY=<redacted> && make deploy'
[title] recorded       = 'Run: export OPENAI_API_KEY=<SECRET> && make deploy'
[muse title] (request_kind, secret in title) = [('muse.approval', True), ('muse.user_input', True)]
```
- The secret was synthetic: `sk-proj-FAKE` plus `uuid4().hex`, built at run time.
- The Grok case ran through the real `wait_grok_turn` tool (`GrokTools`), so the value reached ToolResult output.

### Existing guard
None. `NativeResultEncoder.encode` and `plain` (`vidbyte/tools/builtins/native_host_tool.py:117-148`) serialise the record verbatim.

### Calibration
I keep it Major rather than Blocker. The user's weighted word from request.md §D was turned into "Secrets never appear in argv or errors", and a title sits in a result, not an error. The value is also one the vendor agent produced itself. The realistic channel is a Grok tool-call title that embeds a command line. Muse's `tool_name` is a tool name, which is unlikely to hold a credential, but the same field rule applies to it. R-9 aligned the cap across the three drivers and left the scrub unaligned. A reviewer would catch the gap, and the fix is three wraps.

### Fix (no spec change)
`self._errors.scrub(<title>)[:NATIVE_APPROVAL_TITLE_MAX_CHARS]` at the three sites: scrub first, then cap, as opencode does. `test_grok_host_turns.py:64` (`"Edit README.md"`) still holds.

---

## R-RR4: spec ids in header fields and docstrings. CONFIRMED Minor (R-M11, trivial)

I recounted with my own script (`count_header_ids_narrow.py` and `count_header_ids_section.py`). It reads the added lines of `git diff -U0 origin/main...HEAD -- vidbyte/` and the module docstrings parsed with `ast`.

**Letter-number ids** (EC, INV, AC, FR, NFR, D, T, Q, A, G, W): 87 header lines outside RELATED DOCS and TESTS, across 45 files.

| Header field | Lines |
|---|---|
| ARCHITECTURE NOTE | 30 |
| WHAT NOT TO DO IN THIS FILE | 21 |
| KNOWN EDGE CASES | 21 |
| ROLE IN CODEBASE | 10 |
| FUNCTION INVENTORY | 3 |
| PURPOSE | 2 |

The re-reviewer counted 86; the difference of one is in KNOWN EDGE CASES and comes from the regex boundary.

**Counting `§` marks**, as R-14's own list did ("EC-/INV-/AC-/FR-/D-/T-/§"), the total is 101.

**Docstrings:** two cite ids, not one.
- `muse/host.py:505`: "(D-14)".
- `opencode/wire.py:76`: "Builds one §9.1 record from one decoded opencode value."

**Fix:** strip the ids, keep the plain-English reason, and leave RELATED DOCS and TESTS unchanged, as f067088d did for comments. This is text only.

The two docstrings and the module headers change `__doc__` and the AST constant. I grepped the four packs and `lint/` for `__doc__`, `getdoc` and `get_docstring`, and no `.py` file matched (only `.pyc` caches did). A001 checks that the header fields exist, and the strip keeps every field.

---

## Disagreements with the re-reviewer
1. **R-RR1 is reached through ordinary use.** It needs no hand-lower-cased id, because passing back `handle.session_id` is enough, and fork is affected too.
2. **R-RR2 severity.** I agree with the mechanism and with the reading that EC-158's exemption is about the turn's own session. I disagree on severity: it is a narrow race, the spec does not say which row a descendant's 404 belongs to, and the fix needs a design decision. I record it as Minor with a follow-up, the spec wording above, and a flip condition.
3. **R-RR4 counts.** There are 87 lines, or 101 counting `§`, and two docstrings, not one. These are trivial differences.

I agree with R-RR3 as written.

## Fix interactions for the repair agent
- **R-16** touches only `hostkit/turns.py` under the recommended fix. It is independent of R-17 and R-M11.
- **R-16 and opencode.** Do not fold case for opencode: its `ses…` ids are case-sensitive vendor ids (INV-14). The table already knows its harness through `self._harness`.
- **R-17** touches the same lines R-9 edited (`grok/turn.py:177`, `muse/turn.py:211,235`). Keep `NATIVE_APPROVAL_TITLE_MAX_CHARS` as the cap after the scrub.
- **R-M11** edits the headers of `grok/turn.py`, `muse/turn.py`, `hostkit/turns.py` and others. If it is done in the same iteration, apply it after the R-16 and R-17 code edits to avoid conflicts. Keep every comment line at 72 columns or fewer (R-15).

## Commands run (final lines)
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q -s <scratch>/grok/test_v_grok.py` gave `5 passed in 13.01s`.
- `… <scratch>/muse/test_v_muse.py` gave `3 passed in 12.26s`.
- `… <scratch>/opencode/test_v_opencode.py` gave `3 passed in 11.79s`.
- `python <scratch>/count_header_ids_narrow.py` gave `outside RELATED DOCS/TESTS: 87`, `files: 45`, and one docstring at `muse/host.py:505`.
- `python <scratch>/count_header_ids_section.py` gave `outside RELATED DOCS/TESTS: 101` and two docstrings (`muse/host.py:505`, `opencode/wire.py:76`).
- A read-only OpenAPI probe of `scratchpad/research/opencode-1.18.31-openapi.json` showed:
  - `/session/{sessionID}/children get ['200','400','404']`;
  - `/diff get ['200','400']`;
  - `/abort post ['200','400']`.
- `git status --porcelain` was empty before my `review.md` edit. `git diff -U0 review.md` shows 1 line replaced (the Verdict, extended by one sentence) and 31 lines added.
- I made no commits, installs, pushes, `git add` or `git stash`, and read no credential file.
