# Description
The function is the agent's atomic unit of comprehension, naming, change, test, and reuse. A 200-line function blows past all five at once: it overflows a single read, cannot carry an honest name, localizes nothing, provides no clean test contract, and forces copy-paste reuse instead of recombination. The rule is not aesthetic. Each property below is a concrete reliability gain for an agent operating under limited context. The core pattern is to extract functions until every function does exactly one thing at one level of abstraction, and then to make that constraint enforceable by the linter so violations become loop feedback rather than style advice.

# Intent
The intent of function design for agent readability is to make every callable a clean interface that compresses behavior into a name, a signature, and a small body an agent can verify in one pass. Agents do not fail only because code is wrong; they fail because the unit they need to understand is too large, too entangled, or too implicit to fit cleanly into the current reasoning window.

This principle is trying to make codebases easier for agents to edit without accidentally breaking hidden mid-body invariants. Small single-purpose functions create stable seams for navigation, testing, and reuse. They let the agent read an orchestrator for the story, open one leaf for the local change, and rely on types and tests to catch contract violations.

# Why Short Single-Purpose Functions Are Agent-Native
* Fits in one read: 20-30 lines load, get understood, and get verified in a single pass. The long-function failure is exactly the agent's worst one: it edits part of a 200-line body without holding the whole, fixes line 40, and breaks an invariant at line 160 it never loaded.
* Enables an honest name: one thing means one name with no "and." That name becomes a comprehension cache at the call site. The agent reads the call graph as documentation and never opens the body unless the body is relevant.
* Bounds the blast radius: small single-purpose functions localize edits so the agent can predict what a change affects before making it.
* Gives a clean test: one thing produces one testable contract and one sharp signal in the feedback loop.
* Is a reuse primitive, not a copy template: small orthogonal functions are primitives the agent recombines; large functions force copy-paste-mutate.
* Erases hidden mid-body invariants: a long body accrues implicit local state that the agent must track to edit safely and routinely does not.

# Making One Thing Operational
One thing is famously fuzzy. Apply these four tests before accepting that a function does one thing. If any test fails, split the function at the failing boundary.

* The honest-name test: if you cannot name the function without "and," "or," or "then," it is two functions.
* Single level of abstraction: every statement in the body sits at the same conceptual altitude. Mixing high-level orchestration with low-level byte handling in one body means more than one thing.
* Single reason to change: if two different kinds of requirement change would both force an edit here, the function is doing two jobs.
* One-sentence summary with no conjunction: if the honest description of the function needs a conjunction, split the function at that conjunction.

# Function-Design Practices
* Extract-till-you-drop, and turn the comment into the name: the comment you were about to write above a block becomes the extracted function's name.
* Orchestrator / leaf split: public functions orchestrate and read like a table of contents, while private leaf functions do the work.
* Command / query separation: a function either does something or returns something, never both.
* Kill flag arguments: a boolean or string mode that switches between behaviors is two functions. Split them so the call site names which behavior it wants.
* Cap arguments and group into typed objects: wide argument lists are where agents transpose and guess. Limit positional arguments to three. Beyond three, group into a typed parameter object.
* Pure core, imperative shell: push side effects to the edges and keep the middle pure.

# Enforcement
* Put line count, nesting depth, cyclomatic complexity, and argument count caps in the linter. Line count is only a proxy; the real enemy is branching state that the agent must hold.
* In the lint loop, these caps become feedback the agent meets automatically rather than prose it skims and ignores.
* Suggested baselines: 30 lines per function body, nesting depth 3, cyclomatic complexity 10, and 3 positional arguments before a typed object is required.

# Things Not to Do
* Do not use boolean or string flag arguments to switch between two behaviors inside one function.
* Do not write a function that both changes state and returns a meaningful value.
* Do not leave explanatory comments above blocks of code inside function bodies. The comment that explains what the next block does is the name of the function you should extract.
* Do not accept a wide argument list as the interface for a complex operation.
* Do not enforce function decomposition only via code review comments. Linter caps enforce the same rule on every future change automatically.

# Checklist
* Before writing a function, decide what its one job is and name it without "and," "or," or "then."
* After writing a function body, apply the four one-thing tests: honest-name, single level of abstraction, single reason to change, and one-sentence summary with no conjunction.
* When you feel the urge to write a comment above a block of code inside a function, stop and extract the block into a function whose name is the comment.
* After writing a non-trivial public function, check whether it is actually an orchestrator that should delegate to named private leaf functions.
* Before writing a function with a boolean or string flag argument, split it into explicitly named functions.
* After writing a function that takes more than three positional arguments, group the excess into a typed parameter object.
* After completing a module, configure the linter with caps for function line count, nesting depth, cyclomatic complexity, and positional argument count.
* When a linter cap violation appears during implementation, treat it as a design signal, not a stylistic inconvenience.
* Before opening a pull request, scan every new or modified function for hidden mid-body invariants.

# Few-Shot Examples

## Example 1: Split an Orchestrator from Leaves

```python
# Before: one function validates, formats, writes, and notifies.
def publish_invoice(invoice, user, db, emailer):
    if not invoice.total_cents:
        raise ValueError("missing total")
    subject = f"Invoice {invoice.id}"
    body = f"You owe {invoice.total_cents / 100:.2f}"
    db.invoices.insert(invoice.to_record())
    emailer.send(user.email, subject, body)
```

```python
# After: the public function tells the story, and each leaf owns one job.
def publish_invoice(invoice: Invoice, user: User, services: InvoiceServices) -> None:
    validate_invoice(invoice)
    record = build_invoice_record(invoice)
    message = build_invoice_email(invoice, user)
    save_invoice(record, services.db)
    send_invoice_email(message, services.emailer)
```

The clean interface is `publish_invoice(invoice, user, services) -> None`: one command, no meaningful return value, and each step is named at the call site. An agent can change email formatting by opening `build_invoice_email` without loading database behavior.

## Example 2: Replace a Flag Argument with Named Functions

```python
# Before: the caller must know what final=True changes.
def render_invoice(invoice, final=False):
    watermark = "" if final else "DRAFT"
    return render_template(invoice, watermark=watermark)
```

```python
# After: the call site names intent directly.
def render_draft_invoice(invoice: Invoice) -> str:
    return render_invoice_with_watermark(invoice, watermark="DRAFT")


def render_final_invoice(invoice: Invoice) -> str:
    return render_invoice_with_watermark(invoice, watermark="")
```

The clean interfaces are `render_draft_invoice(invoice)` and `render_final_invoice(invoice)`. They remove mode guessing and make grep-based navigation reliable.

## Example 3: Group Wide Arguments into a Typed Object

```python
# Before: agents can transpose positional arguments.
def create_agent(name, provider, model, system_prompt, tools, max_iterations):
    return Agent(
        name=name,
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        max_iterations=max_iterations,
    )
```

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentConfig:
    name: str
    provider: str
    model: str
    system_prompt: str
    tools: tuple[Tool, ...]
    max_iterations: int


def create_agent(config: AgentConfig) -> Agent:
    return Agent(
        name=config.name,
        provider=config.provider,
        model=config.model,
        system_prompt=config.system_prompt,
        tools=config.tools,
        max_iterations=config.max_iterations,
    )
```

The clean interface is `create_agent(config) -> Agent`: the shape has a name, the call site is self-documenting, and type checking can catch missing or transposed fields.

## Example 4: Keep a Pure Core Inside an Imperative Shell

```python
def summarize_and_store(events: list[Event], store: Store) -> Summary:
    summary = build_summary(events)
    store.save(summary)
    return summary
```

```python
def build_summary(events: list[Event]) -> Summary:
    return Summary(total=len(events), failures=count_failures(events))


def store_summary(summary: Summary, store: Store) -> None:
    store.save(summary)
```

The clean core is `build_summary(events) -> Summary`: deterministic, testable, and reusable without a store. The side effect is isolated in `store_summary(summary, store) -> None`, so agents can reason about persistence separately from computation.
