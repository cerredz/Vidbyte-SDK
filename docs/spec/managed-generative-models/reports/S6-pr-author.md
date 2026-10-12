# S6 PR author report: managed-generative-models

- Stage: S6 PR author. Date: 2026-10-11.
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-managed-generative-models`.
- Start HEAD: `6bedcc7d`. End HEAD: `ad8fdf65` (pushed).
- PR: https://github.com/cerredz/Vidbyte-SDK/pull/759. It is still a draft, and its title no longer has `[WIP]`.
- Source changes: none. The only commit is `ad8fdf65`, which touches `spec.md`, `test-plan.md` (lines 3 and 20) and the new `pr-body.md`.
- This report is left untracked, as briefed.

## 1. What the code does (written from the diff before I opened the spec)

Diff used: `git diff origin/main...HEAD` (three dots, from merge base `00cbd6db`). Correction to the briefing: `git diff e91cf822..HEAD` does **not** show the same file set. It leaves out the 15 files committed before the main merge:
- `request.md`, `code-map.md` and the S0 to S2 reports;
- `test-plan.md`;
- 5 of the pack's test and fixture files.

The production `.py` set is identical in both ranges: 9 files, all under `vidbyte/lib/`.

What it does, step by step:
- **The mode enum.** `TextModelMode` (`AUTO`, `VIDBYTE_MANAGED`) is new in `vidbyte/lib/enums/text_model.py`. It is exported from `vidbyte.lib.enums` and re-exported from `vidbyte.lib.config`.
- **The config.** `TextModelConfig` gains a last field, `mode`, and hides `api_key` from repr.
  - `__post_init__` rejects a `mode` that is not the enum. In explicit managed mode it also refuses a custom endpoint and any provider outside the six, at construction.
  - `validate()` picks the path. If `is_vidbyte_managed()`, it checks the shape and then `resolved_vidbyte_api_key()`. Otherwise it calls `ProviderModelRegistry.resolve_api_key` as before.
  - `resolved_api_key()` returns the non-secret `"vidbyte-managed"` placeholder in managed state.
- **The key fall-through.** `ProviderModelRegistry.find_vidbyte_api_key` tries three keys in order:
  1. the explicit key, which counts only if it is `vb_live_`-prefixed;
  2. the provider env var, which also counts only if prefixed;
  3. `VIDBYTE_API_KEY`, for the six managed providers only.

  `resolve_vidbyte_api_key` (explicit key, else `VIDBYTE_API_KEY`, then a full-match against the live-key pattern) is shared with `DecisionModelConfig`. Jev's two inline copies are gone, so C020 drops from 4 to 2.
- **The constants.** All eight live in `vidbyte/lib/constants/jev.py`.
- **The runner at construction.** `TextModelRunner.__init__` validates. For a managed config, it then pins `mode=VIDBYTE_MANAGED`, the resolved Vidbyte key, `max_output_tokens or 8192`, and `max(630.0, timeout)`. The floor comes first, so NaN becomes 630.
- **The runner per call.** `arun` builds a fresh `VidbyteGatewayTransport(self._transport, provider, model, api_key)` for each managed call. The unchanged adapter builds its native body against it.
- **The gateway transport.** `VidbyteGatewayTransport.request` handles one call:
  - It ignores the adapter's URL and headers and mints one `uuid4().hex` key.
  - It builds `bearer_headers(key)` plus `Idempotency-Key`, and the envelope `{provider, model, body}`.
  - It takes `deadline = loop.time() + timeout_seconds` and makes the first POST.
  - It re-sends at most twice (waits of 0.5 s and 1.0 s) while the answer is a 409, a 502 or not a JSON object, and `loop.time() + wait < deadline`.
  - A 2xx JSON object is returned unchanged. Anything else raises `ProviderRequestError(provider="vidbyte", status_code)` with an SDK-written reason.
  - `_send` records only the exception class. The raise happens after every `except` block, so there is no `__cause__` or `__context__`. Cancellation is not caught.
- **Streaming.** `StreamingTextModelRunner.__init__` refuses managed state after `validate()` and before the provider check. The way-forward clause depends on whether the runner can stream that provider.
- **Lint and docs.** The platform contract is re-vendored (byte copy of backend `ceabda93`, blob `56d4d0b3`), with a Provenance row; the C020 baseline goes from 4 to 2; the README gains a section.
- **Tests.** A 39-test pack. One existing Jev test now blanks `VIDBYTE_API_KEY`.

Two paths I checked and found sound:
- The agent key-crossing guards copy `agent.runner_config`, not the runner's pinned config (`vidbyte/agents/fork.py:85-95`, `vidbyte/agents/settings/fallback.py:155-162`). A pinned `mode=VIDBYTE_MANAGED` or a pinned Vidbyte key therefore never leaks into a child of another provider.
- Every provider has a registered env var, so `find_vidbyte_api_key` cannot raise for a known provider.

## 2. Snippet output (spec §4, run exactly as written)

The snippet ran in-process. The pack's `ScriptedGateway` was patched in at `vidbyte.lib.runners.text.HttpTransport`, and the key was a fake (`"vb_live_" + "a" * 32`). There was no network, and the environment was cleared. The script is `scratchpad/snippet_s4.py`.

```text
openai gpt-5.5
Hi
2
--- recorded by the fake transport ---
requests: 1
POST https://vidbyte-backend.onrender.com/api/v1/models/generate
headers: ['authorization', 'content-type', 'idempotency-key'] | idempotency-key is 32 hex: True
{"provider": "openai", "model": "gpt-5.5", "body": {"model": "gpt-5.5", "input": "Say hi in one word.", "max_output_tokens": 8192}}
timeout_seconds: 630.0
```

The AC-1 test gave `1 passed, 38 deselected in 0.68s`. The snippet runs as written, so there is no AC-1 open item.

## 3. Deviations found (all are in the PR body under "Deviations from the spec")

1. **EC-26.** A 404 is worded by row 6, not as "Vidbyte returned HTTP 404" (§17 deviation 1; spec synced in `15203ae4`).
2. **Contract copy.** It already carries backend main's agent-run routes and four `agent_run_*` codes (§17 deviation 2).
3. **README example.** The comments are moved off column 0, and it prints `response.text, response.usage` rather than §4's three lines (§17 deviation 3, plus the print difference, which I noticed myself).
4. **Re-send wording.** Per r5 (§17 deviation 4).
5. **The backend contract moved past spec A-1** (backend r3 → #672's r4). It now refuses the `gpt-5.6` family, requires `max_tokens` for DeepSeek, and adds rules for the `cache_control` TTL and Gemini `responseModalities`. I checked the last three against the SDK:
   - managed DeepSeek bodies always carry `max_tokens`;
   - `grep cache_control|responseModalities vidbyte/providers/*.py` finds nothing.

   Only the `gpt-5.6` refusal reaches SDK callers. It is stated as a known limitation.

§5 was checked against the code and still matches; it is unchanged. The re-review reached the same verdict.

## 4. Docs edits made (granted list only)

- `spec.md`:
  - frontmatter: `status: pr-open`, `updated: 2026-10-11`; `pr` was already set;
  - a new §6.2 AC-28 row (line 242), whose proof is the five `CumulativeDeadlineTests` and `LastAttemptTests` names, with the two `DirectValidateTests` named as backing EC-7 and EC-3;
  - EC-16 (line 263) now quotes both shipped refusal messages. I verified them with an in-process probe for openai and kimi;
  - one §17 row (line 913).
- `test-plan.md`:
  - line 3: r4 → r5;
  - line 20: EC-38 is moved out of the F row, and the row now points to the deadline tests.
  - `git diff -U0` shows only `@@ -3 +3 @@` and `@@ -20 +20 @@`.

## 5. Gates run at this head (all with `env -u DEEPSEEK_API_KEY -u VIDBYTE_API_KEY PYTHONPATH=$(pwd)`)

| Gate | Command | Result |
|---|---|---|
| Pack | `python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider` | `39 passed in 0.90s` |
| AC-1 | the same, with `-k test_readme_snippet_…` | `1 passed, 38 deselected in 0.68s` |
| Full suite | `python -m pytest tests -q -p no:cacheprovider` | `3011 passed, 1 skipped in 15.82s` |
| CI source stage | `python scripts/run_ci.py --stage source` | `3011 passed, 1 skipped in 15.51s` / `CI passed.` (exit 0) |
| Lint | `python lint/run.py`, at `6bedcc7d` and again at `ad8fdf65` | A002 652/703 IMPROVED, C017 0, C018 1, C019 0, C020 2, S020 1/1, S064 4/4, `SDK-LINT: PASS` |

These were not run here and are quoted from verify-log at `90459fb8` instead; only docs have changed since (`git diff --stat 90459fb8..HEAD -- . ':!docs'` is empty):
- the package stage (it installs the package);
- semgrep (the scratch venv belongs to an earlier session);
- the network-blocked suite.

Packaging: this PR adds no package data. `find_packages(include=['vidbyte*'])` contains `vidbyte.lib.http` and `vidbyte.lib.enums`. Note that `import vidbyte` alone does not load `vidbyte_gateway`, so the smoke test does not import it.

## 6. Final PR state

`gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/759 --json title,isDraft,baseRefName,url`:
```
{"baseRefName":"main","isDraft":true,"title":"feat(lib): add a Vidbyte-managed mode that sends text calls through POST /api/v1/models/generate","url":"https://github.com/cerredz/Vidbyte-SDK/pull/759"}
```
`gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/759`:
```
no checks reported on the 'feat/managed-generative-models' branch
```
The commit API reports 0 check runs and 0 statuses on `ad8fdf65`. Both workflows have `workflow_dispatch` only (`ci.yml` keeps `workflow_call`), under a "TEMPORARILY DISABLED" comment. Nothing was dispatched.

The posted body is 31,188 characters. It starts with `## Motivation` and ends with the Claude Code line.

Other facts behind the PR body:
- **Backend PR head.** #672 is at `69a1836a`, and `git -C …/vidbyte rev-parse 69a1836a:contracts/vidbyte-platform-contract.json` gives `56d4d0b3…`, the same blob as the vendored copy.
- **Contract loader.** `lint/core/platform_contract.py:190-194` checks only `schema_version`, `source.repository`, the format of `source.commit`, and `source.generator`.
- **Default OpenAI model.** It is `gpt-5.6-sol` (`vidbyte/lib/registries/models.py:67`). `TextModelConfig` requires a model name, so this default is reached only through `ProviderModelRegistry.default_model` and the `DEFAULT_PROVIDER_MODELS` users. The PR body says "a managed OpenAI call that uses the default, or any `gpt-5.6*` model".
- **Branch freshness.** origin/main (`4b021d7a`) is 23 commits past `00cbd6db`. `git merge-tree --write-tree` gives a clean merge. None of those commits touch this PR's files, `lint/baseline.json` or `lint/contracts/`.

## 7. Candidate field-guide lessons (report only; not written to the field guide)

1. **@intent placement (R-1, conventions).**
   - Trigger: adding a `# @intent` block to a main function.
   - Action: put the block directly above the lines it explains, one short block per step. Do not put it at the top of the method, fused with narration.
   - Reason: the owner rejected the top-of-method shape on #690 and accepted the moved shape in #747 (`57639080`). A002 counts the block wherever it sits, so lint does not catch this.
   - Quick check: the first code line under each block is the code the slug names, and `python lint/run.py --rule A002` does not rise.
   - Link: PR #759, `92d3d690`.
2. **The marker opens the block (R-5, conventions).**
   - Trigger: writing an `@intent` block under a summary comment.
   - Action: make `# @intent <slug>` the block's first line, and move the summary into a one-line method docstring, as #747 does.
   - Reason: field guide `comment-format.md`: "Keep `# @intent <name>` on its own first line"; no lint rule enforces it.
   - Quick check: an awk scan for `@intent` lines preceded by a `#` line in changed files.
   - Link: PR #759, `23a5e87c`.
3. **One-level call chains in changed code (R-2, conventions).**
   - Trigger: a changed method calls an own-class method that now calls another own-class method.
   - Action: call the lower layer (for example `ProviderModelRegistry`) directly from the main method.
   - Reason: AGENTS.md style 1. The extra hop also re-ran the environment fall-through.
   - Quick check: for each changed method, list the own-class calls made by its callees.
   - Link: PR #759, `745f8efe`.
4. **File Index parity (R-3, repo rule S020).**
   - Trigger: adding a file to a folder whose README has a `## File Index`.
   - Action: add its bullet in the same commit.
   - Reason: S020 counts tracked direct children missing from the index, and lint reads `git ls-files`, so the failure shows only after staging.
   - Quick check: stage, then run `python lint/run.py --rule S020`.
   - Link: PR #759, `8eea0362`.
5. **Env-activated billing makes tests live (R-4, engineering, repo-specific).**
   - Trigger: a lib change that makes an existing env var (such as `VIDBYTE_API_KEY`) switch runners onto a billed network path.
   - Action: blank the variable inside the body of tests with unbound runners: `with patch.dict(os.environ, {"VIDBYTE_API_KEY": ""}):`. Never use the decorator form on `IsolatedAsyncioTestCase`: on Python 3.11.0 the coroutine is never awaited, and the test passes vacuously.
   - Reason: JevAgent developers have the key in their shells, so a plain `pytest` sent a real POST.
   - Quick check: run the full suite with a fake live-format key and a socket-blocking plugin; expect 0 attempts.
   - Link: PR #759, `15eb286e`.
6. **Ratchet headroom hides new A002 names (M-5, conventions).**
   - Trigger: a new public method, `__init__` included, in a file with `@intent` duties.
   - Action: compare the A002 analyzer's finding names between base and head, not the totals.
   - Reason: A002 sits far below its baseline (652 vs 703), so a new finding passes lint.
   - Quick check: diff the names in `python lint/run.py --rule A002 --format json --all` between base and head.
   - Link: PR #759, `443ac21a`.
7. **S064 deadline tests need a fake loop clock (R-6, engineering).**
   - Trigger: testing a sleeping retry loop with a cumulative deadline.
   - Action: patch only the module's `asyncio` attribute with a fake whose `time()` starts away from 0 and whose `sleep()` advances the clock. Use steps that land exactly on the `>=` boundary (0, 600 and 629.5 s against 630 s), and include one timeout above the floor (RR-3).
   - Reason: real clocks cannot pin the comparison or the deadline origin; five mutants survived the first test design.
   - Quick check: mutate `>=` to `>`, move the deadline after the first POST, and take the deadline from the floor constant; each mutant must fail.
   - Link: PR #759, `8eea0362`.
8. **Change behavior, change every description of it (M-1, then RR-2; AGENTS.md style 2).**
   - Trigger: changing what an error message tells the user to do.
   - Action: in the same edit, update the narration comments, the `@intent` text and the README line that describe it.
   - Reason: M-1 fixed the message, but `README.md:269-270` and `streaming_text.py:27-28` and `:58-59` still give the old advice.
   - Quick check: grep the old advice phrase across `README.md` and the module.
   - Link: PR #759, `69ee8aaa`.

## 8. Things that looked wrong while reading (none fixed; no source touched)

- `vidbyte/lib/http/vidbyte_gateway.py:9`: the TESTS header omits `tests/features/sdk_managed_text/test_managed_text_deadline.py` (RR-1, production part).
- `README.md:269-270`, `vidbyte/lib/runners/streaming_text.py:27-28` and `:58-59`: streaming advice that is wrong for gemini, xai, deepseek and kimi (RR-2).
- `tests/features/sdk_managed_text/test_managed_text_deadline.py:40`, `:100` and `:125`: every deadline case uses timeout = floor, so a deadline taken from the floor constant survives (RR-3). The tests are not vacuous otherwise.
- `README.md:254-275` and `vidbyte/lib/http/vidbyte_gateway.py:104`: neither the README's "What managed mode serves and refuses" list nor the 422 remedy names the backend's `gpt-5.6` refusal. The 422 text covers it only as "an unmanaged or unpriced provider or model". This is a docs gap that appeared after #672's repair, not a code bug. It is listed in the PR body's Follow-ups.
- Spec §6.2 lists AC-27 before AC-26 (cosmetic). I did not reorder it, because only the AC-28 row was granted.
- No dead code, and no other test looked vacuous. All 30 spec proof references, and all 36 test names in the PR body, exist on the branch (`git grep "def <name>"`).
