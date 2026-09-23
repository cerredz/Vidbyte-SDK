# Jev preflight preset: `recurring`

## What and why

This adds a second registered preflight preset, `recurring`, to JevAgent. It asks Jev 20 yes/no
questions about general properties of a request. Each property suggests the work is of a
reusable kind: the subject changes over time, the result has variants, the method works on other
inputs, the work belongs to a repeating cycle, and so on.

This PR only asks the questions and records the answers. What the agent does with them (offer or
create a skill or an automation) is deliberately out of scope and will be designed later.

The owner asked for three things:

1. Every question uses the same full structure. The instructions contain five parts: a
   definition, markers from several unrelated domains, a boundary, a focus, and the question. The
   `true` and `false` criteria each carry a `what` and `examples`.
2. One preset line turns the questions on:
   `JevPreflight(preset=(JevPreflightPreset.RECURRING,))`, or `preset=("recurring",)`.
3. Several presets can be selected together, and their questions are appended into the single
   Jev request before it is sent.

This branch includes PR #443 (`JevPreflight`), because `main` has no preflight yet. Once #443
merges, this PR's diff shrinks to the changes below.

## How it works

- `vidbyte/agents/jev/recurring.py` holds `RECURRING_QUESTIONS`, the 20 fixed `noul` questions,
  built with one helper so that every question has the same shape. Each question refers to the
  state field `request` by name. `true` always means "supports reuse", so the #443 mean score
  stays meaningful.
- `presets.py` gains `JevPreflightPreset.RECURRING` and a `JevPreflightAction` enum:
  - `CLARIFY`: the existing clarity behavior. A score below the threshold short-circuits the run.
  - `RECORD`: answers and a mean score are recorded, and nothing else happens.
- `recurring` and `custom` use `RECORD`. Without this, selecting `recurring` together with
  `clarity` would make the runtime treat a low recurring score as an unclear request and return a
  clarifying question. Custom questions move from the `threshold=0.0` workaround to `RECORD`.
- `JevPreflight.definitions()` already concatenates every selected preset's questions, then the
  custom ones, into one tuple, and the runtime sends them as one request. This PR keeps that.
- **Shared state fix.** #443 puts clarity-specific framing ("You are evaluating whether a user
  request is clear enough…") into the request `state`. Every question in the batch reads that
  state, so recurring questions would be judged under clarity framing. The state becomes
  `{"request": <message>}`. The clarity framing moves into each clarity question's own
  instructions, which is where rules belong (asking-jev-questions, strategy 19).

## Files

- `vidbyte/agents/jev/recurring.py`: new; the 20 questions.
- `vidbyte/agents/jev/presets.py`: adds the `RECURRING` preset, `JevPreflightAction`, and the
  registry entry. Moves the clarity framing into clarity questions. Moves custom to `RECORD`.
- `vidbyte/agents/jev/runtime.py`: sends the neutral state, and only `CLARIFY` definitions can
  short-circuit.
- `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`: export
  `JevPreflightAction`.
- `tests/test_jev_preflight.py`: new and updated cases.
- `skills/jev-agent/SKILL.md`: documents the preset and the action rule.

## Risks and open questions

- The clarity questions now carry their framing per question rather than once in the state. The
  meaning is the same, but Jev probabilities may shift slightly. The clarity threshold was never
  tuned, so no tuned value is lost.
- #440 and #441 also redefine preflight. Whichever lands after this must use `JevPreflightAction`.
- The questions are abstract by design. Their accuracy is unmeasured until a labeled set exists.

## Verification

- `python scripts/test-jev-preflight.py`, with new cases:
  - the preset has 20 unique `noul` questions, and each has both criteria with `what` and
    `examples`;
  - one preset line enables it;
  - clarity, recurring, and custom are appended in order into one request;
  - a low recurring score never short-circuits;
  - the state is `{"request": ...}` with no clarity framing;
  - recurring results are marked unavailable when Jev is unavailable.
- `python lint/run.py`, `python scripts/run_ci.py --stage source`, `python scripts/run_ci.py`.
