---
name: asking-jev-questions
description: Write the fixed internal questions a JevAgent capability asks TypeSafe Jev (noul, choice, score) so that Jev matches the state against a definition instead of reasoning its way to an answer. Use when designing, reviewing, or debugging any Jev question, its criteria, its state projection, or the code that acts on its answer.
---

# Asking Jev Questions

Use this skill whenever you write or change a question that a `JevAgent` capability sends to Jev. Read `skills/jev-agent/SKILL.md` first for the package boundary. This skill covers only how to write the question itself.

It was written against `jev-1.13` and TypeSafe's documentation as of September 2026. Recheck the [jaggedness page](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md) when the model version changes.

## The core idea

Jev is a System One model. It reads a `state`, reads a question, and returns calibrated probabilities over options you define. It is fast and good at common-sense judgment. It is not a reasoning model: it does not plan, count, compare dates, follow long chains of logic, or generate text.

Many useful decisions *look* like they need reasoning. "Is this request in scope?" seems to need Jev to work out what the agent is for, then compare the request against that. The trick is that **phrasing does not delete reasoning. It moves it.** Every question has up to three kinds of work in it, and each kind has a correct owner:

| Work | Owner | Examples |
| --- | --- | --- |
| Deciding what a word means | **You**, when you write the question | What counts as "in scope", "trivial", "independent" |
| Arithmetic, counting, dates, combining answers, choosing an action | **Code** | Count list items; combine four yes/no answers into a level; compare P(off-topic) to 0.9 |
| Planning and generation | **The main model** | Writing the subtasks; writing the reply |
| Deciding whether this input fits that description | **Jev** | "Does `request` fall under one of the listed topics?" |

A well-written Jev question leaves Jev only the last row. When a question fails, the usual cause is that work from one of the first three rows leaked into it.

## The two-second test

Before you ship a question, ask: *could a careful person answer this in about two seconds by looking at the state, with my definitions in hand?*

If they would need scratch paper, have to count something, have to imagine how the task will play out, or have to guess what you meant, the question still contains reasoning. Find which pillar it breaks and move that work out.

## The pillars

### 1. Give the definition, then ask

Never make Jev decide what a word means. Put the standard in the question: in structured `instructions`, or in the `criteria` rubric of each option. Then Jev compares instead of infers.

- Bad: `"Is this request in scope for the agent?"` Jev must first work out the agent's scope. That is a hidden inference step.
- Good: ``{"scope": ["billing questions", "refunds", "account access"], "question": "Does `request` ask for help with one of the topics in `scope`?"}``

In `JevAgent`, the definition should come from a named, validated setting on the capability (for example a `scope` description), not from `system_prompt`. A system prompt was written to instruct a generative model. It is not a definition of scope, and asking Jev to extract one from it adds an interpretation step.

### 2. Ask what is true now, not what will happen

Ask about properties the state already has. Do not ask for forecasts. A forecast forces Jev to simulate the future, which is reasoning.

- Bad: `"Will this task take many steps?"`, `"Is another iteration likely to improve the answer?"`
- Good: ``"Does `request` ask for changes to more than one file?"``, ``"Does `last_turn` add a finding beyond `earlier_findings`?"``

A forecast you need can almost always be rebuilt in code from two or three observations.

### 3. One judgment per question, combined in code

Each question gets exactly one property. If you catch yourself writing "and" or "or" between two conditions, split them. Code combines the answers.

- Bad: `"Is this a complex, multi-step task that needs research?"` (three judgments hidden in one).
- Good: three `noul` questions (`needs_tools`, `needs_outside_information`, `has_multiple_deliverables`) and a small function that maps the answers to an effort level.

Splitting also makes a wrong answer traceable: you can see which property Jev got wrong.

### 4. Write the exact condition, because Jev reads literally

Jev answers the question you wrote, not the one you meant. Scoping words ("primary", "any", "only"), implied conditions, and intent are read at face value. When you look at a wrong answer and catch yourself explaining what you really meant, that explanation is the missing part of the instruction. Add it.

- Bad: `"Is the user asking about billing?"` (a message that mentions a charge while asking about delivery may score yes).
- Good: ``{"question": "Is the main request in `message` about billing?", "focus": "Judge the one thing the user wants done, not every topic mentioned."}``

The question key (for example `is_billing`) is never shown to the model. All meaning must be in `instructions` and `criteria`.

### 5. Phrase positively, and keep instructions and criteria aligned

Avoid negations, double negatives, and "unless" clauses. Keep `true` meaning yes. A `noul` whose `true` criterion describes the "no" case, or a Choice whose instructions and rubric pull in different directions, lowers accuracy.

- Bad: `"Is the request not outside the agent's purpose unless it concerns billing?"`
- Good: ``"Does `request` ask for help with one of the topics in `scope`?"`` with `criteria.true = "Asks for help with a listed topic"` and `criteria.false = "Asks for help with something not listed"`.

Treat the criteria as a continuation of the instruction, written in the same direction.

### 6. Keep numbers, counts, and dates in code

Jev is not a calculator. It does not count reliably, does not compare numbers or dates reliably, and cannot turn a Score into an exact number by interpolating between levels. Compute the fact in code and put the result in the state, or turn the value into a named bucket.

- Bad: `"Does the request list more than three items?"`, `"Was this file changed after the deadline?"`
- Good: code computes `{"listed_items": 5}` or `{"changed_after_deadline": true}`. If the decision only depends on that fact, you do not need Jev at all.

Ask yourself first whether a regex, parser, or comparison can answer the question exactly. If so, it belongs in code.

### 7. Send only the state the question needs

Unrelated detail acts as a distractor and lowers accuracy. Filter and project in code before the call. Put a single user request in `request`, not the whole transcript. Put the last turn in `last_turn`, not every turn.

- Bad: the full conversation history, tool logs, and system prompt as one string.
- Good: `{"request": "...", "attached_files": ["billing.py", "refunds.py"]}`

Use a JSON object with descriptive field names for almost every state. A bare string is fine only when the state is one piece of text.

### 8. Point at the field by name

Refer to state fields in backticks (`` `request` ``, `` `last_turn` ``) so Jev does not have to find the relevant part itself. Avoid indirection: "a property of a property", or a question that needs two hops to reach the thing being judged.

- Bad: `"Does the thing the user wants match what the second attachment describes?"`
- Good: code puts the second attachment in `spec`. The question becomes ``"Does `request` ask for the behavior described in `spec`?"``

### 9. Anchor every option with what it covers, what it does not, and examples

For Choice options, Score levels, and `noul` criteria, a label alone is not a definition. Use a structured description with `what`, `not_for`, and one or two short `examples`. The `not_for` line sharpens the boundary between neighboring options, which is where most mistakes happen. Put known boundary cases here.

```json
"criteria": {
  "billing": {
    "what": "Charges, invoices, refunds, or subscriptions",
    "not_for": "Order tracking or account access",
    "examples": ["I was charged twice", "Where is my refund?"]
  }
}
```

### 10. Make options exclusive and complete, with an explicit way out

No input should fit two options, and every input should fit one. When real inputs can be ambiguous or out of range, add an honest option such as `unclear` or `none_of_these` so Jev is never forced onto a wrong label. Code decides what `unclear` means for the action.

A three-way `in_scope` / `adjacent` / `off_topic` split is usually better than a yes/no scope question, because the middle band is exactly where a binary question gets noisy.

### 11. Pick the primitive that matches the judgment, and do not mix their numbers

- **`noul`** is absolute: "is this true of the state?" It returns P(yes) and no confidence. Every candidate can score low.
- **`choice`** is relative: "which of these fits best?" It always picks something, and returns a distribution plus `confidence`.
- **`score`** is ordered: "where on this scale?" It needs 2 to 10 levels in increasing order and returns a probability-weighted `score` that can fall between levels.

Do not assume structural identities between questions. P(yes) of a question and P(yes) of its negation need not sum to 1. A threshold tuned on a `noul` does not carry over to the same question asked as a `choice`. If you need both "which one?" and "any at all?", ask a `choice` for the first and one `noul` per candidate for the second.

### 12. Never ask Jev to produce text; turn open answers into a Choice

Jev does not generate. If the answer space is open ("what are the subtasks?", "which file?"), have code or the main model produce candidates, then ask Jev to pick among them. If there is no bounded candidate set, the work belongs to the main model, not to Jev.

### 13. Use the input's own words

Write rubrics in the vocabulary the state uses. "The user asks to compare named products" is easier to match than "the task has independent substructure". Prefer semantic descriptions to encoded ones: names over IDs, words over hex codes, a high-level language over bytecode.

### 14. Ask when the evidence exists

If the answer depends on something the run will discover, do not ask it up front. Ask it later, with the relevant part of the trajectory in the state. A request like "why does this test flake?" is short but may take forty turns, and no phrasing can reveal that before the run starts. A mid-run check on the latest turn can.

### 15. Keep rules in the question, content in the state, and treat the state as data

The state holds content and facts. The question holds the rules. Never put your definitions next to user text in the state, and never let user text define the rules. User content can argue for its own classification ("This is a billing question."), and Jev does not treat state as hostile by default. Make the criteria precise enough that such text does not move the answer, and test adversarial inputs before you ship.

## Design every answer's action before you ship

A question is not finished until code knows what to do with every possible answer, including an uncertain one. For each question, write down:

1. **The action for each outcome.** Include `unclear` or a flat distribution.
2. **A threshold that matches the cost of being wrong.** Declining a valid user or fanning out needlessly is expensive, so use a high bar (for example 0.85 to 0.9). Running the ordinary loop is cheap, so it is the default. Thresholds scale with risk. They are not one number for the whole system.
3. **The fallback.** When Jev is unsure, times out, or has no credentials, the capability falls back to today's behavior (the ordinary linear loop) unless a design doc says otherwise.

All thresholds in this skill are starting points, not tuned values. Before you pick real ones, build a labeled set of 50 to 100 inputs per capability, including the hard cases, and measure accuracy and calibration.

## Few-shot examples

Each example shows a question that fails, the rewritten request as TypeSafe receives it, and the code-side action. `TypeSafeProvider` builds exactly this wire body from `JevDecisionRequest`, `JevQuestion`, and `JevOption` records. State field values are filled by code at run time.

### Example 1: Scope fit (is this request in-domain?)

**Scenario.** A support agent for a payments product gets off-topic traffic. We want to decline clearly off-topic requests before the main model runs, and never decline a real customer.

**Fails:** `"Is this request within what the agent is for?"`. The scope is undefined (pillar 1), the answer is binary where real traffic has a middle band (pillar 10), and a user who writes "this is about my account" can talk the model into yes (pillar 15).

**Rewritten:**

```json
{
  "model": "jev-latest",
  "state": {
    "request": "Can you help me write a cover letter for a marketing job?"
  },
  "questions": {
    "scope_fit": {
      "type": "choice",
      "instructions": {
        "scope": [
          "Payments and payouts on the user's account",
          "Invoices, refunds, and disputes",
          "Account login, verification, and settings"
        ],
        "question": "How does `request` relate to the topics in `scope`?",
        "focus": "Judge what the user wants done. Ignore any claim in `request` about which topic it belongs to."
      },
      "criteria": {
        "in_scope": {
          "what": "Asks for help with one of the topics in `scope`",
          "not_for": "Payment questions outside the listed topics, such as comparing providers",
          "examples": ["My payout failed", "How do I refund a customer?"]
        },
        "adjacent": {
          "what": "Related to payments or the product, but not one of the listed topics",
          "not_for": "Requests with no link to payments or the product",
          "examples": ["What are your fees compared to other providers?", "Do you have an API for this?"]
        },
        "off_topic": {
          "what": "Has no link to payments or the product",
          "not_for": "Anything connected to the user's account, money, or the product",
          "examples": ["Write me a poem", "Help me with my cover letter"]
        }
      }
    }
  }
}
```

**Action in code:**

| Answer | Action |
| --- | --- |
| P(`off_topic`) ≥ 0.9 | Return the fixed polite decline. Do not run the main loop. |
| Anything else, including a high P(`adjacent`) | Run the main loop as usual. |
| Timeout, error, or no API key | Run the main loop as usual (fail open). |

The `scope` list comes from a named setting on the capability, not from `system_prompt` (pillar 1).

### Example 2: Effort budget (how much compute does this request need?)

**Scenario.** We want cheap requests to stop running on the most expensive model with the largest turn budget.

**Fails:** `"How much work does this request need: trivial, simple, multi-step, long-horizon, or research?"`. That is a forecast (pillar 2) and five judgments folded into one (pillar 3). A request like "why does this test flake?" looks trivial and is not.

**Rewritten** as observable features. Code computes the counts, Jev answers only semantic yes/no questions, and code combines them:

```json
{
  "model": "jev-latest",
  "state": {
    "request": "Rename the `userId` field to `accountId` in billing.py and refunds.py, and update the tests.",
    "attached_files": ["billing.py", "refunds.py", "tests/test_billing.py"]
  },
  "questions": {
    "needs_tools": {
      "type": "noul",
      "instructions": "Does completing `request` require reading, running, or changing files or systems?",
      "criteria": {
        "true": {"what": "Needs files, commands, or live data", "examples": ["Fix the failing test", "What does billing.py do?"]},
        "false": {"what": "Answerable from general knowledge alone", "examples": ["What is a webhook?", "Explain idempotency keys"]}
      }
    },
    "needs_outside_information": {
      "type": "noul",
      "instructions": "Does `request` ask for information from outside the provided files, such as the web, current events, or third-party documentation?",
      "criteria": {
        "true": {"what": "Needs outside sources", "examples": ["Compare our fees to Stripe's current pricing"]},
        "false": {"what": "Everything needed is in `request` or `attached_files`"}
      }
    },
    "has_multiple_deliverables": {
      "type": "noul",
      "instructions": "Does `request` ask for more than one separate result, such as several changes, several documents, or a change plus tests?",
      "criteria": {
        "true": {"what": "Two or more separate results", "examples": ["Rename the field and update the tests"]},
        "false": {"what": "Exactly one result", "examples": ["Rename the field"]}
      }
    },
    "goal_is_open": {
      "type": "noul",
      "instructions": "Does `request` describe a problem to investigate rather than a specific change to make?",
      "criteria": {
        "true": {"what": "The cause or the fix is unknown", "examples": ["Why does this test fail sometimes?", "Find out why payouts are slow"]},
        "false": {"what": "The wanted change is stated", "examples": ["Rename the field", "Add a retry to the payout call"]}
      }
    }
  }
}
```

**Action in code:**

```python
YES = 0.5  # Starting point; tune on a labeled set.

def effort_level(answers: Mapping[str, JevAnswer], attached_files: int) -> EffortLevel:
    # Combines observable features into a level; Jev never sees the levels themselves.
    yes = {name: answer.noul >= YES for name, answer in answers.items()}
    if yes["goal_is_open"] or yes["needs_outside_information"]:
        return EffortLevel.LONG_HORIZON
    if yes["has_multiple_deliverables"] or attached_files > 2:
        return EffortLevel.MULTI_STEP
    if yes["needs_tools"]:
        return EffortLevel.SIMPLE
    return EffortLevel.TRIVIAL
```

When any `noul` sits between 0.35 and 0.65, pick the next level up. Code owns the level-to-budget table (max turns, model tier), and Example 4 raises the budget mid-run when the first estimate was too low.

### Example 3: Decomposition gate (should this fan out?)

**Scenario.** Fan-out to parallel workers only pays off when the task really splits into independent parts. A false yes multiplies cost. A false no just runs the normal loop.

**Fails:** `"Can this task be split into independent subtasks, and what are they?"`. Listing the subtasks is generation (pillar 12), and "can be split" asks Jev to plan the split in its head (pillar 2).

**Rewritten.** Jev only gates. The main model writes the split later and may still decide it is one task.

```json
{
  "model": "jev-latest",
  "state": {
    "request": "Compare the refund policies of Stripe, Adyen, PayPal, Square, and Braintree and tell me which is friendliest to merchants."
  },
  "questions": {
    "names_item_set": {
      "type": "noul",
      "instructions": "Does `request` name, or clearly point to, a set of items that each need the same kind of work?",
      "criteria": {
        "true": {"what": "A set of items, each handled the same way", "examples": ["Compare these five vendors", "Audit each of these ten files", "Summarize every open issue"]},
        "false": {"what": "One item, or one task with several different steps", "examples": ["Fix this bug", "Write a migration and then deploy it"]}
      }
    },
    "items_depend_on_each_other": {
      "type": "noul",
      "instructions": "Does doing the work for one item in `request` need the result of the work for another item?",
      "criteria": {
        "true": {"what": "One item's result is an input to another's", "examples": ["Rank the vendors, then write a contract for the winner"]},
        "false": {"what": "Each item can be handled on its own; results are only combined at the end", "examples": ["Compare these vendors' refund policies"]}
      }
    }
  }
}
```

**Action in code:**

| Answer | Action |
| --- | --- |
| `names_item_set` ≥ 0.85 **and** `items_depend_on_each_other` ≤ 0.2 | Take the fan-out path. The main model writes the subtasks and may return "one task". |
| Anything else | Keep the single linear loop. |

A final comparison ("which is friendliest?") does not make the items dependent. It is the combine step after the parallel work, and the `false` criterion says so explicitly (pillar 4).

### Example 4: Mid-run progress check (should the run keep its budget?)

**Scenario.** Replace the forecast `"Is another iteration likely to materially improve the answer?"` with an observation of what the last turn actually did.

**Fails:** that question is a forecast (pillar 2), and "materially" is undefined (pillar 1).

**Rewritten.** Code projects the state: the last turn's tool calls, the files it changed, and a short list of earlier findings. Code, not Jev, counts turns and files changed.

```json
{
  "model": "jev-latest",
  "state": {
    "earlier_findings": [
      "The flaky test is test_payout_retry.",
      "It fails only when two retries overlap."
    ],
    "last_turn": {
      "tool_calls": ["read_file payouts/retry.py", "run_tests tests/test_payouts.py"],
      "files_changed": [],
      "model_note": "Re-ran the tests. Same failure as before."
    }
  },
  "questions": {
    "last_turn_progress": {
      "type": "score",
      "instructions": {
        "question": "How much did `last_turn` add beyond `earlier_findings`?",
        "focus": "Judge new facts or changes, not effort. Re-running something with the same result adds nothing."
      },
      "criteria": [
        {"summary": "Nothing new", "signals": ["Repeats earlier work", "Same result as before", "No files changed"]},
        {"summary": "A small new fact", "signals": ["Narrows down an earlier finding", "Rules out one cause"]},
        {"summary": "A new finding or a real change", "signals": ["Finds a cause not in `earlier_findings`", "Changes code that addresses the problem"]}
      ]
    }
  }
}
```

**Action in code:** keep a run-local streak. If `score` < 0.5 for two turns in a row, stop and ask the user, or raise the budget one level if the effort level from Example 2 was the lowest one. Do not read `score` as an exact amount of progress. Only compare it to a threshold (pillar 6).

### Example 5: Routing to a handoff target

**Scenario.** A front agent routes requests to one of three registered specialists, or keeps them itself.

**Fails:** `"Which agent is best for this?"` with bare agent names as options. The names mean nothing to Jev (pillar 9), and there is no way out when no specialist fits (pillar 10).

**Rewritten** with each target's registered description as its rubric, plus a `keep` option:

```json
{
  "model": "jev-latest",
  "state": {
    "request": "My invoice shows a charge I don't recognize from last Tuesday."
  },
  "questions": {
    "route": {
      "type": "choice",
      "instructions": {
        "question": "Which handler matches the main thing `request` asks for?",
        "focus": "Pick the handler for what the user wants done, not for words that appear in the message."
      },
      "criteria": {
        "disputes_agent": {
          "what": "Unrecognized or wrong charges, chargebacks, and refund disputes",
          "not_for": "Questions about how pricing works",
          "examples": ["I don't recognize this charge", "I want to dispute a payment"]
        },
        "payouts_agent": {
          "what": "Money the user expected to receive that is late, missing, or failed",
          "not_for": "Charges to the user",
          "examples": ["My payout didn't arrive", "Why was my transfer held?"]
        },
        "account_agent": {
          "what": "Login, verification, and account settings",
          "not_for": "Money movement",
          "examples": ["I'm locked out", "Change my business address"]
        },
        "keep": {
          "what": "General questions that none of the specialists above cover",
          "examples": ["What are your support hours?"]
        }
      }
    }
  }
}
```

**Action in code:** hand off when the chosen target's probability is at least 0.7 and `confidence` is at least 0.5. Otherwise keep the request. When you also need to know whether *any* specialist fits at all, add one `noul` per target and read those separately (pillar 11).

## Quick rewrites

| Instead of | Ask | Pillar |
| --- | --- | --- |
| "Is this in scope?" | "Does `request` ask for help with one of the topics in `scope`?" | 1 |
| "Will this take long?" | "Does `request` describe a problem to investigate rather than a change to make?" | 2 |
| "Is this complex and does it need research?" | Two `noul`s: `needs_outside_information`, `has_multiple_deliverables` | 3 |
| "Is the user asking about billing?" | "Is the *main* request in `message` about billing?" plus a `focus` line | 4 |
| "Is this not unrelated?" | "Is `request` related to one of the topics in `scope`?" | 5 |
| "Are there more than three items?" | Count in code; pass `listed_items: 5` | 6 |
| Whole transcript as state | `{"request": ..., "attached_files": ...}` | 7 |
| "Does it match the second attachment?" | Code puts it in `spec`; ask about `` `spec` `` | 8 |
| Options `["billing", "orders"]` with no rubric | Each option with `what`, `not_for`, `examples` | 9 |
| Yes/no scope gate | `in_scope` / `adjacent` / `off_topic` | 10 |
| Reusing a `noul` threshold on a `choice` | Tune each question type separately | 11 |
| "What are the subtasks?" | Main model writes them; Jev only gates | 12 |
| "Does it have independent substructure?" | "Does it name a set of items that each need the same work?" | 13 |
| "Will another turn help?" | Mid-run: "How much did `last_turn` add beyond `earlier_findings`?" | 14 |
| Definitions pasted into the state beside user text | Definitions in `instructions`; user text in its own state field | 15 |

## Checklist before you ship a question

- [ ] It passes the two-second test.
- [ ] Every term it depends on is defined in `instructions` or `criteria` (1).
- [ ] It asks about the present state, not the future (2, 14).
- [ ] It holds exactly one judgment (3).
- [ ] It says exactly what it means, with no negation, and `true` means yes (4, 5).
- [ ] No counting, arithmetic, or date comparison is left for Jev (6).
- [ ] The state holds only the fields it needs, and the question names them in backticks (7, 8).
- [ ] Every option has `what`, and neighbors have `not_for` and examples (9).
- [ ] The options are exclusive and complete, with an `unclear` or `none` option where inputs can be ambiguous (10).
- [ ] The question type fits the judgment, and its thresholds were tuned for that type (11).
- [ ] Jev picks among candidates; it never produces them (12).
- [ ] User content cannot redefine the rules (15).
- [ ] Code has an action for every outcome, including uncertainty, and the fallback is today's behavior.
- [ ] Thresholds were checked against a labeled set, not guessed.

## Sources

- TypeSafe API reference: https://docs.typesafe.ai/api.md
- Structured instructions and criteria: https://docs.typesafe.ai/primitives/advanced.md
- Known failure modes of `jev-1.13`: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
- Confidence and risk-scaled thresholds: https://docs.typesafe.ai/confidence.md
- State: https://docs.typesafe.ai/concepts/state.md
