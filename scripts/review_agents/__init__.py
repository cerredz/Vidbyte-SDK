"""FILE: scripts/review_agents/__init__.py

PURPOSE: Marks the helper package the Claude review-agents workflow runs between its Claude Code steps.
ROLE IN CODEBASE: .github/workflows/claude-review-agents.yml calls run.py here to gather a round of review comments, see whether the branch conflicts with its base, plan which agent handles which comments, build each agent's prompt, commit and push what an agent changed or merged, and post the summary comment; .github/workflows/claude-review-sweep.yml calls it to start rounds GitHub sent no event for. No model decides any of that; the agents only edit files.
ARCHITECTURE NOTE: The package lives in scripts/, outside the installable vidbyte package, and imports nothing from it, because the plan and report jobs run on the runner's bare Python without the SDK installed and none of this may ship in the wheel.
COMMON MODIFICATION PATTERNS: Add a workflow step as a run.py subcommand backed by one module here; keep every record the steps exchange in review_data.py.
KNOWN EDGE CASES: run.py adds scripts/ to sys.path itself, so `python scripts/review_agents/run.py` works from any working directory.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py.
"""
