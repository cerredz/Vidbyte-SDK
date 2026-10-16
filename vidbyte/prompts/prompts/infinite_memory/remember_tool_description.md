## What it does

Saves one short, typed memory entry to the workspace that every agent in this run, and in every later run, shares. Entries are how knowledge outlives a conversation: histories are trimmed, and every subagent starts fresh, so what is not saved is lost.

## When to use it

Remember only what will matter again: a decision that was made, a fact that was established, a lesson about what works or fails, an open question, or a pointer to a file that holds longer material. Do not record progress updates, plans that will soon change, or anything the workspace map already shows. Before saving, search memory with grep, so you supersede an existing entry instead of adding a second version of it.

## How it behaves

The root's entries are saved at once, each under a new id. A generator's or verifier's entries are staged under a key and saved only once the pair's verifier gives a verdict, and the verifier may drop them first. Every reply ends with a quota line, because each agent may keep only a small number of entries; a refused call does not count against it. To correct an outdated entry, save the new one with supersedes set to the old id, so the old one leaves live memory instead of contradicting the new one.

## Rules and refusals

The text must be one short line under the entry size limit; longer material belongs in a note, with a pointer entry that names it. Text already saved or staged, ignoring case and spacing, is refused. A supersedes id must name a live entry. A refusal says what to fix and changes nothing.
