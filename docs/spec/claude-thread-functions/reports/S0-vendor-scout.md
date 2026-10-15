# S0 vendor scout report: Claude Code CLI

Stage S0 (vendor scout), 2026-10-15. Output: `docs/spec/claude-thread-functions/context/vendor-facts.md` (10 sections). No commits. Nothing in the worktree was touched except these two files. No real key, OAuth login or network endpoint was used: only 127.0.0.1 stand-ins and the docs pages on code.claude.com.

## Probe scripts

All scripts are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/c726d777-284c-4c17-9776-72f9da8a13f9/scratchpad/claude-vendor-probe/` (`SCRATCH`):

| Script | Job |
| :- | :- |
| `SCRATCH/standin.py` | Messages API stand-in (`ok` or `401` mode). Logs to `SCRATCH/logs/<label>.log.jsonl` and saves bodies to `SCRATCH/logs/bodies/<label>-NNN.json`. Refuses `CONNECT` (the proxy trap). |
| `SCRATCH/run.py` | Starts `claude.exe` once with a controlled env. Safety aborts if a credential is not a known fake, the base URL is not 127.0.0.1, or the config dir is outside SCRATCH. Always drops `CLAUDE_CODE_MESSAGING_SOCKET`/`TOKEN`. Writes `SCRATCH/out/<name>.{stdout,stderr,meta.json}`. |
| `SCRATCH/probe.py` | Wraps run.py and prints new stand-in requests, hook markers, `apiKeyHelper` runs, and skill / CLAUDE.md hits in the body. |
| `SCRATCH/dumpbody.py` | Readable outline of one request body. |
| `SCRATCH/hook.py` | Hook command: writes `SCRATCH/markers/<label>-<event>-<ns>.json` with the key *class* and the env var names it saw. |
| `SCRATCH/make_workspaces.py` | Builds `wsE` (env + hooks), `wsEL` (the same as settings.local.json), `wsK` (apiKeyHelper → `SCRATCH/helper.cmd`), `wsW` (env API key). |
| `SCRATCH/make_ws2.py` | Builds `wsM` (`.mcp.json` stdio server → `SCRATCH/mcp_marker.py`) and `wsC` (workspace CLAUDE.md + skill). |
| `SCRATCH/make_skills.py` | Skill fixtures: `cfgS-template/skills/probe-skill`, `plugins/probe-plugin`, `plugins-nomanifest/bare-plugin`, `adddir/.claude/skills/adddir-skill`, `gitparent/.claude/skills/ancestor-skill`, `gitparent/repo/.claude/skills/repo-skill` (the repo was `git init`-ed inside SCRATCH). |
| `SCRATCH/docs/*.md` | Raw markdown of the docs pages (`curl https://code.claude.com/docs/en/<page>.md`), used for the quotes. |

Stand-in ports: A (ok) 62235, B401 (401) 49841, C (ok, the "attacker" target) 49842. All three were stopped at the end; `Stop-Process` was needed for the python processes after the bash wrappers stopped.

## Safety checks on the user's real config

| | Before (18:13–18:17) | After all probes |
| :- | :- | :- |
| `~/.claude.json` mtime | 2026-10-15 18:13:49.959 | 18:28:57.299 (changed between my first check and the real-home runs; unchanged by those runs, 18:28:57.299 before and after h1/h2) |
| `~/.claude/.credentials.json` mtime | 17:25:15.810 | 17:25:15.810 (unchanged) |
| `~/.claude/` dir mtime | 18:08:03.744 | 18:26:08.960 |
| `~/.claude/projects/` | 7 entries | 7 entries, none for a probe workspace |

The `~/.claude.json` and `~/.claude/` changes between 18:13 and 18:28 are **not** attributable to the probes. Every probe ran with `CLAUDE_CONFIG_DIR` set to a fresh SCRATCH folder, and every run before h1/h2 also had `USERPROFILE` pointed at a scratch home, so it could not resolve `~` to the real home. The user's other Claude Code sessions write those files continuously (this agent's own session uses `~/.claude-work`). The two real-home runs (h1, h2) left `~/.claude.json`, `.credentials.json`, `settings.json` and `projects/` unchanged, and their debug logs contain no path under `C:\Users\422mi\.claude`. No credential file was read; only names and mtimes were listed.

## Commands run, with final output lines

Discovery:
1. `env | grep -iE '^(CLAUDE|ANTHROPIC|DISABLE_|...)'` with values redacted. This agent's env has `CLAUDECODE=1`, `CLAUDE_CODE_CHILD_SESSION=1`, `CLAUDE_CODE_SESSION_ID=c726d777-...`, `CLAUDE_CODE_ENTRYPOINT=cli`, `CLAUDE_CONFIG_DIR=C:\Users\422mi\.claude-work`, `CLAUDE_EFFORT=xhigh`, `CLAUDE_CODE_MESSAGING_SOCKET/TOKEN`, `CLAUDE_CODE_EXECPATH`, `CLAUDE_PID`, `CLAUDE_CODE_SESSION_ATTENDED`, and a real `ANTHROPIC_API_KEY=<redacted>` (never passed to any child).
2. `command -v claude` → `/c/users/422mi/.local/bin/claude`. `type -a claude` → 4 identical lines. `cmd //c "where claude"` → `C:\Users\422mi\.local\bin\claude.exe`. `claude --version` → `2.1.301 (Claude Code)`, exit 0.
3. `ls ~/.local/bin | grep claude` → `claude.exe`, `claude.exe.old.1792002380282.12972`, `claude.exe.old.1792092856155.22168`. `ls ~/.local/share/claude/versions` → `2.1.299 2.1.300 2.1.301`. `cmp claude.exe versions/2.1.301` → identical. `npm root -g` → `...\npm\node_modules` (no `@anthropic-ai`). `ls C:/Program Files/ClaudeCode` → No such file.
4. `python -c "shutil.which('claude')"` → `'C:\\users\\422mi\\.local\\bin\\claude.EXE'`.
5. `claude --help` (scratch config, base URL 127.0.0.1:9) → 311 lines, exit 0, saved to `SCRATCH/out/help.txt`.

Docs (WebFetch, plus `curl -s -L https://code.claude.com/docs/en/<page>.md` into `SCRATCH/docs/`): authentication, settings, settings-reference, env-vars, headless, cli-reference, permissions, skills, hooks, claude-directory, memory, plugins.

Probe runs. Each is `python -X utf8 -I SCRATCH/probe.py --name <n> --port <p> --cfg <fresh> --cwd <ws> [--home <scratch>] [...] -- <claude args>`. The prompt was `-p "Say hi"` or `-p "hi"` with `--output-format json` unless noted. The last column gives the final output lines.

| Name | Variant | Exit | Final output |
| :- | :- | :- | :- |
| p01-nested | `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=cli` kept | 0 | `result: "stand-in answer A #3"`, session 037d2f08-...; stderr auto-mode billing notice |
| p02-base | baseline + `--debug-file` | 0 | session c3f73f50-...; debug log 183 lines |
| p03-resume | `--resume c3f73f50` | 0 | same session id, 5 messages sent |
| p04-fork | `--resume c3f73f50 --fork-session` | 0 | new id 467a3e59-..., 8 messages sent |
| p05-unknown | `--resume 11111111-...` | 1 | stdout empty; stderr `No conversation found with session ID: 11111111-2222-4333-8444-555555555555` |
| p06 | resume the original after the fork | 0 | same id; history has no fork turn |
| p07 | resume from another cwd (ws07), same cfg | 0 | same id |
| p08 | resume with another cfg (cfg08) | 1 | `No conversation found with session ID: c3f73f50-...` |
| p09 / p10 | `--session-id aaaaaaaa-...` new / again | 0 / 1 | id aaaaaaaa-... / `Error: Session ID aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee is already in use.` |
| p11 | `--resume --fork-session --session-id 99999999-...` | 0 | fork id 99999999-... |
| p12 / p13 | bad `--session-id` / bad `--resume` | 1 / 1 | `Error: Invalid session ID. Must be a valid UUID.` / `Error: --resume requires a valid session ID or session title when used with --print. ...` |
| p14-401 | B401, timeout 180 s | TIMEOUT | 10 requests, empty stdout and stderr |
| p15-401-default-retries | B401, timeout 590 s | 1 | after 184.55 s: `is_error: true, subtype: success, api_error_status: 401, result: "Invalid API key · Fix external API key"` |
| p16-401-noretry | `CLAUDE_CODE_MAX_RETRIES=0` | 1 | the same JSON after 0.67 s; transcript 564ebdfc-....jsonl written |
| e1-env-default | wsE | 0 | request at **C** with `x-api-key=probe`; 3 hooks ran with key=probe, `VIDBYTE_PROBE_ENV=1` |
| e2 / e4 | wsE `--setting-sources user` / `""` | 0 / 0 | request at A; no hooks |
| e3 / e5 / e9 | wsE `--bare` / `--settings disableAllHooks` / `--safe-mode` | 0 | request at **C**; no hooks |
| e6 / e7 | wsEL default / `--setting-sources user,project` | 0 / 0 | **C** + 3 hooks / A, no hooks |
| e8 | wsE `--restricted` | 0 | A, no hooks |
| e10 | wsE `--settings '{"env":{"ANTHROPIC_BASE_URL":"<A>"},"disableAllHooks":true}'` | 0 | A |
| k1 | wsK, caller key | 0 | `x-api-key=probe` + `authorization=bearer:helper`; helper ran once; 3 hooks |
| k2 | wsK, no caller key | 0 | `x-api-key=helper`, `bearer:helper` |
| k3 / k4 | wsK, no key, `--bare` / `--setting-sources user` | 1 / 1 | `result: "Not logged in · Please run /login"`; helper not run |
| w1 / w2 | wsW default / `--setting-sources user` | 0 / 0 | `x-api-key=wsenv` (key replaced) / `x-api-key=probe` |
| a1 | key + `CLAUDE_CODE_OAUTH_TOKEN` | 0 | `x-api-key=probe`, no authorization |
| a2 | OAuth env only | 0 | `bearer:oauthprobe` |
| a3 | key + `ANTHROPIC_AUTH_TOKEN` | 0 | `x-api-key=probe` + `bearer:authtok` |
| a4 / a5 | fake `<cfg>/.credentials.json` with key / without | 0 / 0 | `x-api-key=probe` / `bearer:oauthprobe` + `CONNECT api.anthropic.com:443` (refused) |
| a6 | OAuth env + `--bare` | 1 | `Not logged in · Please run /login` |
| s1–s12, s7b, s7c, j1 | skills matrix (see vendor-facts §5) | 0 | e.g. s8: `skill_hits={'probe-skill': 2} claude_md=[]`; s2: `n_tools=3 skill_hits={}`; s11: `repo-skill` yes, `ancestor-skill` no; j1: `junction-skill (ancestor-skill)`; s7c: skill body present via `/adddir-skill` prompt |
| m1 / m2 / m3 | wsM default / `--setting-sources user` / `--strict-mcp-config` | 0 | MCP marker ×2 with key=probe / none / none |
| c1 / c2 | wsC default / `--setting-sources user` | 0 | workspace CLAUDE.md + skill present / both absent |
| n1, n1b | `CLAUDE_CODE_CHILD_SESSION=1` + `CLAUDECODE=1`, then resume | 0 / 0 | transcript written; resume works |
| n2 / n3 | inherited `CLAUDE_CODE_SESSION_ID` / `CLAUDE_EFFORT=xhigh` | 0 | fresh id 0f3c5439-... / effort medium |
| n4 | this agent's full env (minus real key and messaging vars), `--env-mode inherit` | 0 | success, transcript written |
| q1 | stdin only | 0 | prompt `Say hi from stdin` |
| q2 / q3 | `"--help me"` / `-- "--help me"` | 1 / 0 | `error: unknown option '--help me'` / prompt `--help me` sent |
| q4 | arg + stdin | 0 | prompt sent as `ARG-PART\nSTDIN-PART` |
| q5 | empty prompt | 1 | `Error: Input must be provided either through stdin or as a prompt argument when using --print` |
| q6 | unicode, newline, quote, backslash arg | 0 | arrived intact (39 chars) |
| q7 | 40,000-char prompt via stdin | 0 | arrived whole (40,002 chars incl. newline) |
| q8 | open stdin pipe + arg | 0 | stderr `Warning: no stdin data received in 3s, proceeding without it. ...` |
| f1 | `--max-turns 1` | 0 | accepted |
| f2 / f2b / f2c / f2d | `--permission-mode default` / `manual` / `bypassPermissions` / `bogus` | 0/0/0/1 | `bogus` → `error: option '--permission-mode <mode>' argument 'bogus' is invalid. Allowed choices are acceptEdits, auto, bypassPermissions, manual, dontAsk, plan.` |
| f3 | `--effort xhigh` | 0 | `output_config: {'effort': 'xhigh'}` |
| f4 / f4b | `--model sonnet` / `claude-made-up-9` | 0 / 0 | `claude-sonnet-5-5` / sent anyway, stderr `[claude-code:unrecognized_model] ...` |
| f6 / f6b | `--append-system-prompt-file` / `--system-prompt` | 0 / 0 | accepted / third system block = `CUSTOM-SYSTEM-PROMPT` |
| f7 | `--max-budget-usd 0.00001` | 1 | `subtype: error_max_budget_usd, terminal_reason: budget_exhausted, errors: ["Reached maximum budget ($0.00001)"]` |
| f9 | `--output-format stream-json` without `--verbose` | 1 | `Error: When using --print, --output-format=stream-json requires --verbose` |
| g1 / g2 | `--no-session-persistence`, then resume | 0 / 1 | 0 transcripts / `No conversation found ...` |
| g3 / g4 / g5 / g6 | new, `--continue`, fork of unknown id, `--continue` in an empty cwd | 0/0/1/0 | `--continue` reuses 98a6d904-...; fork of unknown → `No conversation found`; empty cwd → new session |
| h1 / h2 | **real USERPROFILE**, `--setting-sources user` / default, `--debug-file` | 0 / 0 | `project=[]` skills in both; h2 still sends `C:\Users\422mi\.claude\CLAUDE.md` as project instructions; real config unchanged |
| par1–par4 | 4 parallel runs, the same cfg and cwd | 0 ×4 | 4 distinct sessions |

Final traffic summary across all stand-in logs: 76 (A) + 22 (B401) + 5 (C) = 103 `POST /v1/messages?beta=true` from `claude-cli/2.1.301 (external, sdk-cli)`. Plus 1 `CONNECT api.anthropic.com:443` (a5 only, refused) and 2 curl smoke requests from me. No other endpoint.

## Obstacles

- Python's console encoding (cp1252) broke printing of `✓`. Fixed by running probe scripts with `python -X utf8 -I`.
- Git Bash rewrote `/J` in `mklink /J` and a leading `/adddir-skill` prompt into Windows paths. Fixed with `MSYS_NO_PATHCONV=1`; this is a test-harness quirk only.
- `TaskStop` ended the bash wrappers but not the python stand-ins on Windows. Fixed with `Stop-Process` on the three PIDs (23760, 13832, 1508).
- No obstacle needed a new stand-in route: the CLI calls only `POST /v1/messages?beta=true`.
