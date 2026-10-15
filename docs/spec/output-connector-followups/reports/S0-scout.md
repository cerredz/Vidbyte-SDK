# S0 Scout report: output-connector-followups

**Status:** DONE. The code map was written to `docs/spec/output-connector-followups/context/code-map.md`, with four sections. No commits, installs, or gate runs were made. No other files were modified.

## Planned file list
These were planned from request.md §B sections 0–5, the §C implementation hints, and the areas hint.

- **Docs:** `vidbyte/lib/outputs/README.md`, `docs/spec/agent-output-connectors/spec.md` (§9.2(b)), `vidbyte/agents/output/README.md`.
- **Shared delivery code:** `vidbyte/lib/outputs/{base,delivery,text,__init__}.py`, `vidbyte/lib/dataclasses/outputs.py`, `vidbyte/lib/enums/outputs.py`, `vidbyte/lib/constants/outputs.py`, `vidbyte/lib/http/transport.py`.
- **Connectors:** `vidbyte/lib/outputs/{slack,discord,teams,google_chat,telegram,email,github,linear,jira,notion,webhook}.py`.
- **New connector modules (GitLab, GitHub job summary, Confluence, Typefully, HubSpot):** these are not created yet; I searched for existing helpers they could reuse.
- **Exports and contract:** `vidbyte/agents/output/__init__.py`, `vidbyte/__init__.py`, `contracts/sdk-public-api.json`.
- **Must-not-change files:** `vidbyte/agents/output/{dispatcher,connector}.py`, `vidbyte/lib/errors/base.py`.
- **Tests:** everything under `tests/features/agent_output_connectors/`.
- **Gates:** `lint/*`, `scripts/run_ci.py`, `.github/workflows/*`, `.semgrep/*`, `pyproject.toml`.

## Files actually read
- **Repo rules:** `AGENTS.md`, `CLAUDE.md`, and the REPO_MAP entries for `vidbyte/lib/outputs/`, `vidbyte/agents/output/`, and `vidbyte/lib/http/`.
- **Allowed docs:**
  - `docs/spec/output-connector-followups/request.md` (in full).
  - `docs/spec/output-connector-followups/pipeline.md` ("Niche facts accumulated").
  - `docs/spec/agent-output-connectors/spec.md`: lines 1–369 (§0–§6), 518–884 (§8.5, §9.1–§9.4 including tables (a) and (b)), and 1034–1236 (§12.1–§12.6, §13). I did not read §7, §8.1–§8.4, §10, §11, or §14–§17.
- **`vidbyte/lib/outputs/`:** every file read in full: `README.md`, `__init__.py`, `base.py`, `delivery.py`, `text.py`, and all 11 connector modules.
- **Shared records and helpers:**
  - `vidbyte/lib/dataclasses/outputs.py`, `vidbyte/lib/enums/outputs.py`, and `vidbyte/lib/constants/outputs.py`, read in full.
  - `vidbyte/lib/enums/__init__.py`, the output lines only.
  - `vidbyte/lib/http/transport.py` (the async part in full, plus the start of the sync part), `vidbyte/lib/http/__init__.py`, and `vidbyte/lib/http/parser.py`.
- **`vidbyte/agents/output/`:** `__init__.py`, `connector.py`, `dispatcher.py`, and `README.md`.
- **Errors:** `vidbyte/lib/errors/base.py` in full, and the `OutputDeliveryError` export in `vidbyte/lib/errors/__init__.py`.
- **`vidbyte/__init__.py`:** the header and the output import and `__all__` sections only.
- **File-append precedents:** `vidbyte/lib/tools/filesystem/backends/local.py` (imports, `write_text`, `append_text`) and `vidbyte/harnesses/stores/file.py` (the `to_thread` append).
- **Contract:** `contracts/README.md`, `scripts/generate-sdk-public-api.py`, and the `contracts/sdk-public-api.json` source fields.
- **Gates and CI:** `scripts/run_ci.py`, `.github/workflows/ci.yml`, `.github/workflows/static-policy.yml`, `.semgrep/typed-mapping-boundary-policy.yml`, and `pyproject.toml` (dependencies).
- **Lint framework:** `lint/README.md`, the rules README, `lint/run.py`, `lint/baseline.json`, `lint/ruff.toml`, `lint/core/ruff.py` (head), discovery (partial), and `lint/core/report.py` (the pass line, via grep).
- **Lint rules read:** A001, A002, A003, A006, A007, A009, S008, S011, S012, S013, S020, S024 (partial), S017 (partial), S041, S045, S046, S047, S050, S052, S054, S056, S061, S062. I read only the headers of S063, S064, C016, and S015.
- **Tests:**
  - All 13 files in `tests/features/agent_output_connectors/`.
  - The fake `_send_once` signatures in `tests/test_web_operation_client_retry.py`, `tests/features/coding_agent/conftest.py`, and `scripts/test-async-http-transport.py` (via grep).
- **Field guide:** `provider-api-contracts.md`, `blocking-lint-invariants.md`, `strict-config-dataclasses.md`, `comment-format.md`, `review-scope.md`, `local-ci-verification.md`, `class-bound-helpers.md`, `diagnostic-context.md`, and `vidbyte-gates.md`.

## What the areas hint / vidbyte-gates.md got wrong
- **vidbyte-gates.md, lint pass line.** It gives the lint pass line as `AGENT-LINT: PASS`. The SDK prints `SDK-LINT: PASS` (`lint/core/report.py:58`).
- **vidbyte-gates.md, full gate.** It describes the gate as `pip install -e .[dev]` once, then `run_ci --stage source`, then `run_ci`. The SDK's AGENTS.md names only `python scripts/run_ci.py`. The PYTHONPATH split comes from the field guide's `local-ci-verification.md`: the source stage with `PYTHONPATH`, the package stage without it.
- **request.md §C "Implementation hints" (the areas hint) is accurate**: file names, README line numbers (Discord 63, Teams 64, Telegram 66, Jira 70, Teams note 110, Email Providers 77), the POST-only `OutputHttp.post`, and the 35 s per-connector deadline. Three corrections and additions:
  - **Deadline.** "A connector may make more than one request inside `send()` without a dispatcher change" is true structurally, but the single 35 s deadline covers about one rate-limited request path. A read, then a write (plus pagination), can exceed it (code-map §4 N-8).
  - **Jira row.** The README already says Jira tokens "expire within 365 days" (line 119), so that docs-pass item is mostly already done.
  - **Files the hint does not name:**
    - `vidbyte/lib/http/transport.py`: exact bytes, and it has no raw-body option.
    - `vidbyte/lib/tools/filesystem/backends/local.py`: the only S061-allowlisted file writer.
    - `tests/features/agent_output_connectors/factories.py`: `HttpScript` cannot return response headers.
    - The pack's docs test, which requires "2026-10-11" in every env-var row.
- **The first-batch pipeline niche fact at pipeline.md line 62** ("delivery is an inline try/except … (no `_deliver_outputs`)") is stale. Spec r5 and later, and the code, use `BaseAgent._deliver_outputs`. This does not affect this run, which does not touch `base.py`.
