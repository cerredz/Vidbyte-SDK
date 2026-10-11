# Temporarily disable GitHub Actions

## What and why

Temporarily stop all GitHub Actions in this repo from running automatically.
Requested by the repo owner. No workflow files are deleted, so re-enabling
is a plain revert of the follow-up commit.

## How

Replace every automatic trigger (`pull_request`, `push`, `schedule`-like
tag pushes, path filters) in each workflow's `on:` block with
`on: workflow_dispatch:` plus a `TEMPORARILY DISABLED` comment naming the
revert path, with one exception: `ci.yml` keeps its `workflow_call`
trigger (a call trigger never runs automatically; it only preserves the
reusable-workflow contract `publish.yml` depends on). Manual dispatch
stays available for emergencies. No job, permission, concurrency, or step
is otherwise touched.

## Files

- `docs/design/temporarily-disable-github-actions.md` (this doc)
- `.github/workflows/ci.yml` — `on:` reduced to `workflow_dispatch` + `workflow_call`
- `.github/workflows/publish.yml` — `on:` reduced to `workflow_dispatch` (tag publishes paused)
- `.github/workflows/static-policy.yml` — `on:` reduced to `workflow_dispatch`
- `.github/workflows/actionlint.yml` — `on:` reduced to `workflow_dispatch`
- `.github/workflows/agents-md-placement.yml` — `on:` reduced to `workflow_dispatch`

## Risks and open questions

- While disabled there is no remote gate on PRs or `main`, and tag pushes
  no longer publish to PyPI.
- Branch protection that requires these checks will block merges until a
  bypass is used or the required-checks list is relaxed; re-enable by
  reverting the workflow commit.
- The disable PR itself runs no workflows by design, so there is no remote
  green to watch — verification is local (below).

## Verification

- Parse every edited workflow as YAML and assert `on` holds only
  `workflow_dispatch` (plus `workflow_call` in `ci.yml`).
- `python scripts/run_ci.py` passes locally (or the relevant stage).
- `gh pr checks` on the draft PR shows no failing required checks
  (no automatic runs expected).
