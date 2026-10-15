---
slug: provider-onboarding-skill
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-15 18:41
flags: none (no --from, no --until; PR base main; the orchestrator must NOT merge the PR)
---

# Request: In-repo skill that onboards one new model provider per run, unattended

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (the only user prompt; it launched several spec-pipeline runs, one per checklist item. THIS run is item **#7**. Item #1 is a separate run and is out of scope here):

````
launch a subagent with teh "spec-pipeline" skill for each of the following: 1. [ ] Launch Muse through the Vidbyte gateway, both Vidbyte-paid and with the user's own key — the gateway refuses meta today, so Muse users skip Vidbyte's 2% fee entirely. Builds on: agents can now pick a Meta key out of a mixed key list. First step: scope adding Meta to the backend's provider list and the price table. Want users to be able to use muse models with their meta/muse api keys: 7. [ ] Spin up a provider-onboarding agent — it researches a new vendor's key format, endpoint and prices from first-party sources, then opens the PR that adds them. Builds on: this session's source-backed, mutation-tested method. First step: turn this session's method into a skill. (ask Claude). Can you run number 7 as a continuous, 24/7 run that creates a new pr per provider that it adds?
````

## B. Handoff block and decision ledger (verbatim, if present)

none (no `/talk` HANDOFF block or Re-entry ledger exists). The parent session's settled requirements are recorded in §C under "Key decisions" and "Constraints and assumptions".

## C. Structured conversation notes

### What this PR delivers (one paragraph)
An **in-repo skill that onboards one new model provider per run into the Vidbyte SDK, unattended**. Per run it researches the vendor's key format, endpoint, API dialect, model IDs and prices from first-party sources, wires the provider in the repo's own way, proves it, and opens one PR for that provider. THIS PR builds the skill (plus any small deterministic helper the spec proves necessary). **It does not onboard any provider itself.** After this PR, the parent session creates a 24/7 cloud routine (Anthropic cloud, hourly at most) that runs this skill on a fresh clone of the repo; **the skill is therefore the routine's whole contract**.

### Key decisions (settled by the parent session; do not reopen)
- **Location:** `.claude/skills/onboard-model-provider/SKILL.md`, supporting files beside it. — A cloud session only has the repo clone and cannot see `~/.claude/skills`; Claude Code discovers project skills at `.claude/skills/`; the routine will invoke exactly this path. Precedent: branch `cloud/spec-pipeline-trial-20261010` (commit `336fe4ec`) vendored skills into `.claude/skills/` for a cloud run.
- **One provider per run, one PR per provider**, on branch `feat/provider-<vendor-slug>`. The PR title follows the repo's convention. The PR body cites every first-party source with the date it was opened.
- **Idempotent selection.** Each run picks the next vendor that (a) is not already a `ModelProvider` member; (b) has no open PR on its `feat/provider-<slug>` branch; (c) was never closed-unmerged (treat closed-unmerged as the user's rejection and skip that vendor forever).
- **Seeded candidate list** lives in the skill, with selection criteria: suits the SDK's agent use; has an HTTP API with key auth; has first-party docs. The spec picks the seed list and order, with reasons. Candidates to consider (verify each): Groq, Cerebras, Together AI, Fireworks AI, Perplexity, Cohere, AI21, Alibaba Qwen (DashScope), DeepInfra, SambaNova, Nebius, Upstage, Writer, NVIDIA NIM.
- **Back-pressure.** If 3 or more provider-onboarding PRs are already open, the run makes no changes and exits with a one-line reason. — Merges need the user's `gh pr merge --admin`, so the review queue is the bottleneck.
- **Stop when done.** If no candidate qualifies, exit cleanly with a report. Never invent a vendor.
- **Fail closed on facts.**
  - A key-format rule (`ProviderKeyMatcher.KEY_FORMATS`, "table F") is added only with a first-party source: vendor docs, or the vendor's own GitHub org.
  - Refuse-only rules may rest on secondary sources (the gitleaks config, GitHub secret scanning).
  - With no documented prefix, the vendor goes to table A's "any" row.
  - Prices come only from the vendor's pricing page. Without one, the PR says so and follows the repo's rule for unpriced models (lint rules C009/C010 and the pricing code define it; the scout must find them).
  - Never invent a URL, price, or model ID.
- **Proof bar for each provider PR** (the parent session's method; the skill must encode it as a checklist):
  - The full gate `python scripts/run_ci.py` passes, with known-red tests excepted (see "Constraints").
  - Every new key rule is mutation-checked: revert it, show a test fails, restore it.
  - The property-test pool in `tests/features/sdk_provider_keys/test_provider_keys_property.py` gains the new fake key.
  - A DIRECT-mode wire test proves the key reaches the vendor's endpoint in its auth header (pattern: `test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct` in `tests/features/sdk_provider_keys/test_provider_keys_modes.py`).
  - The registries README "Provider Key Format Sources" table gains a row whose `|` characters are escaped for GFM.
  - Fake keys are built by concatenation (so secret scanners never see a literal key).
- **The per-provider run is ONE agent session following the skill**, not a full spec-pipeline run (the cost of a 24/7 cadence).
- **The routine opens PRs but never merges.**
- **The 24/7 routine itself is NOT part of this PR**; the parent creates it. The skill must state exactly what a routine invocation does, its inputs, and its exit conditions.

### The method being turned into a skill (what the parent session actually did; encode it)
On 2026-10-15 the parent session added Meta (Muse) to `ProviderKeyMatcher` and audited the other rules in SDK PR #1027 (merged as main `72a4ade1`, which is this run's base commit). It found and fixed a cross-vendor key leak in the process. The worked example on main:
- **Code:** `vidbyte/lib/registries/provider_keys.py` — table F (`KEY_FORMATS`), table A (`FORMAT_BOUND_PROVIDERS`, the OpenAI `sk-`/`eyJ` gate), `RESERVED_PREFIXES`.
- **Sources table:** `vidbyte/lib/registries/README.md`, section "Provider Key Format Sources", with a source date on each row.
- **Tests:** `tests/features/sdk_provider_keys/` (fixtures, matching, contract, property, modes).
- **Existing Meta wiring**, showing what "a provider" means across the SDK: `ModelProvider` in `vidbyte/lib/enums/model_provider.py`; `PROVIDER_API_KEY_ENV_VARS` in `vidbyte/lib/constants/jev.py`; default model and endpoint in `vidbyte/lib/registries/models.py`; adapter in `vidbyte/providers/compatible.py` and `vidbyte/providers/__init__.py`; `vidbyte/lib/constants/runners.py`; `vidbyte/lib/enums/model_modality.py`; `vidbyte/lib/agents/modality_detector.py`; the pricing package; lint rule `lint/rules/s014_provider_model_registry_parity.py`.
  - The S0 scout must build the COMPLETE touch-point list for adding a provider by tracing an existing compatible provider (e.g. kimi or mistral) through `git grep`. That list becomes the skill's checklist.
- **Research method:**
  - Fetch the vendor's own docs (authentication page, API reference, pricing page).
  - Corroborate the character set with the gitleaks config (https://raw.githubusercontent.com/gitleaks/gitleaks/master/config/gitleaks.toml) as a secondary source.
  - Check whether a new rule could misroute another vendor's key. The matcher binds unproven keys by elimination, so a too-strict table-A rule turns into a two-key swap. The swap regression test `test_an_openai_access_token_beside_a_deepseek_key_is_refused_not_swapped` shows the failure.
  - Check the adapter's auth header (Bearer vs `x-api-key` vs `x-goog-api-key`).
- **Verification method:** mutation-check each new rule; red tests first; full gate; confirm any failure is pre-existing by rerunning it on a detached origin/main worktree.

### Rejected alternatives
- A full spec-pipeline run per provider — rejected for the cost of a 24/7 cadence; one agent session following the skill instead.
- Keeping the skill under `~/.claude/skills` — rejected; a cloud session only has the repo clone.
- Letting the routine merge its own PRs — rejected; the user merges (`gh pr merge --admin`).
- Building the routine (schedule/cron) in this PR — rejected; the parent session creates it after this PR.
- Onboarding a provider inside this PR — rejected; this PR builds the skill only.

### Constraints and assumptions
- **Repo:** `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` (GitHub `cerredz/Vidbyte-SDK`, public). PR base `main`. This PR is a draft; the orchestrator does not merge it.
- **Environment of this pipeline run:** Windows 11 with Git Bash. Bash heredocs collapse `\\` to `\`: any script with backslashes must be written with the Write tool into a scratch file and run by path. Working copies use CRLF, so anchor text edits without trailing `\n`.
- **Environment of the future routine:** Linux (Anthropic cloud), a fresh clone of the repo, hourly at most. The skill must not depend on Windows (no PowerShell, no `C:` paths, no Windows-only tools).
- **Gate:** `python scripts/run_ci.py` (`--stage package` runs packaging alone). Two tests fail on PRISTINE main and are NOT this PR's fault:
  - `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails deterministically (148 != 120, a merge-base artifact of #1036).
  - `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` is timing-flaky.
  - The pipeline must not spend repair iterations on them. The skill should tell provider runs to check whether these are still red (on a detached origin/main) before excluding them.
- **CI on GitHub** never attaches to PRs (triggers are paused), so PRs show 0 checks and merges need `gh pr merge --admin` by the user. The local full gate is the real gate.
- **Lint ratchet:** watch lint rule S054. Ruff S105 flags any string constant whose name contains `TOKEN`/`SECRET`/`PASSWORD`; name constants accordingly instead of raising a baseline.
- AGENTS.md forbids reading `docs/` in ordinary work. `docs/spec/byok-api-keys/` may be read because the user named this work (it is the parent session's spec for PR #1027).
- Do not touch the main checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` (it has untracked files). Never use bare `git stash`.

### Clarifications and answers
- Q: Which checklist item is this run? — A: #7 only. Item #1 (Muse through the Vidbyte gateway) is a separate run; do not touch it.
- Q: Is the 24/7 behavior built here? — A: No. This PR builds the skill; the parent session schedules it as a cloud routine afterward. The skill is the routine's whole contract.

### Terminology
- **Provider / vendor** — a model API company the SDK can route to; in code, a member of `ModelProvider` (`vidbyte/lib/enums/model_provider.py`).
- **Vendor slug** — the lowercase, hyphenated vendor name used in the branch `feat/provider-<vendor-slug>`.
- **Table F** — `ProviderKeyMatcher.KEY_FORMATS` in `vidbyte/lib/registries/provider_keys.py`: positive key-format rules that bind a key to a vendor; first-party source required.
- **Table A** — `FORMAT_BOUND_PROVIDERS` in the same file (includes the OpenAI `sk-`/`eyJ` gate and an "any" row for vendors with no documented prefix).
- **Refuse-only rule** — a rule (e.g. `RESERVED_PREFIXES`) that only stops a key from going to the wrong vendor; may rest on secondary sources.
- **First-party source** — the vendor's own docs site or the vendor's own GitHub org. **Secondary source** — gitleaks config, GitHub secret-scanning patterns.
- **DIRECT mode** — the SDK calling the vendor's endpoint directly with the user's key (as opposed to relaying through the Vidbyte gateway).
- **Back-pressure** — the run refuses to add work when 3 or more provider-onboarding PRs are already open.
- **Routine** — the Anthropic-cloud scheduled agent (hourly at most) that the parent will create to invoke this skill on a fresh clone.
- **Mutation check** — revert a new rule, show a test fails, restore it.

### Implementation hints
- Skill path: `.claude/skills/onboard-model-provider/SKILL.md`; supporting files (references, seed list, checklists, any helper script) beside it.
- Existing `.claude/` on main contains `ci-settings.json`; check how `.claude/` interacts with lint, packaging (`python scripts/run_ci.py --stage package`), and any repo map / README obligations.
- Trace an existing OpenAI-compatible provider (kimi or mistral) through `git grep` to build the complete per-provider touch-point list; that list becomes the skill's checklist.
- The helper (if any) must be small, deterministic, and justified by the spec (e.g. selection/back-pressure logic computed from `gh` output and the `ModelProvider` enum).
- Parent-session worked example: PR #1027, main `72a4ade1`; spec under `docs/spec/byok-api-keys/` (readable by name).

### Open questions (the spec author resolves from the code or carries as Q-n)
- Which candidates make the seed list, in what order, and why (verify each against first-party docs: HTTP API, key auth, docs exist, agent-suitable).
- How "provider-onboarding PR" is recognized for back-pressure and for the closed-unmerged skip (branch prefix `feat/provider-`? label? title pattern?).
- Whether a deterministic helper script is needed (and where it lives, how it is tested), or whether the skill's prose plus `gh` commands suffice.
- The exact repo rule for unpriced models (lint C009/C010 and the pricing code).
- How a vendor whose API is NOT OpenAI-compatible is handled (skip with a reason, or a different adapter path).
- What the run reports on each exit path (no-op from back-pressure, no candidate left, a vendor that fails research, a gate failure).

## D. Weighted words

From the user's prompt (Prompt 1):
- "Can you run number 7 as a **continuous, 24/7** run that creates a new pr per provider that it adds?" — Prompt 1
- "...that creates **a new pr per provider** that it adds?" — Prompt 1
- "it researches a new vendor's key format, endpoint and prices from **first-party sources**, then opens the PR that adds them." — Prompt 1
- "Builds on: this session's **source-backed, mutation-tested** method." — Prompt 1
- "First step: turn this session's method into a skill." — Prompt 1

From the parent session's settled requirements (§C, binding):
- "**One** provider per run, **one** PR per provider" — settled requirement
- "was **never** closed-unmerged (treat that as the user's rejection and skip it **forever**)" — settled requirement
- "If 3 or more provider-onboarding PRs are already open, the run makes **no changes** and exits with a one-line reason." — settled requirement
- "**Never** invent a vendor." — settled requirement
- "A key-format rule ... is added **only** with a first-party source" — settled requirement
- "Prices come **only** from the vendor's pricing page." — settled requirement
- "**Never** invent a URL, price, or model ID." — settled requirement
- "**Every** new key rule is mutation-checked" — settled requirement
- "The PR body cites **every** first-party source with the date it was opened." — settled requirement
- "The skill is therefore the routine's **whole** contract." / "The skill must state **exactly** what a routine invocation does, its inputs, and its exit conditions." — settled requirement
- "The routine opens PRs but **never** merges." — settled requirement
- "the skill must **not** depend on Windows" — settled requirement
