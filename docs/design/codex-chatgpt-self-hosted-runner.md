# Codex on a ChatGPT login via a self-hosted runner

## What and why

`agents-md-placement.yml` authenticates Codex with an `OPENAI_API_KEY` secret, which
bills per-token API usage. The owner wants these runs to use their ChatGPT Plus Codex
subscription instead. The workflow has never succeeded, because the secret was never set.

Plus plans cannot mint Codex access tokens (Business/Enterprise only), so the only
documented route is OpenAI's "Maintain Codex account auth in CI/CD" pattern: a ChatGPT
`codex login` whose `auth.json` lives on a trusted runner, is refreshed in place by Codex,
and is used by one job at a time. `openai/codex-action` only accepts an API key, so the
workflow calls `codex exec` directly.

## How it works

- The job runs on `runs-on: [self-hosted, linux, codex]`. Each runner is registered to a
  single repository, so the `codex` label is shared across the Vidbyte repositories
  without two repositories ever sharing a runner.
- The runner's `.env` sets `CODEX_HOME` to a directory holding a ChatGPT `codex login`
  made for that runner alone. The job fails fast when `CODEX_HOME` is unset (the
  `~/.codex` fallback could be shared by other runners on the same host) or when
  `codex login status` does not report a ChatGPT login.
- A runner executes one job at a time, which satisfies OpenAI's rule that one `auth.json`
  never serves concurrent jobs. Codex refreshes the tokens itself (after about 8 days, or
  on a 401) and writes them back to the same file, so no secret has to be re-seeded.
- The job installs a pinned Codex CLI (`CODEX_VERSION`) into `$RUNNER_TEMP` and runs it
  with `--ephemeral`, so session transcripts containing PR content do not pile up in
  `CODEX_HOME`.
- `codex-action`'s `drop-sudo` protection does not exist outside the action, so the job
  refuses to run if the runner user has passwordless sudo.
- Codex settings are unchanged: `gpt-6-luna`, `high` effort, and the `:workspace`
  permission profile, passed as `default_permissions` exactly as the action did.
- The commit-and-push step is unchanged.

## Files

- `.github/workflows/agents-md-placement.yml`: self-hosted runner, sudo and login checks,
  direct `codex exec`.
- `.github/actionlint.yaml` (new): declares `codex` as a self-hosted runner label so the
  `Actionlint` workflow accepts it.

## Risks and open questions

- With no online runner, jobs queue and fail after 24 hours instead of running.
- Plus usage limits are shared with the owner's interactive Codex use; a run that hits
  them fails until the window resets.
- `gpt-6-luna` on a ChatGPT login was confirmed locally with the job's exact `codex exec`
  flags (Codex CLI 0.157).
- `cancel-in-progress` can stop a run mid-refresh. Recovery is a fresh `codex login` for
  that runner.

## Verification

- The workflow parses and `actionlint` passes with `codex` declared as a self-hosted label.
- After the runner is online: push to an open PR and confirm the job passes the login
  check and runs Codex.
