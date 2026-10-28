# Design Doc: Remove Claude thinking blocks whose prefix changed mid-run

**Status:** Implemented on this branch.
**Author:** Claude
**Created:** 2026-10-28
**Last Updated:** 2026-10-28

---

## 1. Overview

On Claude Fable 5.1, Opus 5.5, Sonnet 5.5, and Haiku 5.5, a thinking block sent back to the API is valid only while its prefix is unchanged. The prefix is the top-level `system`, the `tools`, and the messages before the block. #1204 removed the one prefix edit every agent made, the live loop counters in `system`. Two agents still change the prefix mid-run on purpose:

- **InfiniteMemoryAgent** re-renders its workspace map, which lives in `system`, after each tool iteration. After a note is written, the next call changes `system`.
- **JevAgent SWARM** adds `launch_swarm` to `tools` once the compute checkpoint selects SWARM.

Each of these replays a block signed under the old prefix, and the API refuses the call with HTTP 400. This change adds one guard in the Anthropic request path. The guard records the prefix each thinking block was signed under. On each later request it removes the blocks the API would refuse, and it removes them the way Anthropic's troubleshooting guide prescribes. The guard covers every agent and every gateway mode, and needs no per-agent patch.

## 2. Evidence

Live, on gateway tests of SDK main `c40d1d5a` through the local Vidbyte gateway (VIDBYTE_MANAGED, Haiku 5.5). In both cases the 400 was billed $0.

| Case | Request | API message (tail) |
| --- | --- | --- |
| `gw/C2/infinite-memory/1` | `req_011CgU1LDkwCbowyutVsxhbd`, call 2 | `messages.1.content.0: Invalid signature in thinking block. The block is bound to a different conversation. ... The system prompt differs from the one this block was created with.` |
| `gw/B13/jev-swarm-long/1` | `req_011CgU1aZQX8bjZY3oo2pH7w`, call 5 | `... The tools list differs from the one this block was created with.` |

Offline repro on main: a scripted wire answers call 1 with `[thinking, tool_use write_note]`. Call 2's `system` differs only in the workspace map line for the new note, and `messages[1].content[0]` replays the call-1 block. The SWARM repro matches it: `tools` changes between call 3 and call 4 (`launch_swarm` appears), and every earlier block is replayed.

## 3. What the API allows (Anthropic docs, retrieved 2026-10-27)

- `preserved-thinking`, "Keeping the prefix unchanged": the checked prefix is `system`, `tools`, and every message before the block. `cache_control` markers and parameters outside those fields are not part of it. Earlier thinking blocks are not in the prefix, but each block records the block before it.
- "What counts as an edit":
  - Valid: "Remove thinking blocks from the start of the history, from the end, or all of them".
  - Invalid: changing `system`, adding a tool, or editing an earlier message.
  - Invalid for every later block: "Remove a thinking block from the middle of the history and keep later ones".
  - Invalid for blocks produced while it was gone: "Put back a thinking block you removed".
- `thinking-troubleshooting`, the signature 400: "strip every `thinking` and `redacted_thinking` block from the history (at minimum the named block and every one after it, in that turn and all later turns), leave each turn's other blocks in place". The named block is the first one that fails.
- "Libraries, proxies, and gateways": "If your code ... strips thinking ... log that it did".
- `thinking.md`: thinking blocks are required within a tool-use turn. Extended (manual) mode also requires that the final assistant turn start with a thinking block. Adaptive mode, the default on these models, does not.

## 4. Options

| | Option | Verdict |
| --- | --- | --- |
| A | **A general guard in `AnthropicProvider`**: record each block's signed prefix, and before each request remove the first stale block, every thinking block after it, and any block removed earlier. | **Chosen.** It follows the documented minimum removal. It covers DIRECT and the gateway, because the gateway forwards the adapter's body. It needs no beta header and keeps blocks that are still valid. |
| B | `drop_block` beta (`thinking-binding-controls-2026-08-01`). | No. The gateway transport discards adapter headers. The docs call it a stopgap. On Sonnet and Haiku 5.5 it works only with explicit adaptive thinking. |
| C | Mid-conversation `system` messages for the map, and `tool_addition` blocks with `defer_loading` for `launch_swarm`. | The documented long-term fix, so the model keeps its reasoning. But it needs betas, model gating, and gateway header passthrough, and it changes two agents and the runtime. Follow-up. |
| D | Per-agent patches (freeze the map, pre-declare `launch_swarm`). | No. Each future prefix edit would need its own patch, and freezing the map changes InfiniteMemoryAgent's behavior. |
| E | Catch the 400, strip, and retry. | No. The gateway withholds the provider's message, so the SDK cannot tell this 400 from another. It also costs a round trip on every edit. |

## 5. Design

`vidbyte/providers/anthropic_thinking.py`:

- `AnthropicThinkingPrefix.digests(payload)`: SHA-256 running digests. Entry `i` covers `system`, `tools`, and `messages[:i]`, canonical JSON with `cache_control` keys and thinking blocks left out, so the comparison matches the API's check.
- `AnthropicThinkingPrefix.block_key(block)`: a digest of a thinking block's `signature`, or of a redacted block's `data`.
- `AnthropicThinkingBindings.record(payload, answer)`: `run_text` calls it after every parsed answer. Each thinking block in the answer is recorded with the digest of the whole request.
- `AnthropicThinkingBindings.strip_stale(payload)`: `_create_payload` calls it last, after `extra_body`, so it sees the body as sent. It works in four steps:
  1. It locates every thinking block, oldest first.
  2. It finds the oldest block whose record differs from its prefix in this request, and removes it with every thinking block after it. Any block already marked removed is removed too.
  3. It builds new content lists, so the caller's history is never mutated and the turn's other blocks stay where they were.
  4. It marks the removed blocks so they never come back, and logs `anthropic_stale_thinking_removed blocks=N` at INFO.
- The state is process-wide (a fork, a resumed agent, or another runner can replay the same history), bounded to 16,384 records with LRU eviction, and guarded by a lock.

The kept blocks always form a valid chain:

- Blocks before the first stale one are intact.
- A block produced after a removal was signed without the removed blocks, so its predecessor is the last kept block.
- A removal always covers a suffix of the blocks that existed then, so a kept block never follows a removed block it was signed with.

A block before the first stale one that has no record (it came from another process, or its record was evicted) is left as it is, which is the behavior on main.

## 6. Invariants and tests

`tests/test_thinking_block_stale_prefix.py` checks the following. Five of these tests fail on main; the two no-over-removal tests pass on both.

1. **InfiniteMemoryAgent.** `write_note` redraws the map. No replayed block's `system`, `tools`, or earlier messages differ from its signing request. The block signed after the change still replays. The write turn keeps its `tool_use`.
2. **JevAgent SWARM.** `launch_swarm` is offered from call 4 on. No stale replay. Blocks signed after the change still replay.
3. **An unchanged prefix keeps every block.** A two-round tool loop replays blocks 0 and 1. This guards against over-removal.
4. **A removed block never returns,** even when `system` changes back.
5. **`cache_control` markers are not a change.**
6. **`redacted_thinking` is handled. Unknown blocks are left alone.**
7. **An edited earlier tool result removes only the later blocks.** A block signed while those were gone replays after the kept earlier block.

`tests/test_thinking_block_replay_prefix.py` (#1204) still passes.

## 7. Risks

- **Lost reasoning.** The model loses the reasoning in each removed block, and the docs warn this raises output tokens. That is the price of not getting a 400. InfiniteMemoryAgent pays it after each workspace change. Option C removes that cost.
- **Older accounts.** These accounts do not enforce the check, so before this change they kept stale blocks silently (`thinking_mismatch_allowed`). They now lose them too. Their requests stay valid.
- **Extended (manual) thinking.** A removal in the final assistant turn can still be refused, because that mode requires the turn to start with thinking. Main already fails these requests.
- **No billing effect.** The SDK sends fewer input tokens, Anthropic bills what it receives, and the SDK prices from `usage`. Removed blocks were never billed separately.

## 8. Follow-ups

- Option C for InfiniteMemoryAgent's map and JevAgent's `launch_swarm`.
- Gateway header passthrough, so callers can opt into `drop_block` and read `input_transformations`.
