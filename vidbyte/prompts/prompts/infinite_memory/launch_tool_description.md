## What it does

Starts subagent pairs that each carry out one task, so the work happens outside your own context. In every pair, a fresh generator does the task from its generator_prompt, then a fresh verifier checks the result against the done criteria from its verifier_prompt, fixes what it can, and ends with a verdict. Every task therefore needs both prompts.

## When to use it

Use it for any piece of work that would fill your context: reading sources, producing substantial content, or anything that takes many tool calls. Do work yourself only when it is quicker than writing a task card for it.

## How it behaves

All the tasks of one call run at the same time, and the call returns once every pair has finished, with one short result card per task in the order you wrote them. A card carries the generator's status, the verifier's verdict, a capped summary and review, the memory entries saved and dropped, and the files written, never the agents' conversations. Both agents start fresh: they see their task card, the context it names, the workspace map, and the shared workspace, but not this conversation. A pair's memory entries are saved only once its verifier gives a verdict, while the notes it writes take effect at once. A task whose name already finished in this run, among the tasks you launched, is not run again: its recorded card comes back under a replayed label. Give new or repeated work a new name.

## Rules and refusals

The whole batch is checked before anything starts, and any problem refuses the whole call with a message that says what to fix. Names must be unique within the call, context may name only live entries, and tools may name only extra tools you hold. The system also limits how many tasks one call may carry, how deep pairs may nest, and how many agents one run may start; a call over a limit is refused with a reason that names the limit. Then split the batch over several calls, launch fewer tasks, or do the work yourself.
