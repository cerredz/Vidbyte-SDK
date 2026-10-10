# What this tool does

Jev read this request before you started and found that it asks for the same work on several separate items, and that no item needs another item's result. This tool lets you split that work across fresh agents that all run at the same time. Each agent carries out one task that you write and hands its result back to you. You then check the results and write the final answer yourself.

# When to use it

Call this tool once, before you start working on the items yourself, if you can write the work as {min_agents} to {agents} tasks that do not overlap. One task can cover one item or a small group of items, so a long list still fits into {agents} tasks. Do not call it if a closer look shows that the items depend on each other, must be done in a set order, or would change the same file, record, or setting. In those cases, do the work yourself as usual. The agents run only once for this request.

# How to write the tasks

Every agent starts fresh. It sees the user's original request and its own task, and it has the same tools and permissions you have. It cannot see this conversation, your notes, or the other agents. Write each task as complete instructions that make sense on their own. Name the exact items the task covers, say what to do with them, and say what result to hand back. Cover every item the user asked about exactly once, and do not add work that the user did not ask for.

# What you get back

The tool returns every agent's handoff in the order you wrote the tasks, each marked as completed or failed. Read every handoff and check it against the user's request. Do any failed or missing work yourself, then write the final answer from the handoffs in the form the user asked for.
