# S3 implementer report: native-grok-opencode-meta-hosts

Status: **BLOCKED (second stop)**. I stopped because one spec row contradicts itself, so no implementation can pass the test that follows it. Nothing was pushed and the worktree is still in place.

**Done so far:**
- P1 is committed, including the A007 fix the coordinator asked for.
- P2 row 22 (transport) and rows 25-28 (hostkit) are committed.
- Row 24 was committed earlier.

| Item | Value |
|---|---|
| Branch | `feat/native-grok-opencode-meta-hosts` |
| Base of this round | `aa00b7d3` |
| HEAD | `f1567ae9` |
| Test baseline | `a716c858` |

## 1. Commits

The first stop's report recorded these commits, made before this round:

| SHA | Work item | §12.3 rows |
|---|---|---|
| `26f897e9` | W-1 | 1-6, 13 |
| `49eae8cc` | W-2 | 7-12, 14, 15 |
| `ba78a4da` | W-3 | 19, 20 |
| `b137305e` | W-4 | 16-18 |
| `c3bd8c6f` | W-14 | 24 |

These are new in this round:

| SHA | Work item | §12.3 rows | What |
|---|---|---|---|
| `6692ee57` | W-2, W-4 (A007 fix) | 8, 9, 10, 13, 17, 18 | Fixes the A007 lint finding by naming the literal lower bounds and byte offsets. It adds four constants: `NATIVE_MIN_LIVE_TURNS`, `GROK_MIN_TURNS`, `OPENCODE_MCP_TIMEOUT_MIN_MS` and `NATIVE_PROCESS_TRUNCATION_PROBE_BYTES`. `ManagedProcess` now trims its stderr tail with a negative slice. |
| `eb47d589` | W-5; FR-15, EC-10, INV-18 | 22 | `McpStdioTransport` extension: `on_message` plus the dispatch fix, `send_request`, `notify`, `respond`, per-call `timeout_seconds`, `exit_grace_seconds` and `stop_process_tree`. The diff is +156/-8 lines, under D-3's limit of about 160. |
| `f1567ae9` | W-6; INV-6, EC-5, EC-9, EC-149 | 25-28 | `vidbyte/harnesses/native/hostkit/{__init__,errors,turns,peers}.py` |

**Why A007 was missed in the first round:** lint rules A002 and A007 scan tracked files only. My first lint run happened while the P1 files were still untracked, so A007 never saw them. Every later lint run in this round was made after `git add`.

## 2. The blocking defect: §6.3.1 contradicts itself for `muse.budget_exhausted`

- **Failing test:** `tests/features/grok_host/test_grok_host_shared_contract.py::test_next_steps_hold_every_code_verbatim`.
- **What it asserts:**
  - `NATIVE_HOST_NEXT_STEPS["muse.budget_exhausted"]` must equal the §6.3.1 text verbatim: "The turn hit Muse's step limit; continue the session with a narrower prompt."
  - The same value must also contain the row's required token, `continue_muse_session`.
  - That text does not contain that token, so both assertions cannot hold.
- **The spec rows:**
  - spec.md:358, the §6.3.1 row: text "The turn hit Muse's step limit; continue the session with a narrower prompt." with required token `continue_muse_session`.
  - spec.md:704, EC-117: "*default*; token `continue_muse_session`". The muse pack's EC-117 row test inherits the same contradiction.
- **Evidence:**
  ```
  E           AssertionError: muse.budget_exhausted
  E           assert 'continue_muse_session' in "The turn hit Muse's step limit; continue the session with a narrower prompt."
  ```
- **Scope of the check:** I scanned every `| EC-` row of the spec whose user sees "*default*; token X" against its code's default text, and every row of the test CATALOG against its own token. This is the only mismatch.
- **Why I did not just fix it:** the briefing lists changing a §6.3.1 next step as an ask-first (BLOCKED) item.

## 3. Verification at `f1567ae9`

- **Lint:** `python lint/run.py` was run with every file staged or committed, and printed `SDK-LINT: PASS` with exit code 0.
  - A007 is back to 255 against an allowance of 255.
  - S045 (ruff ASYNC109) fired on private async helpers that took a parameter named `timeout`. I renamed the parameter to `seconds`.
- **New transport and opencode record tests:**
  - Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_transport_extension.py tests/features/opencode_host/test_opencode_host_records.py`
  - Result: `117 passed, 2 skipped in 3.01s`. The 2 skips are POSIX-only.
- **Grok record and process tests**, run with a throwaway, uncommitted grok package stub because the `grok_api` fixture needs it:
  - Result: `53 passed, 4 skipped in 2.82s`. The three test fixes from the first stop all pass now.
- **Shared-contract tests**, with the same stub: `11 failed, 32 passed`.
  - 1 failure is the defect above.
  - The other 10 need modules from P3 and P4 that do not exist yet: `opencode`, `muse`, `backends`, the toolsets, the fresh imports and the AC-18 audit.
- **MCP neighbours and coding_agent:**
  - Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent`
  - Result: `445 passed, 12 skipped in 16.51s`.
- **Full existing suite**, excluding the 4 new packs:
  - Command: `PYTHONPATH=$(pwd) python -m pytest -q --ignore=tests/features/grok_host --ignore=tests/features/opencode_host --ignore=tests/features/muse_host --ignore=tests/features/native_backends`
  - Result: `3956 passed, 13 skipped in 34.15s`.
- **Tests untouched:** `git diff a716c858..HEAD -- tests/ | wc -l` gives `0`.
- **INV-22 files untouched:** `git diff --quiet 8b77aba0..HEAD -- <the INV-22 paths>` printed `INV-22 files unchanged`.
- **Not run yet:** `scripts/run_ci.py` (source and package stages) and Semgrep.

## 4. Options

1. **Change the §6.3.1 text to contain the token.** For example: "The turn hit Muse's step limit; continue the session with continue_muse_session and a narrower prompt."
   - The spec row, the test CATALOG and my constant change together.
   - EC-117 then passes with the default next step.
2. **Change the required token to a substring of the current text,** for example `continue the session`.
   - The spec row, EC-117, the test CATALOG and the muse EC-117 test change together.
   - The constant stays as it is.
3. **Accept the contradiction and let S3 continue.**
   - The shared-contract test stays red, so S3 cannot report DONE.

## 5. Recommendation

Option 1. The next step should name the function the caller must call, the way every other row's token does. That is a one-line change in each of the spec, the test and `vidbyte/lib/constants/native_hosts.py`; I make the constant edit when I resume. After the fix, S3 resumes at P3 (rows 29-46).

## 6. Niche facts for the next agent

- **Lint scans only tracked files.** `catalog.python_files()` drives A002 and A007, so `git add` new files before running `python lint/run.py`. A PASS with untracked files means nothing.
- **A007** matches a whole split token: `byte` matches but `bytes` does not, and `limit`, `timeout` and `status` match. It also flags any numeric literal whose AST context includes a call named `read`, `send`, `request` or `sleep`.
- **S045 (ASYNC109)** flags any async function with a parameter named exactly `timeout`. Use `timeout_seconds` for public parameters and `seconds` for private ones.
- **A002** has 78 findings of slack (625 against 703). Every function whose identifiers contain `request`, `send`, `transport`, `subprocess`, `provider` or `permission` needs `# @intent` within 4 lines before or 20 lines after its `def`.
- **S024** limits nesting to depth 3, and `with`, `try`, `for` and `if` each count.
- **hostkit:**
  - `NativeErrorFactory.code(problem)` returns `FailureCode("<harness>.<problem>")`, and `NativeErrorFactory.listing(items)` joins at most 20 items with ", ".
  - `NativeTurnTable.live_handles()` and `NativePeer.closed` are small internal additions beyond §8.5.
  - `NativePeer.call` re-raises a JSON-RPC error answer as `McpProtocolError` (it has `details["error"]`) for each host's wire to map.
