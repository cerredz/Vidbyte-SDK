# Design Doc: Keep the request prefix stable so Claude thinking blocks replay

**Status:** Needs a founder decision. No PR is open, and no fix has been chosen.
**Author:** Claude
**Created:** 2026-10-27
**Last Updated:** 2026-10-27

---

## 1. Overview

On Claude Fable 5.1, Opus 5.5, Sonnet 5.5, and Haiku 5.5, every multi-iteration agent run fails on its second model call with HTTP 400. This includes tool loops, sub-agent tools, and InfiniteMemoryAgent. The cause is that the runtime rewrites the top-level `system` prompt on every iteration: the "agent loop settings" block shows live counters (`max_iterations: 1/4`). Anthropic signs each thinking block to its prefix (system, tools, and earlier messages). A changed prefix invalidates every replayed block. Fixing this means choosing where, or whether, the model sees live loop budgets. That is a product decision, so this doc lays out the options and stops.

## 2. Goals & Non-Goals

### Goals
- `system` and `tools` stay byte-identical for the whole run, and `messages` are append-only, as the docs require.
- Keep the agent loop working on every provider, and let automatic prefix caching work across iterations.

### Non-Goals
- Using `drop_block` as the fix. It is the documented stopgap, not the documented fix.
- Changing InfiniteMemoryAgent files. They are under open PRs #1177 and #1191.

## 3. Background & Context

**Live evidence** (billing-readiness run, 2026-10-27): on Haiku 5.5, which thinks by default, `Agent(tools=[helper.as_tool()])` failed on its second call, and so did the CLI's InfiniteMemoryAgent through the gateway on its second turn. Sonnet 5.5 failed the sub-agent case too. The error was `messages.1.content.0: Invalid signature in thinking block. The block is bound to a different conversation.`

**Anthropic's rule** (`preserved-thinking.md`, "Keeping the prefix unchanged"): the checked prefix is the top-level `system`, the set of `tools`, and every message before the block. Changing any of them invalidates that block and all later ones. Accounts created on or after 2026-08-31 get a 400 by default. Older accounts let the block through silently, which is why a run on an older key can look fine. The listed fixes are: keep `system` and `tools` fixed, append only, and put changing context in the newest turn.

**Root cause, from captured request bodies.** I scripted `HttpTransport.request` and ran the live sub-agent case and a plain tool loop. Then, for each replayed block, I diffed the request that signed it against the request that replayed it:

```
parent request 1: block messages.1.content.0 produced by request #0
  system equal: False   tools equal: True   prior messages equal: True
  -- max_iterations: 0/4
  +- max_iterations: 1/4
```

`AgentRuntime._build_iteration_call_options` calls `_render_loop_settings_block(iteration_count, tokens_used, tool_call_count)` and puts the result in `system`, right after the fixed header. It does this on every iteration whenever `max_iterations`, `max_tokens`, or `max_tool_calls` is set. That covers most agents, and InfiniteMemoryAgent by default (`max_iterations=500`). With that block made static, every replayed block's prefix matched in the sub-agent, plain, and three-iteration runs. Tools are stable, messages are append-only, and helper thinking never leaks into the parent. The loop counter is the only prefix edit on these paths.

**Same cause, second cost.** Some providers cache by prefix automatically (OpenAI, DeepSeek, and Gemini's implicit caching). On those, the cache stops matching at this line on every iteration. Everything after the fixed header (the system prompt and tool list), including the agentic-loop prompt and the whole conversation, is billed at the uncached input rate on each loop iteration, so customers pay more for every multi-iteration run. The SDK sets no Anthropic `cache_control` marks today, so Anthropic is not affected this way.

## 4. Requirements

### Functional Requirements
1. For every replayed `thinking` or `redacted_thinking` block, the request's `system`, `tools`, and messages before the block equal those of the request that produced it.
2. Thinking blocks are still sent back with their tool results, unmodified, as the docs require.

### Non-Functional Requirements
- No new beta headers unless the chosen option needs them. One request body works on every model.

## 5. High-Level Design: options

| | Option | Change | Keeps live counters | Fixes 400 | Fixes cache | Risk |
|---|---|---|---|---|---|---|
| A | **Limits only in `system`.** Render `max_iterations: 4` (no usage), or say limits exist without numbers, as the field guide's prompt rule asks. | ~5 lines in `runtime.py` `_render_loop_settings_block`, plus 3 assertions in `scripts/test-agent-loop-settings.py` that pin live counters. | No | Yes, all providers | Yes | Reverses part of #148's deliberate design. The model stops seeing live usage, but enforcement stays in code. |
| B | **A + live usage in the newest turn.** Append a usage line to each new tool-result user turn and keep it in history (append-only). | Medium. Provider-specific tool-result formatting (`vidbyte/lib/tools/formatter.py`), transcripts, and traces. | Yes | Yes | Yes | It touches the tool-result path that other open fix branches edit. Extra tokens every iteration. |
| C | **Anthropic turn-scoped system messages** (`role: system`, `clear_at`, beta `mid-conversation-system-clear-at-2026-08-21`). | Anthropic adapter plus runtime. | Yes, Anthropic only | Anthropic only | No | Beta API, provider-specific. Other providers keep the cache loss. |
| D | **`drop_block` stopgap** (beta `thinking-binding-controls-2026-08-01`, `thinking.block_binding.prefix_mismatch_behavior: "drop_block"`). | Anthropic adapter. | n/a | Request succeeds | No | The system changes every iteration, so every earlier block is dropped every turn. The docs warn this "can significantly increase the output tokens", which customers pay for. On Sonnet and Haiku 5.5 it also requires an explicit `thinking: {"type": "adaptive"}`. |
| E | Strip thinking blocks before replay. | Anthropic adapter. | n/a | Risky | No | The docs say thinking must come back with its tool results. The model also loses its reasoning. |

## 6. Detailed Design

**Recommendation: A now, B later only if evals show live counters help.** A is the smallest change that removes the root cause for every provider, and it restores automatic prefix caching. It also matches the field guide's rule for prompts ("put no numeric limits in prose; say they are enforced"). The limits stay enforced in code by the runtime's budget checks, whatever the prompt says. B is the documented "changing context in the newest turn" pattern, if the founder wants the model to keep seeing live usage. Neither C nor D is recommended: both leave the cache loss on other providers in place and add beta surface.

## 7. Data Model Changes
N/A: no record changes in any option.

## 8. API Changes
N/A for A. B changes the persisted message history shape.

## 9. File Change Manifest (for option A)

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/runtime.py` | `_render_loop_settings_block` renders limits only |
| MODIFY | `scripts/test-agent-loop-settings.py` | 3 assertions pin live counters |
| CREATE | `tests/test_thinking_block_replay_prefix.py` | Regression test (on this branch) |

## 10. Testing Plan

`tests/test_thinking_block_replay_prefix.py` is committed on this branch and fails on main today. It is option-agnostic: it scripts a thinking Claude model that gives each reply a unique signature, finds the request that signed every replayed block, and checks the documented prefix rule.
- `test_plain_multi_iteration_run_replays_thinking_with_an_unchanged_prefix`: two tool rounds, three calls. [Hidden Failure] Fails on main: `system changed`.
- `test_sub_agent_tool_run_replays_thinking_with_an_unchanged_prefix`: the live `helper.as_tool()` case. [Hidden Failure] Fails on main: `request 2 messages.1.content.0 ... system changed`.
- `test_sub_agent_thinking_never_reaches_the_parent`: [Hidden Assumption] Passes. Helper blocks do not leak into the parent.

With the loop block made static (A, simulated by monkeypatch), all three pass. A live check on a key from an account created after 2026-08-31 is left for the founder.

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Anthropic Messages API | preserved thinking (prefix check) | Thinking replay | Enforced by default for new accounts |

## 12. Rollout & Deployment
Under A, the change is not breaking for APIs. Prompt text changes for every agent that has loop limits, so evals that snapshot system prompts need re-pinning. Ship it in the next SDK release, then bump the backend pin.

## 13. Open Questions
- [ ] Should the model keep seeing live loop usage (B), or are limits alone (A) enough?
- [ ] Later prefix editors that will hit thinking models next, and are out of scope here: `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries` (InfiniteMemoryAgent trims old tool results past 90k tokens, which invalidates every later block, in #1177's area); context-window `END_OF_CONVERSATION` placements, which are re-rendered on every call; and the history-rewriting context algorithms. The documented fix for those is server-side context editing or compaction.

## 14. Alternatives Considered
See §5. D and E are rejected as fixes. D stays available as an emergency hotfix only if A cannot ship quickly.
