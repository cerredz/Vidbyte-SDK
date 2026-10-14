LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every §12.3 row, FR, AC and the §4 snippet conform. One Major gap remains: a cancelled `launch_codex_subagents` leaves the turns it already started running, with no interrupt, no handle and no cap slot. One model-facing description also misstates what a review-target field does.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The §4 snippet, run verbatim at the §13 fake seam, prints exactly `True` / `completed The readme describes the SDK.` / `15 check_codex_ready`. Its requests run on the host's own executor thread (`codex-host_0`), and `thread/start` carries `approvalPolicy: on-request`, `approvalsReviewer: auto_review`, `sandbox: read-only` and `ephemeral: False` (AC-1, INV-28, NFR-9).
- The shared-file contract (FR-30, INV-40 to INV-42) holds byte for byte:
  - the 15 `FailureCode` members sit right after `CODEX_RUN_OPTION_UNSUPPORTED`, in spec order;
  - every export insertion is at its sorted spot;
  - the REPO_MAP and README texts match request.md §C;
  - the native `__init__` git blob hashes to `0374a2c8…f497a`;
  - `pyproject.toml`, `contracts/`, `lint/baseline.json` and `vidbyte/__init__.py` are untouched;
  - `CodexAgentError(next_step=)` is keyword-only, and its packet is unchanged when `next_step` is not given.
- Wire translation matches openai-codex:
  - `deny_all` → `approvalPolicy: never` with no reviewer, as in the SDK's `_approval_mode_settings`;
  - the full-access thread sandbox is `danger-full-access`, and the turn sandbox is `{type: dangerFullAccess}`;
  - `excludeTurns: true` on resume, and `lastTurnId`/`excludeTurns` on fork;
  - `config.agents` follows INV-30 exactly: the caller's own entry is kept, or the subagent translation is sent only when `subagents` is set;
  - the review-target shapes and enum wire values match `generated/v2_all.py`.
  Leave `CodexParamsTranslator` as it is.
- Partial failure and late acceptance work as specified for the non-cancel paths:
  - a launch whose 3rd `turn/start` fails sends exactly 2 `turn/interrupt` (asynchronously, through `_stop`), and its message ends "2 turns were started before this failure and were interrupted." (EC-52);
  - a failed `thread/name/set` or `turn/start` names the created thread (`… Thread: thr-1.`, EC-62);
  - a spawn or review cancelled in flight is registered and interrupted once (AC-32).

FINDINGS (ranked, most severe first, max 15)
R-C1 [Major] [conformance] vidbyte/harnesses/native/codex/host.py:421 — A cancelled launch leaves its already-started turns running, unowned by the toolset and outside the live-turn cap
  Evidence:
  - The diff at host.py:414-428 catches only `CodexAgentError`, so `_stop` never runs for a `CancelledError`:
    `started: list[CodexLiveTurn] = []` / `try:` / `for items in batch:` … `started.append(turn)` / `except CodexAgentError as exc:` / `if not started: raise` / `for turn in started: self._stop(turn, None)`.
  - The tool layer, vidbyte/tools/builtins/codex/delegation.py:69-74, releases the slots in `finally` and reaches `self._scope.own(handles)` only on success:
    `await self._scope.reserve(self._host, len(prompts), LAUNCH)` / `try: handles = await self._host.launch_codex_subagents(...)` / `finally: self._scope.release(len(prompts))` / `self._scope.own(handles)`.
  - Probe (inline script at the §13 fake seam):
    - setup: `CodexHostTools(host, max_live_turns=2)`; `launch_codex_subagents` with prompts `["one","two"]`; the 2nd `thread/start` is held and the tool task is cancelled;
    - output: `turn/start so far: 1` / `launch tool call cancelled` / `turn/interrupt sent after 1s: 0` / `thr-1/turn-1 status: inProgress` / `spawn tool 0 ToolStatus.SUCCESS` / `spawn tool 1 ToolStatus.SUCCESS` / `model get on orphan: ToolStatus.ERROR codex.session_not_found: This toolset did not start the turn with that` / `turn/start total: 3 turn/interrupt total: 0`.
  Failure: A launch call is cancelled after item 1's `turn/start` returned, while item 2 is starting. Triggers include the agent run being cancelled and `CodexToolBridge.close()` cancelling a pending tool coroutine. The results:
  - Item 1's paid turn keeps running until it ends or the host closes.
  - The caller never got its handle, so the model can neither wait on it nor interrupt it: the handle tools refuse it with `session_not_found`.
  - The scope does not count it, so 3 turns run under `max_live_turns=2`.
  This breaks the cap that G-4 promises ("Live tool turns are capped"). It also breaks D-22/INV-37's partial-failure rule ("interrupts the started ones on a partial failure"), and it conflicts with INV-11's "no accepted turn is left unowned": the in-flight item k+1 *is* owned and interrupted under INV-11, while items 1..k are not.
  Smallest fix: in `launch_codex_subagents`, stop the started turns on any exception, then re-raise. Only a `CodexAgentError` gets its message rewritten. For example, `except BaseException as exc:` → `for turn in started: self._stop(turn, None)`, then `if not started or not isinstance(exc, CodexAgentError): raise`, then the existing message rewrite. `_stop` is synchronous, so the cancel path needs no await. Under §14, a regression test for this path is "ask first", because test files are S2's.
  Spec IDs: INV-37, INV-32, INV-11, EC-52, D-22, G-4, FR-14, FR-26, T-1

R-C2 [Minor] [conformance] vidbyte/tools/builtins/codex/descriptions.py:58 — The `branch` and `sha` descriptions tell the model that unused fields are ignored, but the record refuses them
  Evidence:
  - descriptions.py:58 `BRANCH_DESCRIPTION = "... It is ignored by the other review targets. ..."`.
  - descriptions.py:59 `SHA_DESCRIPTION = "... It is ignored by the other review targets. ..."`.
  - spec §9.1 `CodexReviewTarget`: "Fields the kind does not use must stay empty."
  - Probe: `CodexReviewTarget(kind=COMMIT, sha="abc", branch="main")` → `ConfigurationError Codex review target commit needs sha; got empty [] and unused ['branch'].`, and the base-branch kind with `sha` set fails the same way.
  Failure: a model that follows the description and sends `branch` with `target_kind: "commit"` gets the error result `configuration.invalid_argument` instead of a review. The model was told the extra field was harmless.
  Smallest fix: replace "It is ignored by the other review targets." with "The other review targets refuse it." in both constants. This keeps 4 sentences (NFR-7). The `title` and `instructions` texts ("used only when …") are accurate as they stand.
  Spec IDs: §9.1 CodexReviewTarget rule, INV-34, NFR-7, AC-35

VERIFIED CLAIMS:
- Scope and budget:
  - The diff touches 54 files. The non-docs, non-test files are exactly the 28 §12.3 paths: no file outside §12.3, and no `.gitattributes`. HELD.
  - The §8.4 budget is used exactly, as §17 says: 18 new files; 30 classes (harness 12, tool layer 17, toolset 1); 15 records; 13 enums; 0 dependencies; largest file host.py at 733 lines. HELD.
  - NFR-10: no existing file reaches 1,000 lines. constants/codex.py went from 267 to 505 lines, and REPO_MAP.md from 398 to 402. HELD.
- §14 Never and Ask-first:
  - `git diff 1d110811..099fac83 -- tests/` is empty, so no S2 test changed after S2_HEAD;
  - no added `noqa`, `type: ignore`, `nosemgrep` or `pragma`;
  - no baseline, manifest or contract change;
  - every implementation commit cites W-, FR- and AC- IDs (the 17 that cite none are all `docs(spec)` pipeline commits).
  HELD.
- §17 deviation 1 (lint C002 workaround) behaves the same:
  - `wait_codex_turn` validates through `CodexSpawnRequest(timeout_seconds=)` and keeps the same message;
  - `limit` uses `type(limit) is not int`;
  - EC-51/EC-54 inputs are refused the same way.
  HELD.
- §17 deviation 2 (a process death also closes goal streams): this is required by INV-25 ("When a registered goal run finishes … the host closes its goal stream") and prevents a stranded watcher. Acceptable. HELD.
- Generated wire values match the Vidbyte enums: WindowsSandboxReadiness, TurnStatus, the account variants, `RateLimitWindow.used_percent` as an int, the ReviewTarget shapes and ReviewStartParams. HELD.
- Approvals (INV-28, D-32):
  - `CODEX_APPROVAL_MODE_WIRE` equals the SDK's `_approval_mode_settings`;
  - `thread/start` sends, in priority order, the explicit fields as given, else the mode, else on-request plus auto_review;
  - resume and fork send approval fields only when they are set;
  - `turn/start` sends only the turn's `approval_mode`, which is allowed because INV-28 says "only when the caller set them" and the explicit fields belong to the thread per the §9.2 field rules;
  - `routes_to_user` treats a granular policy as not-never.
  HELD.
- The error mapping table conforms:
  - ServerBusy and RetryLimitExceeded map to `api_error`;
  - TransportClosed maps to `process_exited` with fixed text;
  - a GOAL_START_CALL CodexError maps to `api_error`, and any other CodexError to `protocol_mismatch`;
  - the D-13 overrides hold;
  - the death flag is checked first;
  - everything is raised `from None`.
  HELD.
- Close and lifecycle:
  - INV-2 to INV-7 match by reading: loop claimed before the first await, SDK import before `which`, the guard order, all six close steps in order, and the executor shut down with `wait=False, cancel_futures=True`;
  - INV-11 connection late acceptance holds (`future.cancel()` first; adopt late turn, goal or review; close wins).
  HELD.
- INV-12 to INV-27 match by reading and through their AC tests, including: INV-19 counts only the turn's own `delta.output_tokens`; INV-23 keys the registry by value; INV-24 reserves before the first await; INV-25 cleans up a failed start in order and registers only after the echo; INV-27 REJECTED_FIELDS equals the §9.2 field-rules table. HELD.
- Tools:
  - INV-31: 15 tools in R3 order, 8 READ and 7 WRITE;
  - INV-33: `require_owned` gates wait, get, steer and interrupt;
  - INV-34: spawn replaces only the six model fields, and continue clears its rejected fields;
  - D-31: wait is clamped to 240 s and defaults to 240 s;
  - INV-35: wait and get use `without_items`, and interrupt returns the fixed sentence;
  - INV-32: `reserve` does its check and increment with no await between them, so two concurrent calls cannot pass the cap together. Only the cancel path in R-C1 escapes the cap.
  HELD.
- Row 7 extraction (INV-39): `validate_names` is a staticmethod, and `handler(loop, fallback)` is used by `attach`. Behaviour is preserved; AC-28's existing tests pass in the `-k codex` sweep. HELD.

Per-ID prosecution vs defense (summary):
| IDs | Verdict | Basis |
|---|---|---|
| FR-1..FR-13, FR-15..FR-25, FR-27..FR-30 | defense | reading + AC tests (101/101) + §4 run; FR-15 subject to R-C2 (text only) |
| FR-14, FR-26 | prosecution (partial) | R-C1: cancelled launch escapes the interrupt rule and the cap; normal and failure paths hold |
| NFR-1, NFR-2, NFR-3, NFR-4, NFR-6, NFR-8, NFR-9, NFR-10 | defense | CI view 35 passed / 66 skipped; AC-5/7/11/32/34 tests; host thread `codex-host_0`; line counts |
| NFR-5, NFR-7 | defense (not re-run here) | gate, Semgrep and S025 are S3 and S5 steps per AC-36; I checked that nothing was suppressed or rebaselined; the R-C2 texts have 4 sentences |
| INV-1..INV-10, INV-12..INV-31, INV-33..INV-36, INV-38..INV-42 | defense | reading + tests + probes above |
| INV-11, INV-32, INV-37 | prosecution (partial) | R-C1 (cancellation path only) |
| AC-1..AC-37 | defense | AC-1 run verbatim; every Proof test passes; AC-18's Given covers failure, not cancellation (R-C1 is outside it); the AC-36 gate steps belong to S3 and S5 |
| EC-1..EC-51, EC-53..EC-81 | defense | the accepted rows (EC-10, 17, 24, 41, 43, 45, 46, 48, 50, 56, 64-66, 68, 69, 77) match the code; EC-62 probed |
| EC-52 | defense for failure, prosecution for cancellation | probe: 2 interrupts and the "2 turns were started" text; cancel variant = R-C1 |
| §12.3 rows 1-28 | defense | all present, none extra; shared-file insertions byte-checked; row 7 behaviour-preserving |
| §12.4 / §12.5 | defense | no manifest, contract, baseline or root-`__init__` change; no `.gitattributes`; docs only under the spec folder |
| §14 never-list | defense | see above |

COMMANDS RUN:
- `git diff --stat origin/main...099fac83` → `54 files changed, 14694 insertions(+), 4 deletions(-)`
- `git diff origin/main...099fac83 -- lint/baseline.json pyproject.toml vidbyte/__init__.py contracts/` → (empty)
- `git diff 1d110811..099fac83 --stat -- tests/` → (empty)
- `git diff origin/main...099fac83 -- vidbyte REPO_MAP.md | grep '^+' | grep -E 'noqa|type: ignore|nosemgrep|pragma'` → (no match, exit 1)
- `git show 099fac83:vidbyte/harnesses/native/__init__.py | sha256sum` → `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a  -`
- `PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` → `101 passed in 8.28s`
- CI view (`sys.modules['openai_codex']=None`) → `35 passed, 66 skipped in 2.10s`
- `pytest $W/tests -k codex -q -p no:cacheprovider` → `338 passed, 3725 deselected in 9.81s`
- §4 snippet, verbatim, at the fake seam → `True` / `completed The readme describes the SDK.` / `15 check_codex_ready`
- Wire probe (`CodexParamsTranslator` on sample requests) → `full-access thread: danger-full-access turn: {'type': 'dangerFullAccess'}` / `deny_all mode: {'approvalPolicy': 'never'}` / `resume reviewer: {'approvalsReviewer': 'auto_review', 'excludeTurns': True, 'threadId': 'th'}` / `agents (no subagents, own config): {'x': 1, 'agents': {'max_threads': 9}}` / `turn with explicit reviewer: {'input': [], 'threadId': 'th'}`
- `sed -n 1,60p …/openai_codex/_approval_mode.py` → `case ApprovalMode.deny_all: return AskForApproval(root=AskForApprovalValue.never), None`
- `CodexReviewTarget` probe → `ConfigurationError Codex review target commit needs sha; got empty [] and unused ['branch'].` (and the same for base branch with `sha`, and custom with `title`)
- EC-62 and EC-52 probe → `thread/name/set -> codex.api_error | … boom Thread: thr-1.` / `turn/start -> codex.api_error | … boom Thread: thr-1.` / `launch -> codex.api_error | … third fails Thread: thr-3. 2 turns were started before this failure and were interrupted.`; after `wait_for("turn/interrupt", count=2)` → `interrupts: 2`
- Cancelled-launch probe (R-C1) → `turn/start so far: 1` / `launch tool call cancelled` / `turn/interrupt sent after 1s: 0` / `thr-1/turn-1 status: inProgress` / `spawn tool 0 ToolStatus.SUCCESS` / `spawn tool 1 ToolStatus.SUCCESS` / `turn/start total: 3 turn/interrupt total: 0`
- Line counts of modified files at 678136bd and 099fac83 → largest existing file `vidbyte/lib/constants/codex.py 267 -> 505`; largest new file `host.py 733`
- `git log --format='%h %s' 678136bd..099fac83 | grep -vc 'FR-\|AC-\|W-'` → `17` (all `docs(spec)`; `grep -vc "^docs(spec)"` on them → `0`)
- `git status --short` → (clean; HEAD 3ebefd11)
