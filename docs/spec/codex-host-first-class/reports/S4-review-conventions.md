LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, records, layering, lint, logging, scope and commit hygiene all meet AGENTS.md and the field guide, but one field-guide rule is broken (14 new comment lines are wider than 72 columns) and 13 of the 25 new main functions have no narration, under headers that say they do; every fix is mechanical, and none needs rework.

Reviewed range: `git diff a7730107...8ea8734f` (slice 2). The worktree HEAD is `18cd3259`, which differs from `8ea8734f` only in `docs/spec/codex-host-first-class/pipeline.md`, so every source line quoted below is the reviewed code.

WHAT THE IMPLEMENTATION GETS RIGHT
- **Placement and records follow AGENTS.md §4 and the Placement Rules.**
  - All 31 new dataclasses are `@dataclass(frozen=True, slots=True)` with a `__post_init__`, and each sits in `vidbyte/lib/dataclasses/<domain>.py`: 11 in features, 2 in modes, 17 in inputs, and `GitWorktreeSpec`.
  - The 10 new enums are in `vidbyte/lib/enums/`.
  - All 23 public methods that take input build their input record on the line right after `_guard`, as #1178 and `strict-config-dataclasses.md` require. The 2 that take no input skip it correctly.
- **The layering and size rules hold.**
  - C021 is clean: no module under native/ gains a top-level UPPER_CASE name.
  - The five SDK-free modules (`host_core`, settings, stream, thread and goal methods) import no openai-codex or SDK-loading collaborator at module level (INV-45).
  - Every file is under its INV-47 ceiling: host 786/900, wire 839/840, `codex_host.py` 891/900, inputs 779/900, and the largest new native module is 362/600.
  - The two-level-chain scan found no nested `def` in any new module.
  - `GitWorktrees` is a canonical lib helper on top of `CliArgv` and `CliRunner`, with no `subprocess`.
- **Lint, logging and error packets are clean.**
  - Lint ends `SDK-LINT: PASS` with no baseline raised. A002 and S009 improved.
  - The new log calls are %-style `event key=value` with `LogToken.of`, no `exc_info`, and no path, branch or git output (INV-9).
  - Every new `CodexAgentError` goes through `CodexErrorMapper.error`, with its cause and next step taken from `vidbyte/lib/constants/codex_host.py`.
- **Scope, commit hygiene and header counts are clean.**
  - `REPO_MAP.md`, `vidbyte/harnesses/README.md` and `vidbyte/harnesses/native/__init__.py` are untouched.
  - Under `vidbyte/tools/`, only the allowed paths changed.
  - No `.pyc` or `__pycache__` file is in the diff.
  - Every commit in the range has the Co-Authored-By trailer, and every feat or fix commit cites its spec IDs.
  - The header counts are true: 42 tools, 55 `CodexHostOperation` members, thirty-four, eleven and two records, and six, eight, five and seven tools per module.
  - The 16 tool descriptions are each one literal of 4–5 sentences with no examples. Each WRITE description names the paid work, and the side-chat description says what D-22 requires.

FINDINGS (ranked)

R-V1 [Blocker] [comment-format] vidbyte/tools/builtins/codex/controls.py:73 — Fourteen new comment lines are wider than the 72-column limit, in 10 files
  Evidence: The field guide's own check, run on the added lines only, prints 14 lines (width in brackets):
    - `feature_wire.py:197` [74]: the `# @intent a-side-chat-fork-is-ephemeral-and-told-it-is-a-side-chat` line;
    - `wire.py:301` [74];
    - `goal_methods.py:98` [73];
    - `settings_methods.py:173` [73] and `:187` [73];
    - `thread_helpers.py:231` [73];
    - `codex_host_inputs.py:678` [73];
    - `controls.py:73` [76], `:163` [73] and `:168` [73];
    - `live.py:237` [74];
    - `thread_actions.py:133` [76] and `:183` [76];
    - `toolsets/codex.py:139` [75].
  None of the files predates the rule with wide comments: the same check on each whole file prints only these 14 lines. So every hit is new code, in an area that was otherwise fully compliant.
  Failure: Field guide `comment-format.md` says "Wrap every comment line at 72 columns, counting the indent … A single-line comment that would pass 72 columns becomes a wrapped block too." Its check is that `awk 'length($0) > 72' <file> | grep -E '^\s*#'` "prints nothing for the files you touched". Spec §12.4 item 7 says the same: "every source comment wraps at 72 columns". A human reviewer would write: "Re-wrap these. We fixed this exact formatting across the codex package (PR #690 → #747)."
  Smallest fix:
    - Re-wrap the 13 narration lines into 2-line blocks.
    - Shorten the `@intent` name at `feature_wire.py:197`, for example `# @intent a-side-chat-fork-is-ephemeral`. No test pins `@intent` names (checked with grep).
    - Re-run the awk check on the 10 files.
  Spec IDs: §12.4 (A002 / comment-format); NFR-6

R-V2 [Major] [narration] vidbyte/harnesses/native/codex/thread_methods.py:243 — 13 of the 25 new public methods have no narration, and two module headers say every method is narrated
  Evidence: The AST comment count, from the scratchpad script `narration.py`, finds 0 comments in the bodies of 13 methods:
    - `settings_methods.py`: `list_codex_collaboration_modes` (:95), `list_codex_mcp_servers` (:133), `get_codex_memory_status` (:222) and `reset_codex_memories` (:232);
    - `thread_methods.py`: `archive` (:185), `unarchive` (:196), `revert` (:205), `rename` (:221), `inject` (:230), `list_codex_background_terminals` (:243), `clean_codex_background_terminals` (:257) and `search_codex_thread_content` (:271);
    - `goal_methods.py`: `clear_codex_goal` (:135).

  Several of these run 4–6 separate steps. For example, `list_codex_background_terminals` runs `_guard`, then the record, the experimental gate, the existence read, the raw build with its parse, and the call.

  Both headers still claim narration. `settings_methods.py:4` and `thread_methods.py:4` each say "Each method is a thin narrated main function", and spec §12.3 rows 26 and 28 promise the same.
  Failure: AGENTS.md §2 says every feature's main function gets "short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments". Spec §12.4 item 6 says "Every main function is narrated". A001 requires that a header tells the truth. A human reviewer would write: "These are the feature entry points. Narrate the steps, or the header is lying."

  This is Major, not Blocker, because the base host already has 6 unnarrated thin methods that the owner accepted, such as `read_codex_thread` (`host.py:412`). But those run guard → record → one read. The multi-step methods here are past that precedent.
  Smallest fix:
    - Add 2–4 one-line step comments to each of the 13. A comment such as `# Codex marks this call experimental, so check the host opted in.` or `# The thread must exist; Codex would not refuse an unknown one.` covers the shared steps.
    - Alternatively, narrate at least the multi-step ones: list and clean terminals, search, revert, the MCP listing, and memory status. Then reword both headers to "Each method is a main function; the multi-step ones are narrated."
  Spec IDs: §12.3 rows 26 and 28; §12.4; FR-33

R-V3 [Minor] [header-truth] vidbyte/lib/enums/codex.py:7 — The header says the SDK does not model the nine new enums, but it models most of them
  Evidence: KNOWN EDGE CASES says the nine first-class-feature enums "mirror wire values of Codex's experimental methods, which the stable SDK does not model". The probe `V -I` of `openai_codex.generated.v2_all` finds, among others, `ModeKind` ['plan','default'], `ThreadMemoryMode`, `McpAuthStatus` (including 'bearerToken'), `McpServerStatusDetail`, `McpServerStartupState` and `TurnPlanStepStatus`. `feature_wire.py:19-20` itself imports `ListMcpServerStatusResponse` and `McpServerStatus`, and it parses typed fields at :265-287. Only the turn-settings status (`TurnSettingsUpdateStatus`) is absent.
  Failure: A001 and spec §12.4 item 5 require that every touched module's header still tells the truth. An agent that trusts this line could wrongly conclude that the MCP or memory wire is unmodeled and route it through `CODEX_HOST_UNMODELED_RAW_METHODS`. A reviewer would write: "The SDK has these. Say which enums mirror a generated model and which mirror only wire values."
  Smallest fix: Rewrite the clause. For example: "mirror openai-codex 0.163's generated enums where one exists (ModeKind, ThreadMemoryMode, McpAuthStatus, McpServerStatusDetail, McpServerStartupState, TurnPlanStepStatus) and the experimental wire values where none does (the turn-settings status)".
  Spec IDs: §12.4 (A001 header truth); D-29

R-V4 [Minor] [header-truth] vidbyte/lib/constants/codex_host.py:7 — Two headers promise that no message quotes stderr, but the new worktree failure does, by design
  Evidence: Two headers make the promise:
    - `constants/codex_host.py:7`: "A summary never quotes an exception's own text, stderr, env values or the account email";
    - `errors.py:7`: "No message carries an exception's own text, stderr, env values or the account email".

  The new message breaks it. `CODEX_HOST_WORKTREE_FAILED_MESSAGE` (`codex_host.py:554`) is `"git worktree add exited with code {exit_code}: {detail}"`. `thread_methods.py:314-315` fills `detail` with git's first stderr line, and `:179` raises it through `CodexErrorMapper.error`. Spec INV-29 and EC-34 require exactly that detail, so the code is right and the headers are wrong.
  Failure: A001 and spec §12.4 item 5 require true headers. A future editor who reads "never stderr" could strip the detail (breaking EC-34), or could trust that error text is stderr-free when it is not. A reviewer would write: "Name the one exception in both headers."
  Smallest fix: Add one sentence to both headers: "The one exception is create_codex_worktree's git failure, which shows git's first stderr line cut to CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS (first-class INV-29, EC-34); no log record carries it (INV-9)."
  Spec IDs: INV-29, EC-34, INV-9, NFR-7

R-V5 [Minor] [citations] vidbyte/harnesses/native/codex/skill_functions.py:181 — Six comments and headers cite the wrong spec ID
  Evidence:
    - **D-16 cited for the plan run (four places).** D-16 is "Goal pause, resume, edit and clear go through the raw thread/goal/set…". The places are:
      - `skill_functions.py:181`, the `@intent` "(first-class INV-16, D-16)";
      - `skill_functions.py:4`, ROLE "(first-class D-16)";
      - the RELATED DOCS lines, "D-16", in `skill_functions.py:8` and `settings_methods.py:8`.
      The plan-run decision is D-8 ("run_codex_plan's run lives in CodexSkillFunctions.run_plan").
    - **EC-14 cited for the missing plan preset.** `skill_functions.py:185` reads "a Codex without one gets no thread at all (EC-14)", and `:7` cites "EC-12, EC-14". EC-14 is "a collaboration-mode turn … with no mode or turn model". The missing preset is INV-16 and AC-11, and "the turn's own model wins" is EC-13.
    - **INV-38 cited for the worktree messages.** `constants/codex_host.py:544` says "(first-class INV-38)". INV-38 covers background terminals; the worktree is INV-29.
    - **A split citation.** `stream_methods.py:63-64` breaks "first-class INV-23" into "(first-" and "class INV-23", so grepping for the ID misses it.
  Failure: Spec §12.3 row 4 says "Each block opens with a # comment that cites its INV or D". These citations are how the next agent finds the governing rule, and a wrong ID sends them to an unrelated decision. A reviewer would write: "D-16 is goal origin. This is D-8."
  Smallest fix: Make five edits:
    - change D-16 to D-8 in the four plan-run places;
    - change "(EC-14)" to "(INV-16, AC-11)";
    - change "EC-12, EC-14" to "EC-12, EC-13";
    - change INV-38 to INV-29;
    - re-wrap `stream_methods.py:63-64` so "first-class INV-23" stays on one line.
  Spec IDs: D-8, D-16, EC-13, EC-14, INV-16, INV-29, INV-38, INV-23

R-V6 [Minor] [INV-46] vidbyte/harnesses/native/codex/feature_wire.py:302 — Native function bodies hold message subjects and fixed values that INV-46 places in lib constants
  Evidence:
    - **Inline message subjects.** These strings become the subject of a `ConfigurationError` message:
      - `feature_wire.py:302`: `"Codex memory status consolidated_threads"`;
      - `feature_wire.py:303`: `"Codex memory status ready"`;
      - `feature_wire.py:338`: `"Codex thread search hit thread"`.
      Their siblings at :253, :294, :310 and :331 build the same kind of subject from method constants instead (`f"{CODEX_THREAD_SEARCH_METHOD} data"`).
    - **Inline fixed values.**
      - `feature_wire.py:192` builds the side-chat boundary item's fixed shape inline: `{"type": "message", "role": "user", "content": [{"type": "input_text", …}]}`.
      - `feature_wire.py:205` hard-codes the `"\n\n"` instruction separator.
      - `feature_wire.py:204` hard-codes the `"."` field-path test. The tools layer names the same idea `THREAD_FIELD_PREFIX`.
      - `preflight.py:97` passes the feature name `"collaboration_mode"` as a literal.

    Wire keys such as `"threadId"` are left out of this count, because base `wire.py` sets that precedent.
  Failure: INV-46 says: "No function body there holds a message text or a field-rule tuple: every fixed value is in vidbyte.lib.constants.codex_host". The owner's #1178 convention (request.md §B.1) says the same: "Every fixed value the native host reads goes in vidbyte/lib/constants/codex_host.py". C021 cannot see non-top-level literals, so only review catches this. A reviewer would write: "Same feedback as #1055: fixed values go in lib."
  Smallest fix:
    - Build the three subjects from method constants, as the siblings do, for example `f"{CODEX_MEMORY_STATUS_METHOD} v2ConsolidatedThreads"`.
    - Move the boundary item template (as a `MappingProxyType`), the separator and the path separator into `codex_host.py`, beside `CODEX_HOST_SIDE_CHAT_BOUNDARY`.
    - Pass a constant, or the `CodexSpawnRequest` field name, at `preflight.py:97`.
  Spec IDs: INV-46; §12.4 item 3; C021

R-V7 [Minor] [canonical-helpers] vidbyte/lib/dataclasses/codex_host_features.py:131 — The new settings record copies the spawn request's sandbox-field check, and two records hand-roll absolute-path checks
  Evidence:
    - **A near-verbatim copy.** `CodexThreadSettingsUpdate._reject_bad_sandbox_fields` (`codex_host_features.py:131-142`) repeats `CodexSpawnRequest`'s network-access and writable-roots rule (`codex_host.py:262-271`), down to the identical `bad_roots = not isinstance(roots, tuple) or any(… os.path.isabs(root) …)` line. Only the message constants differ.
    - **Hand-rolled absolute-path checks with inline messages.**
      - `codex_host_features.py:104-105` checks `cwd` with `os.path.isabs` and raises an inline `f"{owner} cwd must be blank or an absolute path."`.
      - `process.py:117-118` checks with `.is_absolute()` and raises an inline `f"GitWorktreeSpec {name} must be an absolute path; got a relative one."`.

      Neither uses `RecordFieldValidator`. Its `require_directory` (`validation.py:131`) already checks that a path is absolute, but it also requires the directory to exist.
  Failure: AGENTS.md §5 says: "if one is close, add the option you need to it rather than copying it into a variant beside your feature". Field guide `strict-config-dataclasses.md` says: "Call RecordFieldValidator.require_* … When an option is missing (… folder resolution), add it as a keyword with a backward-compatible default." The guide's literal check passes, since there are no `_..._field` helpers. That is why this is Minor and not a Blocker.
  Smallest fix:
    - **In scope:** move the sandbox-field rule into one function in `codex_host.py` that takes the two messages, and call it from both records. Both files are already §12.3 rows.
    - **[scope-adding] follow-up:** add an `exists: bool = True` keyword (or a `require_absolute_path`) to `RecordFieldValidator`, and route the `cwd` and `GitWorktreeSpec` checks through it. This touches `validation.py`, which is outside §12.3.
  Spec IDs: §12.3 rows 8 and 10; D-30; T-5

VERIFIED CLAIMS
1. Lint passes on the reviewed tree. `PYTHONDONTWRITEBYTECODE=1 V lint/run.py` ends `SDK-LINT: PASS`. Every per-rule `--all` scan shows zero findings in the changed files, except A001 on `vidbyte/tools/builtins/__init__.py`. That one predates the diff (its base header is "Context Protocol Header"), and spec row 38 pins its docstring.
2. `CodexHostOperation` has 55 members, and `CodexHostTools.__init__` lists 42 tool classes. Both checked by import. The headers' "forty-two" and "55" are true, and 53 functions − delete − forget − 9 = 42.
3. Every touched file is within INV-47. Checked with `wc -l`: `host.py` 786, `wire.py` 839 (ceiling 840), `lib/dataclasses/codex_host.py` 891, `codex_host_inputs.py` 779, `feature_wire.py` 362, `turn_stream.py` 277, `thread_methods.py` 320 and `lib/constants/codex_host.py` 756.
4. All 31 new dataclasses are frozen, slotted and validated, and the scan found 10 new enum classes. Checked by grep of the added `@dataclass` lines (31 × `frozen=True, slots=True`) and an AST check for `__post_init__` (none missing).
5. The pinned files are untouched and the branch scope holds. `git diff --stat -- REPO_MAP.md vidbyte/harnesses/README.md vidbyte/harnesses/native/__init__.py` is empty. Under `vidbyte/tools` and `vidbyte/lib/configs`, only the 9 allowed paths changed, and no `.pyc` or `__pycache__` file is in the diff.
6. The five SDK-free modules load no SDK at module level. `host_core`, `settings_methods`, `stream_methods`, `thread_methods` and `goal_methods` import no openai-codex, connection, wire, turns, `turn_starts`, `feature_wire` or `turn_stream` module outside `TYPE_CHECKING`. `host._open` (:168-177) imports the SDK modules.
7. The enum header's "the stable SDK does not model" claim is false (R-V3). The `v2_all` probe returns `ModeKind`, `ThreadMemoryMode`, `McpAuthStatus`, `McpServerStatusDetail`, `McpServerStartupState` and `TurnPlanStepStatus`.
8. 14 added comment lines are wider than 72 columns (R-V1). The `git diff -U0` awk scan over added comment lines agrees with a per-file awk scan, line for line.
9. 13 of the 25 new methods have zero body comments (R-V2), and the 6 base precedents are thin guard → record → one-read methods. Checked with an AST and tokenize comment counter on the four mixins and on the base `host.py`.
10. Commit hygiene is clean. Every commit in `a7730107..8ea8734f` carries Co-Authored-By, and all 23 feat and fix commits cite spec IDs.
11. The codex_host test suite passes: `pytest tests/features/codex_host -q` reports 589 passed and 1 skipped.

COMMANDS RUN
- `git diff a7730107...8ea8734f --stat`, plus per-file `git diff` for every changed native, lib and tools module, with output piped through `tr -d '\r'`.
- `git diff -U0 a7730107...8ea8734f -- 'vidbyte/*.py' | awk …` to scan added comment lines over 72 columns, then the per-file `awk '/^[ \t]*#/ && length($0) > 72'`.
- `git diff --stat` and `--name-only` on the pinned files, `vidbyte/tools` and `vidbyte/lib/configs`, plus a grep for `.pyc`, `__pycache__`, `.orig` and `.rej`.
- `git log a7730107..8ea8734f --format=…`, plus a per-commit body check for Co-Authored-By and spec IDs.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 V lint/run.py`, and earlier the per-rule `V lint/run.py --rule X --all`, grepped for the changed files.
- `V -I scratchpad/s4-slice2/narration.py` on the four mixins and the base `host.py` (AST comment counter).
- `V -I scratchpad/s4-slice2/chains.py` on the new native, lib and tools modules (two-level helper chains and nested functions). The only hits are `subscribe → _read → …`, which spec row 18 designs, and the house `execute → _perform` tool wrapper.
- `V -I -c "from openai_codex.generated import v2_all …"` to probe for the enum models.
- `V -c "…len(CodexHostOperation)…"` and an `inspect` count of `CodexHostTools`.
- `wc -l` on the touched modules; grep of headers for TESTS paths, count words and narration claims; grep of the spec for the INV, D and EC rows cited above.
- `PYTHONPATH=. V -m pytest tests/features/codex_host -q -p no:cacheprovider -x`.
- `git status --porcelain` and `git log 8ea8734f..HEAD`, to confirm the tree is clean apart from reports and that HEAD differs only in `pipeline.md`.
