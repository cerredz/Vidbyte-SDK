# S1 spec-author report: codex-host-first-class (slice 2)

| Field | Value |
|---|---|
| Stage | S1 spec author |
| Date | 2026-10-17 |
| Branch | `feat/codex-host-first-class` |
| Spec | `docs/spec/codex-host-first-class/spec.md`, r1 (1,832 lines), committed as `fde5a8b0` |
| Writes | spec.md (committed) and this report (not committed). Throwaway check scripts are in the session scratchpad only. No code, no tests, no installs, no `codex` binary, no push. |

## What I read
- **Rules and the request:**
  - the spec template and AGENTS.md;
  - request.md;
  - `pipeline.md` (the decisions of 22:40 and 23:05, and the niche facts);
  - the S0 scout's `context/code-map.md` (in full) and `reports/S0-scout.md`.
- **Host code, at the places the design touches:**
  - `host.py`: `_open`, spawn, continue, the private start helpers, `delete`, `get_codex_goal`;
  - `wire.py`: `final_answer`, `turn_start`, `pricing`;
  - `thread_helpers.py`: `compact`, `delete`, `goal`;
  - `preflight.py` signatures;
  - `codex_host_inputs.py` (lines 1-100 and 200-405);
  - the `codex_host.py` constant tables (lines 40-180) and the existing message texts;
  - `enums/__init__.py` and `enums/codex.py.__all__`;
  - `enums/process.py`;
  - `lib/process/{argv,runner,__init__}.py`;
  - `dataclasses/process.py` fields;
  - `native_threads.py` header and constants;
  - `tools/builtins/codex/{descriptions,_base,thread_helpers}.py` at the relevant lines.
- **Pins:**
  - the `test_harness_threads_surface.py` export and branch-scope tests;
  - `test_harness_threads_static_policy.py`, which skips codex;
  - the bodies of the superseded tests: hardening contract rows, packaging import probe, input boundary rows, the tool-count tests.
- **SDK 0.163.0, read with `V -I`:**
  - the `notification_registry` method names;
  - the model fields of every streamed notification and raw response;
  - which slice-2 responses have `v2_all` models: 9 have none, and 4 raw ones do;
  - the typed `CodexClient` goal and archive methods;
  - `_start_goal_operation` in full, because D-17 depends on it.
- **External evidence paths** (Codex TUI `side.rs`, `app_server_session.rs`, `session_queue_commands.rs`; the schemas) were checked to exist where §11 says.

## Approaches weighed
1. **Surface placement.**
   - Chosen: four SDK-free mixins over `CodexHostCore`, plus a `CodexTurnStarts` collaborator for the moved start helpers.
   - Rejected:
     - Growing `host.py` (937 lines today) would pass 1,300 lines and break the `vars(CodexHost)` helper-order pin.
     - Collaborators with forwarders would add about 250 lines back and break the same pin.
2. **The experimental wire.**
   - Chosen: the existing raw path with a passthrough response class, and `parse` run on the worker inside the call.
   - Rejected:
     - Hand-written pydantic models for the 9 unmodeled responses.
     - Fake stand-in model names: pydantic ignores extras, so non-empty answers would silently read as empty.
     - Parsing after the call: a malformed answer would then log as a successful call and escape as a raw `ConfigurationError`.
3. **Streaming.**
   - Chosen: a bounded, host-side event log fed by the existing watcher, with drop-oldest plus `GAP`.
   - Rejected: the SDK's private multi-consumer subscription, which is unbounded and needs a second reader thread per stream.
4. **Goal resume.**
   - Chosen: reserve, activate, a status-only set, then wait, under `connection.start`.
   - Rejected:
     - `start_goal_operation`, which always clears the goal and so loses budget and usage.
     - A bare typed set, which sends no `origin` and is untracked.
5. **The worktree.**
   - Chosen: a canonical `GitWorktrees.add` over `CliArgv` and `CliRunner`, under `~/.vidbyte/codex-worktrees/`.
   - Rejected: `codex exec --worktree`, which spends, and inline `subprocess`.

## Where I disagree with the scout or the request
- **Queue add/list/start is not built** (NG-1, blocking Q-1, default "not built"). The request and the 23:05 decision list it as P1. The evidence:
  - Codex's own CLI refuses to queue through a private embedded server;
  - CodexHost always runs one;
  - the TUI never calls `queue/start` or `queue/list`, so Codex drains the queue itself, which is an inference;
  - such turns would start untracked, which breaks slice-1 INV-11;
  - inside one private server, the queue duplicates `continue_codex_thread` after `wait_codex_turn`.

  This is the one place I overrode the request. The request allows it ("impossible or redundant become NG … with evidence").
- **`personality` and `multiAgentMode` on settings update.** The scout notes the gap report omits them. I keep them out on purpose: the schema marks both deprecated (NG-7).
- **Paths outside §11 and §12.** The template itself asks for `path:symbol` in §8.2, for paths in the must-not-regress INVs and in §13. I kept paths there. Everywhere else in §1–§10, repo paths became module or symbol names. External evidence is cited by short file name, and §11 maps each name to its full path.
- **`GitFlag` placement.** The `native_threads` constants header says vendor flags live in `enums/native_threads.py`. I put `GitFlag` in `enums/process.py`, beside `CliOptionStyle`, because it is a process-helper flag (§11 Conflicts 2).
- **`vidbyte.lib.process` exports.** Its header says to export new helpers, but the harness-threads pin fixes `__all__` at three names. `GitWorktrees` is therefore imported from its own module, and the header gains a note.

## Assumptions I am least sure of
1. **A-1:** a status-only `thread/goal/set {status: active}` starts a goal turn. If it is false, `resume_codex_goal` always times out in its start window. It is the riskiest P1 behaviour, and the fake cannot prove it.
2. **A-13:** `thread/resume` on a paused, blocked or usage-limited goal does not auto-start it. If it does, resume could start an untracked turn before the tracked set.
3. **A-14:** the `thread/inject_items` item shape used for the side-chat boundary (a Responses-API user message).
4. **A-11:** a collaboration mode persists to later turns. §4 sidesteps this by passing `DEFAULT` explicitly.
5. **A-2:** an omitted `developer_instructions` behaves as `null`. It is a one-line flip if wrong.
6. **Ceilings.** `wire.py` ≤ 840 is my estimate, about 820 after the edits. A tighter real count could force a BLOCKED report.
