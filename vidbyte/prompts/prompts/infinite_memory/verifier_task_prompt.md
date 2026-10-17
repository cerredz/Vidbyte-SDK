# Your instructions

What the agent that launched this pair wants you to check, and how. Follow them alongside the done criteria.

{instructions}

# Goal

The outcome the generator was asked to achieve.

{goal}

# Done criteria

Judge the work against each of these, one by one, with evidence.

{criteria}

# What the generator reported

Its status and its final answer. Status done means it finished normally, and partial means it stopped before finishing. Treat the answer as claims to check, not as proof.

Status: {status}

{summary}

# Memory entries the generator staged

Each line gives a staged key, its kind, and its text. Every entry left staged is saved once your final reply carries a verdict, so drop the flawed ones with drop_entry. A dash means none.

{staged}

# Files the generator wrote

Workspace files the generator created or changed with its memory tools. They are already written, so check them and fix them in place. A dash means none.

{files}

# Your memory quota

{quota}

# What to do next

Check each done criterion against the evidence, fix what falls short, and review the staged entries. Then end your final reply with exactly one verdict line.