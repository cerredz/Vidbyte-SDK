# Import Prompt

Access the SDK's built-in prompt catalog.

## Getting a Prompt by Enum

```python
from vidbyte import Prompts, Prompt

prompts = Prompts()

# Get a single prompt string
text = prompts.get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)
text = prompts.get(Prompt.STEP_BACK_REASON_PROMPT)
```

## Direct String Imports

Every prompt is also importable as a module-level constant.

```python
from vidbyte.prompts import (
    chain_of_thought_reason_prompt,
    chain_of_thought_system_prompt,
    step_back_reason_prompt,
    skeleton_of_thought_reason_prompt,
    chain_of_draft_reason_prompt,
    tree_of_thoughts_reason_prompt,
    plan_and_execute_planning_prompt,
    self_consistency_reason_prompt,
)

system_prompt = chain_of_thought_system_prompt
```

## Listing All Prompts

```python
from vidbyte import Prompts

prompts = Prompts()

# All enum keys
prompts.keys()            # tuple[Prompt, ...]

# All prompt text keyed by enum
all_text = prompts.all()  # dict[Prompt, str]

# All descriptions
prompts.descriptions()    # dict[Prompt, str]

# Generated import names
prompts.import_names()    # dict[Prompt, str]
```

## Getting a Prompt Family

```python
from vidbyte import Prompts

# Get all prompts within a family
family = Prompts().family("chain_of_thought")
# {"reason_prompt": "...", "system_prompt": "..."}
```

## Available Prompt Families

| Family | Description |
|--------|-------------|
| `agentic_rag` | Agentic RAG prompts |
| `answer_convergence` | Answer convergence sampling |
| `budget_forcing` | Budget-forced retry prompts |
| `chain_of_draft` | Chain of draft reasoning |
| `chain_of_thought` | Chain of thought reasoning |
| `context_engineering` | Context engineering |
| `expert_prompting` | Expert prompting patterns |
| `multi_agent_reflexion` | Multi-agent reflexion |
| `paradigm_router` | Paradigm routing |
| `plan_and_execute` | Plan and execute |
| `self_consistency` | Self-consistency sampling |
| `skeleton_of_thought` | Skeleton of thought |
| `step_back` | Step-back prompting |
| `tree_of_thoughts` | Tree of thoughts |
| `vmao` | Verified multi-agent orchestration |

## Using Prompts with Agents

```python
from vidbyte import Agent, Prompts, Prompt

prompts = Prompts()

agent = Agent(
    name="reasoner",
    system_prompt=prompts.get(Prompt.CHAIN_OF_THOUGHT_SYSTEM_PROMPT),
    provider="openai",
    model_name="gpt-4.1",
)

reply = await agent.arun(prompts.get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT))
```

## Prompt Enum Naming

- Value format: `"<family_key>.<prompt_key>"`
- Enum member: `UPPERCASE_SNAKE` of the value with dots replaced by underscores
- Example: `chain_of_thought.reason_prompt` -> `Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT`
