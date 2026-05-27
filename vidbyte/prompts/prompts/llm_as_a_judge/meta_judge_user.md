You are a meta-judge evaluating the quality of another judge's evaluation. Check whether the verdict below is coherent, whether the reason is consistent with the score, and whether important criteria were missed.

Primary Judge's Verdict:
Score: {primary_score}
Reason: {primary_reason}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}

Output only a valid JSON object:
{{"quality_ok": true or false, "quality_reason": "explanation of why the verdict is or is not high quality"}}
