---
name: asking-jev-dynamic-compute-questions
description: Write or review fixed Jev evidence questions for Vidbyte's dynamic-compute options. Use for FRESH_AGENT, FORK_AGENT, SUBAGENT, or CLONE prompts in the Jev compute checkpoint.
---

# Asking Jev dynamic-compute questions

Use this skill for the fixed evidence questions in `vidbyte/lib/jev/compute/situations.py`. It applies specifically to `FRESH_AGENT`, `FORK_AGENT`, `SUBAGENT`, and `CLONE`. It replaces the general Jev question-writing guidance for these questions; do not load the older `asking-jev-questions` skill for this feature.

## Research evidence

These sources inform which option strengths to investigate; none validates this feature's exact prompts or threshold:

- The *Lost in the Middle* study tested multi-document question answering and key-value retrieval. It reports that performance can fall when relevant information sits in the middle of a long input, with stronger performance near the beginning or end. This motivates checking for lost evidence or continuity in long runs; it does not show that every long run needs a fresh agent. [Paper and abstract](https://arxiv.org/abs/2307.03172)
- Anthropic's engineering guidance recommends starting with simple composable patterns, using parallel work when subtasks are independent or multiple perspectives are useful, and weighing the latency and cost of agentic systems. This is practical guidance drawn from their customer and engineering experience, not a universal performance guarantee. [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Anthropic's multi-agent research article describes benefits from parallel, independent investigations with separate contexts and also reports substantial token costs. Its reported 90.2% improvement is from Anthropic's internal research evaluation and should not be generalized to other tasks or systems. [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

## Question-writing rules

First ask what the option is good at, then derive questions about evidence that its strength is needed in this run. This is the owner's intended reasoning, not a request for Jev to recommend an action. A fresh agent gets a clean context: as a context window grows, accuracy may degrade, failures may become more frequent, the agent may remain stuck on the same error, or its actions may drift from the original goal. Ask separately about those visible failure modes. A fork explores genuinely different approaches to one unresolved goal, so ask about the approaches, their independence, and whether their results can be compared. A subagent completes bounded work for the main agent, so ask about a distinct work unit, the inputs it needs, and a result the main agent can use. A clone repeats the same approach in parallel copies and bets on variance between attempts, so ask about outcomes that vary between tries, a settled approach, a checkable and comparable result, and attempts that cannot collide. Each answer supplies one small piece of evidence; the average across the option's questions is the signal used by the selection policy.

The PR review gives the method in the owner's terms: first consider the option's "actual advantages and strengths"; make each question look for "a different type of evidence"; and make each answer contribute "a small piece of information" about whether the option fits. For a fresh agent, the owner named increasing errors or failure rate toward the end of the run, being stuck on the same failure or error, and drifting or diverging from the original goal as separate examples. Apply that same strengths-to-evidence reasoning to forks and subagents. These examples identify signals to test; they are not scenario details to paste into every prompt.

Treat the following as design heuristics for this classifier, not empirical claims from the sources above:

1. Keep each question about one distinct signal for one option. Begin with the advantage or failure mode that makes the signal relevant, then describe what that signal looks like in an agent's work. Ask whether the signal is present, not whether an agent, fork, or helper should be launched or whether extra compute would help.
2. Use only the supplied run evidence. The shared state supplies the original request, verified brief, exact facts, and recent events, but the question text must not name, explain, or inventory those state fields. Do not refer to hidden context, unprovided tools, or an imagined future outcome.
3. Write each question's entire instructions as one string literal of 10–12 full, coherent sentences. Do not assemble sentence fragments or reuse the same opening and closing sentences across the twelve questions. Give every signal its own explanation and natural transitions. Use three opening sentences to introduce its general problem, define it, and describe how it appears in practice. Then make sentences four through eight five related questions: the fourth asks the first direct question; the fifth digs deeper; the sixth asks about causes or background; the seventh asks about current solutions or attempts; and the eighth connects the signal to the remaining goal or expectation. Finish with two declarative sentences summarizing what evidence counts and what absence or counterevidence means. The five questions refine one signal; they do not introduce five separate requirements. Every sentence must express a complete idea. Avoid scenario-specific examples, clipped sentences, run-on sentences, and generic filler.
4. Give both `when_true` and `when_false` three full, signal-specific sentences. The true side names the observable positive pattern, explains the evidence linking its parts, and shows why it matters to the unfinished work. The false side describes counterevidence, a near miss, and what missing evidence leaves the pattern unestablished. These are answer criteria Jev reads, not labels to compress into one sentence. Make the positive answer mean that the named evidence is present in the run; allow false when the supplied evidence does not establish it. A long context or a plausible task shape alone does not prove the option is needed.
5. Keep each option's evidence question separate from the common compute policy. Code requires all twelve answers for an option and scores their arithmetic mean P(true) against the one inclusive threshold. Do not add gates, per-question vetoes, eligibility conditions, priority-first logic, or option-specific thresholds.
6. Instantiate the existing `JevComputeQuestion` dataclass. Add a question key in `vidbyte/lib/enums/jev.py`, register the ordered option questions in `JevComputeRegistry`, and test the shared state and flattened request. Do not add question dataclass subclasses.

## Review checklist

- The question tests one named evidence signal, not a launch decision or performance forecast.
- The instructions are one literal string of 10–12 connected, complete sentences with no state-field names or repeated boilerplate across questions.
- Sentences one through three explain this signal; sentences four through eight are five related questions in the order above; the final two sentences summarize its positive and negative evidence.
- The first question asks about the option's evidence signal, and the later questions deepen that same signal without scenario-specific examples or a launch recommendation.
- True and false each contain three complete sentences tailored to the signal; together they distinguish support, counterevidence, and insufficient evidence.
- The question is one of exactly twelve for its option and is an existing `JevComputeQuestion` instance.
- Tests cover question count and shape, combined request order, incomplete answers, and option mean scoring.
