# S6 PR author: harness-browser-tools

Stage: S6 PR author · Branch `feat/harness-browser-tools` · Start HEAD `fd4baede` · PR body commit `ce998fa2` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1183 (draft) · Date 2026-10-18.

S6 changed no source, test, lint, script or CI file. It added `docs/spec/harness-browser-tools/pr-body.md` and this report. In `spec.md` it set the frontmatter to `status: pr-open` and added the §17 row `| r5 | 2026-10-18 | S6 PR | finalized for review |`. The `pr:` and `updated: 2026-10-18` fields were already correct. The PR title and body now come from `pr-body.md`: line 1 is the title, and lines 2 onward are the body. The PR stays a draft.

## What the code does, in my own words

This is my reading of the final diff (`origin/main...fd4baede`), checked against the spec.

**The public functions.**
- **What they are.** A caller gets nine coroutines, `run_`, `continue_` and `fork_` × `grok`, `opencode` and `muse`, each named `..._with_browser`. Each one is its plain `_thread` sibling's signature plus keyword-only `tools` and `tool_keys`, placed after `model`.
- **The shared flow.** Every function builds the same two checked records (`NativeThreadRequest` and `BrowserToolRequest`). It then hands them, with its harness's seam object, to one shared coroutine, `NativeBrowserRun.execute` (`vidbyte/harnesses/native/hostkit/browser.py:67`).

**What `execute` does, in order:**
1. It registers the harness key and every tool key with the error factory, so they are scrubbed from any later error text.
2. `BrowserToolRegistry.select` resolves the strings deterministically. It makes no network call and reads no environment.
3. The seam's `check` refuses what that harness cannot carry. Grok refuses keyed remote tools and rule sets over the argv budget. Muse refuses keys, narrowing, and stdio tools in WSL mode. opencode refuses nothing.
4. `prepare` runs these checks and steps:
   - It checks Node only if a stdio tool is selected, and Chrome only if a selected tool drives it.
   - It installs any missing pinned package once into `~/.vidbyte/tools/<tool>-<version>`, through staging and an atomic rename.
   - It creates the per-call `vidbyte-browser-*` temp folder, with `artifacts/` and one `profiles/<tool>/` folder per tool.
5. Inside one `try`, the seam runs the harness through its existing `ThreadRun.execute(..., mount=...)`. That function now returns `NativeThreadRun(result, outcome)`, and the plain path takes `.result`, so it is unchanged.
6. The seam reads the vendor's own tool calls from the output.
7. `require` raises `browser.tools_unavailable` for any server with no evidence.
8. `complete` reaps every process whose command line holds the per-call folder, removes the profiles, lists the artifacts and returns a `BrowserThreadResult`.
9. Any exception or cancel after `prepare` runs `discard` under `asyncio.shield` and re-raises.

**Where each harness differs:**
- **opencode** gets `mcp` and `permission` members inside `OPENCODE_CONFIG_CONTENT`:
  - Server ids are `vidbyte-<tool>`, each with `enabled: true`.
  - For narrowing, the wildcard deny comes first and the exact allows after it.
  - `webfetch` and `websearch` are denied.
  - Keys go in the server `environment`, or in a Bearer header for remote servers.
  - Evidence that a tool worked is any call on a mounted tool.
- **Grok** gets these:
  - a per-call agent file holding JSON `mcpServers`;
  - argv with `--agent=`, exact `--allow`/`--deny` rules and `--disable-web-search`;
  - `--output-format=streaming-json`;
  - the Claude and Cursor MCP scans switched off.

  A `cancelled` stop reason is a failed run. Evidence that a server worked is that `available_commands` lists it or one of its calls COMPLETED (R-2).
- **Muse** gets a `muse/settings.json` of exactly `{"schema_version":1,"mcpServers":{...}}` and `--disable-web-tools`. Its required check is Muse's own "Required MCP server" failure, which the seam converts inside `run`.

**What it never does.** The SDK never talks to a tool server itself. Keys go only into child environment overlays, or into opencode's inline config.

## Deviations

The PR body lists all 19 under "Deviations from the spec":
- **1–16** are the S3 implementation deviations in spec §17. I checked each one against the code; deviation 4 includes the FR-15 point that cleanup can exceed 10 s by one removal try.
- **17 (found by S6).** D-28 and EC-6 say every `tool_keys` name that is not a registry name is "also registered as a secret". The code never does this. `BrowserToolRequest._checked_tool_keys` (`vidbyte/lib/dataclasses/browser_tools.py:204-215`) refuses such a name by position with a constant message, before `execute` registers anything. The outcome the spec protects still holds (AC-30): a key used as a name never reaches a message.
- **18.** The §9.1 rule that the `BrowserMount` folder is outside the workspace is not enforced (R-12). `prepare` uses `tempfile.mkdtemp` (`hostkit/browser.py:266`, `:328`), so a `TMPDIR` inside the workspace breaks it.
- **19.** The §5 diagram has no drift: it matches `NativeBrowserRun.execute` (`hostkit/browser.py:67-111`) step for step, so §5 is unchanged and §17 carries no drift note.

## Snippet output

AC-1 runs the spec §4 snippet byte for byte, with only the workspace literal replaced, against the offline fakes. I ran it twice on `fd4baede`.

The plain run:

`PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_browser_acceptance.py -rA` → `PASSED tests/features/harness_threads/test_harness_threads_browser_acceptance.py::test_the_developer_snippet_runs_as_documented` · `1 passed in 3.14s`.

The second run used a scratch pytest plugin that copies `capsys.readouterr()` to a file. It gave `1 passed in 3.05s` and printed:

```text
ses_0c491925-c665-433c-83dc-87ac40667bfb opencode answer to: Open https://example.com and tell me the page heading.
playwright browser_navigate completed
firecrawl firecrawl_search completed
()
(WindowsPath('<pytest tmp>/vidbyte-browser-s1_86pty/artifacts/page-26096-0000.png'),)
```

`<pytest tmp>` stands for `C:/Users/422mi/AppData/Local/Temp/pytest-of-PC/pytest-5402/case0/tmp`. The snippet was not run against a real vendor or with a real key.

## Checks I ran myself (independent of earlier stages)

| Check | Result |
|---|---|
| The seven browser test files, `fd4baede`, local Windows | `183 passed, 1 skipped in 126.22s (0:02:06)`. The skip is `test_harness_threads_browser_lifecycle.py::test_a_missing_ps_is_not_raised`, which is POSIX-only. |
| Every test name cited in spec §6.2 exists on the branch | All 53 found by grep. |
| Every commit cited in the body is on the branch | Each of the 34 SHAs passed `git merge-base --is-ancestor <sha> HEAD`. |
| No code change after `a44fb17f` | `git diff --stat a44fb17f fd4baede -- vidbyte tests lint scripts .github pyproject.toml` printed nothing. |
| Mermaid blocks parse | I parsed them with mermaid 10.9.1 under jsdom 24.1.0, using a scratch script. Result: pr-body `block 1: OK (flowchart TD)` · `block 2: OK (sequenceDiagram)` · `blocks: 2, failed: 0`. spec §5: `blocks: 1, failed: 0`. The negative control, an unclosed `{"bad`, failed with `Parse error on line 4`, so the checker does catch errors. |
| No credential-shaped text or email in the body or this report | A grep for `sk-` and `fc-` followed by hex, the user's mail domain, and the GitHub-token and AWS-key prefixes found nothing. |
| Body size and shape | 47,203 characters after the `ce998fa2` rows were added (limit 55,000). The title is 99 characters, with no `[WIP]`. The last line is exactly the Claude Code line. Outside code, every `<...>` sits in backticks, so GitHub does not read it as HTML. |
| The GitHub body round-trips | `gh pr view 1183 --json body` matched `pr-body.md` from line 2 on, apart from the trailing newline that jq adds. |
| Muse double-count probe | In memory only (`scratchpad/s6/muse_double_count.py`). Result: `records for one task t1: 3 -> calls: 2` · `VERDICT: DOUBLE-COUNTED`. See "Looked wrong". |

## PR and checks

`gh pr view 1183 --json title,isDraft,baseRefName,url,headRefName,state,labels`, after the final `gh pr edit`:

```json
{"baseRefName":"main","headRefName":"feat/harness-browser-tools","isDraft":true,"labels":[],"state":"OPEN","title":"feat(harnesses): browser tools for the Grok, opencode and Muse threads (run_<harness>_with_browser)","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1183"}
```

The body on GitHub matches `pr-body.md` from line 2 on, and it holds 2 mermaid blocks.

`gh pr checks 1183` printed this and exited 1:

```text
no checks reported on the 'feat/harness-browser-tools' branch
```

That is expected, because both workflows are dispatch-only. The evidence is the dispatched runs on `ce998fa2`. I found each run with `gh run list --workflow <wf> --branch feat/harness-browser-tools -L 1`; `headSha` was `ce998fa2559b1891208553acb7e4a9fb20baf74d` for both. I then watched each with `gh run watch <id> --exit-status`, and both exited 0.

| Workflow | Run | Result | Final lines |
|---|---|---|---|
| CI | 39100749669 | success, 3/3 | Source / Python 3.11 (job 117596348576): `SDK-LINT: PASS` · `6441 passed, 205 skipped in 154.79s (0:02:34)` · `CI passed.` Source / Python 3.12 (job 117596348431): `SDK-LINT: PASS` · `6441 passed, 205 skipped, 19 warnings in 165.69s (0:02:45)` · `CI passed.` Package (job 117597160207): `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| Static policy | 39100751670 | success | `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 1016 files: 0 findings.` |

The known remote flake (`test_real_bash_reports_its_version_and_git`) did not occur, and no rerun was needed.

## Candidate field-guide lessons

Each lesson reads: trigger · preferred action · project-specific reason · quick check · link.

1. **Adding comments in `vidbyte/*.py`** · Wrap every comment line at 72 columns, counting the indent. · Field guide `comment-format.md` requires it, and no lint rule catches it, so R-1 found 10 lines from 73 to 77 columns after CI was green. · Scan the `+` comment lines of `git diff -U0 $(git merge-base origin/main HEAD) -- 'vidbyte/*.py'`. Diff against the merge base and the working tree; `origin/main...HEAD` reads commits only. · https://github.com/cerredz/Vidbyte-SDK/pull/1183 (R-1, `8286f1aa`)
2. **Adding a policy or boundary function (a `__post_init__`, a refusal, a subprocess, a permission order)** · Put a `# @intent <name>` block at the function. · The repo-wide A002 ratchet (baseline 703) hides new hits under `SDK-LINT: PASS`: R-6 found 12 unmarked functions while lint passed. · Run A002's analyzer per changed file at the merge base and at HEAD, and count with multiplicity, because two same-named `__post_init__` collapse otherwise. NEW must be 0. · PR 1183 (R-6, `103a27a5`)
3. **A cleanup or retry helper needs a time bound** · Compute one deadline in the main function, pass it down, and check the clock inside the loop. Never wrap each item in its own `asyncio.timeout`. · A per-item timeout forced a three-level call chain, which breaks AGENTS.md principle 1, and it restarted the budget on every item, which breaks INV-12. The S064 rule wants the clock check, and S024 forbids the deeper nesting. · Run an AST scan for same-class three-level chains on the changed files; lint S064 and S024 must not rise. · PR 1183 (R-3, `4c686557`)
4. **Editing `vidbyte/harnesses/README.md`'s `native/` bullet, `REPO_MAP.md`'s native rows or `vidbyte/harnesses/native/__init__.py`** · Update `tests/features/codex_host/test_codex_host_packaging.py` (`README_BULLET`, `REPO_MAP_SECTION`, `NATIVE_INIT_SHA256`) in the same commit. · Those three are pinned byte for byte, including a SHA-256 of the whole `native/__init__.py`. · `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/codex_host/test_codex_host_packaging.py` · PR 1183 (R-5, `1990e363`)
5. **Replacing `sys.platform == "win32"` with a named constant** · Keep the literal, with a comment saying why. · mypy narrows the platform only on the literal. With a constant, `mypy --platform win32` reports `signal.SIGKILL` in `vidbyte/lib/process/reaper.py`. · `mypy --platform win32 <file>` · PR 1183 (R-8, `e8e543a9`)
6. **Deciding from Grok's streaming-json output whether an MCP server worked** · Count only a server listed in `available_commands`, or one with a call whose last `tool_call_update` status is `completed`. · Grok answers a call to a server that never connected with "Tool not found" and exits 0, so counting any call let a dead mount return success (R-2, a Blocker). · Add a fake case with `grok_unlisted` plus a call to that server; it must raise `browser.tools_unavailable`. · PR 1183 (R-2, `fb8c0508`, `8b02afdd`)
7. **Writing a registry row's source comment or a README key rule** · Quote the vendor-facts line, never a paraphrase from memory. · The tavily comment claimed "exits at start without its key", which is false (vendor facts line 274), and the README's key rule contradicted the row. That README is what AGENTS.md tells the next agent to read before adding a tool. · `git grep` the claim against `docs/spec/<slug>/context/vendor-facts.md`. · PR 1183 (R-4, `36e5129e`)
8. **Confirming checks on a Vidbyte-SDK PR** · Dispatch `CI` and `Static policy` with `--ref <branch>`, find each run with `gh run list --workflow <wf> --branch <branch> -L 1`, check `headSha`, then `gh run watch <id> --exit-status`. · Both workflows are dispatch-only, so `gh pr checks` prints "no checks reported" even when everything is green. · `headSha` must equal `git rev-parse HEAD`. · PR 1183 (this stage)

## Looked wrong (not fixed; S6 makes no source changes)

- **`vidbyte/harnesses/native/muse/wire.py:209-218` (Minor, conditional on A-1).** `MuseExecOutput.tool_calls` makes one `BrowserToolCall` per `task.lifecycle.proposed` record and one per `side_effect_intent` record. If real Muse prints both for one `task_id`, the call is counted twice; the in-memory probe gave 2 calls for 1 task. It does not affect the required check, because Muse's `missing` always returns `()`. Fix once A-1 is verified: dedupe by `task_id`.
- **`vidbyte/harnesses/native/grok/wire.py:162,172` (low risk).** Statuses are keyed by `toolCallId`. If Grok omitted the id, every id-less call would share the `None` key, and one completed status would mark them all completed. That would feed `GrokBrowserHarness.missing` through the COMPLETED rule. The vendor facts show the id is always present.
- **Spec D-28 and EC-6 text versus `vidbyte/lib/dataclasses/browser_tools.py:204-215`.** The spec promises secret registration that the code never does (deviation 17). This is harmless, because the refusal is by position and never quotes the name, but the spec text is stale.
- **The open review follow-ups, at HEAD:**
  - R-11: `grok/mounts.py:111` and `opencode/mounts.py:54`, `env_remove` written twice.
  - R-12: `hostkit/browser.py:266,328`, the per-call folder from `tempfile.mkdtemp` with no outside-workspace check.
  - R-13: `hostkit/browser.py:168-171`, "entry missing", then "folder exists", raises broken-cache without re-checking the entry.
  - R-14: `hostkit/browser.py:235-240`, one `os.rename` with no retry on a transient `PermissionError`.
  - R-15: `hostkit/browser.py:266`, which runs before the `try` at `:93`, so a cancel there leaks the folder.
  - R-18: `grok/wire.py:96,160,186` and `opencode/wire.py:66,119`, stdout parsed several times.
  - R-19: `opencode/mounts.py:31`, the no-op `check`.
  - R-C2: no test for the positive half of the Grok rule.
- **Inherited, not this branch:** `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails locally with `assert 167 == 120`, the same as on `origin/main`.

## Process notes

- **Ordering.** The body is committed in `ce998fa2`, and this report is committed after it. The body's Verification table cites the remote runs on `43735a6c`, which is code-identical to every later commit, and the runs on `ce998fa2` are added above. The runs on the final HEAD, the commit that adds this report, are in the S6 STATUS block, because a commit cannot record its own CI result.
- **Mermaid rules.** Both diagrams quote every label that holds parentheses or colons, use no `;`, no `<...>` and no `end` node id, and parse with mermaid 10.9.1.
- **Scratch files.** Everything is under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/1da32edd-ec0f-4839-ba1f-52db538ed13c/scratchpad/s6/`: the tee plugin, the snippet output, the Muse probe, the mermaid checker and its install, the split title and body, and the CI watch logs.
