# Design Doc: Minimum Content Length for Jev Questions

**Status:** Draft  
**Author:** OpenCode  
**Created:** 2026-09-26  
**Last Updated:** 2026-09-26

## 1. Overview

Update the `asking-jev-questions` skill with a minimum-length criterion for a complete fixed Jev question: the combined text Jev receives in the instructions and both answer criteria must contain at least 2,000 tokens. Explain that the floor applies to the meaningful, rendered prompt content rather than Python syntax, and add one complete `JevPreflightQuestion` example whose string fields each use one standalone literal.

## 2. Goals & Non-Goals

### Goals
- Add a checkable 2,000-token minimum for the full instructions/answers combination.
- Explain why a complete, sufficiently detailed question needs this space in one paragraph at the end of the skill.
- Add a whole dataclass example showing the brief, both criteria, gap, and question key, with each string value written as one literal rather than adjacent concatenated literals.

### Non-Goals
- Change SDK runtime behavior, Jev dataclasses, lint rules, or the question schema.
- Require each individual section or field to independently reach 2,000 tokens.
- Add a tokenizer dependency or automated token-count validation.
- Rewrite or remove existing guidance and examples.

## 3. Background & Context

The repository-level `skills/asking-jev-questions/SKILL.md` is the authoring guide for Jev questions. It documents `JevBrief(introduction, state, definitions, rules, question)` and `JevCriterion(what, not_for, easy, boundary)`. Concrete questions subclass `JevPreflightQuestion` and provide an instructions brief, true and false criteria, and a gap. Existing field-guide guidance reinforces the structured layout, complete criteria, and one literal per string. The requested threshold is a documentation criterion for the complete prompt combination; it does not alter the SDK's serialized contract.

## 4. Requirements

### Functional Requirements
1. The skill must state that a complete question's combined instructions, true criterion, and false criterion content is at least 2,000 tokens.
2. The skill must clarify that counting applies to the text sent to Jev after rendering, not code identifiers, punctuation, whitespace, or dataclass source syntax; count with the tokenizer for the configured Jev model when available, otherwise use a consistent tokenizer estimate and exceed the floor rather than target it exactly.
3. The rule must not imply that each field individually needs 2,000 tokens, or that filler/repetition satisfies the criterion; the content must remain relevant, complete, and useful for recognition.
4. Add a paragraph at the end that explains the minimum's purpose and how to apply it.
5. Add one complete example of a `JevPreflightQuestion` subclass. It must include the structured brief, both structured answer criteria, the gap, and a key.
6. Every string in the example must be represented by exactly one string literal; do not split content into adjacent literals or use concatenation.
7. Retain every existing section of the skill and follow its existing guidance on definitions, rules, mirrored criteria, examples, gaps, and one judgment per question.

### Non-Functional Requirements
- Keep the addition readable and directly actionable for future agents.
- Do not add runtime dependencies or change public APIs.
- Preserve compatibility with the existing S062 single-literal convention.
- Verification: inspect the diff and run `python -m pip install -e ".[dev]"`, `python lint/run.py --rule S062`, then `python scripts/run_ci.py` as the complete required local gate.

## 5. High-Level Design

Modify only the Jev question-authoring skill and append a final explanatory paragraph plus a complete illustrative fixed-question dataclass. Place the length criterion in the existing “Writing a full question” guidance and add it to the checklist so authors encounter it as both a rule and a ship check. The example will show all `JevPreflightQuestion` fields, with sufficient relevant definition/rule/criterion content to demonstrate the minimum, and each field value will be one string literal.

No runtime path changes: source authors write and render the structured brief, and Jev receives the existing rendered instructions and answer option descriptions. The new guidance defines the combined count across that actual prompt content, rather than counting the serialized Python object or asking for 2,000 tokens per field.

## 6. Detailed Design

### 6.1 Skill length criterion

**File(s):** `skills/asking-jev-questions/SKILL.md`  
**Type:** Modified

#### What it does
Specifies that the combined rendered instructions and both answer-side criteria for one fixed Jev question must be at least 2,000 tokens. The text must be substantive; the target is completeness, not padding.

#### Interface / API
N/A - this is authoring guidance only; no SDK interface changes.

#### Logic / Algorithm
1. Render the brief using the existing `JevBrief.render()` shape.
2. Include the text in both `JevCriterion` values, including `what`, `not_for`, and labeled examples.
3. Count the combined model-facing text with the configured Jev model tokenizer where available.
4. Revise concise or incomplete content with relevant definitions, decision rules, boundaries, and examples until it reaches at least 2,000 tokens; do not duplicate wording or add irrelevant material to reach the number.

#### Edge Cases & Error Handling
- Do not count Python identifiers, field names, formatting syntax, or code fences as prompt content.
- If the exact tokenizer is unavailable during authoring, use a consistent tokenizer estimate and provide margin above 2,000 tokens.
- The requirement is one combined minimum, not a per-field minimum; each component must still satisfy its own layout and quality requirements.

### 6.2 Complete example

**File(s):** `skills/asking-jev-questions/SKILL.md`  
**Type:** Modified

#### What it does
Demonstrates one complete dataclass subclass that passes the full question layout, includes instructions and both answer criteria, and represents every string as a single literal.

#### Interface / API
Use the existing `JevPreflightQuestion`, `JevBrief`, `JevCriterion`, and question-key contracts; no new symbols or external APIs.

#### Logic / Algorithm
1. Choose a single observable question and keep it to one judgment.
2. Define the state and all terms before using them in rules.
3. Include all decision rules in the brief and mirrored evidence in the two criteria.
4. Make the total model-facing content at least 2,000 tokens.
5. Keep each string as one literal; tuples may contain multiple independent one-literal examples.

#### Edge Cases & Error Handling
- Avoid adjacent literal concatenation, even where a long string would be easier to wrap.
- Keep the `gap` standalone because its reader does not receive the brief.
- Use enough relevant detail to meet the floor without contradicting the single-judgment requirement.

## 7. Data Model Changes

N/A - no data model changes; the example uses existing dataclasses only.

## 8. API Changes

N/A - no API, endpoint, or public SDK behavior changes.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `skills/asking-jev-questions/SKILL.md` | Add the combined 2,000-token criterion, checklist entry, final explanatory paragraph, and full one-literal-per-string example. |

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Jev model tokenizer | Configured Jev model version, when available | Estimate the combined model-facing token count | Exact tokenization can vary with model version; guidance calls for a consistent estimate with margin when unavailable. |
| Existing SDK Jev dataclasses | Current repository definitions | Ensure the example matches the existing question contract | Low; the example is documentation and will be reviewed against current definitions. |

## 11. Rollout & Deployment

- No feature flag or migration is needed; this is a source skill update.
- This is not a runtime or API breaking change.
- Rollback is reverting the skill-file modification.
- The normal SDK CI workflow remains applicable, including source and package verification.

## 12. Open Questions

- [ ] The user requested a 2,000-token floor but did not identify a specific tokenizer. Use the configured Jev model tokenizer when known and otherwise an estimate with margin.

## 13. Alternatives Considered

### Alternative 1: Require 2,000 tokens per field
- What: Apply the floor independently to `instructions`, `when_true`, and `when_false`.
- Why rejected: The request describes the full instructions/questions/answers combination, so the total question payload is the relevant unit.

### Alternative 2: Add a tokenizer tool or CI check
- What: Add a new dependency or validation step to count every question automatically.
- Why rejected: The requested change is to the skill guidance, and tokenizer-specific enforcement would expand scope and introduce a dependency/API decision.

### Alternative 3: Add length without a complete example
- What: Add only a checklist sentence.
- Why rejected: The request explicitly asks for an entire example and single-literal string values.
