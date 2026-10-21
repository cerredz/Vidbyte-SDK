<task>
{prompt}
</task>

<previous-step>
Another agent worked on this task just before you. Its answer:

{previous}

The change it made to the workspace, as a diff of the whole repository (empty when it changed
nothing):

{diff}
</previous-step>

Continue the task from where that agent left off. Check its answer and its change against the
workspace before you build on them.
