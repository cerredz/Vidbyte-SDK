## Purpose

The memory entries and workspace files this pair should start from.

## How to write it

Name an entry as a hash sign followed by its id; that entry's text is pasted into the generator's first message. Name a file by its path relative to the workspace folder; the generator is told to read it rather than given its text. Choose only what the task needs, since every pasted entry and listed file costs the generator attention, and leave the list out when nothing applies.

## Rules

Only the generator receives this context, so name what the verifier needs in the verifier prompt. An entry id that is unknown or already superseded refuses the whole call, so take ids from a recent search of live memory. The list has a size limit, and a list over it is refused with the limit named.
