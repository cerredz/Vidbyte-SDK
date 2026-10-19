# S6 PR author: meta-muse-managed-text

- **STATUS:** DONE
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1180. It is still a draft on base `main`.
- **Title:** `feat(gateway): send Muse through the Vidbyte gateway, and match Meta's LLM_ keys only to Meta`
- **Commits:**
  - `ecfd7712` `docs(spec): finalize meta-muse-managed-text for PR` (spec.md and pr-body.md). After it was pushed, the PR's head was `ecfd7712`.
  - A second docs commit adds this report and a one-sentence fix to `pr-body.md`. The head SHA is re-checked after that push (see the end of this report).
- **Source and test changes:** none. `git diff --stat 75187327 HEAD -- . ':!docs'` is empty.

## 1. The code as shipped, read before the spec

I read `git diff 845a4d9b...75187327` before opening `spec.md`. My notes are in the scratchpad (`S6-code-first-notes.md`). Four product files change.

**1. `vidbyte/lib/constants/jev.py` (+5 -2).** `ModelProvider.META` joins `VIDBYTE_MANAGED_TEXT_PROVIDERS`, so the set grows from 6 to 7. It has two readers:
- `TextModelConfig._require_gateway_shape` (`model_configs.py:204`). A `meta` config in `AUTO` (the default) or `VIDBYTE_MANAGED` no longer raises M-12.
- The M-18 wording (`provider_keys.py:312`). It now offers "META_API_KEY or Vidbyte's own meta account".

Because `AUTO` is the default, every `meta` config, agent, fallback, fork or member that is not set to `DIRECT` now goes to the gateway. It either relays the Meta key or is Vidbyte-paid.

**2. `vidbyte/lib/registries/provider_keys.py` (+7 -3).** The Meta row (`:59`) changes:
- prefixes: `("LLM|",)` becomes `("LLM|", "LLM_")`;
- pattern: `LLM(?:\|[0-9]+\|[A-Za-z0-9_-]+|_[0-9]+_[A-Za-z0-9_-]+)`.

Two pieces of existing code do the rest. `accepts_unproven` reserves every literal prefix in a row to that row's provider, and META is format-bound. So a malformed `LLM_` key is taken by no provider and gets M-6. Two Meta keys in different shapes get M-7.

**3. `vidbyte/lib/registries/README.md` (+1 -1).** Table F's meta row gives both patterns. It cites Meta's 2026-10-17 sentence and the error-handling page, and it keeps the 2026-10-15 `LLM|` source (Q-7).

**4. `README.md` (+7 -7).** Three bullets change: Providers, Output cap, and Prefixes ("`LLM_` or `LLM|` (Meta)" at `:292`).

**The path a call takes.** The PR's mermaid chart is this path, and it is now also spec §5.
1. *Agent.* The agent matches its key list once, in `BaseAgent.__init__` (`base.py:191`), against its primary and every fallback provider. At run time, `ModalityDetector.create_runner` builds a `TextModelConfig` from that record.
2. *Config.* `TextModelConfig.__post_init__` runs `_require_gateway_shape` first (`model_configs.py:95-96`): the endpoint check raises M-13, a `ConfigurationError`, and then the provider check raises M-12. Only after that does it run the match (`:100`). A record passed in is only checked, not matched again.
3. *Runner.* `TextModelRunner.__init__` reads `credentials()` for the mode. It pins the cap (`max_output_tokens or 32_768`) and the timeout (at least 630 s) (`text.py:57-62`).
4. *Request.* `arun` builds one `VidbyteGatewayTransport` per call. `MetaProvider` builds the same body as in `DIRECT`, with `max_tokens` (`compatible.py:87`). The transport POSTs the envelope.
5. *Re-sends.* A 409, a 502, or an answer that is not a JSON object is re-sent at most twice, with the same Idempotency-Key.
6. *Errors.* Every other failure raises a `ProviderRequestError` worded from the status alone.

**What does not change:** `MetaProvider`, the gateway transport, the runner, `pricing.py` (`muse-spark-1.1` at 1.25, 4.25 and 0.15), and streaming, which refuses every gateway mode.

## 2. Evidence I produced (S6)

Every script is in the scratchpad: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`.

### 2.1 The §4 snippet, in both key shapes

- **Script.** `s6_run_snippet.py` reads the python block out of spec §4 at run time, so the snippet is never retyped. Fake keys are built by concatenation. Only the inner HTTP transport is faked.
- **Branch.** At `75187327`, with the output in `s6_snippet_branch.txt`, the run exits 0 and each shape reports `verdict: PASS`:
  - The snippet prints `['Hi', 'Hello']`, and 2 requests go to `https://vidbyte-backend.onrender.com/api/v1/models/generate`.
  - *Agent call:* headers `authorization`, `content-type`, `idempotency-key` and `x-vidbyte-provider-key`. The bearer is the Vidbyte key, the relay header holds the Meta key, and the envelope is `meta/muse-spark-1.1`.
  - *Both calls:* `max_tokens` 32768, no `max_completion_tokens`, timeout 630.0.
  - *Paid call:* three headers, and no relay header.
  - The Anthropic key is in no request, and the Meta key appears nowhere outside the relay header.
  - The run ends with `RESULT: section 4 snippet runs as written in both Meta key shapes`.
- **Merge base.** At `845a4d9b` (a `git archive` copy in `s6_base/`, output in `s6_snippet_base.txt`), 0 requests are sent in either shape:
  - `LLM_` shape: `ConfigurationError: api_keys[1] (53 characters) has no prefix that proves its provider, and none of the providers configured here (meta, anthropic) can take such a key. …`
  - `LLM|` shape: `AgentExecutionError: Agent 'muse' failed to generate a reply.`, caused by M-12. The Anthropic fallback never runs.

### 2.2 Messages, from `s6_messages.py` (branch, then merge base)

- **M-12, branch:** "The Vidbyte gateway serves only: anthropic, deepseek, gemini, kimi, meta, openai, xai. Use mode=TextModelMode.DIRECT to call openrouter with your own key." At the merge base the list has six providers.
- **M-18 for a `meta` primary, branch:** "… or pass no provider keys to use META_API_KEY or Vidbyte's own meta account." The merge base ends "… to use META_API_KEY."
- **Custom endpoint on `meta` in `AUTO`:** `ConfigurationError` (M-13), the same on both. This is why I corrected two labels in my first chart. It had read "UnsupportedProviderError M-12, or M-13 for an endpoint", but the endpoint check runs first and raises a `ConfigurationError`.

### 2.3 Meta's first-party pages

Re-fetched with curl on 2026-10-17 at 22:24 UTC, into `s6_meta_pages/`:
- **`authentication.md`.** sha256 `065bf421…40d008f4`, the same as the S5 re-review's fetch. Line `:13` reads "API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores". The pipe form appears 0 times.
- **`error-handling.md:509`.** "API key not in `LLM_{numeric_id}_{secret}` format".
- **`pricing-rate-limits.md`.** In the Muse Spark Standard table (whose models include `muse-spark-1.1`): cached input $0.15, input $1.25, output $4.25. That matches `pricing.py:284`.
- **`reasoning.md:390`.** The cap sentence.
- **`protocols/chat-completions.md:405`.** The alias sentence. Line `:425` adds "Requesting more than the model's configured maximum returns `HTTP 400`", which is the A-2 mechanism.
- **No output limit for `muse-spark-1.1`** appears on any of these pages, so A-2 still stands.

### 2.4 Gates I ran at `75187327`

- **25 AC proof nodes** (listed in `s6_nodes.txt`): `25 passed in 1.36s`. Seven other cited nodes: `7 passed in 0.96s`.
- **Feature area:** `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider` gives `192 passed in 2.24s`.
- **Lint:** `py -3.11 lint/run.py` exits 0. It prints `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` and `SDK-LINT: PASS`, with 0 regressed and 0 errored.
- **`run_ci.py`:** not run, as the brief says. The body quotes the S5 and orchestrator lines from `verify-log.md` and `reports/S5-repair-1.md`. Their source tree equals HEAD: `git diff --stat 8033c08c HEAD -- . ':!docs'` is empty.

### 2.5 Checks on the body (`s6_check_body.py`, `s6_mermaid_check.mjs`, GitHub's renderer)

- **Title.** It matches `feat(<scope>): …` and has no `WIP`.
- **Merge sentence.** Body line 1 equals the canonical sentence, and `spec.md` holds 7 identical copies.
- **Test names.** 64 names are cited: 14 test modules, 33 test functions and 17 test classes. Every one exists on the branch (`git grep`).
- **AC rows.** The AC table has exactly AC-1..AC-18, each once.
- **Tables.** There are 5 markdown tables with even column counts. Rendered through GitHub (`gh api markdown -F text=@… -f mode=gfm`), there are 5 `<table>`s with even cell counts. The regex cells (`\\|` in the source) render as `LLM\|[0-9]+…`.
- **Key literals.** A key literal is `LLM`, optional backslashes, `_` or `|`, then a digit. There are 0 in `pr-body.md`, 0 in the spec diff, 0 in the branch diff, and 0 in commit messages.
- **Mermaid.** There is exactly one block. Mermaid 11.4.1 parses it as `flowchart-v2`, and a broken control chart is rejected. `spec.md` now has 2 blocks, which parse as `flowchart-v2` and `sequence`. GitHub's `body_html` shows a mermaid container.
- **Closing line.** The last line is `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- **Checkboxes.** 2 are ticked: "Documentation and examples …" and "No credentials …", both verified. 9 are unticked: the 3 merge prerequisites, "Existing repository checks pass" (the known red test is named beside it), the wheel item (N/A), and the 4 live-check calls (a)-(d).
- **What GitHub stored.** `gh pr view --json body` equals `tail -n +3 pr-body.md`, byte for byte (42,202 characters, before this report's commit).

### 2.6 External state, checked with `gh`

- **#710** (cerredz/Vidbyte): open and a draft, head `36c5a628`. It is not deployed.
- **#1147:** open and a draft. It changes `tests/features/harness_threads/test_harness_threads_surface.py` (+65 -22). I don't claim it fixes the red test.
- **The #1027 bug is not on PyPI.** PyPI's latest `vidbyte-sdk` is 0.3.0. `git merge-base --is-ancestor 72a4ade1 v0.3.0` exits 1, and `72a4ade1` is in both origin/main and `845a4d9b`.
- **Hotfix PR:** no PR exists for `fix/meta-llm-key-shape`, and I did not open one.
- **Remote checks:** `gh pr checks` prints `no checks reported on the 'feat/meta-muse-managed-text' branch` and exits 1, because CI triggers are paused.

## 3. Deviations from the spec, as stated in the PR body

1. **S5 R-C1 (Minor, spec wording).** INV-16 (`spec.md:179`), AC-17 (iii) (`:209`), EC-8 (`:223`), EC-17 and §9.4 (`:398`) say M-6 "in every mode". A `TextModelConfig` built directly for openrouter, mistral, glm or minimax in a gateway mode gets M-12 first. This is because `model_configs.py:95-96` runs before the match at `:100`. It still fails closed and sends nothing. I changed only §5's prose to state this order. The Part B and C text is left for a later spec revision.
2. **The merge sentence is the body's first line,** above `## Motivation`, as the brief asks. AC-15's literal wording puts it first inside Motivation. The wording is identical.
3. **Spec §5 is documentation only.** Its flowchart is replaced with the PR chart, and its prose is aligned with the code. §17 has the row `r4 | 2026-10-17 | S6 PR | finalized for review …`.

## 4. Follow-ups listed in the body

There are 8:
1. Run A's Q-1, so Muse 1.2 and 1.3 are served.
2. A-2 and A-6, until the live check runs.
3. The standalone hotfix PR (the coordinator's call, with the squash-merge conflict note).
4. S5 R-C2: the `LLM_` half of the README Prefixes bullet is untested, at `test_managed_text_acceptance.py:256`.
5. S4 R-8: the README-section extraction block is copied 3 times.
6. Both packs' FEATURE.md "Historical Regressions: None yet" should record R-1 (`sdk_managed_text/FEATURE.md:73`, `sdk_provider_keys/FEATURE.md:96`).
7. Q-1..Q-7, each keeping its default: no, and Q-7 keeps `LLM|`.
8. The known red test, with PR #1147.

The pre-merge live check is listed under Verification as open, with calls (a)-(d) unticked.

## 5. Candidate field-guide lessons (for the coordinator; not written to the field guide)

PR link for all of them: https://github.com/cerredz/Vidbyte-SDK/pull/1180.

**L-1 (from R-1): check the vendor's live page for its key shape when you build, not from memory.**
- **Trigger:** a key-format rule, an allowlist row, a README bullet, or a test fake encodes a vendor's documented key shape. This applies to any first-party format the code depends on.
- **Preferred action:**
  - Re-fetch the vendor's live first-party page while building. Prefer its `.md` form. Grep for the exact sentence.
  - Record the URL, the date and the sha256 in the source comment and in the registries table F row.
  - Build one test fake in the documented shape, by concatenation.
  - Reserve the documented prefix, even for keys that do not fully match, so that an unexpected variant fails closed.
- **Reason:** vendors change shapes. #1027 read `LLM|<id>|<secret>` on Meta's page on 2026-10-15. On 2026-10-17 the page documented only `LLM_<id>_<secret>`. The stale rule refused the user's real key (M-6), or relayed it to Kimi or DeepSeek by elimination. Every test still passed, because each fake used the stale shape.
- **Quick check:** `curl -sS https://dev.meta.ai/docs/authentication.md | grep -n "start with"`, and confirm that the pipe form's count is 0. Then put a fake in the documented shape through `ProviderKeyMatcher.provider_of`.

**L-2 (from R-2): wrap added comments at 72 columns.**
- **Trigger:** adding `#` comment lines to any `.py` file, test packs included. `comment-format.md` applies to tests too.
- **Preferred action:** wrap added comments at 72 columns as you write them.
- **Reason:** S4 found 52 added test-comment lines wider than 72 columns. They had to be fixed afterwards (`4af4d8e0`).
- **Quick check:** `git diff -U0 origin/main...HEAD -- '*.py' | grep -E '^\+\s*#' | awk 'length($0) > 73'` prints nothing. The limit is 73 because of the leading `+`.

**L-3 (from R-6): name every table in the modification-pattern line.**
- **Trigger:** extending a feature-test pack's per-provider tables to a new provider.
- **Preferred action:** update each touched file's `COMMON MODIFICATION PATTERNS` docstring line so it names every table a new provider must join. Here those were `SERVED`, `PROVIDER_KEYS`, `POOL`/`PROVEN`, `MANAGED_PROVIDERS`, `ORACLE_KEYS`/`CAP_FIELD`/`EMITTED_KEYS`/`FULL_CONFIG` and `_CHAT_PROVIDERS`.
- **Reason:** the next provider onboarding reads those lines. A table the line leaves out is missed silently, and the pack still passes.
- **Quick check:** for every table name in your diff, grep the touched file's `COMMON MODIFICATION PATTERNS` line for it.

**L-4 (from R-7): keep test-module layout lint-clean.**
- **Trigger:** adding top-level constants or `def`s to a test module.
- **Preferred action:** put new constants with the existing constant block, not between classes. Leave two blank lines before top-level definitions.
- **Reason:** S4 flagged an E302 at `test_provider_keys_agents.py:494`, and constants placed mid-file in `test_provider_keys_failures.py`. The repo lint does not catch either.
- **Quick check:** `ruff check --select E301,E302,E303,E304,E305 <changed .py files>` prints `All checks passed!`.

**L-5 (S6, niche): escape a regex's own `\|` inside a GFM table cell.**
- **Trigger:** a GFM table cell has to show a regex that contains its own `\|`.
- **Preferred action:** write `\\|` for the regex's `\|`, and `\|` for an alternation `|`. Check the result with GitHub's renderer: `gh api markdown -F text=@file -f mode=gfm`.
- **Reason:** GitHub turns `\|` into `|` before it renders a code span, so the regex shows without its backslash.
- **Quick check:** the rendered HTML contains the regex exactly, and every table row has the same cell count.

## 6. Open items

- **Bugs in source:** none found.
- **Spec wording (not a code bug):** INV-16 (`spec.md:179`), AC-17 (iii) (`:209`), EC-8 (`:223`) and §9.4 (`:398`) still say M-6 "in every mode" (S5 R-C1). Only §5 was aligned. A later revision should qualify those lines.
- **Merge prerequisites:** all three are open. #710 is not deployed, ops has not provisioned the backend's `META_API_KEY`, and the live check has not run.
- **Hotfix PR:** not opened. That is the coordinator's call.
