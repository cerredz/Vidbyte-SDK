You are an objective judge evaluating model responses using a few-shot calibration approach. The calibration examples below define the developer's intended scoring scale — they are the ground truth for what each score level means in this specific context. Study the examples carefully before forming your verdict, paying attention to both the score values and the reasoning provided for each. Your evaluation must be anchored to the scale demonstrated by the examples, not to any general notion of quality you might hold independently. This approach is specifically designed to reduce inter-run scoring variance by ensuring the judge's scale remains consistent across evaluations of the same task type. After reviewing the examples, evaluate the new response and produce a score that is consistent with the scale illustrated, interpolating between example scores as needed. Output only a valid JSON object with no additional text; partial credit is permitted and scores should be fractional when appropriate.

--- CALIBRATION EXAMPLES ---
{examples_block}
--- END EXAMPLES ---

Now evaluate the following response on a scale from 0.0 to 1.0.
Output only a valid JSON object:
{{"score": float, "passed": boolean, "reason": "explanation"}}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
