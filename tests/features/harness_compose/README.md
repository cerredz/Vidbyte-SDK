# Composite thread function tests

## Folder Description / Intent

This folder tests `vidbyte.harnesses.native.compose`, the composites over the nine harness thread functions: binding steps, chains, verification with isolated readers, handoffs, staged retries, the ensemble, diff capture, disposable worktrees and structured answers. Everything runs offline. Every vendor program is the base pack's scripted stand-in (tests/features/harness_threads/fake_harness.py), launched as a real child process from its path. `git`, `CliRunner`, the nine functions and the filesystem are real. `ThreadComposeError.relevant_tests` points here.

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, the suite map and the strategies left out.
- `conftest.py` provides the lazy contract imports, the sandbox (home, workspace, PATH with the real git, temporary folder, git configuration shut out), git helpers and a tree oracle, stand-in scenarios and log readers, the step binder, the `CliRunner` spy, prompt renderers, the `ThreadComposeError` check, timing knobs and process liveness checks.
- `test_harness_compose_acceptance.py` runs the spec's example end to end against stand-ins on PATH.
- `test_harness_compose_surface.py` checks the 42 names, the lib exports, the vocabularies, the contract constants, the signatures, a side-effect-free import and the import layering.
- `test_harness_compose_prompts.py` checks the 22 prompt files, their fields, the ported files' forbidden texts, the 12,000-character room and the package-data entry.
- `test_harness_compose_binding.py` checks the binders, direct calls, the step's invoker and that a composite starts the same child process as a direct call.
- `test_harness_compose_validation.py` checks that every invalid input is refused before any I/O, and that the command-line unit count is unchanged.
- `test_harness_compose_chain.py` checks chains, the pair aliases, the early stop and the prompt fit.
- `test_harness_compose_verify.py` checks verification, the trio aliases, isolated readers and writing readers.
- `test_harness_compose_answers.py` checks structured answers, cut answers, repair turns, `JsonText` and the record bounds.
- `test_harness_compose_handoff.py` checks handoffs.
- `test_harness_compose_stages.py` checks staged runs, the decision table and the retry rungs.
- `test_harness_compose_ensemble.py` checks the ensemble's roles, narrowing, repairs, the selector's prompt room and stops.
- `test_harness_compose_git.py` checks git availability, repository checks, git hygiene and git failures.
- `test_harness_compose_workspace.py` checks `capture_diff` and `in_worktree`.
- `test_harness_compose_concurrency.py` checks cancellation, a failed worktree add that stops its siblings, and Grok serialization.
- `test_harness_compose_keys.py` checks that no bound key leaks into prompts, errors (refusals of caller text that holds a key included), reprs or git.

## Logs

- 2026-10-17 - Created at S2 of the spec pipeline for `docs/spec/native-thread-compose/spec.md` r3, before the implementation existed; every test is red until compose lands (`docs/spec/native-thread-compose/test-plan.md`). The base pack's stand-in gained the scenario fields `label`, `answers`, `replies`, `observe_files` and `write_files`, and the `marker` program, all read with defaults so the base pack runs unchanged.
- 2026-10-18 - After the S4 review (`docs/spec/native-thread-compose/review.md`): the comment lines were rewrapped to 72 columns (R-11), the EC-19 fan-out tests were added (R-16), with a `reference-transaction` hook as the outside fault, and the caller-text refusal cases were added with a 16-character key (R-17). The two-failed-adds case is red until R-10 lands, and the caller-text cases until R-3 lands.
