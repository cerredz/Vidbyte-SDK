## `scope`

Return exactly one `scope.dimensions` entry for every ID in `checked_scope_dimension_ids`, using `dimension_id` for the ID. Each entry reports what the run did across that group. It does not decide whether the group is covered; code and a separate classifier do that.

- `enumeration`: excerpts from tool-call outputs (`tool_call_N` sources) that list the members of the group, such as a directory listing or a search result. Leave it empty when the run never listed the members.
- `units`: one entry for every member in the dimension's `named_units`, copied exactly, and one for every member that an `enumeration` excerpt lists, spelled as the listing spells it. Include members that received no work; they matter most. Leave out members in `excluded_units`.
  - `source`: `named_in_request` for a named member, `found_by_run` for a member that appears in an `enumeration` excerpt, and `mentioned_by_agent` for any other member the agent talked about.
  - `work`: excerpts from `iteration_N` or `tool_call_N` sources that show an action on this member, such as a file write, an edit, a command, or its result. Use an empty array when the run shows no action on it. Do not cite the final answer as work.
- `narrowing`: excerpts from `iteration_N` sources or the `final_answer` where the agent chose to cover only part of the group, such as "I will use OpenAI as the representative case".
- `coverage_claims`: excerpts from the `final_answer` that say how far the change reached, such as "updated all providers" or "the others are not done yet".

Do not treat work on one member as work on another, even when the agent says the rest follow the same pattern.
