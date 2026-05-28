You are a careful evaluator breaking down a high-level evaluation criterion into precise, independently verifiable sub-questions. Criteria decomposition is used to reduce inter-run variance caused by vague rubrics — by forcing the criterion to be expressed as a checklist of yes/no questions, the evaluation becomes more reproducible and less sensitive to wording ambiguities. Each sub-question must be non-overlapping: answering one should not logically imply the answer to another. Each sub-question must also be answerable with a direct yes or no based solely on the response and the task prompt, with no additional inference required. Target exactly {num_sub_criteria} sub-questions — fewer reduces coverage, more introduces overlap. Write sub-questions from the perspective of the evaluator, not the respondent: for example, "Does the response define X?" rather than "Did you define X?". Output only a numbered list of sub-questions with no additional text, headers, or explanation.

Break the following evaluation criterion into exactly {num_sub_criteria} specific, non-overlapping sub-questions that can each be answered yes or no.

Criterion: {criterion}

Output a numbered list of sub-questions only. No other text.
