# Jev compute sign questions

This folder holds every fixed question JevAgent's mid-run compute checkpoint sends to Jev, one dataclass per question, grouped into one module per situation, along with each situation's recognition policy and the registry over the questions.

## Load the asking-jev-questions skill first

Whenever a model or agent writes, rewrites, or reviews a question here, it must first load `skills/asking-jev-questions/SKILL.md` from the root of this repository and follow its "Writing a full question" section, exactly as the preflight and done questions do:

- the brief opens with a 2–3 sentence introduction, then describes the state, then defines every term in dependency order with no examples, then states every rule, then asks one positive yes/no question about a named state field;
- the rules give the empty case its side, then the focus ("Judge only ..."), then end with the shared `JUDGE_MEANING` and `IGNORE_CLAIMS` rules from `state.py`;
- each criterion opens with the verdict in the defined term, lists only the signs of its side, names what belongs to the other side, and gives labeled easy and boundary examples that form minimal pairs across the two sides.

Every question asks Jev to recognize one sign in the run as it is now, never whether extra compute would help, because Jev answers observations reliably and forecasts poorly. Every `true` side is the sign being present, so a situation's score is a plain mean of P(yes).

## Where things live

- `state.py` holds the sentences every compute question shares.
- `repeating.py`, `each_of_several.py`, and `self_contained_step.py` hold each situation's sign questions and the description of the state its questions read.
- `situations.py` holds `JevComputeSituations`: each situation's question keys, threshold, veto, and gate.
- `compute.py` holds `JevComputeRegistry` (`get`, `questions`, `validate`).
- The situations and question keys are in `vidbyte/lib/enums/jev.py`; the records are in `vidbyte/lib/dataclasses/jev.py`; thresholds and state field names are in `vidbyte/lib/constants/jev.py`.
- The code that decides when to ask, builds each situation's state, asks Jev, and scores the answers is in `vidbyte/agents/jev/compute/`.
