LENS: conformance
VERDICT: SOUND — All seven repairs (R-1 to R-7) hold on every path I could drive, on WSL 3.12.3, Windows 3.11.0 and Windows 3.13.1. They introduce no regression and no unreported deviation. One Minor leftover remains in the model-facing bash description.

Scope: the code diff `4e285d91..581fc272 -- vidbyte/ tests/` (the `bash.py` `_stop` body, its `@intent` and description, `_spawn`'s hint, `coding.py` `_resolve_root` and its header, the agents README bullet, the EC-11 test and the pack README). I also re-walked every spec ID against HEAD `b197b8ed`, which differs from `581fc272` only under `docs/`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **`_stop` now holds D-18, INV-12 and INV-26 on every path, without touching the stop policy.**
  - What changed: a `try:` around the kill and the bounded wait, `PermissionError` suppressed next to `ProcessLookupError`, and `transport.close()` in `finally:` under `contextlib.suppress(PermissionError)` (`bash.py:179-191`).
  - What did not change: `_stop` is still reached only from the two handlers (`bash.py:114`, `:122`), so a normal completion still kills and closes nothing (INV-25). Its nesting is depth 3 (S024 21/25).
  - Do not "simplify" either suppression away. The killpg one alone, or the `finally` alone, still raises (probe row `[REVIEWERS-FIX] … raised PermissionError`).
- **`_resolve_root` uses `os.path.isdir(root_dir)` behind the unchanged `isinstance(root_dir, (str, os.PathLike))` guard** (`coding.py:102`).
  - It rejects `""` and `" "`.
  - It accepts `"."`, an absolute `str`, a `Path`, a custom `os.PathLike` and a `str` subclass.
  - The error type, message and `details` shape are as before (§9.2).
- **The bash description is one five-sentence f-string with the EC-14 Windows caveat, and it states every §12.3 row 1 content item** (`bash.py:68`).
  - S025's `SentenceCounter` gives 5 for the tool description and 4 for the `command` parameter. The text has no examples, and S062 is clean.
  - The exit-code clause is now limited to commands that finish, which matches `_render` (`bash.py:197`) against the timeout marker (`bash.py:117`).
- **The test tree changed only where the orchestrator granted it.**
  - `git diff d158d5f6..b197b8ed --stat -- tests/ pyproject.toml` lists exactly the two granted files. Against `origin/main`, the test tree is additions only (all `A`).
  - `lint/` and `lint/baseline.json` show a 0-line diff.
  - The EC-11 test now fails the `stdin`-dropping mutant on both platforms, so it can no longer pass vacuously.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Minor] [fix completeness (R-4) / model-facing parity] vidbyte/tools/builtins/bash.py:68 — The R-4 rewrite left the last sentence saying the background process "is killed", which is false on Windows, the platform whose caveat R-4 added one sentence earlier
  Evidence: Sentence 4 now reads "…a command still running after {BASH_TIMEOUT_SECONDS:g} seconds is stopped instead, except that on Windows only Git's bash launcher is stopped and the command itself may keep running." Sentence 5 still reads "A background process must redirect both its standard output and its standard error to a file, otherwise the call waits for the time limit and the process is killed." On win32, `_stop` kills only the launcher, and only while `process.returncode is None` (`bash.py:183-184`). A background child that holds the pipe outlives the launcher's exit, so at the limit nothing kills it. EC-14 says "killing the launcher — and even `taskkill /F /T` — leaves the command running". Field guide `model-facing-tool-contracts.md` asks for a "Check: … validation/rendering parity".
  Failure: On Windows, a model runs `python server.py &` without redirecting its streams. The call waits 600 s and returns `timeout`. The model has been told the server was killed, but it is still running and holding its port. A retry then fails with "address in use", and the model has been told no process is left. (For a conventions lens: a human reviewer would write "sentence 5 contradicts sentence 4 on Windows".)
  Smallest fix: End sentence 5 with "…otherwise the call waits for the time limit and is then stopped as described above". Keep the one literal and five sentences.
  Spec IDs: EC-14 (spirit; the caveat itself is stated), EC-9. Note: §12.3 row 1 dictates "and the process is killed" verbatim, so the implementation follows the spec's wording. This is why it is Minor, and it may also be a follow-up.

VERIFIED CLAIMS: <each claim checked and whether it held>
- **HELD: R-1 @415f7c22, "`_stop` never raises and always closes the transport", on POSIX.**
  - Ran on WSL 3.12.3 against HEAD with `probe_stop.py` and `probe_eperm_alive.py`. Every `[CODE]` row ends `transport is_closing=True`:
    - `timeout, then cancel during grace wait: raised CancelledError after 1.60s`
    - `cancel, then second cancel during grace wait: raised CancelledError after 1.00s`
    - `EPERM on timeout path: returned ERROR {'error': 'timeout', 'truncated': False} after 1.01s`
    - `EPERM on cancel path: raised CancelledError after 0.50s`
    - `timeout path, leader alive and unsignallable: returned ERROR {'error': 'timeout'…} after 2.00s`
    - `cancel path, leader alive and unsignallable: raised CancelledError after 1.50s`
  - Leftover processes: none.
- **HELD: R-1 on Windows, including Python 3.13, where `Process.wait()` waits for the pipe.**
  - Method: the real `bash.py`, exec'd against in-memory stubs of its two `vidbyte` imports, with limit 1 s and grace 1 s and the command `sleep 6.17`.
  - 3.13.1:
    - normal completion `SUCCESS` in 0.03 s, `is_closing=True`
    - timeout `ERROR {'error': 'timeout'}` in 2.02 s (≤ limit + grace), `is_closing=True`
    - cancel at 0.5 s → `CancelledError` at 1.52 s
    - cancel, then a second cancel at 0.8 s → `CancelledError` at 0.81 s, `is_closing=True`
    - timeout, then cancel during the grace wait → `CancelledError` at 1.51 s, `is_closing=True`
    - after `asyncio.run`: `unraisable=[] warnings=[]`
  - 3.11.0: timeout at 1.03 s, cancel at 0.50 s, all rows `is_closing=True`, nothing unraisable.
  - `tasklist` afterwards showed no `sleep.exe`.
  - This also gives evidence for the open manual halves of AC-27 (Python 3.13) and AC-28 on Windows.
- **HELD: R-2 @a49b7dd8, "the EC-11 test can now fail".**
  - `drive_ec11.py existing code` → `1 passed` (Windows 0.10 s; WSL 0.08 s).
  - `existing mutant` → `1 failed in 10.26s … pytest_exit=1 mutant_spawns=1` (Windows) and `1 failed in 10.81s … pytest_exit=1` (WSL).
- **HELD: R-3 @64df91ce, "`root_dir=""` is rejected; every allowed type still works".**
  - Rejected with `ConfigurationError`: `""` (details `{'root_dir': ''}`), `" "`, a file, a missing path, a `str` with NUL, `42`, `None`, `bytes`.
  - Accepted: `"."`, `Path("")`, `Path(".")` (the known limit, since `Path("")` is `Path(".")`), an absolute `str`, a `Path`, a custom `os.PathLike` and a `str` subclass.
  - A bytes-returning `os.PathLike` raises `TypeError` from `Path(...)`. This is not a regression: before R-3, `Path(root_dir).is_dir()` raised the same `TypeError`, and §8.5 types `root_dir` as `str | Path`.
- **HELD: R-4 @977c7d23, "5 sentences, Windows caveat, exit-code clause only for finished commands, every §12.3 row 1 item".**
  - S025 `SentenceCounter().count(...)` gives tool 5 and param 4. All 8 row 1 content items are present.
  - The one residual inconsistency is R-C1.
- **HELD: R-5 @15aed1e0, "`CodingAgent.restore(state)` raises TypeError".**
  - `CodingAgent.restore(st)` → `TypeError CodingAgent.__init__() missing 1 required keyword-only argument: 'root_dir'`.
  - `BaseAgent.restore(st, tools=a.tools.all())` → `BaseAgent` with the seven names and `['execute','read','safe','write']`.
  - `fork()` → `BaseAgent`.
  - The README bullet and the header line 9 match this. Line 5 of the header no longer lists "restores".
- **HELD: R-6 @388993f9, "neutral hint, class name only" (EC-15, §8.5).**
  - A removed root gives `(NotADirectoryError). Check that the root folder still exists, and that the command has no NUL characters and is not too long.`, and a NUL gives `(ValueError)` with the same hint.
  - Both carry `{'error': 'spawn_failed'}`, and no exception message appears.
- **HELD: R-7 @581fc272.** `read_lines.py`, `write_text.py` and `replace_text.py` are in `vidbyte/tools/filesystem/`, `glob.py` and `grep.py` are in `vidbyte/tools/builtins/code_search/`, and `fetch.py` is in `vidbyte/tools/builtins/operations/`. This matches the README line 7.
- **HELD: AC-1, the spec §4 snippet run as written** from a temp folder holding `my-project`, with the pack's offline `ScriptedToolRunner` bound for `run`.
  - It printed the absolute `…\my-project` (equal to the expected path) and `('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')`.
  - `run` returned with `('succeeded', 'succeeded')`, and the policy is allow-all.
- **HELD: AC-19 / NFR-2 lint.**
  - `SDK-LINT: PASS`, with every touched rule at main's count: A001 643, A002 682, A006 34, A007 255, S009 340, S015 13, S016 50, S017 78, S019 5, S024 21, S025 261, S039 5, S045 2, S051 258, S062 889.
  - C016, S006, S052 and S055 are 0. No IMPROVED headroom was consumed.
- **HELD: §8.4 budget / NFR-1.**
  - Code files touched against main: exactly the 8 §12.3 files.
  - New source files: 2. Classes: 2 in `coding.py`, 1 in `bash.py`. Dependencies: 0.
  - Line counts: 178 (≤ 200) and 200 (≤ 250).
  - No `noqa`, `type: ignore`, env read, `shell=True`, `create_subprocess_shell`, `os.system` or Sandbox use in either file.
- **HELD: §14 Never.** The `lint/` diff is 0 lines. Tests against main are additions only, and since S2 only the two granted files changed.
- **HELD: deviations are recorded.** The R-1 `PermissionError` and `finally` change is in spec §17 "Implementation deviations". No other repair departs from §12.3. R-3, R-4 and R-6 change implementation detail and text that §12.3 leaves open.
- **HELD: gates.**
  - Remote CI `38075705506` and Static policy `38075707127` both `completed success` on `581fc272`.
  - `581fc272..b197b8ed` touches only `docs/`, and `origin/feat/coding-agent` is `b197b8ed`.
  - Full local pytest: 2715 passed, 12 skipped.
- **HELD, with a note: INV-12 "always propagates" within `_stop`.**
  - No handler in `_stop` catches `CancelledError`: `suppress(TimeoutError)` does not match it, and the kill block has no await.
  - Residual: on Python 3.11, stdlib `asyncio.wait_for` returns the inner result when a cancel lands exactly as the awaited future completes. This is pre-existing, comes from the `wait_for` that D-14 and D-17 mandate, applies to every `wait_for` in the SDK, and was not introduced by the repairs. Not raised.
- **DID NOT HOLD (docs-only, no effect on the PR): the S5 repair report's "S025 … 261/263 (it was 263 before R-4)".** The S3 report and review.md both record S025 = 261 at `4c4a62ef`. The old 6-sentence description already met S025's ≥ 4 floor, so R-4 could not move the count.

COMMANDS RUN: <each with its final lines>
- `git diff --stat origin/main...b197b8ed -- . ':(exclude)docs'` → `16 files changed, 1866 insertions(+), 4 deletions(-)` (8 §12.3 files plus 8 S2 pack files)
- `git diff origin/main...b197b8ed -- lint/baseline.json lint/ | wc -l` → `0`
- `git diff --stat d158d5f6..b197b8ed -- tests/ pyproject.toml` → `2 files changed, 13 insertions(+), 3 deletions(-)` (README.md, test_bash_tool_contract.py)
- `git diff 4e285d91..581fc272 -- vidbyte/ tests/` → reviewed hunk by hunk (bash.py, coding.py, agents README, pack README, EC-11 test)
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/coding_agent/` (Windows 3.11) → `86 passed, 11 skipped in 5.03s`
- `wsl.exe -d MuseUbuntu1 … /tmp/s2-coding-agent-venv/bin/python -m pytest -q -p no:cacheprovider tests/features/coding_agent/` → `97 passed in 17.26s`
- `python lint/run.py` → `S062 RATCHETED: 889 known finding(s)…` / `SDK-LINT: PASS`
- `wsl.exe … python scratchpad/probe_stop.py` → every `[CODE]` row `is_closing=True`; `leftover processes: none`
- `wsl.exe … python scratchpad/probe_eperm_alive.py` → `[CODE] … returned ERROR {'error': 'timeout'…} after 2.00s; transport is_closing=True` / `[CODE] … raised CancelledError after 1.50s; transport is_closing=True`; `leftover processes: none`
- `python scratchpad/drive_ec11.py <wt> <scratch> existing code|mutant` (Windows) → `pytest_exit=0 mutant_spawns=0` / `1 failed in 10.26s … pytest_exit=1 mutant_spawns=1`
- the same in WSL → `1 passed in 0.08s … pytest_exit=0` / `1 failed in 10.81s … pytest_exit=1 mutant_spawns=1`
- stubbed-import probe of the real `bash.py` (heredoc on stdin; no file written), Python 3.13.1 and 3.11.0 on Windows → the rows quoted above; `after asyncio.run: unraisable=[] warnings=[]`; `tasklist /FI "IMAGENAME eq sleep.exe"` → `INFO: No tasks are running…`
- §4 snippet heredoc in a `TemporaryDirectory` → `('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')` / `done ('succeeded', 'succeeded')` / `policy: ['execute', 'read', 'safe', 'write']`
- root_dir probe heredoc → the 16 rows summarized under R-3
- S025 `SentenceCounter` and restore/fork heredoc → `count tool: 5 param: 4` / `CodingAgent.restore -> TypeError … 'root_dir'` / `BaseAgent.restore -> BaseAgent (…7 names…) ['execute', 'read', 'safe', 'write']` / `fork -> BaseAgent`
- spawn_failed heredoc → `removed root: error {'error': 'spawn_failed'} | bash could not start this command (NotADirectoryError). Check that the root folder still exists, …`
- `python -m ruff check --config lint/ruff.toml --select I001 --no-cache <test_bash_tool_contract.py coding.py bash.py>` → `All checks passed!`
- `gh run view 38075705506|38075707127 --json …` → `CI completed success 581fc272` / `Static policy completed success 581fc272`
- `git diff --stat 581fc272..b197b8ed` → `4 files changed, 173 insertions(+), 9 deletions(-)` (all under `docs/spec/coding-agent/`)
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` (full suite, Windows 3.11) → `2715 passed, 12 skipped in 23.31s`
- `git status --short | wc -l` after every run → `0`
