LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the code follows AGENTS.md placement, layering, literal policy and every zero-headroom ratchet. But it adds four A002 intent-comment findings that §12.4 says to close, and its REPO_MAP entry breaks the map's "code-free" rule. Neither changes behaviour.

Reviewed: `git diff origin/main...0a2752dd` (merge base `b28c3027`; origin/main has since moved to `c04e5ef5`, and the three-dot diff is unchanged). Lint counts are compared with `b28c3027:lint/baseline.json`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- Nothing of #1044's rejected host stack survives, per field guide `review-scope.md`. Zero tracked files remain under `docs/spec/claude-host`, `tests/features/claude_host`, `vidbyte/tools/builtins/claude` and `vidbyte/tools/toolsets/claude.py`. `pyproject.toml`, `vidbyte/tools`, `vidbyte/lib/errors/__init__.py`, `vidbyte/lib/configs`, `vidbyte/__init__.py`, `contracts/`, `.env.example`, `llms.txt` and `artifacts/` are absent from the three-dot diff. `git grep` finds `ClaudeHost`, `claude_agent_sdk`, `ClaudeOperationError` and `ClaudeTools` only in test guards and spec records.
- Placement and exports match AGENTS.md:
  - The three new enums are `StrEnum`s in `vidbyte/lib/enums/native_threads.py`, exported from `vidbyte/lib/enums/__init__.py`.
  - `ClaudeThreadConfig` is `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/native_threads.py`. Each check names `ClaudeThreadConfig.<field>`, and the timeout bound comes from the constants package (`strict-config-dataclasses.md`).
  - The public functions are static methods bound in the package init (`class-bound-helpers.md`), with one guarded try in `_call` (`provider-api-contracts.md`).
  - I001 is clean on every touched path.
- The literal policy and layering hold:
  - `test_harness_threads_static_policy.py` names all three `claude/*.py` modules and `hostkit/folders.py`, and passes.
  - A006 is 34/34 and A007 is 255/255.
  - Every flag is a `ClaudeFlag` member, every child variable a `NativeEnvironmentVariable` member, and every new constant is used.
  - Semgrep reports 0 findings on the touched files.
- The zero-headroom ratchets and the comment format are respected:
  - S008 19/19 (`ClaudeWire.read` C901 = 8), S009 350/350, S015 13/13, S017 79/79, S019 5/5, S051 259/259, C006 104/104, C008 45/45.
  - `lint/` is unchanged against `b28c3027`.
  - No added `#` line under `vidbyte/` is wider than 72 columns.
  - Every module header that counted harnesses now names Claude Code. No stale "Grok, opencode and Muse" remains under `vidbyte/`.

FINDINGS (ranked, most severe first, max 15)

R-V1 [Major] [agentic-engineering / lint A002 / §12.4] vidbyte/harnesses/native/claude/threads.py:67, :91; vidbyte/harnesses/native/claude/wire.py:38; vidbyte/lib/dataclasses/native_threads.py:229 — Four new policy-bearing functions ship without the `# @intent` block that §12.4 requires
  Evidence:
  - `python lint/run.py --rule A002 --all --format json` lists:
    - `claude/threads.py 67 _call {'categories': 'external boundaries'}`
    - `claude/threads.py 91 execute {'categories': 'external boundaries, fallback, redaction'}`
    - `claude/wire.py 38 read {'categories': 'external boundaries'}`
    - `lib/dataclasses/native_threads.py 229 __post_init__ {'categories': 'permissions'}` (this is `ClaudeThreadConfig`)
  - I ran `lint.rules.a002_intent_comments.IntentAnalyzer` over the native-thread files at both commits (scratchpad `s4conv_a002_cmp.py`): `b28c3027 TOTAL 19` → `0a2752dd TOTAL 23`. The whole-tree count is now 578, so main's is 574. The ratchet still says PASS only because the baseline has headroom (703).
  - A related gap: `vidbyte/lib/dataclasses/native_threads.py:139-141` explains Claude's lowercase-UUID thread-id rule in a plain comment. That rule is the control that stops `--resume` from matching a session title or a transcript path (D-8, T-1). Its block sits above the `if` at :142, not above the line it explains (:143), and it has no `@intent`.
  Failure:
  - §12.4 says "each load-bearing policy block opens with `# @intent <name>` within 20 lines of the function's start (`NativePrivateFolders.prepare`, `ClaudeThreadRun._environment`, `_inherited_names`, `_argv` and any other function A002 flags)". Row 19's "`@intent` blocks only on `_environment`, `_inherited_names` and `_argv`" contradicts this, and the implementer followed row 19.
  - Field guide `class-bound-helpers.md` says: "`A002 intent-comments` passes, since a new boundary function needs its own `@intent` block". `comment-format.md` says: "Put each block directly above the code it explains."
  - The rules these four functions carry are real and survive only in the file headers today:
    - `read` never judges success by `subtype`, because Claude Code reports "success" on a 401.
    - `execute` registers the key for scrubbing before any vendor text is read.
    - `_call` lets cancellation through and keeps raw exception text out of messages.
    - `ClaudeThreadConfig` converts the permission mode into a closed enum that has no approve-everything member.
  - The brief counts a per-rule count that worsens against main as a finding even when the run passes.
  - Not a Blocker: Grok's `_call`, `execute` and `read`, and `GrokThreadConfig.__post_init__`, carry the same four findings on main, so the code follows its sibling's grain.
  Smallest fix:
  - Add a 2–4 line `# @intent <name>` block, at most 72 columns, as the first comment of each of the four functions:
    - `claude-call-errors-stay-typed` in `_call`
    - `claude-key-scrubbed-before-vendor-text` in `execute`
    - `claude-success-never-from-subtype` in `read`
    - `claude-permission-mode-is-closed` in `ClaudeThreadConfig.__post_init__`
  - Move the :139-141 block directly above :143 and open it with `# @intent claude-thread-ids-are-uuids`.
  - Check: `python lint/run.py --rule A002` reports 574, and the AST count for these files returns to 19.
  Spec IDs: §12.4 (`@intent` line), §12.3 row 19, FR-15, D-8

R-V2 [Major] [field guide agents-md-map.md / REPO_MAP] REPO_MAP.md:161 — The map entry for `vidbyte/harnesses/native/` gains six code references in a map that calls itself code-free
  Evidence:
  - The new paragraph adds `` `run_claude_thread` ``, `` `continue_claude_thread` ``, `` `fork_claude_thread` ``, `` `~/.vidbyte/claude-configs/` ``, `` `--setting-sources user` `` and `` `CLAUDE.md` ``, plus a sentence on vendor behaviour.
  - REPO_MAP.md:7 says "`llms.txt` — … code-heavy where this Map is code-free". REPO_MAP.md:3 says "nothing that isn't derivable from the tree itself".
  - An awk count over main's REPO_MAP finds 88 of 92 folder entries with no backtick at all. This entry had 2 code references on main and has 8 now.
  Failure:
  - Field guide `agents-md-map.md` (the File Index now lives in REPO_MAP.md, per AGENTS.md "Repository Map") says: "no backtick-quoted file names, no child-folder path references, no shell/CLI commands … Check: No folder-heading description contains a backtick-quoted file name, a `.py`/`.md` … extension, a child-folder path, or a literal command".
  - The owner's words on PR #334 were "folder description should [not] have any files names or commands … Rework all of the sections". A reviewer would ask for the Claude sentences in plain words.
  - Note for the verifier: spec AC-23 itself demands these tokens, and `test_harness_threads_claude_acceptance.py:154` pins them (`(*FUNCTIONS, "claude-configs", "--setting-sources user")` in the REPO_MAP native section). The spec contradicts the field guide, and the implementer followed the spec. #1036's merged version of the same entry already had 2 references, which argues against Blocker.
  Smallest fix:
  - Reword the Claude sentences of REPO_MAP.md:161 in plain words. For example: "…or a private Claude Code config folder under the user's home, with every inherited Anthropic and Claude variable left out…; Claude Code also reads settings only from that private folder, so a workspace's own settings, hooks, MCP servers, instructions and skills never load."
  - Leave the function names and the flag to `vidbyte/harnesses/README.md`, which already carries them.
  - This needs an approved test edit: limit the token loop at `test_harness_threads_claude_acceptance.py:153-155` to the README. AC-23 then changes to match. If test edits are not approved, record the conflict as a follow-up for the user instead.
  Spec IDs: AC-23, FR-15, §12.3 row 30

R-V3 [Minor] [AGENTS.md principle 5 / house style] vidbyte/harnesses/native/claude/threads.py:135 — `ClaudeThreadRun._fallback` copies `GrokThreadRun._fallback` (grok/threads.py:131) with only the constants changed. That is the same duplication D-15 gave as the reason to extract `NativePrivateFolders`.
  Evidence:
  - Both bodies are `suffix = NATIVE_WINDOWS_EXECUTABLE_SUFFIX if sys.platform == NATIVE_WINDOWS_PLATFORM else ""; try: return Path.home().joinpath(*<FOLDERS>, <PROGRAM> + suffix) except RuntimeError: return None`.
  - Only `GROK_HOME_FOLDERS`/`GROK_PROGRAM` versus `CLAUDE_INSTALL_FOLDERS`/`CLAUDE_PROGRAM` differ.
  Failure:
  - AGENTS.md principle 5 says "whenever a canonical helper … would save writing the same logic a second time, build it that way".
  - The spec's own D-15 says "leaving Grok's copy would keep a duplicate that the PR itself creates". The PR applied that rule to `_prepare_home` but not to the fallback path, which a reviewer will notice.
  Smallest fix:
  - Add one helper next to `NativeLauncher.resolve` in `hostkit/launcher.py`, for example `NativeLauncher.home_fallback(parts, program) -> Path | None`. Call it from both `execute` methods and delete both `_fallback` methods.
  - Row 19 prescribed the copy, and §14 makes hostkit changes ask-first, so this needs orchestrator approval. Otherwise it is a follow-up.
  Spec IDs: §12.3 row 19, D-15, INV-20

R-V4 [Minor] [readability / headers] vidbyte/harnesses/README.md:178; vidbyte/harnesses/native/hostkit/folders.py:5, :9 — Spec IDs from two different specs appear side by side, and neither spec is named
  Evidence:
  - The README bullet cites #1036's `(EC-27)` for Grok's skills race, `(EC-39)`, `(EC-43)`, `(EC-44)` and `(T-6)`, next to this spec's `(EC-9)`, `(EC-10)`, `(EC-20)`, `(EC-21)`, `(EC-22)`, `(EC-28)`, `(EC-30)`, `(EC-37)` and `(T-4)`. In this spec, EC-27 is "a prompt longer than 24,000 characters on win32" and T-6 is "a planted program", so the bullet's EC-27 and T-6 resolve to the wrong rows if read against this spec.
  - `hostkit/folders.py:5` says "(spec INV-16)" for the literal policy. Its siblings `hostkit/errors.py:5` and `hostkit/launcher.py:5` say "(spec INV-15)" for the same policy.
  - `folders.py:9` cites "spec EC-31" and "spec EC-21" (this spec's IDs), although the module also serves Grok, whose race is EC-27 of #1036.
  - The bullet grew from 2,165 to 5,146 characters on one line, which makes the mix harder to read.
  Failure:
  - AGENTS.md makes `docs/` opaque, so an ID a reader cannot resolve is noise, and an ID that resolves to the wrong row misleads.
  - House style says "write for the second reader". The agentic-engineering `file_headers.md` deep-dive asks for accurate headers.
  Smallest fix:
  - Qualify every new spec ID with its spec (for example "claude-thread-functions EC-21") or replace it with the plain words it stands for.
  - In `hostkit/folders.py`, write "(the literal policy of the harness thread specs)" instead of "(spec INV-16)", and cite the race by description.
  Spec IDs: FR-15, §12.3 rows 29 and 32

R-V5 [Minor] [placement rules / enums over literals] vidbyte/lib/constants/native_threads.py:144 — An environment variable name is held as a raw string, while `NativeEnvironmentVariable` is the closed vocabulary of child variable names
  Evidence:
  - `CLAUDE_INHERITED_ENVIRONMENT_KEPT = frozenset({"CLAUDE_CODE_GIT_BASH_PATH"})`.
  - The enums header defines `NativeEnvironmentVariable` as "the child environment variable names", and Muse removes its variable as `NativeEnvironmentVariable.META_API_KEY.value`.
  Failure:
  - AGENTS.md says "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum". This is #1036's resolved comment "define enums for flags/hardcoded strings" (KD-6).
  - §8.5 prescribed the literal. Adding a member is ask-first under §14, and it changes the `EXPECTED_ENUMS["NativeEnvironmentVariable"]` pin.
  Smallest fix:
  - Add `NativeEnvironmentVariable.CLAUDE_CODE_GIT_BASH_PATH` and write `frozenset({NativeEnvironmentVariable.CLAUDE_CODE_GIT_BASH_PATH.value})`.
  - This needs orchestrator approval for the enum member and the surface pin. Otherwise it is a follow-up.
  Spec IDs: INV-16, §8.5, FR-13

R-V6 [Minor] [function design] vidbyte/harnesses/native/claude/wire.py:117, :87 — `_missing_member` takes a `text` parameter it never reads, and `read` states the "which id do we report" rule twice
  Evidence:
  - `python -m ruff check vidbyte/harnesses/native ... --isolated --select ...,ARG` reports `ARG004 Unused static method argument: text --> vidbyte\harnesses\native\claude\wire.py:117:76`. The call site is :75.
  - :52 `newest = request.thread_id if request.verb is NativeThreadVerb.CONTINUE else session`
  - :87 `thread_id = request.thread_id if request.verb is NativeThreadVerb.CONTINUE and request.thread_id is not None else session`. The two lines differ only so that mypy can narrow the type, and nothing says so.
  Failure:
  - Agentic-engineering `function_design.md` and house style call for honest signatures and "obvious over clever". A reviewer will ask why `text` is passed, and why the final id is computed differently from `newest`.
  - The spec records the unused parameter as S3 deviation 2, so it is known, not hidden.
  Smallest fix:
  - Drop `text` from `_missing_member` and from its call at :75. The body only ever returns `CLAUDE_RESULT_FIELD` as the last case.
  - Add one comment line at :87 saying the `is not None` exists to narrow the type for `NativeThreadResult`.
  Spec IDs: §8.5 (`_missing_member` signature), §12.3 row 20

VERIFIED CLAIMS:
1. **Held.** S3: "Zero-headroom ratchets all at baseline: S008 19/19, S009 350/350, A007 255/255, S015 13/13, S051 259/259, S017 79/79, S019 5/5, A006 34/34, C006 104/104, C008 45/45". My `python lint/run.py` shows exactly these. A001 is 641/642.
2. **Partly held.** S3: "A002 579/703 … the four new findings are the Claude copies of Grok's `_call`, `execute` and `read` pattern". There are 4 new findings, confirmed by symbol, but the count is now 578 against main's 574, and the fourth finding is `ClaudeThreadConfig.__post_init__`, not a copy of `read`. That is R-V1.
3. **Held.** S3 and NFR-4: "`lint/baseline.json` untouched". `git diff --stat b28c3027 0a2752dd -- lint/` prints nothing.
4. **Held.** S3 and §12.4: "`ClaudeWire.read` is ruff C901 complexity 8". `ruff --select C901 --config lint.mccabe.max-complexity=1` reports `read is too complex (8 > 1)`.
5. **Held.** AC-19 and §12.4: the literal policy covers `claude/*` and `hostkit/folders.py`. `NAMED_MODULES` lists all four, and the static-policy test passes (48 passed with surface, claude_surface and claude_acceptance).
6. **Held.** NFR-3: `claude/*.py` is 360 lines or fewer. `wc -l` gives 22 + 190 + 148 = 360. NFR-7 also holds: the constants file is 518 lines (≤ 600).
7. **Held.** §12.5: "`llms.txt`, `artifacts/file_index.md`, `contracts/`, `vidbyte/lib/README.md`: no change". `git grep` finds no native-thread name in any of them, and none is in the diff.
8. **Held.** §12.4: "Imports sorted (`ruff --select I001` clean for the touched files)". The whole-tree run (223 pre-existing findings) has none in a touched path.
9. **Held.** §12.4: comments ≤ 72 columns. No added comment line under `vidbyte/` is wider. Six added comment lines in S2's test files are 73–74 characters (for example `test_harness_threads_claude_process_bounds.py:89`, `test_harness_threads_surface.py:127`), where the pack had none before. This is cosmetic and is not filed.
10. **Held.** §12.4: "every header that counts harnesses or functions is updated". `git grep` for "Grok, opencode and Muse", "nine … functions" and "three harness" under `vidbyte/` finds only the updated `runner.py` wording.
11. **Held.** §12.4, prebuilt-agents: no new dependency and no SDK CLI command. `pyproject.toml` and `vidbyte/cli` are absent from the diff.
12. **Held.** NG-11: the failure vocabulary still works. `PYTHONPATH=$(pwd) python scripts/test-session-failure-vocabulary.py` → `45/45 tests passed`.
13. **Held.** Test pack index: every file in `tests/features/harness_threads/` is named in its README, and every test file in FEATURE.md.
14. **Held for S3's own commits.** Commit hygiene: S3's 33 row commits each cite W-/FR-/INV-/AC- IDs and end with the `Co-Authored-By: Claude Opus 5.5` trailer. No cache, `.pyc` or generated file is in the diff. The only key-like string is the test placeholder `sk-ant-placeholder-key-0003`. Two docs-only commits lack the trailer: `adbffcfe` (orchestrator) and `6a9b94f1` (S2). They cannot be fixed without rewriting pushed history, so this is not filed.

COMMANDS RUN:
- `git diff origin/main...0a2752dd -- vidbyte/harnesses REPO_MAP.md` and `-- vidbyte/lib` → read every hunk; I also opened the whole of each new module.
- `PYTHONPATH=$(pwd) python lint/run.py` → `S064 RATCHETED: 4 known finding(s) …` / `SDK-LINT: PASS` (exit 0). IMPROVED: A001 641/642, A002 578/703, C011, C012, S001, S010, S025, S061, S063.
- `PYTHONPATH=$(pwd) python lint/run.py --rule A002 --all --format json` → 3 findings in `claude/*.py` and 1 in `ClaudeThreadConfig.__post_init__`.
- `python s4conv_a002_cmp.py b28c3027 0a2752dd` (IntentAnalyzer over `git show` sources, read-only) → `b28c3027 TOTAL 19` / `0a2752dd TOTAL 23`.
- `git diff --stat b28c3027 0a2752dd -- lint/` → empty.
- `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache --output-format concise | grep <touched paths>` → none, then `Found 223 errors.` (pre-existing).
- `python -m ruff check vidbyte/harnesses/native vidbyte/lib/{dataclasses,constants,enums}/native_threads.py --config lint/ruff.toml --no-cache` → `All checks passed!`
- `python -m ruff check … --isolated --select C901,PLR0912,PLR0915,ARG` → `ARG004 Unused static method argument: text --> vidbyte\harnesses\native\claude\wire.py:117:76` / `Found 1 error.`
- `python -m ruff check vidbyte/harnesses/native/claude vidbyte/harnesses/native/hostkit/folders.py --isolated --select C901 --config "lint.mccabe.max-complexity=1"` → `read is too complex (8 > 1)`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/test_harness_threads_static_policy.py …_surface.py …_claude_surface.py …_claude_acceptance.py` → `48 passed in 3.62s`.
- `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte/harnesses/native vidbyte/lib/{dataclasses,constants,enums}/native_threads.py` (semgrep venv on PATH, `PYTHONUTF8=1`) → `Ran 1 rule on 22 files: 0 findings.`
- `PYTHONPATH=$(pwd) python scripts/test-session-failure-vocabulary.py` → `45/45 tests passed`.
- `git grep -n -I -E "ClaudeHost|claude_host|claude_agent_sdk|ClaudeOperationError|ClaudeTools|…" 0a2752dd -- . ':!docs/spec/claude-thread-functions'` → only `docs/spec/harness-thread-functions/*`, `docs/design/codex-harness-agent.md`, `skills/runtime-primitives/SKILL.md:30` (unrelated, as on main) and the test guards.
- `git ls-tree -r --name-only 0a2752dd -- docs/spec/claude-host tests/features/claude_host vidbyte/tools/builtins/claude vidbyte/tools/toolsets/claude.py | wc -l` → `0`.
- `git log --no-merges … --not origin/main` with a trailer check → `NO TRAILER adbffcfe`, `NO TRAILER 6a9b94f1`.
- An awk count of REPO_MAP folder entries with backticks at `b28c3027` → `4 HAS_BACKTICK`, `88 clean`.

FOLLOW-UPS FOR THE USER (not for the repair loop)
- Q-1, internal helper: `NativePrivateFolders.prepare(request, errors, *, parts, key_hex_chars, skills_dir, unknown_detail, failure_detail)` takes five layout primitives at every call site. If the user answers Q-1 "yes, dataclass inputs everywhere", a frozen `NativePrivateFolderLayout` record belongs in the same cross-harness change. Not filed, per the orchestrator's decision 6.
