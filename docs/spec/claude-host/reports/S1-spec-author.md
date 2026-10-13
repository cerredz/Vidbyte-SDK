# S1 spec author report: claude-host (r1)

- **Spec:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host/docs/spec/claude-host/spec.md` (1,366 lines).
- **Commit:** `21a947a7` on `feat/claude-host` ("docs(spec): add claude-host spec r1"). Only `spec.md` is in it; this report is not committed.
- **Base:** `678136bd4358bcf9f120504cecd818d36a3d46fe`.
- **Mechanical checks run:**
  - 18 `## §` headings;
  - digit-led table rows only in §12.3 (rows 1–31);
  - every ID range is contiguous and defined: G 4, NG 11, INV 26, AC 36, EC 56, FR 25, NFR 11, D 28, T 4, W 21, A 16, Q 10;
  - no file paths outside §8.2, the must-not-regress INVs, §11, §12 and §13.
- **Not run:** no gate, lint, test or install. The briefing forbids it.

## 1. What I read

**Pipeline inputs**
- The S1 briefing.
- The spec template `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/spec-template.md`.
- `request.md`, all of §A–§E, including the verbatim R2 and R3 replies.
- `context/code-map.md`, all four sections.
- `pipeline.md`.

I opened no other file under `docs/`, so `reports/S0-scout.md` was not read; the scout's findings came to me through code-map.md and the pipeline niche facts. I did not read the CodexHost worktree.

**Repository rules**
- `AGENTS.md` in full.
- `CLAUDE.md`, which is `@AGENTS.md`.
- `REPO_MAP.md`: the harnesses, lib, tools and toolsets entries.
- `vidbyte/harnesses/README.md`.
- READMEs of every touched folder, checked for `## File Index` and `## Notes for agents`.
- Lint rule sources under `lint/rules/`: A001, A002, A003, A005, A006, A007, A008, C001, C002, C003, C006, C007, C008, C011, S002, S003, S005, S012, S016, S017, S020, S021, S027, S036, S039, S042, S045 and S061.
- `lint/core/report.py`, plus the code-map summaries of the remaining rules.

**Field guide** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`): the entries listed in spec §11. They are model-facing-tool-contracts, strict-config-dataclasses, class-bound-helpers, provider-api-contracts, blocking-lint-invariants, comment-format, prebuilt-agents, agents-md-map, cli-backed-source-integrations, local-ci-verification, review-scope, runtime-boundaries and diagnostic-context.

**Repository source** (read-only; `vidbyte/agents/codex/` read as a pattern only)
- **Codex pattern:**
  - `vidbyte/agents/codex/` transport, tools and agent;
  - `vidbyte/lib/dataclasses/codex.py`, `vidbyte/lib/enums/codex.py`, `vidbyte/lib/constants/codex.py`.
- **Shared lib files:**
  - `vidbyte/lib/enums/failure.py` and `vidbyte/lib/enums/__init__.py`;
  - `vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`;
  - `vidbyte/lib/dataclasses/tools.py` and `vidbyte/lib/dataclasses/security.py`;
  - `vidbyte/lib/tools/formatter.py`.
- **Tools:**
  - `vidbyte/tools/builtins/sessions/` and `vidbyte/tools/builtins/pause.py`;
  - `vidbyte/tools/toolsets/coding.py` and `vidbyte/tools/toolsets/__init__.py`;
  - `vidbyte/tools/catalog.py` and `vidbyte/tools/executor.py`.
- **Server, config and CI:**
  - `vidbyte/mcp_server/server/core.py`;
  - `pyproject.toml` and `.github/workflows/ci.yml`;
  - `scripts/run_ci.py` (the gate list only).
- **Test seams:** `tests/test_codex_tools.py:264-319` and `tests/test_session_failures.py`.

**Vendor material** (untrusted and read-only; never imported, executed or copied; any Python that read it ran with `-I`)
- **claude-agent-sdk 0.2.165 sdist,** extracted to the session scratchpad. I read:
  - `types.py`, `client.py` and `_internal/message_parser.py`;
  - `_internal/session_mutations.py` and `_internal/sessions.py`;
  - the subprocess transport (`_build_command`, `_find_cli`);
  - the anyio task-compat layer.
- **The TypeScript `@anthropic-ai/claude-agent-sdk` `sdk.d.ts`:** types and doc comments.
- **The user's `claude.exe` 2.1.296:** help strings found with `grep -a`. The binary was never run, and `claude` was never invoked.

## 2. Approaches weighed and why this one

**Chosen.** `ClaudeHost` is an async context manager bound to the loop that entered it (D-1). It runs one `claude` process per turn (D-2), and spawn returns a handle at once. One pump task per turn reads to the prompt's own result (D-28). Wait, get, track, steer and interrupt act on that live turn.

This is the smallest design that satisfies every ★ live function. Nothing outlives its turn, so there is nothing for a reaper, memory governor or idle-eviction policy to manage. That keeps rule 11 controls out of scope.

**Rejected smaller design: module-level functions with no host** (§8.3 Rejected 1).
- A spawn would block until the result, which fails FR-5 and INV-3, and request.md says a blocking spawn holds the agent for minutes.
- No live object would exist for wait, steer or interrupt to reach (FR-11–13).
- There would be no registry for the busy guard or the cap (INV-4, INV-5).

**Rejected: one long-lived process per session until close** (§8.3 Rejected 2). Idle 260 MB processes would accumulate (NFR-7), and it needs an idle-eviction policy nobody asked for (hard rule 9).

**Smaller choices inside the design:**

| Choice | Picked | Runner-up and why it lost |
|---|---|---|
| Steer | Interrupt, then resend after the result (D-3) | Mid-turn `query()`. The CLI may queue it, fold it into the running turn or coalesce several sends. The Python parser drops `queued_turn_count` and `user_message_uuids`, so the host could not count the remaining results. |
| Time budget | A watchdog that interrupts (D-4) | `asyncio.timeout` / `wait_for` around reads. The vendor warns that cancellation can skip close-escalation and orphan the child. |
| Readiness and models | One initialize probe (D-5) | `claude --version` plus `claude auth status --json` subprocesses. That adds a runner and the S052/S055 lint surface, and initialize already carries the account, models and version. |
| Record validation errors | `ClaudeOperationError` with `configuration.*` codes (D-15) | `ConfigurationError`. With it, a tool could leak a second exception type into the agent loop, and callers would handle two classes. |
| `model_unknown` | From the assistant error `model_not_found` (D-7) | A pre-check against initialize's model list. It would falsely refuse full model ids that the alias list omits. |
| Fork | Offline file copy in `asyncio.to_thread` (D-19) | Resume with `fork_session=True`. That needs a process, while R3 makes fork offline and instant. |
| Records | Two modules, `claude` and `claude_host` (D-16) | One module. It would head toward the 1,205-line Codex record module. |
| Pin | `>=0.2.165,<0.3.0` (D-18) | `==0.2.165`. Only public API is used, and Codex's exact pin exists only because of its private-attribute access. |
| Flag-only fields | `extra_args` only for flags verified in the 2.1.296 binary; one env variable (D-9) | Excluding them all. The briefing allows verified flags. |

## 3. Where I disagree with the scout or the request, with evidence

1. **Scout: "Neither the repo nor claude-agent-sdk 0.2.165 has a max-output-token env var."** True of the SDK package, but the 2.1.296 binary contains `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 8 times, including "CLAUDE_CODE_MAX_OUTPUT_TOKENS environment variable". `max_output_tokens` maps to it (D-9). A-5 covers its exact semantics.
2. **Scout: "`fallback_model` is a single string."** True of the Python option type. But the 2.1.296 `--fallback-model` help says "Accepts a comma-separated list to try each in order". The request field is an ordered tuple, comma-joined (D-11), which satisfies R3's "ordered list".
3. **Scout: "Plugins are local folders only."** True of the SDK's typed `plugins` option. The binary also has `--plugin-url <url>` (repeatable), and `--plugin-dir` accepts a folder or a `.zip`. Plugin URLs go through `extra_args`, capped at one value because an `extra_args` key cannot repeat (D-9).
4. **Scout lists S045 as "`async def` with a `timeout` parameter."** This is a refinement, not a conflict. S045 is Ruff ASYNC109 (`lint/rules/s045_async_function_with_timeout.py:28`), which matches the parameter name `timeout` itself. Every async parameter is named `timeout_seconds`, and §12.4 says so.
5. **Request: "`ResultError` with subtype `error_max_budget_usd` / `error_max_turns` → `budget_exhausted`".** I agree with the scout that in a live client turn these arrive as `ResultMessage(is_error=True, subtype=...)`. Classification reads the result message (§9.2 precedence item 9), and `ResultError` is mapped only if raised.
6. **Request: "assistant error kinds … → the matching codes".**
   - Python's `AssistantMessageError` literal (types.py:1038) has no `model_not_found`.
   - The TS union `SDKAssistantMessageError` (sdk.d.ts:3717) does list it.
   - The Python parser passes the raw `error` string through (message_parser.py:214).

   So `model_not_found` maps to `model_unknown` (D-7).
7. **Rate-limit types.** The Python `RateLimitType` literal has 5 values (types.py:1392). The TS union (sdk.d.ts:5707) adds `seven_day_overage_included`, and the parser passes the raw string (message_parser.py:363). The enum follows the wire, with 6 members, and an unknown type is skipped (EC-52).
8. **R3: "Put `hooks_applied` and `plugins_applied` from the initialize result on every handle".**
   - The handle is returned before initialize runs, so `hooks_applied` goes on the turn result.
   - `plugins_applied` is never surfaced. Python's initialize request never lists plugins, and the DTS says the field is "Absent when the request listed no plugins" (D-21).
9. **Request: fork "Wraps `fork_session()` (a file copy), or `resume` + `fork_session=True`".** Only the offline copy is used (D-19). The SDK returns `ForkSessionResult(session_id)` (`_internal/session_mutations.py:233-245`), not a string, and the host returns its `session_id`.
10. **R3 field `prompt_suggestions`.** It is excluded (NG-7, optional Q-6). The CLI emits suggestion messages after the result, and the 0.2.165 parser drops message types it does not know, so no ★ function could ever surface one.
11. **Not in the request or scout: the first result does not always end the turn.** The 0.2.165 `ResultMessage.origin` docstring says it "lets a streaming-input consumer distinguish the result of its own prompt ... from results of injected turns such as background-task notifications". `MessageOriginKind` says to treat unknown kinds as not human. D-28, AC-36 and EC-56 make only an absent or `human` origin end the turn.
12. **Scout's `load_timeout_ms` note.** I agree. It maps to the SDK's `load_timeout_ms`, documented as the session_store load timeout, not process start (§9.2 field table).
13. **House style `vidbyte-gates.md` versus the repo.** It says the lint line reads `AGENT-LINT: PASS` and that semgrep runs inside `run_ci.py`. The repo prints `SDK-LINT: PASS` (`lint/core/report.py:58`), and semgrep runs only in `static-policy.yml`. The repo wins (§11 conflicts).
14. **REPO_MAP toolsets entry is stale.** It says the folder "currently holds one such bundle", but `vidbyte/tools/toolsets/` holds `coding.py` and `paradigm_minimal.py`. Not reworded (NG-8, out of slice).
15. **Contract wording "inserts in sorted position".** The import list in `vidbyte/lib/errors/__init__.py` is not sorted: `CodexAgentError` sits between `AgentExecutionError` and `AgentSpeedError`. Row 26 therefore names explicit neighbours (`AggregateExecutionError` and `ConfigurationError`) instead of a computed sorted slot.

## 4. Assumptions I am least sure of

- **A-8 and A-9: steer and interrupt concurrency.**
  - A-8: an interrupted turn ends with exactly one result for its prompt, and the resend starts exactly one new turn.
  - A-9: one client may be read by the pump task while another task calls `interrupt()`.

  I verified both by reading the code, never by running it. If A-9 is wrong, steer and interrupt route through the pump with a small command queue; only `ClaudeLiveSession` changes. If A-8 is wrong, steer needs the CLI's `session_state_changed` idle signal.
- **A-6: initialize is free.** A connect with no prompt sends only `initialize`, makes no model request, and returns `account`, `models` and `claude_code_version` on 2.1.296. The field is in the binary's schema, but I saw no runtime evidence that the probe costs nothing.
- **A-2: headless denial.** With `permission_prompts=NONE`, a tool needing permission is denied and listed in `permission_denials` rather than waiting. If wrong, those turns wait until the time budget or an interrupt.
- **A-3: CLI flags in SDK mode.** The verified flags behave in stream-json mode as their help says. The weakest case is `--no-session-persistence`, whose help says "only works with --print".
- **A-1: images.** List content with base64 image blocks is accepted over `query(AsyncIterable[dict])`. Unverified in the Python SDK. If wrong, `images` becomes a limitation.
- **A-13: bare without a key.** Under `--bare` with no API key, `account.apiKeySource` is absent or `none`. This drives EC-6's precheck.
- **A-12 and A-4, also unverified at runtime.** `--worktree` must work headless before the first turn, and `--autocompact` must accept a plain integer.
- **Lint slack is unverified.** No gate ran at S1, and A001 has no headroom (643), so every new `.py`, tests included, needs the seven-field header. The first gate run at S2 or S3 must record pre-existing failures.

**Open questions:** Q-1 to Q-10, all non-blocking with default No. None blocks the spec.

## Addendum: r2 (2026-10-13)

- **Commit:** `ac39bb46`, on top of the orchestrator's `978ebfa5`. Only `spec.md` is in it.
- **Mechanical checks re-run:**
  - 18 `## §` headings;
  - digit-led rows only in §12.3 (1–31);
  - every ID defined, with these maxima: AC 38, EC 58, A 17 (G, NG, INV, FR, NFR, D, T, W and Q unchanged);
  - every edited table row has its table's column count.
- **Budget:** unchanged at 22 new files, 9 modified and 69 classes. Only constants were added (row 14).

**Dispositions:** all ten findings were accepted; §16 has one row per R-n.

| Finding | Change |
|---|---|
| R-1 | The marker hash uses the committed blob or CRLF-normalized bytes. No `.gitattributes`, per the orchestrator. |
| R-2 | A grace timer, `CLAUDE_INTERRUPT_GRACE_SECONDS = 30.0`, runs after every interrupt that returns. It is a constant rather than a request field (rule 9). EC-53 is no longer a limitation, and the spec:733 contradiction is resolved. Adds AC-37 and A-17. |
| R-3 | `repr=False` on the request `env` and the MCP `env` and `headers`. |
| R-4 | `--permission-prompts none` for NONE. Re-verified in claude.exe 2.1.296: the help text quoted in §11, plus `.default("host")`. |
| R-5 | `ClaudeProbe.locate_cli` mirrors `_find_cli` minus the bundled CLI, re-read at `subprocess_cli.py:255-316`, with the batch refusal at :415 and :807. Adds EC-57 and AC-38. |
| R-6 | The S054 line, plus S105-safe constant names for A-7. |
| R-7 | NFR-1's target is reworded. |
| R-8 | Four generic next-step constants. |
| R-9 | Steer wording. DTS:4571 confirms that the interrupt kills background tasks when `perTaskStopAffordance` is absent; the Python SDK never sends that field. |
| R-10 | Header KNOWN EDGE CASES content for rows 3, 15 and 22. |

**Also applied:**
- **Orchestrator contract change (`978ebfa5`):** rows 30 and 31 and §12.5 insert the request.md §C REPO_MAP and README texts verbatim. FR-24 and AC-32 needed no change.
- **Reviewer fact on zeroed crash-result cost (DTS:5738/5746):** stated as limitation EC-58.

**Choices I made beyond the reviewer's text:**
- **POSIX CLI lookup.** `_find_cli` also probes six home and system locations on POSIX. D-5 keeps only `which` there, because a missing CLI on POSIX gives a clear `not_installed`, not a loop. R-5's evidence and the orchestrator's note were Windows-only.
- **Grace value of 30 s.** It is my choice; nothing in the repo or the conversation fixes it. A-17 records that it is unverified at runtime.
- **One precondition next step.** EC-20, EC-21 and EC-25 now carry their specifics in the reason, under one `CLAUDE_PRECONDITION_NEXT_STEP`, instead of three ad hoc next steps.

**New least-sure assumptions:**
- **A-17:** an acknowledged interrupt yields its result within 30 s.
- **A-3, now also covering `--permission-prompts`:** its help says "with --print", and the SDK never passes `--print`.
