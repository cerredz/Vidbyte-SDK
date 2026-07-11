# Contributing to Vidbyte SDK

Thanks for helping improve Vidbyte SDK. Contributions should keep the public package small,
inspectable, and useful for developers building reliable AI agent harnesses.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security
issues privately using the process in [SECURITY.md](SECURITY.md), not through a public issue.

## Development Setup

Vidbyte SDK requires Python 3.11 or newer.

```bash
git clone https://github.com/cerredz/Vidbyte-SDK.git
cd Vidbyte-SDK
python -m venv .venv
```

Activate the environment in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or activate it on macOS and Linux:

```bash
source .venv/bin/activate
```

Then install the SDK into the active environment:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

## Making a Change

1. Create a focused branch from the latest `main`.
2. Keep public API changes explicit and document compatibility implications.
3. Update nearby documentation when behavior, imports, package assets, or examples change.
4. Do not commit `__pycache__`, bytecode, virtual environments, build output, distributions, or
   `*.egg-info` directories.
5. Keep credentials, provider tokens, private prompts, and customer data out of commits and issue
   reports.

When adding non-Python runtime assets, confirm that the built wheel contains them and that the
installed package can load them outside the source checkout.

## Verification

Run the repository's existing checks before opening a pull request:

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import Agent, Tools, VidbyteSDK, tool; sdk = VidbyteSDK(); print(Agent.__name__, Tools.__name__, type(sdk.agents).__name__, callable(tool))"
```

Packaging changes should additionally build and validate both distributions:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

## Pull Requests

Use the pull-request template and include:

- The problem and intended outcome.
- Compatibility or migration implications.
- Commands run and relevant output.
- Documentation changes.
- Any follow-up work that is intentionally out of scope.

Small, coherent pull requests are easier to review. Maintainers may ask to split unrelated changes.

## Issues and Feature Requests

Use the repository's structured
[bug report](https://github.com/cerredz/Vidbyte-SDK/issues/new?template=bug_report.yml) or
[feature request](https://github.com/cerredz/Vidbyte-SDK/issues/new?template=feature_request.yml)
form. Search existing issues first and provide the smallest reproducible example you can share
safely.
