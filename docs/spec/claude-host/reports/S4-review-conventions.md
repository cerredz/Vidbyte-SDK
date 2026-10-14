LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, headers, exports, tool contracts, shared files and lint are clean, but `ClaudeLiveSession` breaks AGENTS.md principle 1, the SDK converters use the reflection-with-empty-defaults pattern the field guide rejects, and 69 code comments rely on spec IDs while the policy vocabulary stays as private harness literals.

WHAT THE IMPLEMENTATION GETS RIGHT

- Placement and records. All 23 records are `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/claude.py` and `claude_host.py`, and each has a `__post_init__`. The 17 enums are in `vidbyte/lib/enums/claude.py` and exported. Bounds and next steps are in `vidbyte/lib/constants/claude.py`. No new harness, tool or record file has a numeric literal other than 0 or 1, and `CLAUDE_FAILURE_NEXT_STEPS` covers exactly the 16 `claude.*` codes.
- Layering. `claude_agent_sdk` is imported only in `ClaudeSdkLoader.load`, and importing the harness and the toolset leaves it unloaded. The tools import `ClaudeHost` only under `TYPE_CHECKING`. The one module-level function is the SDK-required `_image_prompt`. There are no nested defs and no `print` calls.
- Tool contracts. The 28 descriptions are single literals of 4–5 sentences with no example markers. Every schema is closed through one `_spec` (`additionalProperties: False`). Error results are built from `failure_code`, `reason` and `next_step`, never from exception text. `ClaudeTools(Tools)` has a static `get_tools`, as prebuilt-agents.md:5 asks.
- Shared files and comments. The changed files are exactly the 31 rows of §12.3. Shared edits only insert lines (140 added, 0 removed) and keep sorted order. The REPO_MAP and harnesses README inserts match request.md §C byte for byte. The marker blob's SHA-256 matches. No added comment line passes 72 columns, and `lint/baseline.json` is untouched.

FINDINGS

R-V1 [Blocker] [field-guide: class-bound-helpers] vidbyte/harnesses/native/claude/history.py:83-96, vidbyte/harnesses/native/claude/session.py:257-350 — The SDK record converters read the pinned 0.2.165 records through `vars()` with empty defaults, so a renamed or removed field becomes "" or None instead of `claude.protocol_mismatch`
  Evidence:
  - history.py:85 has `fields = vars(info)`, and :88 has `summary=fields.get("summary") or "",`. The pinned SDK declares this field required (`claude_agent_sdk/types.py:1767 summary: str`), and :87 and :89 read the other two required fields by subscript.
  - In the same file, `fork` reads the SDK result directly: history.py:77 `forked: str = result.session_id`.
  - session.py:285 has `result_text=fields.get("result") or "",`, and :290-291 have `stop_reason=fields.get("stop_reason") or "",` and `terminal_reason=fields.get("terminal_reason") or "",`. Also :314 `kind = vars(message).get("error")` and :321 `kind = info.get("rate_limit_type")`.
  - The converters take `message: object` or `info: object` (session.py:257, 312, 318, 338; history.py:83, 100). The `_on_*` handlers also change session state, so they are not plain wire constructors.
  Failure:
  - class-bound-helpers.md:26-27: "Read the pinned SDK's fields directly; preserve missing values …" and "Generic reflection with empty defaults masks contract drift". This lesson comes from the owner's review of PR #409.
  - strict-config-dataclasses.md:43 allows a `: object` parameter only on an SDK-dictated callback or a documented wire constructor.
  - The extra allows any version below 0.3.0. If a later 0.2.x renames `terminal_reason` or `summary`, the value silently becomes "". It should fail as `claude.protocol_mismatch`, which history.py:7 promises for a malformed record.
  - A reviewer would write: "This is the reflection pattern I rejected in #409. Read the pinned fields, and let drift fail as protocol_mismatch."
  Smallest fix:
  - Read every field the 0.2.165 record declares by subscript, for example `fields["summary"]` and `fields["terminal_reason"] or ""`. Keep `or ""` only where a §8.5 `str` field receives an SDK `str | None`.
  - Keep `.get` only for `description`, because `TaskNotificationMessage` lacks that field (SDK types.py:1229-1250).
  - No other change is needed. The existing guarded `try` already maps the `KeyError` to `claude.protocol_mismatch`, and the S2 fakes declare every one of these fields (claude_host_fixtures.py:266-372), so the pack stays green. No new class or file.
  Spec IDs: EC-16; FR-17

R-V2 [Blocker] [AGENTS.md principle 1] vidbyte/harnesses/native/claude/session.py:233-245, 364-395 — `ClaudeLiveSession` chains its own helpers two to four levels deep, and the S3 report names only one of the chains
  Evidence:
  - The pump: `run` calls `_read` (:170 `prompt = self._take_steer() if await self._read(stream) else None`), which calls `_on_result`, `_on_assistant`, `_on_rate_limit` and `_on_task` (:238-245).
  - The interrupt path: `steer`, `interrupt` and `_watch` (:449, :478, :362) start `_interrupt_client`. It calls `self._start_close()` (:373) and `self._arm_grace(prompt)` (:377). `_arm_grace` starts `asyncio.create_task(self._expire(prompt))` (:383), and `_expire` calls `self._start_close()` (:395).
  - S3-implementer.md:253 admits only the pump chain.
  Failure:
  - AGENTS.md:23: "a function may call another of its own functions, but that second function should not call a third".
  - The same rule appears in spec §12.4 (spec.md:1204) and house-style.md:45. class-bound-helpers.md:47 adds "Keep a linear run of checks in one function instead of single-use helpers".
  - To learn what a steer does when Claude Code never answers, a reader must follow steer → `_interrupt_client` → `_arm_grace` → `_expire` → `_start_close`. A reviewer would write: "Flatten this. You can't read the grace path from steer()."
  Smallest fix:
  - Within the budget: move `_arm_grace` (3 lines, called only at :377) into `_interrupt_client`. Then each coroutine the session schedules calls at most `_start_close`.
  - Needs the spec author: the pump's `run → _read → _on_*` cannot be folded into `run` without breaking S024 (S3-implementer.md:253). A separate reader class would be class 70 against the 69-class §8.4 budget. The spec author must either raise the budget by one class or record the exception in §12.4. The same decision should state whether a coroutine started with `create_task` counts as a new main function.
  Spec IDs: §12.4 Function shape; row 7

R-V3 [Major] [comments: docs/ is opaque] vidbyte/harnesses/native/claude/host.py:160 and 11 more files — 69 added comments and docstrings cite spec IDs or "section 9.2", but no file names the spec, and AGENTS.md tells agents not to open docs/
  Evidence:
  - The added lines hold 69 matches: host.py 31, session.py 12, `_base.py` 7, toolsets/claude.py 5, and 1–2 each in eight more files.
  - Public docstring, host.py:160: `"""Start one Claude Code turn from a request and return its handle at once, while the turn runs in the background (INV-3)."""`
  - `_base.py:41`: `# (D-13, T-2).`
  - dataclasses/claude.py:383: `"""Every setting one Claude Code turn starts with, in the order of the section 9.2 field mapping."""`
  - sessions.py:6: "needs a decision in the spec first (D-13 …)".
  - `git grep 'RELATED DOCS.*docs/spec/claude-host' d9c5fea2 -- vidbyte` prints 0 lines. All of `vidbyte/` on main has 3 such references, and the one with many IDs names its spec (`vidbyte/tools/builtins/bash.py:10`).
  Failure:
  - AGENTS.md:13: "Do not grep, glob, or read files under `docs/` as part of ordinary work". An ID sends the next agent to a document it is told not to read.
  - intent_based_commenting.md:11: "A future agent should not need to search a design doc".
  - The `ClaudeHost` docstrings also show "(INV-3)" to SDK users in `help()` and IDE hovers.
  - A reviewer would write: "What is D-13? Say the rule, not the ticket."
  Smallest fix:
  - Delete the parenthesized IDs; each sentence already states its rule.
  - Replace "section 9.2 order" with the order itself, such as "ClaudeSpawnRequest's field order" or "the order get_tools lists".
  - Where an ID is used as a noun ("the INV-13 error result"), name the thing instead ("the coded error result `_failed` builds").
  - This changes comment and docstring text only.
  Spec IDs: n/a

R-V4 [Major] [constants placement] vidbyte/harnesses/native/claude/failures.py:37-48 — The failure-classification vocabulary and several operation names stay private literals in the harness, against §12.4 and contrary to what deviation 1 says
  Evidence:
  - failures.py:37 `_BUDGET_SUBTYPES = ("error_max_budget_usd", "error_max_turns")`, :40 `_SCHEMA_SUBTYPE = "error_max_structured_output_retries"`, and :43-48 `_ASSISTANT_ERROR_CODES = (("rate_limit", FailureCode.CLAUDE_USAGE_LIMITED), …)`.
  - session.py:60 `_HUMAN_ORIGIN = "human"`.
  - "get_server_info" is written three times (session.py:65 `_INFO_OPERATION`, probe.py:88, probe.py:152). "steer_claude_session" is written twice (host.py:281, session.py:69).
  - session.py:212 reads `info.get("hooks_applied")` three lines above `info.get(CLAUDE_VERSION_FIELD)` (:215). probe.py:139-149 reads ten literal initialize-answer keys.
  - Deviation 1 (spec.md:1477) says "no policy string or field key is a literal in the harness".
  Failure:
  - spec §12.4 (spec.md:1197): "Numeric bounds and policy strings are `CLAUDE_*` constants in `vidbyte/lib/constants/claude.py`".
  - house-style.md:44: "No hardcoded meaningful strings … event kinds, error codes".
  - Codex keeps the same kinds of value in lib: `vidbyte/lib/constants/codex.py:95` `CODEX_FAILURE_CLASSIFICATION` and :189-190 for the wire method names.
  - A reviewer would write: "Why does one operation name live in three files, and why isn't the subtype table next to CLAUDE_FAILURE_NEXT_STEPS?"
  Smallest fix:
  - Move the subtype, assistant-error and origin-kind vocabularies and the session and probe operation names into `vidbyte/lib/constants/claude.py` as `CLAUDE_*` constants. That file is already in the budget, and no class is added.
  - Import them in failures.py, session.py, probe.py and host.py. Then either name the remaining initialize keys there too, or correct the wording of deviation 1.
  - Not part of this fix: typing `ClaudeTurnOutcome.subtype` and `assistant_errors` as enums would change §8.5 and the class budget, so that needs the spec author.
  Spec IDs: §12.4 Placement and layering (constants line); deviation 1

R-V5 [Minor] [AGENTS.md principle 2] vidbyte/harnesses/native/claude/host.py:240-303 — Five ★ functions have no narration, though §12.4 requires it for every ★ method
  Evidence:
  - Comment lines per method, counted from the AST: `get_claude_session_info` (240-246) 0, `wait_claude_turn` (264-270) 0, `get_claude_turn_result` (272-277) 0, `interrupt_claude_turn` (291-296) 0, `track_claude_session_usage` (298-303) 0.
  - `fork_claude_session` (214-224) has a single comment, above its last line.
  Failure: AGENTS.md:27 and spec §12.4 (spec.md:1191), "every ★ method of `ClaudeHost`". The bodies are 5–6 lines long, so this affects clarity only.
  Smallest fix: add one short comment per step: the guard and SDK check, the argument check, and the session call (for example, "Ask the turn for its snapshot; waiting never changes it.").
  Spec IDs: §12.4 Headers and comments

R-V6 [Minor] [@intent] vidbyte/harnesses/native/claude/tool_server.py:34 — One `@intent` slug names two different rules, and one rule appears under four different slugs
  Evidence:
  - `# @intent request-tools-ride-the-vidbyte-mcp-server` appears at options.py:155 for one rule: the server must be named vidbyte. It appears again at tool_server.py:34 for a different rule: the executor allows every permission because Claude Code has already approved the call.
  - The D-13 rule (the model sets only prompts) appears under four slugs:
    - `the-developer-fixes-every-spawn-setting` (`_base.py:37`, on two attribute assignments);
    - `the-model-sets-only-the-prompt` (sessions.py:41);
    - `the-model-sets-only-the-prompts` (sessions.py:111);
    - `the-base-request-defaults-to-an-empty-request` (toolsets/claude.py:45), a slug that restates the line below it.
  - S3-implementer.md:261 says these blocks were added because A002 flags `_request` and `permission`.
  - `_check_prompting` (dataclasses/claude.py:515-519) states one rule, then adds "The system prompt options and images must fit too."
  Failure: intent_based_commenting.md:62: "Keep the name short, searchable, and specific". Main reuses one slug for one rule across many sites (`null-optional-arg-means-default` 20 times). Searching a slug should land on exactly one rule.
  Smallest fix:
  - Give tool_server.py:34 a slug that names its own rule, for example `claude-code-approves-before-vidbyte-runs`.
  - Use one slug for the D-13 rule at all four sites.
  - Move the system-prompt and image checks in `_check_prompting` under a plain comment instead of the intent block.
  - This changes comments only.
  Spec IDs: §12.4 Headers and comments (A002 line)

R-V7 [Minor] [house style: dispatch] vidbyte/harnesses/native/claude/history.py:108-115 — The transcript converter uses a three-case if/elif ladder on one value
  Evidence: `if kind == "text": … elif kind == "tool_use": … elif kind == "tool_result": … else: parts.append(f"[{kind}]")`
  Failure: spec §12.4 (spec.md:1206): "dispatch by dict or small per-kind helpers, not if-ladders"; house-style.md:46.
  Smallest fix: use `match kind:` with the three cases and `case _:` as the default.
  Spec IDs: §12.4 Function shape

R-V8 [Minor] [dead code] vidbyte/lib/dataclasses/claude.py:118-122 — `_ClaudeFieldRules.whole` has no caller and repeats the bool guard in `count`
  Evidence: `grep -rn -w whole` over the claude records, harness, tools and tests finds only the definition (:119-122). Its check `isinstance(value, bool) or not isinstance(value, int)` repeats :127.
  Failure: spec §12.4 (spec.md:1214): "Each meaningful `isinstance(x, bool)` guard is written once".
  Smallest fix: delete `whole`.
  Spec IDs: §12.4 Records and validation

R-V9 [Minor] [scope-adding] vidbyte/tools/README.md:89-91 — The tools README that the new headers cite still lists the builtin groups and toolsets without the Claude ones
  Evidence: README:89 reads "`builtins/`: a minimal subprocess bash tool, code search, context, …", and :91 reads "`toolsets/`: … including `CodingAgentTools`". readiness.py:8, history.py:8, `_base.py:9` and toolsets/claude.py:8 all name this README under RELATED DOCS.
  Failure: AGENTS.md:11 says each folder's README documents that folder. §12.5 does not require this edit, and it would touch a new shared file, so it belongs in a follow-up.
  Smallest fix: a follow-up PR adds "Claude Code host tools" to :89 and `ClaudeTools` to :91.
  Spec IDs: n/a

VERIFIED CLAIMS:
- Deviation 1, "no policy string or field key is a literal in the harness": DID NOT HOLD. See R-V4: probe.py:88 and :139-152, session.py:60, :65-69 and :212, failures.py:37-48.
- §12.4 "every ★ method of ClaudeHost" is narrated: DID NOT HOLD. Five methods have no comments (R-V5).
- §12.4 "Call chains are one level deep": DID NOT HOLD. S3's tricky-parts note (S3-implementer.md:253) is accurate but incomplete (R-V2).
- Deviation 9, `_optional_argument` already exists and treats null as omitted under the same `@intent`: HELD. origin/main `vidbyte/tools/base.py:111-116` carries `# @intent null-optional-arg-means-default`.
- Deviation 11, every added comment line fits in 72 columns: HELD. The field-guide awk check prints 0 lines across all 22 new files and the added diff lines.
- §8.4 budget of 22 files and 69 classes: HELD. There are exactly 22 added `vidbyte/*.py` files and 69 added `class` lines, and every file is under 1,000 lines (largest: dataclasses/claude.py at 578).
- Files touched match §12.3: HELD. `comm -3` between the 31 row paths and the changed non-test, non-pipeline files is empty.
- Shared-file contract: HELD.
  - The marker blob SHA-256 is `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
  - The 16 CLAUDE_* codes sit between `CONFIGURATION_INVALID_ARGUMENT` and `CODEX_SDK_UNAVAILABLE`.
  - The REPO_MAP and README texts match request.md byte for byte, and the README is 8,840 characters.
  - The ten shared files only gain lines (140 insertions, 0 deletions), at sorted positions.
  - `pyproject.toml`'s `claude` list mirrors `codex`'s.
- Lint, "no new findings": HELD. `lint/run.py` reports SDK-LINT: PASS, with 0 findings in any new file. All 47 findings in shared files sit on lines older than this branch. Ruff I001 on `errors/__init__.py` also fails on main's blob.
- `CLAUDE_FAILURE_NEXT_STEPS` covers exactly the 16 codes: HELD (16 = 16). Importing the harness and the toolset leaves `claude_agent_sdk` unloaded: HELD.
- S3 pack result of 165/165: HELD. 165 passed in 5.17 s, on fakes only; `claude_agent_sdk` is not installed in that interpreter, so no real `claude` could start.
- Commit hygiene: HELD with notes.
  - The 34 implementation commits (34f27cdc..5edf1a4d) are atomic per row, and their subjects use §14's `type(scope): summary [W-…; FR-…]` form.
  - Four of them are in-branch fixups: e7382a26, f0c84cd0, dceb2dfe (lint-driven `@intent` markers) and 5edf1a4d (comment rewrap).
  - HEAD has since moved to cdf44876, which changes only pipeline.md, so the source is unchanged from d9c5fea2.

COMMANDS RUN:
- `git diff origin/main...d9c5fea2 --stat -- <10 shared files>` → `10 files changed, 140 insertions(+)`
- `git log --format='%h %an %s' origin/main..d9c5fea2` → 51 commits; last line `f86759a2 cerredz docs(spec): add claude-host request capture, recon, and pipeline state`
- `git log d9c5fea2..HEAD; git diff --stat d9c5fea2 HEAD` → `cdf44876 … record claude-host S3 done and S4 start in pipeline.md`; `1 file changed`
- `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W python lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS` (exit 0)
- `python lint/run.py --all --format json`, filtered to changed paths → `findings in changed files: 47`. All are in shared files (A001 builtins/__init__:1 and toolsets/__init__:1; A002, A003 and S062 in errors/base.py outside 198-228; C015 pyproject.toml:74; S051 errors/__init__:22). There are none in new files.
- `git show origin/main:vidbyte/lib/errors/__init__.py | python -m ruff check --no-cache --config lint/ruff.toml --select I001 --stdin-filename … -` → `Found 1 error.` (same on HEAD)
- `git diff origin/main...d9c5fea2 -- vidbyte | grep '^+' | grep -E '^\+\s*#' | awk 'length($0) > 73' | wc -l` → `0`. The per-file `awk 'length($0) > 72'` check on the 22 new files also prints 0.
- `git diff … | grep -o '# @intent [a-z0-9-]+' | sort | uniq -c | awk '$1>1'` → `2 # @intent request-tools-ride-the-vidbyte-mcp-server`; 28 added in total
- Spec-ID grep on added lines → `69`. The same grep on origin/main `vidbyte/*.py` → `3`. `git grep 'RELATED DOCS.*docs/spec/claude-host' d9c5fea2 -- vidbyte | wc -l` → `0`
- `git show origin/main:vidbyte/tools/base.py | grep -n -A8 'def _optional_argument'` → `111: def _optional_argument(…)` / `112: # @intent null-optional-arg-means-default`
- `git show d9c5fea2:vidbyte/harnesses/native/__init__.py | sha256sum` → `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a *-`
- `git diff --stat origin/main...d9c5fea2 -- lint/` → (empty)
- `git diff --diff-filter=A --name-only … -- 'vidbyte/*.py' | wc -l` → `22`; added `class` lines → `69`; `comm -3` against the §12.3 row paths → (empty)
- Byte comparison of the REPO_MAP and README inserts with request.md → `REPO_MAP text: byte-equal` / `README bullet: byte-equal` / `README chars: 8840`
- `python -m pytest tests/features/claude_host -q -p no:cacheprovider` (PYTHONDONTWRITEBYTECODE=1) → `165 passed in 5.17s`
- `python -c "…CLAUDE_FAILURE_NEXT_STEPS… sys.modules"` → `codes 16 mapping 16 equal True` / `sdk loaded after harness/tool imports: False`
- Description check (sentence split, example markers) → `28 descriptions; sentence counts: {4: 27, 5: 1} ; example markers: none`
- AST scans of the 22 new files → `nested defs: none` / `print calls: none`. Numeric literals other than 0 and 1: none. Bodies over 40 lines: session `__init__` 57, `sdk.load` 54, `_on_result` 52, `run` 49. Per-method comment counts for ClaudeHost are as in R-V5.
- `grep -rn -w whole vidbyte/lib/dataclasses/ vidbyte/harnesses/native/ vidbyte/tools/builtins/claude/ tests/features/claude_host/` → only `vidbyte/lib/dataclasses/claude.py:119-122` within the claude files
- `git show origin/main:vidbyte/lib/constants/codex.py | sed -n '86,112p'` → `CODEX_FAILURE_CLASSIFICATION: Mapping[str, tuple[str, str, str, str]] = {`
- SDK 0.2.165 `types.py` (read-only extract) → `1767: summary: str`; `1349: stop_reason: str | None = None`; `1363: terminal_reason: str | None = None`. `TaskNotificationMessage` has no `description` field.
