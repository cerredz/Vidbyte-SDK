## Section `required_sequence`
Fill `sections.required_sequence.stages` only when the request requires parts of the work to happen in a particular order. The agent will not be allowed to finish until its recorded work shows every stage you list done, in the order you list them. A stage the user never asked for will block a correct run, so list only stages the request asks for.

A request requires an order when it does one of these:
- It uses ordering words between parts of the work: "first", "then", "next", "after", "before", "once ... is done", "only then", "finally".
- It numbers or letters its steps.
- It names a sequence of phases, such as "research, draft, review, publish".

A list of deliverables with no order between them is not a required order. For example, "add tests and update the docs" names two deliverables in no particular order. Return `"stages": []` for that request, and for every request with no required order.

For each stage, in the required order:
- `name`: a short name of one to three words, such as "Research", "Draft", or "Review".
- `source_text`: the exact words from the request that ask for this stage, copied character for character. Letter case may differ; nothing else may. Do not paraphrase, shorten, or join words from different places. Every stage must have its own words in the request. Do not add setup, verification, or wrap-up stages that the request does not ask for.
- `completion_criterion`: one or two sentences that describe what finishing this stage looks like, in terms someone could see in the agent's actions and tool results. Describe the visible result, such as "A complete draft of the post exists in a file". Do not describe quality, such as "A good draft".
- `produces`: what this stage outputs for later stages, such as "notes on the sources" or "the draft file". Use an empty string when later stages do not use anything it outputs.
- `depends_on_previous`: true only when the request says, or clearly means, that this stage works from the previous stage's output, as in "write a draft from your research" or "review the draft". Always false for the first stage.

Keep one stage for each phase the request names. Do not split a stage into sub-steps. Do not merge two stages the request names separately. List at most 12 stages.
