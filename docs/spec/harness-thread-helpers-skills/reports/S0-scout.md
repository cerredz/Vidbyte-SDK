# S0 scout report: harness-thread-helpers-skills

Stage: S0 (recon). Output: `context/code-map.md`. No commits, no installs, no gate runs, no lint runs and no pytest runs. Nothing outside the two output files was created or modified. The worktree status shows only the untracked `docs/spec/harness-thread-helpers-skills/`.

## 1. Planned file list (written before reading code, from the briefing's areas hint, then confirmed with `git ls-files` and `git grep`)

**Rules and docs:**
- `AGENTS.md`
- `CLAUDE.md`
- `REPO_MAP.md` (native and process entries)
- `vidbyte/harnesses/README.md`
- `vidbyte/lib/README.md`
- `lint/README.md`
- `lint/baseline.json`
- the relevant `lint/rules/*`
- `scripts/run_ci.py`
- `pyproject.toml` (pytest section)
- `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`

**Request and PR #1036 records:**
- `docs/spec/harness-thread-helpers-skills/request.md`
- PR #1036's `request.md`, `spec.md` and `review.md`

**Code to be edited or modeled on:**
- `vidbyte/harnesses/native/__init__.py`
- `vidbyte/harnesses/native/{grok,opencode,muse}/__init__.py`
- `vidbyte/harnesses/native/{grok,opencode}/{threads,wire}.py`
- `vidbyte/harnesses/native/muse/{threads,wire,launcher}.py`
- `vidbyte/harnesses/native/hostkit/{__init__,errors,launcher,skills}.py`

**Lib records, enums, constants and errors:**
- `vidbyte/lib/dataclasses/{native_threads,validation,process}.py`
- `vidbyte/lib/enums/{native_threads,__init__,failure,process}.py`
- `vidbyte/lib/constants/native_threads.py`
- `vidbyte/lib/errors/base.py`
- `vidbyte/lib/process/{argv,runner,__init__}.py`

**Neighbours:**
- `vidbyte/harnesses/__init__.py`
- `vidbyte/harnesses/serialization.py` (for `HarnessRedactor`)
- `vidbyte/__init__.py` (root exports)

**Tests:**
- all of `tests/features/harness_threads/`
- `tests/test_session_failures.py`
- `tests/test_codex_failure_recovery.py`

**Other harnesses (listing only):**
- `vidbyte/agents/` (codex, coding, skills, runtimes)
- `vidbyte/harnesses/` (non-native modules)
- `vidbyte/sessions/`

## 2. Files actually read

**Read in full:**
- AGENTS.md; CLAUDE.md
- request.md (this run)
- PR #1036 request.md and review.md
- lint/README.md
- vidbyte-gates.md
- Native package:
  - `native/__init__.py` and the three subpackage `__init__.py` files
  - `grok/threads.py`, `grok/wire.py`
  - `opencode/threads.py`, `opencode/wire.py`
  - `muse/threads.py`, `muse/wire.py`, `muse/launcher.py`
  - `hostkit/__init__.py`, `errors.py`, `launcher.py`, `skills.py`
- Lib:
  - `lib/dataclasses/native_threads.py`, `validation.py`, `process.py`
  - `lib/enums/native_threads.py`, `__init__.py`, `failure.py`, `process.py`
  - `lib/constants/native_threads.py`
  - `lib/errors/base.py`
  - `lib/process/argv.py`, `runner.py`, `__init__.py`
- Docs and config:
  - `vidbyte/harnesses/README.md`
  - `vidbyte/lib/README.md`
  - `scripts/run_ci.py`
  - `.semgrep/typed-mapping-boundary-policy.yml`
- Tests (`tests/features/harness_threads/`):
  - `FEATURE.md`, `README.md`, `conftest.py`, `fake_harness.py`
  - `test_harness_threads_surface.py`, `_errors`, `_static_policy`, `_acceptance`, `_threads`, `_credentials`, `_records`, `_arguments`, `_argv`, `_launcher`, `_skills`, `_wsl`

**Read in part:**
- PR #1036 spec.md: §1–§8.1 (lines 29–360), §13–§15 (844–970), and §17 with its deviations (1008–1046). §8.5–§12 and §16 were not read.
- `REPO_MAP.md`: the native and process entries (lines 159–161, 215).
- `test_harness_threads_process_bounds.py` and `_runner.py`: skimmed.
- Lint rules:
  - Read in full: A007, A009, S020, S061, S052, S008, S024, A006
  - Headers only: A001 (and its field list), S015, C016, C006, C012, S009
- `lint/baseline.json`
- `.github/workflows/ci.yml` (lines 1–30) and `static-policy.yml` (the semgrep lines)
- `pyproject.toml` (pytest lines)
- Module headers of `vidbyte/agents/codex/{agent,fork,transport}.py`, `vidbyte/harnesses/{client,stores/base}.py` and `vidbyte/agents/coding.py`

**Counted, not read:** `git show` of `failure.py` at the merge base, parsed with the surface test's own AST filter. That count is where the 148 comes from.

**CLI help probes:** run keyless with self-update off: grok, opencode, and Muse in `MuseUbuntu1`. No prompt, no key, no model call. Commands and output are in code-map §4.5.

**Not read, on purpose:**
- Anything else under `docs/`.
- The raw research captures in the scratchpad (`msp.schema.json`, `muse-skills.json`, `oc-export.json`, `oc-config.json`, `inspect*.json`).
- Field-guide `local-ci-verification.md` (outside the repo).

## 3. What the areas hint or vidbyte-gates.md got wrong

**Areas hint (orchestrator briefing):**
- **The Muse probe command fails as given.** `wsl.exe -e muse --help` uses the default distro `Ubuntu`, which is WSL2 and cannot start on this machine ("HCS_E_HYPERV_NOT_INSTALLED"). The working form is `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -e /usr/local/bin/muse …`.
- **"`vidbyte/harnesses/__init__.py`, `vidbyte/__init__.py` if any" as export points:** neither exports native. Only `vidbyte/harnesses/native/__init__.py` and the three subpackage `__init__` files do. INV-23 and a surface test forbid the others.
- **"any README under `vidbyte/harnesses/native/`":** there is none.
- **"Muse list/compact helpers would reuse it (`session/list`, `session/compact`)":**
  - `MuseMethod` has neither member.
  - The fake serve rejects any frame without `sessionId` and `excludeItems: true` with `-32602` before it dispatches on the method, so `session/list` would fail there.
  - Whether either method exists on Muse 1.0.1 is unverified.
- **"The new tests will extend this fake for `session list`, `export`, `sessions search/delete`":**
  - None of these exists in the fake today.
  - The fake Grok session layout (`sessions/<sha16>/<id>.json`) is not the real `summary.json` layout.
  - The fake is already 683 lines.
- **The briefing implies main = f216fdcf.** `origin/main` has moved to `72a4ade1` (#1027, `serialization.py` and `credential_keys.py`).
- **"28 FailureCode members":** correct for the native tail. But the surface test still asserts that main has 120 members, and at the merge base main has 148. So `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails locally whenever `origin/main` is reachable. It is a pre-existing failure, separate from this change, and CI skips it only because of the shallow clone.

**vidbyte-gates.md:**
- **"CI runs the same `run_ci.py`; semgrep is part of it":** `scripts/run_ci.py` contains no semgrep step. Semgrep runs only in `.github/workflows/static-policy.yml:30`. In addition, `ci.yml`'s automatic triggers are disabled, so CI must be dispatched (request.md:63).
- **"`python -m pip install -e ".[dev]"` once":** request.md:65 forbids this in the global Python while the concurrent PR #1055 pipeline runs. Use the venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills`, which exists.
- **The gates file omits the worktree `PYTHONPATH` step.** `lint/README.md` gives `$env:PYTHONPATH=(Get-Location).Path` before `python scripts/run_ci.py --stage source`. PR #1036 AC-18 and §13 use `PYTHONPATH=$(pwd)`.

## 4. Process notes

- The Muse store location (a code-map §4.1 question) is answered from code plus PR #1036 spec A-20. The probe of A-20 itself is S1's, not mine. The exact in-distro data path remains unverified.
- Two items need a live, keyed run that only the user may do:
  - the real Grok `summary.json` format
  - whether `grok -p "/goal …"` expands
