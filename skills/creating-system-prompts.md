# Creating System Prompts

Use this skill when creating or revising Vidbyte system prompts.

System prompts are the primary drivers of agent behavior. They should be detailed, sectioned, and explicit enough that the model can infer correct behavior without relying on implied intent. Short anonymous strings are acceptable only for tiny tests or placeholders; production prompts should read like operating manuals for the agent.

## Required Sections

Every substantial system prompt should include these sections:

## Identity

Define the role of the agent in detail. Explain what domain it operates in, what professional posture it should take, what kinds of evidence it should trust, and what boundaries it must not cross. The identity section should establish tone, vocabulary, and decision-making defaults. It should not merely say "You are helpful." It should describe the agent's responsibilities as if the prompt is defining the agent's job.

## Goal

Explain the objective of the agent and what successful completion looks like. This section should describe the artifact, answer, decision, or workflow the agent is expected to produce. Include scope boundaries, acceptance criteria, and the conditions under which the agent should stop. The goal should be concrete enough that the model can judge whether its current output is complete.

## Checklist

Provide a bullet list of behaviors the agent should remember while working. Include domain-specific checks, safety boundaries, formatting constraints, verification steps, and common failure modes. The checklist should be long enough to cover the important behavior of the task, not just generic advice. Prefer direct imperatives.

## Input Description

Describe the input the agent will receive. Name the input fields, explain what each field means, and clarify which parts are evidence versus instructions. If the agent receives another agent's context window, conversation history, tool output, serialized data, or user request, describe how to interpret each part and what assumptions are unsafe.

## Output Description

Describe the required output shape and quality bar. Specify exact fields, formatting, allowed values, forbidden wrapper text, validation expectations, and how the output will be consumed. If downstream code parses the output, say so and require strict parseability.

## Prompt Length And Detail

System prompts should be on the longer side when they govern real agent behavior. Each major section should be detailed enough to remove ambiguity, often several paragraphs for complex agents. Long prompts are valuable when every section carries behavioral signal: identity narrows role, goal defines completion, checklist preserves rules under pressure, input description prevents misreading context, and output description makes validation explicit.

Do not make prompts long by repeating generic encouragement. Add length by explaining edge cases, priorities, boundaries, failure modes, examples of evidence, and exact output contracts.

## Review Checklist

Before handing off a system prompt, verify:

* The prompt has Identity, Goal, Checklist, Input Description, and Output Description sections.
* The Identity section defines a specific role and behavioral posture.
* The Goal section states what done means.
* The Checklist contains concrete, domain-relevant reminders.
* The Input Description explains how to interpret every supplied input region.
* The Output Description defines a strict output contract.
* The prompt avoids vague encouragement and short anonymous instruction strings.
* The prompt includes enough detail to drive behavior without extra explanation.
