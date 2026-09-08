# Codex continual artifacts

Completed-item observations trigger deterministic native trace update requests.
UpdateTraceTool enforces the existing shape and merge contract. Failed updates
retain the previous artifact; cancellation aborts. Tests use real schema and merge
objects with a fake native transport. Acceptance, failure, isolation, and native
request contract coverage are required; live model quality is outside this pack.
