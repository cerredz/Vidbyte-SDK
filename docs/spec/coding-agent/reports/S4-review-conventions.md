LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the PR passes the lint ratchet, the CI gates and every §12.3/§12.4 line, but it puts a tool view in the agents layer against the repo's grain, and three model-facing or documentation texts say things the code does not do.

Code under review: `git diff origin/main...4e285d91` (merge base `8f23fd67`). HEAD `6345baa2` adds only `docs/spec/coding-agent/pipeline.md`; it was ignored as the briefing asked.

WHAT THE IMPLEMENTATION GETS RIGHT
- The PR adds zero lint findings. In `python lint/run.py --all --format json`, `vidbyte/agents/coding.py`, `vidbyte/tools/builtins/bash.py` and all six `tests/features/coding_agent/*.py` modules have no findings under any rule. The only findings in touched files are older ones in the three modified `__init__.py` files: A001 header format, S001 F401, and S015 root imports. Every rule count equals main's §11 baseline.
- Both new headers use the A001 `FILE:/PURPOSE:/ROLE IN CODEBASE:/…/TESTS:` form of `jev/agent.py`, and they also add FUNCTION INVENTORY and WHAT NOT TO DO. The `bash.py` header is accurate against the code, including the claim "Python 3.12+ Process.wait() returns only after every pipe closes": in CPython 3.12.3, `_process_exited` only reaches `_try_finish`, which finishes the transport after every pipe has disconnected.
- AGENTS.md Styles 1 and 2 hold. `BashTool.execute` calls a flat set of helpers (`_spawn`, `_collect`, `_stop`, `_render`), none of which calls another. `CodingAgent.__init__`, `BashTool.execute` and `_FetchedPagesView.execute` are narrated step by step. There are no nested functions or lambdas in the source files, and no new enum or dataclass. Helpers are class-bound and `__all__` lists only the classes (`class-bound-helpers.md` check holds).
- Exports and docs land exactly as §12.3 rows 2 and 4–8 specify, with the bullet texts verbatim. The contract was regenerated after the root export was committed: its `source.commit` is `1bb1d3b4`, and `--check` passes. Each row is its own commit with W-/FR-/AC- IDs. No commit contains a secret, bytecode, egg-info or a cache file.

FINDINGS (ranked, most severe first)

R-V1 [Major] [placement/layering] vidbyte/agents/coding.py:132 — `_FetchedPagesView`, a `_ToolWrapper` tool class, is defined in the agents layer. Every other tool view, and the one prior single-consumer agent tool, lives in `vidbyte/tools/`.
  Evidence:
  - `grep -rn "(_ToolWrapper)" vidbyte` finds `vidbyte/tools/base.py:113 _CustomizedTool`, `vidbyte/tools/activity.py:152 _ActivityBoundTool`, and `vidbyte/agents/coding.py:132 _FetchedPagesView`.
  - `grep -rnE "class \w+\((BaseTool|_ToolWrapper|PricedOperationTool)" vidbyte/agents` finds only `coding.py:132`, so this is the first tool class in `vidbyte/agents/`.
  - The nearest sibling, `ContinualTraceAgent`, also has a tool with one consumer. That tool, `UpdateTraceTool`, lives in the tools layer: `vidbyte/agents/continual_trace.py:30` has `from vidbyte.tools.continual_trace import UpdateTraceTool`.
  - The view also reads a private class attribute across the layer boundary: `coding.py:168` `result.metadata.get(PricedOperationTool._PAYLOAD_KEY)`. `grep -rn _PAYLOAD_KEY vidbyte` shows that every other use is inside `operations/base.py`.
  Failure: AGENTS.md:9 says to read REPO_MAP "before you create a file … and put new code where it says that kind of code belongs".
  - REPO_MAP.md:61 describes `vidbyte/agents/` as "Executable agent actors".
  - REPO_MAP.md:305 makes `vidbyte/tools/` the layer that turns a function, schema and permission into "something a model can actually call and a result the model can read back". It calls this "the layer to understand before writing any new tool, custom or otherwise".
  - A reviewer of this repo has already left this kind of comment ("should be defined in the middleware layer", recorded in `blocking-lint-invariants.md`, PR #399). Expect: "this wrapper is a tool, move it to `vidbyte/tools/` like `UpdateTraceTool`".
  Smallest fix: move `_FetchedPagesView` unchanged into a private module beside the operations it wraps, for example `vidbyte/tools/builtins/operations/_fetched_pages.py`, so `_PAYLOAD_KEY` stays inside the `operations` package.
  - `coding.py` then imports it.
  - Update the two headers' ROLE/ARCHITECTURE lines and the `vidbyte/tools/README.md` sentence.
  - `fetch.py` stays byte-identical (INV-20).
  - Note for the verifier: this reopens spec D-16 and adds a third source file against the §8.4 budget, so it needs an orchestrator decision. It adds no feature.
  Spec IDs: D-16, §8.4 (conflicts), FR-6, §12.3 row 3.

R-V2 [Minor] [docs/header accuracy] vidbyte/agents/README.md:109 (also vidbyte/agents/coding.py:5) — the README says `restore()` gives a `BaseAgent`, but `CodingAgent.restore(state)` raises `TypeError`. EC-20 requires the README to document that.
  Evidence:
  - README.md:109: "- `fork()` and `restore()` give a `BaseAgent`: restore a saved state with `BaseAgent.restore(state, tools=CodingAgent(...).tools.all())`."
  - coding.py:5 ARCHITECTURE NOTE: "so runs, forks, restores, sessions, and JevAgent specialist checks behave exactly as for a BaseAgent". Line 9 of the same header says the opposite: "CodingAgent.restore(state) raises TypeError".
  - Run (`PYTHONPATH=$(pwd) python -`):
    - `agent.restore(st)` → `TypeError CodingAgent.__init__() missing 1 required keyword-only argument: 'root_dir'`
    - `CodingAgent.restore(st)` → the same `TypeError`
    - `BaseAgent.restore(st, tools=a.tools.all())` → `BaseAgent True`
  Failure: A developer who reads "`restore()` gives a `BaseAgent`" and calls `agent.restore(state)` gets a `TypeError`. Spec EC-20 marks this limitation "documented in README", and the README never mentions it. The header contradicts itself, against the file-header deep-dive ("The header must describe the code that exists").
  Smallest fix:
  - README bullet: "`fork()` returns a plain `BaseAgent`. `CodingAgent.restore(state)` raises `TypeError` (no `root_dir`), so restore with `BaseAgent.restore(state, tools=CodingAgent(...).tools.all())`."
  - Header: drop "restores" from the coding.py:5 list.
  Spec IDs: EC-20, D-8, §12.3 row 7.

R-V3 [Minor] [field guide: model-facing-tool-contracts.md] vidbyte/tools/builtins/bash.py:68 — the model-facing description says a command over the limit "is stopped", which is false on Windows. EC-14 lists the tool description as one of the three places that must state this limitation.
  Evidence:
  - bash.py:68: "A command that has not finished after {BASH_TIMEOUT_SECONDS:g} seconds is stopped, and standard input is closed, …"
  - On `win32`, `_stop` (bash.py:179-180) kills only Git's launcher.
  - Spec EC-14: "accepted limitation, stated in the tool description, the `bash.py` header, and the README". The header (bash.py:9) and the README (README.md:110) state it; the description does not.
  Failure: On the user's own Windows machine, the model is told a timed-out `npm run dev` was stopped while it keeps holding its port. The model then starts a second copy, which fails with the port in use. The field-guide check "validation/rendering parity" fails because the description promises a behavior the tool does not have on that platform.
  Smallest fix: change the clause to "is stopped (on Windows only its Git launcher is stopped, so the command itself may keep running)". Do this in the same edit as R-V6.
  Spec IDs: EC-14, A-9.

R-V4 [Minor] [error packets: agentic-engineering error_messages.md] vidbyte/tools/builtins/bash.py:148 — every spawn failure gets the advice "Shorten the command or remove NUL characters from it", including failures where the command is fine.
  Evidence:
  - bash.py:148: `f"bash could not start this command ({type(exc).__name__}). Shorten the command or remove NUL characters from it."` is returned for any `OSError` or `ValueError`.
  - Run: `BashTool(d)`, then `shutil.rmtree(d)`, then `execute(ToolCall(tool_name="bash", arguments={"command": "echo hi"}))` → `ToolStatus.ERROR 'bash could not start this command (NotADirectoryError). Shorten the command or remove NUL characters from it.' {'error': 'spawn_failed'}`.
  - `BashTool("definitely/not/here")` gives the same result. Construction does not validate the public `BashTool` root.
  Failure: A model whose root folder was removed mid-run (for example by its own `git clean -fdx` or `rm -rf`) is told to shorten a valid `echo hi`. It retries rewritten commands until the run ends. The remediation in an error packet must match the failure mode; here it matches only the two causes EC-15 names.
  Smallest fix: make the advice neutral and name the root as a cause: "Check that the root folder still exists, and that the command has no NUL characters and is not too long." Still name only the exception class (S017).
  Spec IDs: EC-15.

R-V5 [Minor] [folder README: agentic-engineering folder_readme.md] tests/features/coding_agent/README.md:7 — the pack README sends the file tools to the wrong folder.
  Evidence:
  - README.md:7: "The file, search and fetch tools these tests compose belong in `vidbyte/tools/builtins/`".
  - `ls vidbyte/tools/filesystem/` lists `read_lines.py`, `replace_text.py` and `write_text.py`.
  - REPO_MAP.md:311-313 names `vidbyte/tools/filesystem/` as the dedicated filesystem family.
  Failure: The folder-README checklist says: "verify that nothing in the description, index, or log contradicts the code you shipped". An agent fixing a `read_lines` regression found by this pack would look in `vidbyte/tools/builtins/`.
  Smallest fix: "The read, write and edit tools belong in `vidbyte/tools/filesystem/`, the search and fetch tools in `vidbyte/tools/builtins/`, …".
  Spec IDs: n/a.

R-V6 [Minor] [field guide: model-facing-tool-contracts.md] vidbyte/tools/builtins/bash.py:68 — the tool description has six sentences. The field guide asks for a "consistent 4–5 sentence" description for the tool and each parameter, and the `command` parameter (bash.py:75) has four.
  Evidence: the bash.py:68 literal splits into six sentences, from "Runs one command …" to "A background process must redirect …". S025 passes because it only sets a minimum of 4.
  Failure: The Do line of `model-facing-tool-contracts.md` says "give the tool and every parameter a consistent 4–5 sentence general description".
  Smallest fix: merge the stdin clause into the first sentence. That gives five sentences and leaves room for the R-V3 wording in the same edit.
  Spec IDs: §12.3 row 1 (description content).

Considered and not raised:
- **BASH_* constants stay in `bash.py`.** REPO_MAP.md:161 limits `vidbyte/lib/constants/` to values "that would otherwise need to appear in two places", and these have one consumer. The tests patch the module globals.
- **`metadata["error"]` uses string codes** (D-15). Every builtin does this, and AGENTS.md's enum rule names fields, parameters and registry keys.
- **`parents[:3]` literal.** A007 does not flag it, and the `@intent` comment explains it.
- **The `_collect` tuple return.** AGENTS.md Style 4 exempts small private helpers.
- **Long lines.** The ruff config selects only TID251, and the repo uses long lines throughout.
- **`"CodingAgent"` placed in the Jev block of the root `__all__`.** Spec row 5 asked for this, and that `__all__` is not sorted.
- **`docs/spec/coding-agent/` (11 pipeline files, a new `docs/spec/` folder).** REPO_MAP is required to list only top-level folders and `vidbyte/` subpackages. Committing these files is a pipeline decision, not a repo rule. `review-scope.md` counts docs as part of a feature's minimal surface.

FIELD-GUIDE QUICK CHECKS (each entry spec §11 lists, plus `init.md` matches)
- `local-ci-verification.md`:
  - Held: running `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;…"` and the fresh-interpreter imports resolve the worktree.
  - Held: whole-tree `ruff --select I001` reports no touched path (222 findings, none in a touched file).
  - Held: `git ls-files -u` is empty (no merge in progress).
  - Not re-run: semgrep. Remote Static policy run 38046510490 at `4c4a62ef` succeeded.
- `blocking-lint-invariants.md`:
  - Held: no helper named `request` (S012 0).
  - Held: A006 34/34, with no function-local imports in the new modules.
  - Held: S060 32/32 and S039 5/5.
- `model-facing-tool-contracts.md`:
  - Failed: see R-V3 and R-V6.
  - Held: no examples in the descriptions.
  - Held: the view's spec is the wrapped tool's spec (the fetch descriptions say "into clean markdown", which matches the page text the view adds).
- `cli-backed-source-integrations.md`:
  - Held: output is clipped by bytes before decoding, the tool has its own timeout and cancellation, and spawn errors are classified safely.
  - Not applied: "no command strings in model-facing inputs" (D-10, the user asked for Bash) and "one library runner" (the entry is about provider CLIs, not this tool).
- `strict-config-dataclasses.md`:
  - Held: the 50,000-byte cap equals the repo's broad model-facing cap (Glob/Grep `max_chars` upper bound).
  - Not applicable: the settings-class entries. `CodingAgent` is an agent, and its `ConfigurationError`s follow the `JevAgent` precedent.
- `runtime-boundaries.md`: Held. No parallel configurable ceiling; `ToolSettings.tool_timeout_seconds` remains the knob.
- `class-bound-helpers.md`: Held. `__all__ = ["BashTool"]` and `__all__ = ["CodingAgent"]`; the wrapper is module-private.
- `agents-md-map.md`: Not applicable. REPO_MAP is untouched, and no folder under `vidbyte/` is added.
- `review-scope.md`: Held. The source diff is exactly the 8 §12.3 files (`git diff 4df5615e..4c4a62ef --stat`: 8 files, +412/−4). Spec D-16 is reviewed separately in R-V1.
- `priced-operation-execution.md` (matched by the keyed fetch view): Held. Usage still comes from the wrapped tool's metadata, and the runtime unwraps `_ToolWrapper` before pricing.

§12.4 STANDARDS CHECKLIST — line by line
- [x] A001 headers in both new files, in jev format. Accuracy fails at coding.py:5 (R-V2).
- [x] New files tracked before lint.
- [x] A002 `@intent` on `CodingAgent.__init__`, `_web_fetch_tool`, `_spawn`, `_collect`, `_stop` (and `_find_bash` and the view's `execute`). A002 682 = main.
- [x] `sys.platform` branches for `killpg`/`SIGKILL`.
- [x] A007 255 = main. The read loop has no literal.
- [x] S025/S062 hold: each description is a single literal of at least 4 sentences with no examples. The 4–5 band is missed (R-V6).
- [x] S055: argv exec only. S052: asyncio subprocess API only.
- [x] S019: `except asyncio.CancelledError` awaits `_stop` and then re-raises.
- [x] Only two `process.wait()` calls, both bounded. `_stop` runs only on timeout or cancellation.
- [x] Transport closed via `getattr(process, "_transport", None)`. Whether `_stop` really "never raises" belongs to the engineering lens (implementer's tricky part 2).
- [x] S024 21, S006 0, S039 5, S045 2, S016 50, S017 78, A008 3. Decoding is UTF-8 with `errors="replace"`.
- [x] I001 clean on touched paths. Imports point downward only, and A006 = 34.
- [x] One-level call chains. Main functions narrated.
- [x] Files are 194 and 177 lines; every function is under 40 lines; S008 19.
- [x] No new dataclass or enum. Helpers are class-bound. `__all__` is correct and S015 is 13.
- [x] `vidbyte/__init__.py` committed (`1bb1d3b4`) before the contract (`5d71a9f4`). `--check` passes.
- [x] `CodingAgent` overrides no `BaseAgent` method. Its own attributes are `_resolve_root` and `_web_fetch_tool`, and `BaseAgent` defines neither.
- [x] The protected files are byte-identical to main: `git diff origin/main...4e285d91 --stat` over the operations/filesystem/code_search tools, `base.py` and `vidbyte/lib` is empty.
- [x] No key in messages or details. `ConfigurationError` uses `details=`.
- [x] No rule count rises. The baseline is untouched.
- [x] Gate: the full pytest run passes locally. `run_ci.py` itself was not re-run (read-only). Remote CI is green.
- [x] REPO_MAP is not edited. Nothing out of scope was built.

§12.5 NON-CODE ACTIONS
- [x] Agents README section and Key Modules bullet. The restore wording is wrong (R-V2).
- [x] Tools README: the `builtins/` line and the Priced Operation Tools sentence.
- [x] Contract regenerated. Exports in all three `__init__` files.
- [x] REPO_MAP: no change. This holds because REPO_MAP lists only top-level folders and `vidbyte/` subpackages, and no `vidbyte/` folder is added.
- [x] `llms.txt` and `artifacts/file_index.md`: no change. `JevAgent` is absent from `llms.txt`, and `file_index` is folder-level.
- [x] `vidbyte/lib/constants/`: no change.
- [x] Root README: no change. Its Package Structure section is folder-level.
- [x] `.env.example` and design doc: none. `spec.md` is the design record.
- [x] Remote CI dispatched, and both runs succeeded.

PREDICTED main-rule violations after merging `origin/main` (`e6cdfa31`). These were read with `git show origin/main:lint/rules/…`, not run:
- **A009** (README ≤ 40,000 chars): predicted clean. `vidbyte/agents/README.md` is 10,433 chars, `vidbyte/tools/README.md` 6,037, and `tests/features/coding_agent/README.md` 2,768. Main did not change either `vidbyte/` README.
- **C006** (finite numeric guards in `__init__`/`__post_init__`/validator-named functions): predicted clean. The validation sites in the diff (`CodingAgent.__init__`, `BashTool.__init__`, `_FetchedPagesView.__init__`, the two `validate_call`s, and the test `__init__`s) contain no ordered numeric comparison. `len(supplied) > 1` sits in `_web_fetch_tool`, which does not match `_VALIDATOR_NAME`.
- **C007** (bool switches on *Settings/*Config/*Configuration/*Policy/*Options classes or config modules): predicted clean. The diff adds no such class and no bool parameter.
- **C008** (primitive validators outside `vidbyte/lib/dataclasses/validation.py`): predicted clean.
  - `validate_call` → family "" ("call" is not a primitive).
  - `_resolve_root` → "".
  - `_find_bash` → no verb.
  - The test helper `_is_running` → "" ("running" is not a primitive).
- Main did not touch any of the 8 non-doc files in this PR (`git diff --stat 8f23fd67..origin/main` over them is empty), and C016 compares exports, not the commit, so it stays clean after the merge.

VERIFIED CLAIMS
1. **Held.** Implementer: "SDK-LINT: PASS, every counted rule equal to main's".
   - Counts: A001 643, A002 682, A003 36, A005 33, A006 34, A007 255, A008 3, S001 57, S009 340, S015 13, S016 50, S017 78, S019 5, S024 21, S025 261, S039 5, S045 2, S051 258, S062 889.
   - The `--all` JSON has zero findings in the new files.
2. **Held.** "C016, S052 and S055 are CLEAN": each is 0 CLEAN, and `generate-sdk-public-api.py --check` reports "current at 1bb1d3b4… 594 exports".
3. **Held.** "Coding-agent pack on Windows 3.11: 86 passed, 11 skipped": I got 86 passed, 11 skipped in 4.97s.
4. **Held, pytest part only.** "Full gate passed" claimed 2715 passed, 12 skipped. My full pytest run gave the same counts in 18.30s. I did not run `run_ci.py`.
5. **Held.** "Remote runs 38046509073 (CI) and 38046510490 (static-policy) succeeded at 4c4a62ef": both succeeded on `headSha 4c4a62ef`. The CI jobs were Source 3.11, Source 3.12 and Package; the other run was Static policy.
6. **Held.** "No file outside §12.3; tests untouched": `git diff d158d5f6..4e285d91 --stat -- tests/ pyproject.toml lint/` is empty, and the source diff is the 8 rows.
7. **Held.** INV-1 / §12.4 "overrides no BaseAgent method": confirmed by script (own attributes are `_resolve_root` and `_web_fetch_tool`, and neither is on `BaseAgent`).
8. **Held.** Test plan "42 test functions and 97 collected cases": I counted 12+10+5+9+6 = 42 functions and 86+11 = 97 cases.
9. **Held.** bash.py header "Python 3.12+ Process.wait() waits for every pipe": confirmed from the CPython 3.12.3 source in WSL1 `MuseUbuntu1`.
10. **Did not hold.** README and coding.py header on restore (R-V2).
11. **Held.** §12.3 rows 2, 4, 5, 7 and 8 bullet texts match the spec verbatim. The row 7 section is 25 lines, at most the 30 allowed.
12. **Held.** Import direction and cycles: fresh-interpreter imports of `vidbyte.agents.coding`, `vidbyte.tools.builtins.bash`, `vidbyte.tools.builtins` and `vidbyte.agents` all succeed.
13. **Held.** No secrets: the only key-like strings in the diff are placeholders (`fc-your-key`, `fc-test-key`, `tvly-test-key`, `env-SECRET-must-not-be-used`).

COMMANDS RUN
- `python lint/run.py` → "SDK-LINT: PASS" (EXIT=0). The rule table is quoted under VERIFIED CLAIMS 1.
- `python lint/run.py --all --format json`, filtered to touched paths → only the older A001/S001/S015 findings in the three `__init__.py` files.
- `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` → "Found 222 errors.", none in a touched path.
- `python scripts/generate-sdk-public-api.py --check` → "contracts/sdk-public-api.json is current at 1bb1d3b4… (vidbyte-sdk 0.2.0, 594 exports)." EXIT=0.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/coding_agent/` → "86 passed, 11 skipped in 4.97s".
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` → "2715 passed, 12 skipped in 18.30s".
- Restore and fork probe script → "agent.restore -> TypeError … 'root_dir'", "BaseAgent.restore -> BaseAgent True", "fork -> BaseAgent", "CodingAgent own attrs: ['_resolve_root', '_web_fetch_tool']" and "[]".
- Spawn-failure probe → "ToolStatus.ERROR 'bash could not start this command (NotADirectoryError). Shorten the command or remove NUL characters from it.' {'error': 'spawn_failed'}" (twice).
- `wsl.exe -d MuseUbuntu1 -e python3 -c "…inspect.getsource(BaseSubprocessTransport._process_exited/_wait/_try_finish)"` → 3.12.3. `_process_exited` calls `_try_finish`, which finishes only after every pipe has disconnected.
- `gh run view 38046509073` / `38046510490` → conclusion "success", headSha "4c4a62ef…".
- `git show --stat` on the 10 feature commits → one row per commit, with IDs cited. `4c4a62ef` is comments only.
- `git show origin/main:lint/rules/{a009,c006,c007,c008}_*.py`, read for the predictions above.
- README character counts via `git show 4e285d91:<path> | python -c "len(...)"` → 10433 / 6037 / 2768.
