# S3 · Implementer report: agent-output-connectors

- **Status:** DONE. All 36 §12.3 rows are built, and every local gate passes.
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/882 (draft, placeholder body).
- **Spec:** r5, with frontmatter `status: implemented` and `pr:` set. §17 has the S3 row and an "Implementation deviations" list.
- **Dispatched CI (not waited on):** `ci.yml` run 38194285572 and `static-policy.yml` run 38194287162, both on `feat/agent-output-connectors`.
- **Row-27 blocker (S3-1):** resolved by the orchestrator's option 2, as spec r5 describes. `_generate_reply` measures 10 / 9 / 50, the same as the base commit, so S008 stays at its baseline of 19.

## Commits (S3 only, in §12.6 order)

`git log origin/main..HEAD --oneline` also lists the S0–S2 spec and test commits, which are not repeated here.

| SHA | Row | Subject |
|---|---|---|
| `36e84fed` | 1 | output destination and delivery status enums |
| `8817164b` | 2 | output delivery constants |
| `dc7e1200` | 3 | output content, receipt, request, and SMTP records |
| `53924d2b` | 24 | export output enums from `vidbyte.lib.enums` |
| `3be20d04` | 25 | `OutputDeliveryError` with its diagnostic packet |
| `f4e58b57` | 26 | export `OutputDeliveryError` |
| `d467c46c` | 5 | `BaseOutput` and `OutputArguments` |
| `341ffcd7` | 6 | `OutputText` |
| `4035d639` | 7 | `OutputHttp` and `OutputSmtp` |
| `7c53507e` | 4 | provider base exports |
| `26bd9eed`, `b12daf3d`, `ff2fd34b`, `ee34d69c`, `3a436e71`, `44d46b76`, `5629fdaa`, `873cc1c7`, `eef057a1`, `ccb53d7d`, `5b6a18c7` | 8–18 | Slack, Discord, Teams, Google Chat, Telegram, email, GitHub, Linear, Jira, Notion, webhook |
| `64b32f9b` | 4 | connector exports |
| `a0b1c0cd` | 21 | `OutputConnector` and `OutputShaping` |
| `960f626d` | 22 | `OutputDispatcher` |
| `f1e767b9` | 20 | the `vidbyte.agents.output` package (18 names) |
| `d0e34971` | 29 | `JevAgentSettings.outputs` |
| `1b26a42b` | — | BLOCKED-round report |
| `4346dfb5` | 27 | `outputs=` on `BaseAgent`, `_deliver_outputs`, `_record_last_trace` (cites S008, S3-1) |
| `498a566c` | 28 | forks get `outputs=()` |
| `7a17fc09` | 30 | `JevAgent` passes `settings.outputs` |
| `839e8e33` | 31 | 17 root exports |
| `7fedbbc5` | 32 | `contracts/sdk-public-api.json` regenerated (separate commit, C016) |
| `90db7eb1` | 19 | `vidbyte/lib/outputs/README.md` |
| `f03454bd` | 23 | `vidbyte/agents/output/README.md` |
| `b0b9378a` | 33 | `vidbyte/agents/README.md` section and Key Modules line |
| `7838376e` | 34 | `vidbyte/agents/jev/README.md` paragraph |
| `154339bb` | 35 | `vidbyte/lib/README.md` Key Modules line |
| `fa430c8f` | 36 | `REPO_MAP.md` folder entries |
| `f55f3a7f` | — | spec frontmatter: draft PR and `status: implemented` |
| `58238a64` | — | spec §17 S3 row and implementation deviations |

## Data flow, as built

1. **Construction.** `BaseAgent(outputs=...)`, or `JevAgentSettings(outputs=...)` passed on by `JevAgent`, runs `OutputDispatcher.connectors`, which validates the value into a tuple of distinct connector instances (`vidbyte/agents/output/dispatcher.py`, `vidbyte/agents/base.py`, `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/agent.py`).
2. **Credentials.** Each connector resolves its credential once in `__init__` through `OutputArguments`: the explicit argument first, then the environment variable (`vidbyte/lib/outputs/base.py`).
3. **Forks and restore.** `AgentForker.fork` passes `outputs=()` (`vidbyte/agents/fork.py`). `BaseAgent.restore(state, outputs=...)` re-attaches only what the caller passes. `export_state` is unchanged.
4. **The run.** `_generate_reply` records the reply, calls `_record_last_trace(metadata)`, runs the handoff, notifies the session, and runs `_assert_schema_satisfied`. Then, `if self.outputs:`, it awaits `self._deliver_outputs(reply, metadata)`, before the queued-prompt drain (`vidbyte/agents/base.py`).
5. **Failure handling.** `_deliver_outputs` awaits `OutputDispatcher.deliver(self.outputs, reply, metadata)`. On any `BaseException`, it clears `_queued_prompts`, calls `_notify_session_exception`, and re-raises.
6. **Dispatch.** `OutputDispatcher.deliver` works in this order:
   1. The skip rule (`OutputShaping.is_deliverable`): a blank reply, or a stop reason other than `final_response` or `is_done`, gives every connector a SKIPPED receipt.
   2. It gathers `_deliver_one` for every connector with `return_exceptions=True` and re-raises any non-`Exception` result.
   3. It builds the receipts in configured order and stores them at `metadata["deliveries"]`.
   4. If any receipt failed, it raises `OutputDeliveryError` chained from the first `Exception`.
7. **One connector.** `_deliver_one` runs `render`, or `OutputShaping.content`, and checks that the result is `OutputContent`. It then runs `asyncio.wait_for(send, OUTPUT_DELIVERY_DEADLINE_SECONDS)`; a timeout becomes FAILED `network` (`vidbyte/agents/output/connector.py`).
8. **HTTP send.** Each HTTP connector's `send` shapes text with `OutputText` and builds one `OutputRequest`. `OutputHttp.post` sends it through `HttpTransport().request` with the §9.2 arguments, and maps the result to a receipt through `_error_code` and `_link` (`vidbyte/lib/outputs/*.py`, `delivery.py`, `text.py`).
9. **Email send.** `EmailOutput.send` builds an `EmailMessage` and runs `asyncio.to_thread(OutputSmtp.send, ...)`, which uses STARTTLS, or implicit TLS on port 465 (`email.py`, `delivery.py`).
10. **Public surface.** `vidbyte.agents.output` exports 18 names and the root `vidbyte` exports 17. `contracts/sdk-public-api.json` lists 623 exports.

## §12.3 checklist

- [x] P1: rows 1, 2, 3, 24, 25, 26.
- [x] P2: rows 4, 5, 6, 7.
- [x] P3: rows 8–18, and row 4's connector exports.
- [x] P4: rows 21, 22, 20, 29, 27, 28, 30.
- [x] P5: row 31, then row 32 in its own commit, then rows 19, 23, 33, 34, 35, 36.

**Mechanical check.** Every CREATE row shows `A` and every MODIFY row shows `M` in `git diff --name-status db3988ff..HEAD`. The diff contains no other file outside the spec folder and the S2 tests.

**§12.4.** Every item is satisfied, except one pre-existing exception. On the base commit, `vidbyte/lib/errors/__init__.py` already reports I001 at line 22 (reproduced on `git show db3988ff:...`). It was left unsorted. Other checks:
- **I001 filter:** clean for every new file and for `jev/settings.py`, `errors/base.py`, `enums/__init__.py`, and `vidbyte/__init__.py`.
- **72-column comments:** the awk check prints nothing for any new file or any added comment line.
- **Imports:** nothing under `vidbyte/lib/` imports `vidbyte.agents` at runtime, and `vidbyte/agents/output/` imports nothing from `vidbyte.agents` outside itself.
- **HTTP clients:** no `httpx`, `requests`, `aiohttp`, `http.client`, or `urllib.request` under `vidbyte/lib/outputs/`.
- **Diff scan:** no `TODO`, `noqa`, or `type: ignore` in the diff.

**§12.5.** Every action is done. `llms.txt` and `artifacts/file_index.md` are untouched.

**§6.2.** No Proof cell was blank. All 26 already name tests, and AC-22 names the gate commands, so there was no SHA to fill in.

## Deviations (also recorded under spec §17)

1. **`OutputArguments.optional_callable`:** the parameter is typed `Callable[[AgentMessage], OutputContent] | None` instead of `object` (§8.5). This avoids a `cast` under mypy's `disallow_any_generics`, and the runtime check is unchanged. The orchestrator accepted it.
2. **`OutputArguments.identifier`:** returns the canonical lowercase, dashed UUID.
3. **`OutputShaping.content`:** falls back to `reply.sender` whenever no title is found (`title or reply.sender`).
4. **`OutputRequest`:** rejects header keys that are not lowercase.
5. **Pre-existing I001 in `vidbyte/lib/errors/__init__.py`:** left as it was on the base commit. S051 is at 258 against a baseline of 259.

The `*_MENTION_PREFIX` names and `OUTPUT_ERROR_TOKEN_MAX_CHARS` were deviations in the BLOCKED round. Spec r5 adopted them, so they are no longer deviations.

## Files outside §12.3

None, apart from the spec folder itself: `spec.md` frontmatter and §17, and this report.

## Budget (§8.4)

- **New files:** 23 of 23 (21 `.py` and 2 READMEs).
- **Classes:** 26 of 26 in 19 modules. That is 25 classes in 18 new modules, plus `OutputDeliveryError` in `vidbyte/lib/errors/base.py`.
- **New dependencies:** 0. `pyproject.toml` is unchanged.
- **Exports:** 17 root exports and 18 names in `vidbyte.agents.output`.
- **`vidbyte/agents/base.py`:** +29 / −4 lines against a limit of 35 added lines, including the 3 moved last-trace lines.
- **Module sizes:** the largest new module is 149 lines; connector modules are 77 lines at most.

## Gates (final lines)

1. **Feature pack:** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`
   ```
   313 passed in 1.71s
   ```
2. **Touched suites:** fork isolation, durable sessions, fork tool, Jev agent, queued-prompt usage, both restore suites, session failures, workflow forks, the CodingAgent contract, and the README size limit.
   ```
   294 passed in 2.36s
   ```
3. **S008 measurement** (`ruff --select C901,PLR0912,PLR0915` with all limits set to 1), `_generate_reply`:
   ```
   C901 `_generate_reply` is too complex (10 > 1)
   PLR0912 Too many branches (9 > 1)
   PLR0915 Too many statements (50 > 1)
   ```
   The base commit measures the same 10 / 9 / 50.
4. **Lint:** `python lint/run.py`
   ```
   S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all

   S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

   SDK-LINT: PASS
   ```
   S008 shows `19 19 RATCHETED`. S054 shows `3 3 RATCHETED`. S009 shows `349 350 IMPROVED`. A009 is `0 0 CLEAN`. No rule is REGRESSED, and no baseline was touched.
5. **Source stage:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
   ```
   ====================== 3516 passed, 12 skipped in 29.73s ======================
   CI passed.
   ```
6. **Full gate:** `python scripts/run_ci.py` with PYTHONPATH unset (lint, compileall, the context and trace checks, pytest, sdist and wheel build, isolated install, and smoke)
   ```
   No broken requirements found.
   Installed vidbyte-sdk 0.2.1 passed smoke checks.
   CI passed.
   ```
7. **Contract check:** `python scripts/generate-sdk-public-api.py --check`
   ```
   contracts/sdk-public-api.json is current at 839e8e33a369743d0643463137f05a6b5eb39282 (vidbyte-sdk 0.2.1, 623 exports).
   ```
8. **Semgrep 1.170.1 (§11):** run from a dedicated scratchpad venv, with the venv's `Scripts` first on PATH, because the global install is broken by mcp 2.x.
   ```
   1/1: ✓ All tests passed
   Ran 1 rule on 896 files: 0 findings.
   ```

## Tricky parts for the next agent

- **`_generate_reply` is exactly at the S008 limit (10 / 9 / 50).** Any added statement or branch there regresses S008. The `if self.outputs:` guard is what keeps INV-22 (an agent without outputs adds no await). The unguarded call would measure 9 / 8 / 49.
- **`_deliver_outputs` calls `_notify_session_exception` itself,** because the runtime `try` in `_generate_reply` has already closed. AC-23(b) proves this for an agent run directly. `Session.run` also captures the failure, and AC-23(a) checks it is captured once.
- **Cancellation:** `deliver` re-raises a `CancelledError` that `gather` returns, and `_deliver_outputs` catches it as a `BaseException`, clears the run's queued prompts, and re-raises (AC-18).
- **The delivery deadline** is read from the module global at call time, so tests can monkeypatch `dispatcher.OUTPUT_DELIVERY_DEADLINE_SECONDS`.
- **README facts:** `vidbyte/lib/outputs/README.md` states only facts verified in spec §9.2's catalog (a). For example, it names only Gmail's SMTP host, because the other hosts were not verified; it links each provider's SMTP page instead.
- **Pre-existing, not ours:** `python scripts/test-github-content-readmes.py` reports 110/114, with all 4 failures in `vidbyte/harnesses/README.md`. That script is not part of `run_ci`.
- **Windows line endings:** the working tree is CRLF and git normalizes it. New READMEs were written with LF and are normalized on commit.
