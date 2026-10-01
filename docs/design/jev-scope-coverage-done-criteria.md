# Jev scope coverage continuation gate

## API

Enable the gate through `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.SCOPE_COVERAGE,)))`. It composes with `MULTI_PART` and `CLAIMS`; all enabled finish questions share one Jev request and one handoff per finish attempt.

## Run state

Before work starts, `JevRunState` records groups for which the request asks the same change to reach multiple members. It stores a short request quote, the requested change, a member noun and matching rule, breadth, universe, named members, exclusions, and any quote that explicitly allows partial work. Quoted fields and named members must appear in the original request after whitespace and case normalization.

The gate checks only `every_member` and `named_list` scopes without a partial-coverage allowance. Single targets and examples remain visible in state but do not block. A one-time request-only Jev review checks groups the state builder labeled `one_example` or `single_target`; it can widen those labels before the main agent starts.

## Finish review

At each finish attempt, `JevHandoff` reports the workspace enumeration and work evidence for every request-named member and every additional member the run enumerated. Code ignores unsupported mentions, derives unit sources, adds empty evidence records for named or enumerated members the handoff omitted, and removes explicit exclusions.

`JevRunState` puts one `noul` question in the shared finish request for each required member with reported work. Code marks members with no work evidence incomplete without asking Jev to infer an absent action. For a workspace-wide group, a missing enumeration is also an incomplete item. The evidence question checks whether the requested change was carried out for that member and remains in place.

## Continuation behavior

Any missing member, incomplete answer, or missing workspace enumeration sends the main agent back through the same loop with feedback naming the group and member. The normal `JevContinualSettings.max_continuations` limit applies. When the limit is reached, the current answer stands and the last result remains on `JevAgent.response`. Missing run state, handoff failure, or Jev failure follows the existing fail-open behavior.

The response exposes request-derived groups at `agent.response.run_state.scope_coverage`, finish evidence at `agent.response.handoff.scope_coverage`, and the check result at `agent.response.done[JevDoneCheck.SCOPE_COVERAGE]`.

## Limits

The gate judges only members named in the request or listed by the run. For open-ended groups, it does not attempt to discover an unknowable complete universe. A workspace enumeration is taken from the generated handoff, so the gate can check that a list exists and review each listed member but cannot prove that the list itself is exhaustive.
