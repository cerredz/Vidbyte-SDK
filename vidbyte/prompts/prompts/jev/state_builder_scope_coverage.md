## `scope`

For `scope.dimensions`, add one entry for each group of items that the request asks a change to reach, such as "all of our model providers", "every endpoint in the API", or "the web, CLI, and API". Add no entry when the request is about one thing only. Code checks every quoted field against the request, so copy text exactly.

- `id`: a stable concise identifier made from lowercase letters, digits, and underscores.
- `request_quote`: the exact span of the request that states the group and the change.
- `requested_change`: the change each member must receive, in the user's words.
- `unit_noun`: what one member is, as a short singular noun phrase ("model provider").
- `membership_rule`: how someone watching the run could recognize a member, such as "a provider module under vidbyte/lib/providers/".
- `breadth`: `every_member` when the request says all, every, each, across, or names a whole group; `named_list` when it spells out two or more specific members; `one_example` when it asks for an example, a sample, or to start with one; `single_target` when it names exactly one item.
- `universe`: `named_in_request` when the request itself lists every member; `found_in_workspace` when the members exist in the environment and must be listed during the run; `open_ended` when the group has no finite list, such as "every edge case".
- `named_units`: the members the request names, each copied exactly from the request. Use an empty array when it names none.
- `excluded_units`: the members the request explicitly leaves out, each copied exactly from the request.
- `partial_allowed_quote`: the exact request text that allows covering only part of the group, such as "just do one for now". Use an empty string when there is none.
- `deliverable_id`: the `multi_part.deliverables` ID this group belongs to when that section exists and one deliverable clearly owns it; otherwise an empty string.

A `named_list` must use `named_in_request` and name at least two members. A `named_in_request` universe must name at least one member. Do not invent members, guess what a workspace contains, or widen the group beyond the request.
