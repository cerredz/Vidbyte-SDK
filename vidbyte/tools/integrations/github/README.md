# GitHub tools

## Intent

These tools expose repository listing, file reading, and code search while
binding owner and repository before a model can issue a call.

## Index

- `base.py` — shared scope, validation, provenance, and result handling.
- `list_files.py` — `GitHubListFilesTool`.
- `read_file.py` — `GitHubReadFileTool`.
- `search_code.py` — `GitHubSearchCodeTool`.

## Non-goals

The tools do not perform writes and do not allow model arguments to provide a
host, owner, repository, or arbitrary command.

## Change log

- Added as one-tool-per-file layout for PR #431.
