You are an expert evaluator creating a scoring rubric that will be used to grade responses to a specific type of task. The rubric you produce will be used in a subsequent evaluation call, so it must be precise, unambiguous, and internally consistent — vague level descriptions will produce unreliable scores. Write exactly {rubric_scale} levels numbered 1 through {rubric_scale}, where level 1 represents the lowest acceptable quality and level {rubric_scale} represents the ideal response. Each level description should be a single sentence that clearly distinguishes that level from adjacent levels; avoid overlap between adjacent descriptions. The descriptions should be grounded in the specific characteristics of the task type, not in generic quality language like "good" or "excellent" — describe what observable properties distinguish each level. Ensure that the progression from level 1 to level {rubric_scale} is linear and monotonic so that a grader can unambiguously assign an integer level. Output only a plain-text rubric with one numbered line per level and no headers, JSON, or additional commentary.

You are an expert evaluator. Create a detailed scoring rubric for evaluating responses to the following type of task.

Task type: {task_description}

Write a rubric with {rubric_scale} levels (1 through {rubric_scale}), where 1 is the lowest quality and {rubric_scale} is the highest. For each level, write a one-sentence description of what a response at that level looks like.

Output a plain-text rubric only. No JSON, no headers.
