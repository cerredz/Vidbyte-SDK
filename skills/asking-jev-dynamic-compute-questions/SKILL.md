---
name: asking-jev-dynamic-compute-questions
description: Write or review fixed Jev evidence questions for Vidbyte's dynamic-compute options. Use for FRESH_AGENT, FORK_AGENT, or SUBAGENT prompts in the Jev compute checkpoint.
---

# Asking Jev dynamic-compute questions

Use this skill for the fixed evidence questions in `vidbyte/lib/jev/compute/situations.py`. It applies specifically to `FRESH_AGENT`, `FORK_AGENT`, and `SUBAGENT`. It replaces the general Jev question-writing guidance for these questions; do not load the older `asking-jev-questions` skill for this feature.

## Research evidence

These sources inform which option strengths to investigate; none validates this feature's exact prompts or threshold:

- The *Lost in the Middle* study tested multi-document question answering and key-value retrieval. It reports that performance can fall when relevant information sits in the middle of a long input, with stronger performance near the beginning or end. This motivates checking for lost evidence or continuity in long runs; it does not show that every long run needs a fresh agent. [Paper and abstract](https://arxiv.org/abs/2307.03172)
- Anthropic's engineering guidance recommends starting with simple composable patterns, using parallel work when subtasks are independent or multiple perspectives are useful, and weighing the latency and cost of agentic systems. This is practical guidance drawn from their customer and engineering experience, not a universal performance guarantee. [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Anthropic's multi-agent research article describes benefits from parallel, independent investigations with separate contexts and also reports substantial token costs. Its reported 90.2% improvement is from Anthropic's internal research evaluation and should not be generalized to other tasks or systems. [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

## Question-writing rules

Start with what each option is good at, then ask which separate, visible signals would show that advantage matters in the current run. `FRESH_AGENT` gets a clean context: look for worsening errors, stalled retries, goal drift, forgotten constraints or evidence, and whether verified notes preserve enough continuity to resume. `FORK_AGENT` compares alternatives: look for distinct plausible approaches, a shared starting point, independent and bounded trials, comparable outcomes, and isolated effects. `SUBAGENT` gives a helper a bounded independent unit: look for a clear deliverable and inputs, separate tool work, limited coordination, parallel progress, and a result the main agent can use. These are evidence families, not requirements that every signal must be present.

Treat the following as design heuristics for this classifier, not empirical claims from the sources above:

1. Keep each question about one distinct signal for one option. Its answer should contribute evidence to the option's average. Ask whether the signal is present, not whether an agent, fork, or helper should be launched or whether extra compute would help.
2. Use only the supplied run evidence. The shared state supplies the original request, verified brief, exact facts, and recent events, but the question text must not name, explain, or inventory those state fields. Do not refer to hidden context, unprovided tools, or an imagined future outcome.
3. Write each question's entire instructions as one string literal of 10–12 full, coherent sentences. Do not assemble a tuple of sentence fragments or join several strings. Use roughly 2–3 opening sentences to introduce the general problem, 2–3 to define what the signal looks like in practice, then transition into what to inspect. Ask the overarching question and use the final sentences to clarify its general boundaries. Every sentence must express a complete idea and lead naturally to the next. Avoid scenario-specific examples, clipped sentences, and run-on sentences.
4. Make the positive answer mean that the named evidence is present in the run. Keep the true and false descriptions short and plain. Allow false when the supplied evidence does not establish the signal. A long context or a plausible task shape alone does not prove the option is needed.
5. Keep each option's evidence question separate from the common compute policy. Code requires all twelve answers for an option and scores their arithmetic mean P(true) against the one inclusive threshold. Do not add gates, per-question vetoes, eligibility conditions, priority-first logic, or option-specific thresholds.
6. Instantiate the existing `JevComputeQuestion` dataclass. Add a question key in `vidbyte/lib/enums/jev.py`, register the ordered option questions in `JevComputeRegistry`, and test the shared state and flattened request. Do not add question dataclass subclasses.

## Review checklist

- The question tests one named evidence signal, not a launch decision or performance forecast.
- The instructions are one literal string of 10–12 connected, complete sentences with no state-field names.
- The prompt introduces a general failure mode or option strength, describes its observable form, and asks one positive evidence question without scenario-specific examples.
- True and false are short, observable, and leave unsupported evidence false.
- The question is one of exactly twelve for its option and is an existing `JevComputeQuestion` instance.
- Tests cover question count and shape, combined request order, incomplete answers, and option mean scoring.
