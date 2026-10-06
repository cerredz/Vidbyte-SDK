---
name: asking-jev-dynamic-compute-questions
description: Write or review fixed Jev evidence questions for Vidbyte's dynamic-compute options. Use for FRESH_AGENT, FORK_AGENT, or SUBAGENT prompts in the Jev compute checkpoint.
---

# Asking Jev dynamic-compute questions

Use this skill for the fixed evidence questions in `vidbyte/lib/jev/compute/situations.py`. It applies specifically to `FRESH_AGENT`, `FORK_AGENT`, and `SUBAGENT`. It replaces the general Jev question-writing guidance for these questions; do not load the older `asking-jev-questions` skill for this feature.

## Research evidence

These sources inform question design, but none validates this feature's exact prompts or threshold:

- The *Lost in the Middle* study tested multi-document question answering and key-value retrieval. It reports that performance can fall when relevant information sits in the middle of a long input, with stronger performance near the beginning or end. This supports keeping questions tied to visible state fields and avoiding assumptions that long context is uniformly usable; it does not establish that a particular Jev question is reliable. [Paper and abstract](https://arxiv.org/abs/2307.03172)
- Anthropic's engineering guidance recommends starting with simple composable patterns, using parallel work when subtasks are independent or multiple perspectives are useful, and weighing the latency and cost of agentic systems. This is practical guidance drawn from their customer and engineering experience, not a universal performance guarantee. [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Anthropic's multi-agent research article describes benefits from parallel, independent investigations with separate contexts and also reports substantial token costs. Its reported 90.2% improvement is from Anthropic's internal research evaluation and should not be generalized to other tasks or systems. [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

## Question-writing rules

Treat the following as design heuristics for this classifier, not empirical claims from the sources above:

1. Keep each question about one observable signal in the run. Do not ask whether an agent, fork, or helper should be launched, whether extra compute would help, or what action Jev recommends.
2. Use only the shared state fields `request`, `brief`, `facts`, and `recent`. `request` preserves the user's goal and constraints; `brief` contains the code-owned original request and passages verified against numbered run events; `facts` contains exact run counts; `recent` contains a bounded tail of numbered events. Do not refer to hidden context, unprovided tools, or a new option-specific field.
3. Write exactly eight distinct introductory sentences before one direct positive evidence question. Explain which shared fields bear on the signal, how to compare the evidence, and what does not establish it. End the instructions with that question.
4. Make the positive answer mean that the named evidence is present. Keep the true and false descriptions short and plain. Allow false when the state lacks enough evidence to establish the signal.
5. Keep each option's evidence question separate from the common compute policy. Code requires all twelve answers for an option and scores their arithmetic mean P(true) against the one inclusive threshold. Do not add gates, per-question vetoes, eligibility conditions, priority-first logic, or option-specific thresholds.
6. Instantiate the existing `JevComputeQuestion` dataclass. Add a question key in `vidbyte/lib/enums/jev.py`, register the ordered option questions in `JevComputeRegistry`, and test the shared state and flattened request. Do not add question dataclass subclasses.

## Review checklist

- The question tests one named evidence signal, not a launch decision or performance forecast.
- The prompt uses only `request`, `brief`, `facts`, and `recent`.
- It has eight distinct introductory sentences and exactly one positive question at the end.
- True and false are short, observable, and leave unsupported evidence false.
- The question is one of exactly twelve for its option and is an existing `JevComputeQuestion` instance.
- Tests cover question count and shape, combined request order, incomplete answers, and option mean scoring.
