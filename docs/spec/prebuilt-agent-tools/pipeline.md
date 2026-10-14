---
slug: prebuilt-agent-tools
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-prebuilt-agent-tools
branch: feat/prebuilt-agent-tools
base_commit: 8387d66680951766f02b0d740d78eb6450cb6419
pr:
until: none
started: 2026-10-14 02:46
---

# Pipeline: A library of 250+ prebuilt agent tools in vidbyte-sdk

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 02:46 | 03:20 | reports/S0-scout.md, reports/S0-research.md | base_commit 8387d666; code-map.md; research.md |
| S1 spec + review | running | 03:25 | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 1/2 (round 1 launched) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-14 02:46 — Unset the branch upstream (`git branch --unset-upstream`) after `git worktree add` set it to `origin/main` — prevents any agent's bare `git push` from targeting main; pushes must be `git push -u origin feat/prebuilt-agent-tools`.
- 2026-10-14 02:48 — Launched a second S0 agent (research scout) in parallel with the code scout, writing `context/research.md` — the user offered to "ground your ideas in recent agentic research"; separating the catalogue research from repo recon keeps the spec author's context on design. It touched no repo code.
- 2026-10-14 02:46 — Assumption recorded in request.md §C (for the spec author to confirm as an A- item): tools are deterministic, local, standard-library only, no network/keys/new deps.

## User replies (verbatim)
- none

## Niche facts accumulated (carried into every later briefing)
- Tools are `BaseTool` subclasses or `@tool`/`FunctionTool` functions; attached via `Agent(tools=...)`, `add_tool`, or a `Tools` collection — *source:* S0 scout
- YAML/declarative discovery only finds public `BaseTool` subclasses exported from `vidbyte.tools.builtins` (`vidbyte/lib/registries/components.py:113,124`); `@tool` functions are never discovered — *source:* S0 scout
- Large-scale precedent: `vidbyte/tools/builtins/reasoning/` (218 classes, a catalog object, CI count guard `scripts/check_reasoning_trace_contracts.py` hard-codes 182 at line 39). `filesystem/` and `calculator.py` carry lint debt — do not copy them — *source:* S0 scout
- A001 file headers required on every `.py` including tests; S025 requires ≥4-sentence descriptions on class-based tools and parameters; S016/S017 constrain error raising/reporting; A007 named constants; S062 bans adjacent string-literal concatenation (use one literal or explicit `+`) — *source:* S0 scout
- Declarative tool lists are capped at 128 entries (`vidbyte/lib/dataclasses/config.py:75`, `vidbyte/lib/dataclasses/agent_descriptor.py:49`) — *source:* S0 scout
- `vidbyte/lib/enums/tools.py` does not exist; a new tool enum goes there and into `vidbyte/lib/enums/__init__.py` `__all__` — *source:* S0 scout
- `vidbyte/__init__.py` is 1,297 lines; any root export triggers C016 and requires `python scripts/generate-sdk-public-api.py` to regenerate `contracts/sdk-public-api.json` — *source:* S0 scout
- Semgrep is NOT in `scripts/run_ci.py`; it runs only in `.github/workflows/static-policy.yml:24-30`; rule `no-untyped-mapping-fallback` likely hits JSON tools under `vidbyte/tools/builtins/` — *source:* S0 scout
- `@tool` parameter descriptions are `""` unless `Annotated[..., Field(description=...)]` (`vidbyte/tools/function_tool.py:117`) — *source:* S0 scout
- Tool names taken already include `diff`, `find`, `stat`, `zip`, `copy`, `checksum`, `glob`, `grep`; reserved `isDone`, `updateTrace`; Codex requires `^[A-Za-z0-9_-]+$`, ≤128 chars, reserves `mcp` — *source:* S0 scout
- Python floor `>=3.11` (pyproject.toml:10) so `tomllib` is available; CI source job runs on ubuntu-latest with 3.11 and 3.12 — *source:* orchestrator check
- `tzdata` is NOT a declared dependency; `zoneinfo` works on this Windows machine only because `tzdata` is installed globally in site-packages. On a clean Windows install `ZoneInfo('America/New_York')` raises `ZoneInfoNotFoundError` — *source:* orchestrator check
- Full gate: `python scripts/run_ci.py` (stages `--stage source`, `--stage package --dist-dir dist`); lint `python lint/run.py [--rule ID]`; one test file `python -m pytest -q tests/<file>.py` — *source:* code-map.md §1.3, §3.3
- Research: tool-selection accuracy drops past ~30–50 tools (Anthropic) and the 90% line sits at 10–15 tools for Haiku-class / 20–30 for Sonnet-class models (production log study); ship category toolsets + a catalogue search, never all 250 at once — *source:* research.md "Recommended grouping"
- Python 3.11+ raises ValueError converting an int over 4,300 digits to str: big-integer/factorial/Fibonacci tools need a digit cap; never change the limit globally — *source:* S0 research
- `statistics.correlation(method="ranked")` (Spearman) is 3.12+; CI also runs 3.11, so implement it by hand — *source:* S0 research
- Avoid platform-dependent stdlib: `mimetypes.guess_type`, `socket.getservbyname`, `locale` — *source:* S0 research
- `re` has no timeout: cap pattern and input length; `xml.etree` must reject DOCTYPE (entity bombs); every enumerating tool needs an output cap plus a truncation notice — *source:* S0 research
- Possible overlap with existing built-ins: `calculator` (exact arithmetic) and `reasoning/{bayesian_update, expected_value_trace, decision_matrix_trace, fermi_estimate}` — verify before selecting — *source:* S0 research
- research.md has 461 candidates in 30 categories, each category marks its "Drop first" rows; 7 categories exceed ~15–20 tools — *source:* S0 research
- Only time-dependent candidate: `current_datetime_in_timezone` — needs an injectable clock for tests — *source:* S0 research
- Contract names (spec r1 §8.5): `PrebuiltTools(Tools)` in `vidbyte/tools/toolsets/prebuilt.py` with static `select_categories`/`get_tools`; `PrebuiltToolCategory` enum (31 members, `values()`); `<Category>ToolFunctions` classes with `tool_functions()`; `PrebuiltToolSupport.argument_error(parameter_name, problem, expected)`; `PrebuiltJsonSchemaValidator.find_violations`; aliases `PrebuiltToolOutput`, `PrebuiltToolFunction` — *source:* S1 author
- Design r1: each tool is a typed `@staticmethod` on a `<Category>ToolFunctions` class wrapped by existing `FunctionTool`; 277 tools / 31 categories (6–12 each); 40 new files; 0 deps; returns dicts; errors via `ToolExecutionError` — *source:* S1 author
- Test seam: call like a model — `await tool.execute(ToolCall(name, args))` then `json.loads(result.output)`; failure kind in `result.metadata["error_type"]` ("validation" / "ToolExecutionError"); no `tests/conftest.py`; test file basenames must be unique across `tests/` — *source:* S1 author
- Seeded RNG sequences, `ipaddress` flags, and `unicodedata` can differ between Python 3.11 and 3.12 (CI runs both): tests must not pin them — *source:* S1 author
- A007 checks every name in a function signature against tokens (`interval`, `token`, `char`, `byte`, `limit`, `depth`) when a numeric literal is in an annotation; C006/C008 flag `validate*`-style and `finite_float`-style helper names; pydantic warns on params named `schema_json`, `json`, `copy` (BaseModel attributes) — *source:* S1 author
- New files must be `git add`-ed before `python lint/run.py` and semgrep: they read tracked files only (S020 checks the README file index) — *source:* S1 author
- Integer outputs capped at 4,000 digits (INV-18); exact numbers travel as text (`IntText`, `DecText`) — *source:* S1 author
