{{
  "proposal": integer,
  "approach": string,
  "rationale": string,
  "guidance": string
}}

- `proposal` is the number of the one proposal you select, a proposal number offered in this
  round, written as a JSON integer.
- `approach` states what is to be done, concretely enough to act on without the other
  proposals.
- `rationale` explains why this proposal beat the others, with the evidence you checked.
- `guidance` is the execution brief for the implementer: the steps to take, the costs and
  risks to handle, the assumptions to verify, and how to validate the result.
- Every string is non-empty.
