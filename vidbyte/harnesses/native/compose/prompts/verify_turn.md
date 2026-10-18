<task>
{prompt}
</task>

<change>
Another agent has just worked on the task above in this workspace. The files it changed, one
per line:

{files}

The change as a diff of the whole repository:

{diff}
</change>

Review the change, and do not change any file yourself. Decide whether it accomplishes the
task correctly and completely. Read the changed files and whatever else in the workspace you
need, and check that the change does what the task asks, that it is correct, that it covers
the cases the task implies, and that it breaks nothing around it. Base your decision on what
you checked, not on how plausible the change looks.
