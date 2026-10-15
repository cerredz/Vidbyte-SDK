---
slug: harness-thread-functions
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-functions
branch: feat/native-grok-opencode-meta-hosts
base_commit: 1c0d264b (merge of origin/main 179d8adc into PR head c1fdaef9; pushed; MERGEABLE)
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1036
until: none
started: 2026-10-15
---

# Pipeline: reshape PR #1036 into harness thread functions and resolve the owner's review comments

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-15 | 2026-10-15 | reports/S0-scout.md, reports/S0-vendor-scout.md | merge of origin/main; code-map.md; vendor-facts.md |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-15 — Work on the existing PR branch `feat/native-grok-opencode-meta-hosts` in a new worktree, not a new `feat/<slug>` branch — the owner said "update the pr" (request.md §A Prompt 4).
- 2026-10-15 — Merge origin/main (179d8adc) into the branch at S0 through a dedicated merge agent before recon — GitHub reported the PR CONFLICTING (REPO_MAP.md, vidbyte/lib/README.md, vidbyte/lib/enums/__init__.py, vidbyte/lib/errors/base.py), and every later stage must ground on current main. Merge, never rebase (the branch is pushed; force-push forbidden).
- 2026-10-15 — Two S0 scouts instead of one: a code scout (code-map.md) and a vendor scout (vendor-facts.md) — the change spans about 67 SDK files and depends on vendor facts (how each CLI takes a key, skills, config, fork) that no repo file records.
- 2026-10-15 — The PR stays non-draft (the owner's current state); the pipeline does not toggle draft status. S3 retitles it `[WIP] …` and replaces the body with a placeholder because the old body documents an API that is being removed; S6 writes the final title and body.
- 2026-10-15 — "Resolve the comments that I left" = apply each comment's rule across the whole PR (comments 1 and 3 generalize: "for all of these", "for all providers"), then at S6 reply on each of the four threads with the fixing commit and resolve the thread.
- 2026-10-15 — The DeepSeek balance read, readiness checks, usage tracking, and code the thread shape does not use are candidates for removal (request.md §C KD-1..KD-9, Rejected alternatives); the spec author decides per item and lists every removal in the spec's non-goals or work breakdown so the owner can interrupt.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- SDK CI auto-triggers are disabled: after a push, dispatch `gh workflow run ci.yml --ref feat/native-grok-opencode-meta-hosts` and `gh workflow run static-policy.yml --ref feat/native-grok-opencode-meta-hosts`; read results with `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs --jq '.check_runs[] | "\(.name)\t\(.conclusion)"'` (gh pr checks stays empty). Known 3.11 flake: tests/test_mcp_stdio_transport.py::…test_cancelled_waiter_does_not_break_transport — rerun failed jobs first. — *source:* memory vidbyte-sdk-ci-manual-dispatch
- The global `python` has vidbyte installed editable from the canonical checkout; from this worktree run the source stage as `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` and the package stage as `python scripts/run_ci.py --stage package` with PYTHONPATH unset. Check: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` prints the worktree. — *source:* field-guide local-ci-verification.md, memory vidbyte-sdk-local-gate-gotchas
- Semgrep (`semgrep==1.170.1`) must run from its own venv (the SDK pulls mcp 2.x, which breaks semgrep); it scans only git-tracked files, so `git add` new files first. — *source:* memory, field guide
- `git ls-files -u` must be empty before trusting lint during a merge. S051 import sorting: check with `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`. Local S009 (mypy) can differ on Windows. — *source:* field guide, memory
- Merging main later: conflicts on `contracts/sdk-public-api.json` `source.commit` → take ours, commit the merge, run `scripts/generate-sdk-public-api.py`, commit the regen separately. — *source:* memory vidbyte-sdk-local-gate-gotchas
- Briefing anti-stall rules: every subprocess gets a timeout and stdin=/dev/null; `GIT_TERMINAL_PROMPT=0`, `GIT_EDITOR=true`; at most 2–4 experiments; write the report skeleton first. — *source:* memory spec-pipeline-orchestration
- Stage files by explicit path; the SDK does not gitignore `.venv`. Never `git stash` (the stash stack is shared with other sessions). — *source:* memory pr-comment-resolver-skill-quirks, environment
- S0 merge: HEAD 1c0d264b; conflicts resolved as unions (REPO_MAP/lib README: outputs/ before process/; enums __init__: native_hosts then outputs imports; errors/base.py: `from typing import TYPE_CHECKING, Any` + TYPE_CHECKING block last). Native-host packs 1668 passed / 19 skipped; lint `SDK-LINT: PASS` (S063/S064 ratcheted 4 known). — *source:* S0 merge agent
- Grok 1.0.52: key only via env `XAI_API_KEY` (legacy `GROK_CODE_XAI_API_KEY`), no flag; a stored login in ~/.grok/auth.json beats the env key, so only a private `GROK_HOME` makes the caller's key win. Sessions live under `$GROK_HOME/sessions/<encoded-cwd>/<id>/` → continue/fork must reuse the same GROK_HOME and --cwd. Headless: `grok -p "<p>" --output-format json`; continue `--resume <id>`; fork `--resume <id> --fork-session [--session-id <uuid>]`; every form needs a prompt. JSON: {text, stopReason, sessionId, requestId, cwd, num_turns, usage, modelUsage, total_cost_usd, …}; error → {"type":"error","message":…} exit 1. Skills per run only via `grok agent --no-leader --plugin-dir D stdio` or ACP session/new `_meta.pluginDirs` (D/skills/<name>/SKILL.md); `grok -p` rejects --plugin-dir. `GROK_CONFIG` overlay cannot set auth or skills. — *source:* vendor-facts.md
- opencode 1.18.31: per-provider env keys (`ZHIPU_API_KEY` for zai/zai-coding-plan/zhipuai/zhipuai-coding-plan, `DEEPSEEK_API_KEY`), but a stored auth.json key beats env and a config `apiKey` beats both → pass `OPENCODE_CONFIG_CONTENT={"provider":{"<id>":{"options":{"apiKey":"{env:VAR}"}}}}` with the key in the child env. Skills per run: `OPENCODE_CONFIG_CONTENT` `{"skills":{"paths":[...]}}` (probe-verified). Headless `opencode run --format json [-s <id> [--fork]] -m <provider>/<model> --agent <a> --variant <v> --dir <D> "<p>"` prints JSONL `{type, timestamp, sessionID, …}` (step_start, step_finish, text, tool_use, reasoning, error); `run` rejects every permission ask unless `--auto`; reads piped stdin into the prompt → stdin=DEVNULL; continue/fork with no prompt exits 1. Undocumented: `OPENCODE_AUTH_CONTENT`, `OPENCODE_PERMISSION` (merged last), `OPENCODE_DB`. — *source:* vendor-facts.md
- Muse 1.0.1 (WSL distro MuseUbuntu1, bash launcher): `muse exec --api-key-stdin` (`--api-key` refused) or `META_API_KEY` (beats the account login). Skills: workspace `.agents/skills` + `--trust-workspace`, or a private `XDG_CONFIG_HOME/muse/skills`. Continue `muse exec --session-id <id> "<p>"`; NO headless fork (only MSP `session/fork` over `muse serve`). Set `MUSE_NO_AUTO_UPDATE=1` on every child. Sessions under `${XDG_DATA_HOME:-~/.local/share}/muse/sessions`. `exec --json` event schema UNVERIFIED (free offline check: `muse exec --provider echo --json`). — *source:* vendor-facts.md
- Code map (S0 scout): `vidbyte/harnesses/native/__init__.py` is pinned byte-for-byte by SHA-256 (INV-19 in tests/features/grok_host/test_grok_host_shared_contract.py), which also pins all 53 next-step texts (CATALOG), 89 constants by name and value, 13 enums' members, and that `import vidbyte` imports all four toolsets (AUDIT_PROBE). Every conftest's `check_native_error` rejects error-context keys outside a fixed 20-key set. Tool names are pinned to host method names (TOOL_TABLE). Every pack supplies keys with `monkeypatch.setenv` (contradicts KD-2). → the test author must rewrite or delete these pins; the implementer cannot. — *source:* S0 scout
- Code map: `NativeHostError` gives every code the same `likely_causes` sentence and its `related_docs` points into docs/spec/native-grok-opencode-meta-hosts/spec.md (`vidbyte/lib/errors/base.py:599,601`). The PR's `vidbyte/lib/constants/native_hosts.py:3` header states "A value only one module reads … stays beside that reader" — the policy comments 2 and 4 reject. AGENTS.md's constants rule is written for JEV only; the general rule comes from the field guide and lint A007. Main has no flag/protocol-string enum; nearest precedent `vidbyte/lib/enums/codex.py` (vendor wire values). `Skills.materialize(key, dest_dir)` is main's only code that writes skills into a harness folder. — *source:* S0 scout
- Code map: Semgrep is not in run_ci.py; it runs in `.github/workflows/static-policy.yml:24-30`. `HarnessBackends` static methods bound as module functions (backends/__init__.py) are the in-PR precedent for module-function APIs over a static helper class. `review-scope.md` says rebuild an overcomplicated PR on a fresh branch; the owner said update in place (settled), so the rebuild happens inside this branch. — *source:* S0 scout
- GLM Coding Plan allowlist names OpenCode, not Grok or Muse; Muse has no GLM/DeepSeek route (`--provider echo|meta` only). — *source:* vendor-facts.md
