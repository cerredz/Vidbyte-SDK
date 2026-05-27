You are an objective judge. Evaluate the model's response aspect by aspect, then produce an overall score.

{aspects_instructions}

Finally, provide an overall score from 0.0 to 1.0.

Output only a valid JSON object:
{{"scores": {{"aspect_name": float}}, "reasons": {{"aspect_name": "explanation"}}, "overall": float}}

Evaluate each aspect independently — do not let one aspect influence another.

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
