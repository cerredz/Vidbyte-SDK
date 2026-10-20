# Composite thread function tests

## Folder Description / Intent

This folder tests `vidbyte.harnesses.native.compose`, the composites over the nine harness thread functions: binding steps, chains, verification with isolated readers, handoffs, staged retries, the ensemble, diff capture, disposable worktrees and structured answers. Everything runs offline. Every vendor program is the base pack's scripted stand-in (tests/features/harness_threads/fake_harness.py), launched as a real child process from its path. `git`, `CliRunner`, the nine functions and the filesystem are real. `ThreadComposeError.relevant_tests` points here.

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, the suite map and the strategies left out.
- `conftest.py` provides the lazy contract imports, the sandbox (home, workspace, PATH with the real git, temporary folder, git configuration shut out), git helpers and a tree oracle, stand-in scenarios and log readers, the step binder, the `CliRunner` spy, prompt renderers, the `ThreadComposeError` check, timing knobs and process liveness checks.
- `test_harness_compose_acceptance.py` runs the spec's example end to end against stand-ins on PATH.
- `test_harness_compose_surface.py` checks the 42 names, the lib exports (`JsonText` and `SecretText` among them), the vocabularies, the contract constants, the signatures, a side-effect-free import and the import layering.
- `test_harness_compose_prompts.py` checks the 22 prompt files, their fields, the ported files' forbidden texts, the 12,000-character room and the package-data entry.
- `test_harness_compose_binding.py` checks the binders, direct calls, the step's invoker and that a composite starts the same child process as a direct call.
- `test_harness_compose_validation.py` checks that every invalid input is refused before any I/O, a template blank without its spliced values and caller text holding a surrogate included, and that the command-line unit count is unchanged.
- `test_harness_compose_chain.py` checks chains, the pair aliases, the early stop, the prompt fit and the repair of surrogate halves in an answer.
- `test_harness_compose_verify.py` checks verification, the trio aliases, isolated readers and writing readers.
- `test_harness_compose_answers.py` checks structured answers, cut answers, repair turns, `JsonText` and the record bounds.
- `test_harness_compose_handoff.py` checks handoffs.
- `test_harness_compose_stages.py` checks staged runs, the decision table and the retry rungs.
- `test_harness_compose_ensemble.py` checks the ensemble's roles, narrowing, repairs, the selector's prompt room and stops.
- `test_harness_compose_git.py` checks git availability, repository checks, git hygiene and git failures.
- `test_harness_compose_workspace.py` checks `capture_diff` and `in_worktree`.
- `test_harness_compose_concurrency.py` checks cancellation (a second cancel, an anyio cancel scope and a cancel during a slow worktree add included), a failed worktree add that stops its siblings, and Grok serialization.
- `test_harness_compose_removal.py` checks a reader worktree that cannot be removed: the record keeps every finished answer, and a running sibling is stopped first.
- `test_harness_compose_derived_steps.py` checks that steps compose derives after I/O began (a relocated verifier, an anchored repair turn, a ladder rung) record a vanished skill folder instead of raising.
- `test_harness_compose_keys.py` checks that no bound key leaks into prompts, errors (refusals of caller text or of a record field that holds a key included), answer problems, the cause, context and traceback of a folder failure, reprs or git.

## Logs

- 2026-10-17 - Created at S2 of the spec pipeline for `docs/spec/native-thread-compose/spec.md` r3, before the implementation existed; every test is red until compose lands (`docs/spec/native-thread-compose/test-plan.md`). The base pack's stand-in gained the scenario fields `label`, `answers`, `replies`, `observe_files` and `write_files`, and the `marker` program, all read with defaults so the base pack runs unchanged.
- 2026-10-18 - After the S4 review (`docs/spec/native-thread-compose/review.md`): the comment lines were rewrapped to 72 columns (R-11), the EC-19 fan-out tests were added (R-16), with a `reference-transaction` hook as the outside fault, and the caller-text refusal cases were added with a 16-character key (R-17). The two-failed-adds case is red until R-10 lands, and the caller-text cases until R-3 lands.
- 2026-10-18 - After S5 repair 1, each confirmed fix that only scratch probes had proven got a test that fails on S3's code (`e1bf20d8`) and passes on the repair (`docs/spec/native-thread-compose/test-plan.md`, Coverage added after S5 repair 1): R-8 (a reader worktree that cannot be removed), R-15 (steps derived after I/O), R-10 (repeated cancels during cleanup), R-14 (a cancel during a slow worktree add), R-12 (surrogate halves in an answer), R-13 (a blank template; its `{prompt}` cases stay red until R-32 lands), EC-81 (a surrogate in caller text), AC-22 (the `SecretText` export). The stand-in gained the scenario fields `delete_paths` and `term_linger`, read with defaults so the base pack runs unchanged.
- 2026-10-19 - After review R-33 (`docs/spec/native-thread-compose/reports/S5-findings-verifier-rr1.md`): `test_harness_compose_keys.py` gained 18 record rows, one per record field whose refusal could quote a 16-character key (a `ThreadStep` built directly or changed with `dataclasses.replace`, `StageSpec`, `ThreadVerdict`, `StageAttempt`, `EnsembleRole`, `EnsembleSelection`, `WorkspaceDiff`). It also gained 3 answer rows, where a stand-in answers its own key into a verdict's `decision`, a selection's `proposal` or a plan role's `name`, and a guard row for a round's `kept` list. The 21 R-33 rows are red until R-33 lands, and the guard passes now. The caller-text cases now also read every exception a refusal keeps as its context or cause.
- 2026-10-20 - After review R-34 (`docs/spec/native-thread-compose/reports/S5-findings-verifier-rr2.md`): `test_harness_compose_keys.py` gained two rows in which a reader's worktree cannot be removed because a file named after its key is held, through `verify_with` and `run_ensemble`, and two rows for the same rule at the folder sites, a temporary folder and a matching folder that cannot be made. The AC-15 file-name test now also reads the traceback. The four new rows are red until R-34 lands.
