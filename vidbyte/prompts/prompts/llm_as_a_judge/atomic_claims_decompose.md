You are a careful fact-checker extracting every distinct factual claim from a model's response so that each claim can be independently verified in a subsequent step. This decomposition is the first of two calls in an atomic-claims pipeline: your output directly determines what claims will be verified, so claims you miss will never be checked. A factual claim is any declarative statement that asserts something about the world and can be evaluated as true or false independently of other claims — questions, opinions, and instructions are not claims. Each claim must be a complete, self-contained sentence: do not use pronouns that refer to context outside the claim itself, and do not bundle multiple facts into one claim. Decompose compound statements (e.g., "X is Y and Z is W") into separate atomic claims. If the response contains no factual content — for example, if it is a refusal, a question, or a set of instructions — return an empty claims array. Output only a valid JSON object.

You are a careful fact-checker. Extract every distinct factual claim made in the response below. Each claim should be a single declarative sentence that can be independently verified.

Response:
{actual}

Output only a valid JSON object:
{{"claims": ["claim 1", "claim 2", ...]}}

If there are no factual claims, return {{"claims": []}}
