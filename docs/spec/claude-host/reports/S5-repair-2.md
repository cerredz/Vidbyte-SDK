# S5 repair, iteration 2: claude-host

- **Agent:** S5 repair, iteration 2 of 8.
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host`, on branch `feat/claude-host`.
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1044. It stays a draft, and I left its title and body as they were.
- **Start:** HEAD was 9211d4ef (spec r6), and the remote was at 615fc54a. The four docs commits 0a938faa..9211d4ef went out with this iteration's push.
- **Code head:** 2c537b1a. This iteration's docs commit comes after it.
- **No catch-up merge.** After `git fetch origin`, `git rev-list --count HEAD..origin/main` gave 0, and origin/main is still 8387d666.

## Gate matrix

Every gate below ran in this worktree, in this iteration, at 2c537b1a. The raw output is in the session scratchpad under `repair2/`, in the `gate-*.txt` files.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests, pack | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` | PASS | `181 passed in 5.58s` |
| new tests, CI view | the same pack with `sys.modules['claude_agent_sdk']=None` | PASS | `181 passed in 5.44s` |
| new tests, the four new cases | `…::StopInSteerWindowTests …::SteeredResultFieldsTests` | PASS | `4 passed in 0.83s` |
| source stage | `PYTHONPATH=$W $PY scripts/run_ci.py --stage source` | PASS | `====== 4182 passed, 27 skipped in 39.25s ======` / `CI passed.` / `exit=0` |
| package stage | `$PY scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / `exit=0` |
| lint | `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s). …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` / `exit=0` |
| semgrep | `PATH="/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `• Findings: 0 (0 blocking)` / `Ran 1 rule on 915 files: 0 findings.` / `exit=0` |
| public API | `PYTHONPATH=$W $PY scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).` / `exit=0` |
| shared-file contract | `git show HEAD:vidbyte/harnesses/native/__init__.py \| sha256sum` | PASS | `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a` |
| remote ci.yml | `gh workflow run ci.yml --ref feat/claude-host`, run 38519021773 | PASS | head 2c537b1a, conclusion `success`. Source / Python 3.12: `4190 passed, 19 skipped, 19 warnings in 40.98s` / `CI passed.` Source / Python 3.11: `4190 passed, 19 skipped in 45.27s` / `CI passed.` Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static-policy | `gh workflow run static-policy.yml --ref feat/claude-host`, run 38519023850 | PASS | head 2c537b1a, conclusion `success` |

Notes:
- **Lint.** The lint rule table is identical, row for row, to iteration 1's run. The same eight IMPROVED rows come from main's merged work, and `lint/baseline.json` is untouched.
- **Tests contract.** `git diff --numstat 9a8ecc3c..HEAD -- tests/features/claude_host` gives `23 0 FEATURE.md`, `4 0 README.md` and `377 0 test_claude_host_review_gaps.py`. Against 615fc54a, this iteration changed only those three files and `vidbyte/harnesses/native/claude/session.py`.

## Per finding

### R-22 (Major): fixed @b5989730

**Root cause.** R-2's yield sat in `_query`, after `_take_steer` had already emptied the steer slot. Every stop path clears only that slot: `_watch`, `_expire`, `interrupt` and `close`. A failed steer interrupt withdraws only while `self._steer is not None`. So a message that had been taken but not yet written was out of reach for one loop pass.

**Change** (session.py, `+12/−11`):
- `_take_steer` is now `async` and opens with `if self._steer is not None: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)`, before `steer, self._steer = self._steer, None`.
- `run` awaits it: `prompt = await self._take_steer() if await self._read(stream) else None`.
- The yield and its comment are gone from `_query`.
- The header's KNOWN EDGE CASES sentence and the `_take_steer` docstring say where the yield now sits.

The call depth is unchanged (`run` → `_take_steer` already existed), and `CLAUDE_STEER_YIELD_SECONDS` is kept, because A007 rejects a literal `asyncio.sleep(0)`.

**Alternatives rejected:**
- Re-checking after a yield in `_query` misses P3 and would have to un-count `_prompts_sent`.
- A yield inside `_read` breaks S024.
- Awaiting the interrupt task breaks AC-37(d), as iteration 1 found.

**Tests.** `StopInSteerWindowTests` adds P1 (caller interrupt), P2b (`aclose` scheduled before `finish()`) and P3 (a failed steer interrupt). The red run against the unfixed session.py (identical to 615fc54a's) gave `3 failed in 0.91s`:
- `None != 'action.precondition_failed'`, twice;
- `Lists differ: ['Summarize the repository layout.', 'focus on tests'] != ['Summarize the repository layout.']`.

With the fix: `3 passed in 0.78s`, and the pack gave `180 passed`.

**Probe** (`repair2/probe_fixed.py`), against the fixed module:
- P1, P2b and P4 → `raised action.precondition_failed`, with no second query.
- P3 → `raised claude.process_exited`, with no steered query; final `completed 'The first answer.'`.
- R-2 control → `[…,'receive_messages','interrupt','query','disconnect']` → `completed 'steered answer'`.
- These results match the verifier's candidate column exactly.

### R-23 (Minor): fixed @2c537b1a

**Root cause.** `_result`'s result fields change only in `_on_result`, so the snapshot of a steered prompt that never got its own result still showed the interrupted prompt's fields.

**Change** (session.py, `+5/−1`):
- Inside `_take_steer`'s `if steer is not None:`, after `self._steered = self._steers`, the code applies `replace(self._result, result_text="", structured_output=None, num_turns=None, duration_ms=None, stop_reason="", terminal_reason="", permission_denials=())`.
- A three-line comment says why, and the docstring names the reset.
- `session_id`, `hooks_applied` and `total_cost_usd` (INV-20) stay, and `_outcome` is untouched.

**Test.** `SteeredResultFieldsTests` sets `fake.interrupt_reply` to a full result, so every one of the seven fields is non-default when the test is red. With the verifier's draft, which used the default interrupted result, a partial reset would have passed. The steered prompt's reply is the init message and then END.
- **Red at b5989730:** `Tuples differ: ('The parser bug is fixed.', {'summary': 'P[113 chars]'),)) != ('', None, None, None, '', '', ())`.
- **Green with the fix.** The test also asserts `total_cost_usd == 0.008` and the code `claude.process_exited`.

**All four new tests against 615fc54a's session.py.** I wrote that version over the working file and restored it afterwards. Result: `4 failed in 0.93s`, with the four assertion messages above.

### R-24 (Minor, spec text): fixed @9211d4ef (spec r6), checked here

- The code now matches deviation 14 and row 7: one yield, inside `_take_steer`, before the take, and only while a steer is pending.
- It matches row 14: `CLAUDE_STEER_YIELD_SECONDS = 0` at vidbyte/lib/constants/claude.py:54.
- It matches EC-52 and row 12: `_on_rate_limit` skips an unknown type, status or overage status.
- No other file in vidbyte, tests, lint or REPO_MAP.md describes the old placement.
- spec.md is unedited.

## Test changes proposed (BLOCKED)

None. No existing test was changed. The 165 original tests and the 12 from iteration 1 are byte-identical, and this iteration only appended lines.

## Findings I believe are wrong

None.

## What remains open, and what I would try next

- **No confirmed finding and no gate is open.**
- **Follow-ups not handed in:** R-15, R-16, R-17, R-18, R-20 (scope-adding, NG-8) and R-21.
- **P4, the time budget landing in the pass, has no committed test.** A deterministic test must start `ClaudeLiveSession._watch(client, 0)` by hand, which reaches into private state. The probe shows the fix covers it. If a reviewer asks for a test, the least intrusive shape is the probe's: take the session from `host._sessions[handle.handle_id]`, assign `_watchdog = asyncio.ensure_future(session._watch(client, 0))` before `client.finish(...)`, then call the steer directly.
- **The verifier's residual, which I did not raise as a finding.** Suppose a steer's interrupt raises in the pass and a second `steer()` from another task is stored in that same pass. The second message is then taken without a yield of its own. That needs two steers in one loop pass, so the exposure is negligible.
