## Purpose

The brief for the verifier, the fresh agent that checks the generator's work after it finishes, fixes what it can, and ends with a verdict.

## How to write it

Say what to check and how: the sources of truth to compare against, the checks to run, and what counts as failing. The verifier does not receive the entries and paths named in context, so name every file, entry, or source it needs to judge the work. Say which fixes it may make itself and which problems should fail the task instead.

## Rules

The verifier sees the goal, the done criteria, the generator's status and final answer, the memory entries it staged, and the workspace files it wrote, but never its conversation. Its final reply must end with a verdict line; without one, the work counts as unchecked and nothing the pair staged is saved.
