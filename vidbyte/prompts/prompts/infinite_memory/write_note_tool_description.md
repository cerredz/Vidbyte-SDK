## What it does

Writes longer material to a file in the shared workspace, where every agent and every later run can read it. Notes hold what does not fit in a one-line memory entry: findings with their sources, drafts, tables, plans, and progress logs.

## When to use it

Use it for a deliverable, for material too long for an entry, and for a running log of progress that must survive the trimming of your history. When later agents will need to find an important note, also remember a pointer entry that names it.

## How it behaves

A path that does not exist yet creates a new file, which needs a one-line description for the workspace map and uses your small allowance of new files. A path that exists gets the text appended to its end. The write takes effect at once and is not staged, so other agents can read it immediately and no verdict undoes it. Every reply ends with your quota line.

## Rules and refusals

The path must stay inside the workspace and end in .md, .txt, .json, or .jsonl. Seed files, run journals, and the bookkeeping files of memory cannot be written. Each file and the workspace as a whole have size and file-count limits, and a write over any limit is refused with the limit named and nothing written. When your new-file allowance is spent, append to an existing note instead.
