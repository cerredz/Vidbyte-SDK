# S5 repair, iteration 1 of 8: meta-muse-managed-text

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text`, branch `feat/meta-muse-managed-text`. Iteration start: `607c2e16`; the orchestrator's `cda14a71` was added mid-run. Draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1180, which stays a draft.

## Outcome

R-1, the Blocker, is fixed in production. A Muse user can now pass the key Meta issues today, `LLM_<numeric id>_<secret>`, in `api_keys`. The SDK matches it to `meta` and to no other provider, in every mode. A malformed `LLM_` key now fails closed with M-6 and is sent nowhere; before, it bound by elimination to Kimi, DeepSeek, Mistral, GLM or MiniMax and was relayed to that vendor. Every other confirmed finding is verified fixed, except R-8, which is a follow-up by design. Every gate is green except one test, and I showed that test fails the same way at base `845a4d9b`.

## Root cause, in one line

The META row of `ProviderKeyMatcher.KEY_FORMATS` proved and reserved only the `LLM|` form that #1027 read on 2026-10-15. Meta's authentication page documents only `LLM_` today, so the real key was unproven, unreserved, and open to any provider that takes unproven keys.

## Commits

| SHA | Message | Files |
|---|---|---|
| `9309eed04f8bcec7bad29d73715933f49d0ba550` (**P**) | `fix(provider-keys): prove and reserve Meta's documented LLM_ key shape [R-1]` | `vidbyte/lib/registries/provider_keys.py` (+7/-3), `vidbyte/lib/registries/README.md` (+1/-1) |
| `874890bd` | `fix(readme): name both Meta key prefixes in the Prefixes bullet [R-1]` | `README.md` (+2/-2) |
| docs commit | `docs(spec): verify-log iteration 1 for meta-muse-managed-text` | `review.md`, `verify-log.md` (new), this report |

P follows the orchestrator's hotfix-split rule. It is one self-contained commit holding exactly the two registries files: no root README, no tests, no `docs/spec`. The README bullet is its own `[R-1]` commit. I first committed it with the subject `docs(readme): …`, then amended it to `fix(readme): …` before any push, to match the brief's `fix(<scope>)` format. Nothing pushed was rewritten.

### What changed, exactly
- **`provider_keys.py`.** One code line changed: the META row becomes `(ModelProvider.META, ("LLM|", "LLM_"), re.compile(r"LLM(?:\|[0-9]+\|[A-Za-z0-9_-]+|_[0-9]+_[A-Za-z0-9_-]+)"))`. That is §8.5 byte for byte, with no flags, still last, and `LLM|` branch identical to the old pattern. The row's 2-line comment becomes a 6-line PEP 8 block at 70/71/69/72/69/63 columns, indent included. It quotes Meta's sentence with its backticks, then gives the URL, the read date 2026-10-17, and the kept `LLM|` form (#1027, 2026-10-15, spec Q-7). Nothing else changes: not the other five rows, their order, `FORMAT_BOUND_PROVIDERS`, `RESERVED_PREFIXES`, the `OPENAI_*` prefixes, any method or message, the imports, or the A001 header. The header's KNOWN EDGE CASES line ("an LLM| key whose app ID is not digits") is still true.
- **Registries README, table F `meta` row.**
  - The Pattern cell reads `` `LLM_[0-9]+_[A-Za-z0-9_-]+` or `LLM\\|[0-9]+\\|[A-Za-z0-9_-]+` ``, written as the gemini row writes two patterns.
  - The Source cell now opens with "Opened on 2026-10-17", the authentication URL, Meta's sentence verbatim, and the error-handling URL with its cause "API key not in `LLM_{numeric_id}_{secret}` format".
  - It keeps the whole 2026-10-15 text, then adds "On 2026-10-17 that page no longer shows the `LLM\|` form; the rule keeps it (meta-muse-managed-text spec Q-7)". No test checks that clause, so I checked it myself against the live page: `LLM|` appears 0 times in `authentication.md` and 0 times in `error-handling.md`.
  - The Muse Code sentence, the secret-characters sentence, and the gitleaks note are kept unchanged.
  - Table A's fail-closed claim at `:62` ("If that is ever wrong, a real key is refused, never sent to another vendor") is now true for `LLM_` keys; the probe below shows it. The file is 7,849 characters, under the A009 limit.
- **Root README.** The Prefixes bullet in `### Vidbyte-managed text calls` now reads "… `xai-` (xAI), `LLM_` or `LLM|` (Meta), and `AIza` or `AQ.` (Gemini)." Only its last two lines are re-wrapped, to 70 and 57 columns. **No test binds the `LLM_` half**; AC-13 asserts only "`LLM|` (Meta)". I checked it by eye and with `grep -nF '`LLM_` or `LLM|` (Meta)' README.md`, which finds `README.md:292`.

## First-party source (fetched in this iteration)

I fetched both pages with `curl` at 2026-10-17 13:17 UTC into a separate untrusted-data folder in the scratchpad:
- `https://dev.meta.ai/docs/authentication.md`: HTTP 200, 2,692 bytes, sha256 `065bf421ea2c15b04f3a6fc706ab1222e8b29e225392ceb57610af8e40d008f4`. Line 13 reads: "API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores:". The example on lines 16 and 38 has an `LLM_` tag, a 16-digit ID, `_`, and an elided secret. It is not copied anywhere.
- `https://dev.meta.ai/docs/error-handling.md`: HTTP 200, 30,145 bytes, sha256 `5a827b565c249193ab3c72c13f0a7a2891e7dc33c993c46eb422692d09802d6a`. `:70` reads "Malformed API key (not in `LLM_{id}_{secret}` format)". `:509` reads "**Cause:** API key not in `LLM_{numeric_id}_{secret}` format." `:511` reads "The key should start with `LLM_`."

## Verification beyond the tests

**Probe** `<scratchpad>/s5r1_probe.py` (not committed). It builds every fake key by concatenation and prints no key. Results on the real row:
- Both shapes prove `meta`, and no provider takes either one unproven.
- The malformed `LLM_` keys (word ID, dot in the secret, no secret, bare `LLM_`, missing ID) are unproven and taken by no provider.
- The near misses lowercase `llm_`, `LLM-` and `LLMx` stay open to 8 providers (INV-17: nothing outside the `LLM_` prefix changed).
- The S4 misroute case: an anthropic primary, a kimi other, and the list `[K_ANTHROPIC, <Meta key>]`, with and without meta configured. In both shapes the kimi call gets no Meta key, and meta gets it.
- A lone Meta key for a deepseek primary is refused, and the error text holds no key.
- **Backtracking.** 1,000 `fullmatch` calls on 512-character adversarial inputs take 0.9, 2.1 and 1.5 ms in total. The ID class is digits only and cannot match `_` or `|`, so the split between ID and secret is unambiguous and matching is linear. That matters on a path that decides where a paid credential goes.

**Mutation (R-3).** `S4E_MUTANT=meta_key_to_keyless PYTHONPATH="$(pwd);<scratchpad>/plugins" py -3.11 -m pytest <area> -p s4e_mutants --tb=no` gives `1 failed, 191 passed`. The failure is `MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own`. In S4 the same mutant survived with `183 passed`.

**Hotfix cherry-pick of P (orchestrator request).**
```
$ git worktree add --detach <scratchpad>/s5-pick origin/main
HEAD is now at 6f5a7310 feat(harnesses): add CodexHost with agent tools, thread helpers and skill functions (#1055)
$ git cherry-pick --no-commit 9309eed04f8bcec7bad29d73715933f49d0ba550
cherry-pick exit=0
M  vidbyte/lib/registries/README.md
M  vidbyte/lib/registries/provider_keys.py
 2 files changed, 8 insertions(+), 4 deletions(-)
$ git worktree remove --force <scratchpad>/s5-pick && git worktree prune
```
After removal, `git worktree list` shows no `s5-pick` and the directory is gone. No tests were run there, as asked. Also, `git diff --stat 845a4d9b origin/main` over the two registries files and the root `README.md` is empty, so main has not touched any of them.

## Findings

| ID | Status set in `review.md` | How it was verified in this iteration |
|---|---|---|
| R-1 | fixed @9309eed0 (P) and @874890bd | area went from `15 failed, 177 passed` to `192 passed`; probe; source text checked against the live page |
| R-2 | fixed @4af4d8e0 | `git diff -U0 origin/main...HEAD -- '*.py' \| grep -E '^\+\s*#' \| awk 'length($0) > 73'` prints nothing: 0 of 216 added `#` lines, R-1's six included |
| R-3 | fixed @23c4e9c4 | the mutant is killed (above) |
| R-4, R-5, R-9, R-10, R-11 | fixed @04729669 (spec r4) | spec spot-checks: R-5's four remaining `jev.py:84` hits are §16/§17 history rows; EC-16 and §9.4 name team workers; §12.5 has calls (c) and (d); §9.2 records Run A's text |
| R-6 | fixed @4af4d8e0 | each of the six CMP lines names its table; `mt/FEATURE.md` no longer mentions `ORACLE_KEYS` |
| R-7 | fixed @4af4d8e0 | ruff E301-E305 over the 16 changed `.py` files says `All checks passed!`; the `META_*` constants are at `:63` and `:67`, after `RELAY_FORBIDDEN` |
| R-8 | open (follow-up) | not built, by design |

## Gate matrix (all run in this worktree, in this iteration, one at a time)

**Area** (`PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider`):
```
........................................................................ [ 75%]
................................................                         [100%]
192 passed in 2.09s
```

**Lint** (`py -3.11 lint/run.py`, exit 0; 0 REGRESSED and 0 ERRORED by grep):
```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
The IMPROVED verdicts were there before this PR and are not ratcheted, because this PR makes none of those improvements.

**Full source stage** (`PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`):
```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 6269 passed, 16 skipped in 118.49s (0:01:58) ============
CI failed: Command failed with exit code 1: C:\Users\422mi\AppData\Local\Programs\Python\Python311\python.exe -m pytest (cwd=C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-meta-muse-managed-text).
```
6269 is S3's 6260 plus the 9 new r4 test methods. The log has exactly one `FAILED` line.

**Package stage** (`py -3.11 scripts/run_ci.py --stage package`, PYTHONPATH unset, exit 0):
```
No broken requirements found.
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

**Proof run** (`py -3.11 scripts/run_ci.py`, PYTHONPATH unset). The import check printed `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py`.
```
E       AssertionError: assert 148 == 120
tests\features\harness_threads\test_harness_threads_surface.py:193: AssertionError
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 6269 passed, 16 skipped in 123.56s (0:02:03) ============
CI failed: Command failed with exit code 1: C:\Users\422mi\AppData\Local\Programs\Python\Python311\python.exe -m pytest (cwd=C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-meta-muse-managed-text).
```

**The red test is inherited, shown in this iteration.** I ran it in a detached worktree at `845a4d9b` and removed the worktree afterwards:
```
>       assert len(main_members) == 120
E       AssertionError: assert 148 == 120
1 failed in 1.89s
```
**MCP stdio flake:** it did not fire. `tests\test_mcp_stdio_transport.py ......................` was all green in the source run.
**Semgrep:** remote only. It cannot run locally (mcp 2.x) and is not a `run_ci.py` step. I did not chase it.
**Remote checks** (after pushing `874890bd`): `gh pr checks 1180 --repo cerredz/Vidbyte-SDK` printed `no checks reported on the 'feat/meta-muse-managed-text' branch`. SDK CI triggers are paused, which is an accepted external condition.

## Scope and safety checks
- `git diff --stat origin/main...HEAD -- vidbyte` lists exactly `jev.py`, `registries/README.md` and `provider_keys.py`. Outside `docs/` and `tests/`, only the root `README.md` is added to those.
- `git diff 2ba4a678..HEAD -- vidbyte/lib/constants/jev.py lint/` is empty, so the `jev.py` widening and both lint JSON files are as S4 approved them.
- `git diff --stat 263fa4e9..HEAD -- tests` is empty: no test or pack doc was touched.
- `grep -cE 'LLM\\*[_|][0-9]'` gives 0 over the whole branch diff and 0 over every branch commit message.
- No install, no force-push, no stash. The main checkouts were not touched. Both scratch worktrees were removed and pruned.

## Niche facts for the next agent
- The README Prefixes bullet's `LLM_` half is bound by no test. A regression there goes unnoticed unless someone greps for "`LLM_` or `LLM|` (Meta)".
- The AC-18 comment test walks upward from the `(ModelProvider.META,` line while lines start with `#`. A blank line or a code line between the block and the row makes the test see no comment.
- `META_EXAMPLE_KEY = LLM\\*[_|][0-9]` also matches the README's escaped `LLM\\|` followed by a digit. Prose may say "`LLM_{numeric_id}`", which is fine, but never `LLM_` or `LLM|` followed by a digit.
- The harness_threads count depends on the merge base: `148 == 120` at `845a4d9b`, and `167 == 120` at origin/main `6f5a7310` (S3). If the branch is rebased, S6 must quote the new number.
- `git rev-parse origin/feat/meta-muse-managed-text` fails in this worktree because there is no local tracking ref. Use `git ls-remote origin refs/heads/feat/meta-muse-managed-text`.

## The larger move this opens

P is a self-contained fix for a bug that is on `main` today, inherited from #1027: a documented Meta key bound by elimination and was relayed to another vendor. That bug does not depend on Muse being served through the gateway. The orchestrator's hotfix branch can carry P to users before the gated #710 merge, and P applies cleanly on `6f5a7310`. The one thing nothing local can prove is D-9's secret class. Only §12.5 live call (c), a real `LLM_` key through `api_keys`, settles it. The hotfix PR should carry that same check as its merge condition.
