LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — I attacked the await-free exactly-once event machine on every stop, timeout, stray-cancel and failure path, and it held each time. Three things around it break under real provider shapes and real load. The compaction size estimate reads only message["content"], so a Gemini member never compacts. A busy inbox can be recorded as delivered and still never reach the model. One transient provider error fails a member for the rest of the day.

Reviewed: git diff 39ce8b20...936e3278 (HEAD b6037e50 adds only review docs; `git diff 936e3278 b6037e50 -- vidbyte tests` is empty). Probes and the mutation plugin are in C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/6308f8f2-185f-45a5-b1b7-9102079fc8ee/scratchpad/s4eng/ (abbreviated below as s4eng/). No repo file other than this report was written.

The four leads from the previous draft:
- Lead 1 (auto compaction without hysteresis): confirmed as R-E4.
- Lead 2 (no model retry; AC-10 patches one in): confirmed as R-E3.
- Lead 3 (history_trimmed recorded for a refused call): confirmed, but the impact is small, so it is a Minor, R-E6.
- Lead 4 (uncapped inbox): confirmed as R-E2.
R-E1 and R-E5 are new.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Exactly-once accounting.** Each state change sits in one block with no `await` and is followed by one flush of the event outbox, run under the one-slot semaphore (events.py). Every message gets exactly one outcome and every agent exactly one terminal event on the stop, timeout, stray-cancel and failure paths. The cancel branch defers its record without flushing, and the final flush delivers it in sequence order. Mutations proved this: fail_keeps_inbox, stopped_recipient_queued, cancel_state_swap, wake_refused_not_recorded_at_turn_end, dropped_no_plus_one and trunc_at_cap were all killed by the pack. Do not restructure `_stop`, `_fail`, `_drain`, `end_turn` or `post_message`.
- **No paid call after the stop.** The observer refuses `before_model_call` once `stopping` is set (agent_swarm_observer.py:40-47), and `after_model_response` records the call and then aborts (the no_post_abort mutation was killed). The budget check uses `>=` against `total_tokens`, which includes all four Anthropic buckets (budget_gt, budget_ignores_total and measure_input_not_prompt were killed). The summary side call is counted once against the budget (side_call_not_budgeted was killed; `BaseAgent._invoke_runner`, base.py:1519-1533, only calls the runner and records nothing itself).
- **Cancellation hygiene.** bash re-raises CancelledError (vidbyte/tools/builtins/bash.py), the loop propagates it, and `task.cancelling()==0` separates a stray cancel from the swarm's own. A time limit that expires inside a long tool call does not hang.
- **Containment.** The shared loop is untouched: the NFR-1 diff is 0 lines. `_received` redacts provider keys from `model_error` text. The Tavily and Gemini keys live only inside their clients (Gemini sends its key in a header). All members share one stateless search tool. Every file is well under 1,000 lines (runtime.py has 410).

FINDINGS (ranked, most severe first, max 15)

R-E1 [Blocker] [compaction / provider shapes] vidbyte/agents/agent_swarm/member.py:121-132 (and the fallback at :119) — `_keep_last` sizes history by `str(message.get("content") or "")`, so Gemini tool calls and results (which carry `parts` and no `content`) and OpenAI tool-call arguments count as 0 tokens. The member keeps its whole history and nothing is ever summarized. This breaks both the automatic trigger (FR-8) and the `compact` tool (G-4) for every Gemini member, and for OpenAI members whose history is mostly writes.
  Evidence: member.py:129 `used += TokenEstimate.count(str(message.get("content") or ""))`. The formatter builds Gemini history turns as `{"role": "user", "parts": [{"functionResponse": ...}]}` and `{"role": "model", "parts": [{"functionCall": ...}]}` with no `content` key (vidbyte/lib/tools/formatter.py:478-490, :322-330). OpenAI tool calls are stored as `{"role", "content": None, "tool_calls"}`. The engine's own counter does count call arguments (vidbyte/middleware/compaction/strategies.py:66-73, `@intent call-turns-measure-their-call-arguments`); the swarm's estimate does not.
  - Probe `s4eng/probe_keep_last_gemini.py` (6 Gemini read_text calls with 60,000-char results; target 27,000):
    "gemini messages: 12 | _keep_last returns: 12"
    "swarm estimate of all messages: 0 tokens"
    "str(message) estimate of all messages: 90324 tokens"
    "openai write_text messages: 12 | _keep_last returns: 12"
  - Full-run probe `s4eng/probe_keep_last.py` (OpenAI; six 60,000-char write_text calls; reported input rising from 10,000 to 85,000):
    "compaction events: 0 | history_trimmed: [(24, 2)]"
    7 runner calls, so no summary call was ever made.
    The stored assistant tool-call message has keys ['content', 'role', 'tool_calls'] and a content length of 0.
  Failure: Take a Gemini member, or an OpenAI member that mostly calls write_text or patch_file, whose reported prompt reaches 72,000 tokens. `_keep_last` returns len(messages), so the engine's `while split and kept < keep_last` loop keeps every group (strategies.py:350-353). Nothing older is left to summarize, so no summary call is made and no `compaction` event is recorded.
  - The `compact` tool has already told the model "Compaction will apply before your next model call", and the tool description says "Compaction also happens automatically when your history grows long".
  - The live list grows without bound in memory. The 90,000-token trim drops the oldest groups on every call, so the agent loses old context with no handoff summary. That makes the trim the mechanism, which INV-36 forbids.
  - The pack cannot see any of this. `ScriptedSwarm._respond` (agent_swarm_fixtures.py:390-405) can only script OpenAI and Anthropic shapes, so no Gemini history is ever built.
  Smallest fix: estimate the whole provider message in `_keep_last` and in the `_measured_context` fallback. `TokenEstimate.count(str(message))` is one line in each place. Better still, reuse the engine's own per-message text so both sides count the same thing. Add one test that compacts a Gemini-shaped history (a `_respond` branch for `ModelProvider.GEMINI`) and one that compacts an OpenAI write_text-only history.
  Spec IDs: FR-8, G-4, INV-33 ("four-characters-per-token estimate fits ... the target"), INV-36, A-10 (Gemini is a supported member provider).

R-E2 [Major] [scale / back-pressure] vidbyte/agents/agent_swarm/runtime.py:338-344 — `_drain` joins every queued message into one user message. When their sum is over the 90,000-token trim, the trim drops that one group whole. Every message in it has already been recorded `message_delivered`, but the model never reads any of them, on this call or any later one.
  Evidence: runtime.py:340-344 takes the whole inbox, records MESSAGE_DELIVERED for each message, and renders them all into one AGENT_SWARM_INBOX text. member.py:109-111 appends that text as one user message. `_trim_groups_to_tokens` keeps the newest groups that fit and skips any group that is over budget on its own.
  - Probe `s4eng/trim_probe.py` (499 workers each send a 1,500-char report to a coordinator, 375 tokens each):
    "inbox chars 757495 est tokens 189373"
    "sent roles ['user', 'assistant', 'tool']"
    "inbox reaches the model: False"
    "history_trimmed recorded: [1]"
  - Full-run probe `s4eng/probe_inbox_block.py` (alice and bob each send 200,000 chars to receiver during its blocked search):
    events 20 message_delivered receiver alice, 21 message_delivered receiver bob, 22 history_trimmed receiver dropped=1, 23 model_called receiver
    "receiver's 2nd call carries alice's text: False | bob's text: False"
    stop_reason quiet
  Failure: Under G-5's 500 agents, workers report to a coordinator while it sits in a long tool call. Each report is tiny (1,500 chars), but together they exceed 90,000 tokens. The record says every report was delivered, the coordinator never sees any of them, and the senders believe the reports landed. The trim runs on every call and never persists (INV-36), so the oversize message stays in the live list and is dropped again on every later call. The swarm then ends `quiet`, with the work lost.
  Smallest fix: in `_drain`, take messages oldest first while the rendered block stays within a delivery budget, always at least one. AGENT_SWARM_COMPACTION_TARGET_TOKENS × 4 characters reuses an existing constant. Record `message_delivered` only for the messages taken, in the same block (INV-8 keeps holding), and leave the rest queued for the next iteration or turn end. `end_turn` already treats a non-empty inbox as mail. A single message that is itself over the trim stays a [scope-adding] follow-up, because NG-10 rules out a message length cap.
  Spec IDs: INV-7 and INV-8 (the outcome is exactly-once on paper only), FR-6, G-5, INV-36.

R-E3 [Major] [error handling / retries] vidbyte/agents/agent_swarm/member.py:223 — the member's middleware tuple (trim, turn, observer) has no model retry, and the SDK has none by default. One transient 429 or 503 therefore fails that member for the rest of a swarm that may run for a day. The spec assumes "the loop's own retries" exist, and the AC-10 test passes only because it installs a retry that production never has.
  Evidence:
  - The observer's `on_model_error` returns `continue_()` (agent_swarm_observer.py:60-68), and vidbyte/agents/runtime.py:821 re-raises.
  - `HttpTransport` `retry_count` defaults to 0 (vidbyte/lib/http/transport.py:55), and openai.py:37 and anthropic.py:31 pass none.
  - `AgentLoopSettings.max_retries` exists (vidbyte/agents/settings/loop.py:57) but the loop never reads it.
  - tests/features/agent_swarm/agent_swarm_fixtures.py:549-550: `class RetryModelErrorOnce(AgentMiddleware): """... the loop's own retry seam, which the member agent does not install (spec AC-10)."""`
  - Probe `s4eng/probe_retry.py` (the AC-10 script without `install_model_retry`):
    event 6 model_error builder 'ProviderRequestError: openai returned 429...'
    event 7 agent_failed builder
    builder made 1 of its 2 scripted calls
    stop_reason quiet
  Failure: 500 members share one API key, and any one of them takes a single 429. That member fails, its inbox is marked `message_undelivered`, its peers' messages to it are refused, and the swarm can still end `quiet` (see R-E7). EC-25's expected outcome, "repeated model_error during an outage until the loop's own retries fail the member", describes a mechanism that does not exist.
  Smallest fix: either (a) add a bounded retry for transient `ProviderRequestError` (429, 5xx) to the member's tuple, or (b) correct EC-25, AC-10 and the package README to say that a member's first provider error fails it, and rewrite AC-10's Given.
  - Do not drop in `ModelRetryMiddleware` or `ExponentialBackoffRetryMiddleware` as they stand. Their attempt counter is per run (retry.py:24-26, 49; exponential_backoff_retry.py:75-88) and never resets on success. A member runs one loop for the whole swarm, so after max_attempts transient errors spread across a day, the next one aborts. Option (a) needs a counter that resets after each successful call.
  - The verifier may judge (a) to be [scope-adding]. If so, (b) is the in-scope repair.
  Spec IDs: AC-10, EC-25, INV-23 ("the loop's own retry decision stays untouched"), G-5.

R-E4 [Major] [cost / control loop] vidbyte/agents/agent_swarm/member.py:83-90 — automatic compaction has no hysteresis. When the part of the prompt compaction cannot touch, plus the summary and the kept tail, still reports at least 72,000 tokens, every tool iteration makes another paid summary call that re-summarizes the previous summary.
  Evidence: member.py:87 `elif trigger_at is not None and measured >= trigger_at: trigger = AUTO`. Nothing considers whether the last compaction moved the measurement. Compaction cannot touch the fixed part (system prompt 17,923 chars plus tool schemas of about 7,400 chars, roughly 6,300 tokens) or the goal (never in `messages`, per INV-4).
  - Probe `s4eng/probe_hysteresis.py` (reported input 80,000 on every loop call; one 20,000-char self-note per iteration):
    14 loop calls, 7 summary side calls
    7 compaction events at sequences 34, 40, 46, 52, 58, 64 and 70, one every iteration from the 7th on
    messages_dropped of 3 to 4 each time
  Failure: Any of these inputs keeps the real prompt at or above the trigger after a compaction:
  - a goal over about 38,000 tokens;
  - a tail that the estimate undercounts (R-E1's tool-call arguments);
  - text where 4 characters per token is an underestimate, such as dense code or CJK.
  Each member then pays one extra summary call per tool iteration for the rest of the run. Across 500 members that roughly doubles model calls with no gain in context.
  Smallest fix: an AUTO compaction should also require that the history has grown since the last compaction by at least trigger − target. That means keeping the post-compaction estimate per member and comparing the current estimate against it plus 45,000. A TOOL request stays unconditional. This adds one sentence to INV-32.
  Spec IDs: FR-8, INV-32, D-12 (its sizing assumes a compacted prompt lands near the target, as the constants header says: "a compacted history sits far below the trim").

R-E5 [Major] [test quality] tests/features/agent_swarm/ — four plausible bugs each survive the whole pack (268 passed with each mutation), one of them the guard against a paid compaction call after the stop. test-plan.md:91's stated reason for not testing EC-27 is false.
  Evidence: mutation plugin `s4eng/mut/s4mut.py` rewrites one method in memory only. Run: `S4MUT=<id> PYTHONPATH="<worktree>;<s4eng>/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p s4mut`. The four survivors:
  - compact_while_stopping (member.py:91, drop `and not self.swarm_runtime.stopping`): the EC-7 test (test-plan.md:46) never has a due compaction when the stop arrives.
  - keep_last_zero (member.py:132, `return max(kept, 1)` → `return kept`).
  - self_writer_as_peer (runtime.py:261, `peer=previous` always): AC-13's writes alternate agents, so a same-agent rewrite is never tested.
  - side_call_tokens_not_added (member.py:151 removed): nothing asserts the member's `tokens_used` includes the side call.
  test-plan.md:91 says EC-27's "at least the newest group" is "the engine's rounding inside SummarizeRangeCompaction". That is false: with keep_last=0 the loop at strategies.py:350-353 keeps nothing. The guarantee is member.py:132's `max(kept, 1)`, and no test pins it. The fixtures also cannot script a Gemini response (agent_swarm_fixtures.py:390-405), which is why R-E1 is invisible to the pack.
  Failure: A refactor that drops any of these four lines ships green.
  - Dropping the stop guard makes a paid summary call after the budget stop: EC-7 with a member whose measured context is at least 72,000 when the budget is crossed.
  - Dropping `max(kept, 1)` means one tool result larger than the target makes the strategy keep zero groups.
  - The other two give wrong `file_changed` peers and an undercounted member `tokens_used`.
  Smallest fix: add four tests and correct test-plan.md:91.
  - EC-7 variant: the budget stop lands while the member's reported prompt is at least 72,000. Assert no `compaction` event and no extra runner call.
  - EC-27: one tool result larger than the target. Assert the newest group is kept verbatim and the summary covers the rest.
  - INV-26: the same agent writes one path twice. Assert the second write has peer "".
  - INV-35: the loop result's `tokens_used` after a compaction equals the loop usage plus the side-call usage (runtime.py passes `state.tokens_used` into every exit record).
  Also add a Gemini branch to `_respond` (see R-E1).
  Spec IDs: INV-32, INV-33, INV-26, INV-35, EC-7, EC-27, AC-13.

R-E6 [Minor] [observability exactness] vidbyte/middleware/builtins/agent_swarm_observer.py:88-99 vs :40-47 — the trim runs before the observer, so `history_trimmed` is recorded for a model call that the observer then refuses because the swarm is stopping. INV-24 counts one such event "per model call", and this call never happens.
  Evidence: the tuple order is Trim, Turn, Observer (member.py:223). The trim records whenever `transform.metadata.get("changed")`; the observer aborts only afterwards, on `stopping`.
  - Probe `s4eng/probe_trim_after_stop.py`:
    13 swarm_stopping max_tokens, 15 tool_called builder, 16 history_trimmed builder dropped=2, 17 agent_released builder
    "builder model calls reaching the runner: 2" (model_called events 6 and 11 only)
  Failure: A member whose history is over the trim finishes a tool call after the stop. The record shows a trim with no matching `model_called`, and a consumer that pairs trims with calls miscounts.
  Smallest fix: in `AgentSwarmTrimMiddleware.before_model_call`, return the parent decision without recording when `self.swarm_runtime.stopping` is set. A residual window remains if the stop is decided during the trim's own flush.
  Spec IDs: INV-24, NFR-4.

R-E7 [Minor] [scope-adding] [partial failure] vidbyte/agents/agent_swarm/runtime.py:375-386 — `_end_check` reports `quiet` when 499 of 500 agents failed and one finished. A partial failure reads as success at the result level, and only the `agent_failed` events in `result.events` show it.
  Evidence: `running = [name for name in self._names if name not in self._failed]`. FAILED is decided only when no agent is running (EC-14), and `AgentSwarmResult` (vidbyte/lib/dataclasses/agent_swarm.py:291-301) has no failure count. probe_retry.py ends `quiet` after `agent_failed builder`.
  Failure: Combined with R-E3, a 429 storm fails most members and the caller still sees `stop_reason=quiet`.
  Smallest fix: a follow-up for the user, not for the repair loop. Either document that callers must scan for `agent_failed`, or add a failed-agent summary to the result. The spec defines the stop reasons and has no such field (NG-10: no result-level fields beyond those listed).
  Spec IDs: EC-14, INV-12 (n/a as a violation).

VERIFIED CLAIMS:
- NFR-1, shared loop untouched: HELD. `git diff 39ce8b20 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py` has 0 lines.
- NFR-3 and INV-37, no sleep, polling or Lock: HELD. The only grep hit is runtime.py:8's header text "Do not poll or sleep".
- INV-7, INV-12 and INV-14, exactly one outcome per message and one terminal event per agent on the stop, timeout, stray-cancel and failure paths: HELD. 12 of 16 mutations were killed, and I read the cancel-branch deferred flush.
- INV-35, the summary side call is recorded once and counted against the budget: HELD. `_invoke_runner` (base.py:1519-1533) records nothing, and `_count_side_call`'s `usage_record is not None` guard (member.py:152) holds. The "added to tokens_used" part is untested (R-E5).
- Budget uses `total_tokens` with all four Anthropic buckets, and `>=` at the limit: HELD (budget_ignores_total and budget_gt were killed).
- S2 fix commit 1ddc6b9d tightens the oracle rather than loosening it: HELD. D1 excludes compaction from the base count, D2 adds an exact label, and D3 gates the side call.
- Secrets never reach events (`_received` redaction; the key lives only in its client) and the search tool is stateless: HELD.
- CancelledError propagates through bash and the loop, and a timeout during a tool call does not hang: HELD.
- My own hypothesis that the summarizer transcript drops OpenAI sent-message text: REFUTED. When `content` is None the engine renders the whole dict, and promise text was present for both OpenAI and Anthropic (s4eng/probe_summary_transcript.py). It is not a finding.
- INV-33's "four-characters-per-token estimate" applied to provider messages: REFUTED for Gemini parts and OpenAI tool-call arguments (R-E1).
- EC-25's "until the loop's own retries fail the member": REFUTED, because no retry exists (R-E3).
- AC-10's "the agent does not fail": HOLDS ONLY with the test-installed `RetryModelErrorOnce` (R-E3).
- test-plan.md:91's EC-27 rationale: REFUTED (strategies.py:350-353 keeps nothing at keep_last=0; R-E5).
- INV-24's "per model call": REFUTED for a call refused after the stop (R-E6).
- INV-32 and D-12, a compacted prompt drops below the trigger: REFUTED when the uncompactable part is large or underestimated (R-E4).

COMMANDS RUN:
- `PYTHONPATH=<worktree> python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` → "268 passed in 6.97s" (an earlier run gave 6.96s)
- `git diff 39ce8b20 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py | wc -l` → 0
- `grep -rn "sleep\|Lock(" vidbyte/agents/agent_swarm vidbyte/middleware/builtins/agent_swarm*` → only runtime.py:8 (header text) and a .pyc match
- `git diff --stat 39ce8b20...936e3278` → "72 files changed, 6531 insertions(+), 1268 deletions(-)"; `git diff 936e3278 b6037e50 --stat -- vidbyte tests` → empty
- `python s4eng/probe_keep_last_gemini.py` → "gemini messages: 12 | _keep_last returns: 12 (target 27,000 tokens)" / "swarm estimate of all messages: 0 tokens" / "str(message) estimate of all messages: 90324 tokens" / "openai write_text messages: 12 | _keep_last returns: 12"
- `python s4eng/probe_keep_last.py` → "compaction events: 0 | history_trimmed: [(24, 2)]"; 7 builder runner calls; assistant tool-call keys ['content', 'role', 'tool_calls'], content len 0
- `python s4eng/trim_probe.py` → "inbox chars 757495 est tokens 189373" / "sent roles ['user', 'assistant', 'tool']" / "inbox reaches the model: False" / "history_trimmed recorded: [1]"
- `python s4eng/probe_inbox_block.py` → 20/21 message_delivered receiver (alice, bob), 22 history_trimmed dropped=1; "receiver's 2nd call carries alice's text: False | bob's text: False"; stop_reason quiet
- `python s4eng/probe_retry.py` → "6 model_error builder 'ProviderRequestError: openai returned 429...'", "7 agent_failed builder"; 1 of 2 scripted calls made; stop_reason quiet
- `python s4eng/probe_hysteresis.py` → 14 loop calls, 7 summary side calls, compaction events at 34, 40, 46, 52, 58, 64, 70
- `python s4eng/probe_trim_after_stop.py` → "13 swarm_stopping max_tokens", "15 tool_called builder", "16 history_trimmed builder dropped=2", "17 agent_released builder"; "builder model calls reaching the runner: 2"
- `python s4eng/probe_summary_transcript.py` → promise text present in the summarizer transcript for OpenAI and Anthropic (hypothesis refuted)
- 16 mutation runs `S4MUT=<id> ... -p s4mut`:
  - Survivors, each "268 passed": compact_while_stopping, keep_last_zero, self_writer_as_peer, side_call_tokens_not_added.
  - Killed (the pack fails): trunc_at_cap, cancel_state_swap, budget_gt, budget_ignores_total, dropped_no_plus_one, trim_records_unchanged, fail_keeps_inbox, no_post_abort, side_call_not_budgeted, stopped_recipient_queued, measure_input_not_prompt, wake_refused_not_recorded_at_turn_end.
