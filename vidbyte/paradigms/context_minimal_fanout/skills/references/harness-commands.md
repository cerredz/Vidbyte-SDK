# Harness Subagent Command Reference

Use this reference from the fanout skills when launching implementation branches.
Command names and flags drift across coding harnesses, so keep updates confined
to this file.

## General Fanout Pattern

1. Write one prompt file per subtask, for example
   `.fanout/prompts/<branch-id>.md`.
2. Launch one process, background task, or built-in subagent per prompt.
3. Record each branch id, command, process id or task id, output file, and owned
   paths.
4. Wait for every branch to finish before merging results.
5. Treat nonzero exits, missing reports, or ownership boundary violations as
   parent-level blockers.

POSIX shell example:

```bash
mkdir -p .fanout/logs
codex exec --sandbox workspace-write - < .fanout/prompts/api.md > .fanout/logs/api.out 2> .fanout/logs/api.err &
pid_api=$!
codex exec --sandbox workspace-write - < .fanout/prompts/docs.md > .fanout/logs/docs.out 2> .fanout/logs/docs.err &
pid_docs=$!
wait "$pid_api" "$pid_docs"
```

PowerShell example:

```powershell
New-Item -ItemType Directory -Force .fanout/logs | Out-Null
$api = Start-Process codex -ArgumentList @("exec", "--sandbox", "workspace-write", "-") -RedirectStandardInput .fanout/prompts/api.md -RedirectStandardOutput .fanout/logs/api.out -RedirectStandardError .fanout/logs/api.err -NoNewWindow -PassThru
$docs = Start-Process codex -ArgumentList @("exec", "--sandbox", "workspace-write", "-") -RedirectStandardInput .fanout/prompts/docs.md -RedirectStandardOutput .fanout/logs/docs.out -RedirectStandardError .fanout/logs/docs.err -NoNewWindow -PassThru
Wait-Process -Id $api.Id, $docs.Id
```

## Claude Code

Interactive Claude Code sessions should prefer the built-in Task/Agent subagent
tool when it is available, because it preserves the parent session's subagent
tracking. Give each subagent a complete branch prompt and wait for all
background tasks before merging.

For headless or scripted runs, Claude Code supports print mode:

```bash
claude -p "$(cat .fanout/prompts/api.md)"
cat .fanout/prompts/api.md | claude -p "Execute this branch prompt and report changed files, verification, and blockers."
```

Useful flags vary by installation. Check `claude --help` for permission flags
such as `--permission-mode` and tool allowlists such as `--allowedTools`.

## Codex CLI

Codex non-interactive mode uses `codex exec`:

```bash
codex exec --sandbox workspace-write "$(cat .fanout/prompts/api.md)"
cat .fanout/prompts/api.md | codex exec -
codex exec --json --sandbox workspace-write - < .fanout/prompts/api.md > .fanout/logs/api.jsonl
```

Use `--sandbox workspace-write` for branch implementation in a trusted
workspace. Use a stricter sandbox for read-only design or review branches.

## OpenCode

OpenCode documents programmatic CLI runs with `opencode run`:

```bash
opencode run "$(cat .fanout/prompts/api.md)"
opencode run "Execute .fanout/prompts/api.md and report changed files, verification, and blockers."
```

OpenCode agent selection and permission behavior can be configured in
`opencode.json`. Check `opencode run --help` and `opencode agent --help` for the
current flags on the installed version.

## Cursor CLI

Cursor's CLI documentation currently presents the agent command for terminal and
headless workflows:

```bash
agent chat "$(cat .fanout/prompts/api.md)"
```

Some installations expose the command as `cursor-agent` and support
non-interactive prompt flags. Verify locally before using:

```bash
cursor-agent --help
cursor-agent -p "$(cat .fanout/prompts/api.md)"
```

If both `agent` and `cursor-agent` exist, use the command documented by your
installed Cursor CLI version and record it in the parent split plan.

## Gemini CLI

Gemini CLI supports prompt mode with `-p` or `--prompt`:

```bash
gemini -p "$(cat .fanout/prompts/api.md)"
gemini --prompt "$(cat .fanout/prompts/api.md)"
```

For automation-heavy work, inspect the installed version's permission flags with
`gemini --help` before granting edit or command execution permissions.

## Discovering Other Platforms

For any other harness:

1. Run `<tool> --help` and look for non-interactive, print, prompt, run, exec,
   batch, or headless modes.
2. Search the official docs for "CLI", "headless", "scripting",
   "non-interactive", "automation", or "subagents".
3. Prefer a command that accepts a prompt file or stdin so branch prompts remain
   auditable.
4. Launch one isolated process or task per branch and capture stdout, stderr,
   exit status, and changed files.
5. If the platform has built-in subagents inside the current session, prefer
   those over raw shell fanout when they provide clearer task tracking.
