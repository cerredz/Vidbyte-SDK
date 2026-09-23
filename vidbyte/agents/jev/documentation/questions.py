"""FILE: vidbyte/agents/jev/documentation/questions.py

PURPOSE: Defines the fixed Noul questions JevDocumentation asks to decide whether a request needs outside documentation, and the threshold that turns their answers into one boolean.
ROLE IN CODEBASE: agent.py sends DOCUMENTATION_QUESTIONS in one Jev request over the state {"request": ...} and compares the highest P(true) with DOCUMENTATION_THRESHOLD.
ARCHITECTURE NOTE: Every question recognizes one visible sign that the work depends on an outside interface, so none of them needs Jev to know a library's name. Each is built from the same five parts (definition, markers, boundary, focus, question) and one true/false rubric, following skills/asking-jev-questions/SKILL.md.
COMMON MODIFICATION PATTERNS: Add one _DocumentationText entry; keep `true` meaning "needs documentation", because the answers are combined by taking the highest P(true).
KNOWN EDGE CASES: The signs are independent, so a single strong answer must decide; averaging would bury a pasted third-party stack trace under nine weak answers. The threshold is an untuned starting point.
RELATED DOCS: docs/design/jev-documentation.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_documentation.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.constants.jev import JEV_NOUL_FALSE, JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevOption, JevQuestion
from vidbyte.lib.enums import JevQuestionType

DOCUMENTATION_QUESTION_PREFIX = "documentation"
DOCUMENTATION_STATE_FIELD = "request"
# The highest P(true) across the questions must reach this for the request to need documentation.
DOCUMENTATION_THRESHOLD = 0.7


@dataclass(frozen=True, slots=True)
class _DocumentationText:
    """The five instruction parts and the true/false rubric of one documentation question."""

    key: str
    definition: str
    markers: str
    boundary: str
    focus: str
    question: str
    true_examples: tuple[str, str]
    false_examples: tuple[str, str]

    def to_jev_question(self) -> JevQuestion:
        # @intent one-shape-for-every-documentation-question
        # Joining fixed parts in a fixed order keeps every question definition-first and question-last.
        instructions = " ".join((self.definition, self.markers, self.boundary, self.focus, self.question))
        return JevQuestion(
            name=f"{DOCUMENTATION_QUESTION_PREFIX}.{self.key}",
            question_type=JevQuestionType.NOUL,
            instructions=instructions,
            options=(
                JevOption(name=JEV_NOUL_TRUE, description={"what": "The work needs documentation for an outside interface.", "examples": list(self.true_examples)}),
                JevOption(name=JEV_NOUL_FALSE, description={"what": "The work does not show this sign.", "examples": list(self.false_examples)}),
            ),
        )


_TEXTS = (
    _DocumentationText(
        key="outside_interface",
        definition="An outside interface is a library, SDK, API, command-line tool, framework, or hosted platform that someone other than the user builds and documents, and whose exact names, options, and behavior the work must get right.",
        markers="Calling a payment or email API, importing a package, configuring a cloud service, writing a query for a hosted database, building on a web framework, and fixing an error raised inside someone else's module all rely on an outside interface.",
        boundary="Work that uses only the user's own code, a language's core syntax, or general ideas does not rely on one, and neither does a request that only mentions a product, such as comparing two vendors or asking what a tool is for.",
        focus="Judge what the work would have to call, configure, or fix, even if you do not recognize the names involved.",
        question="Does the work in `request` rely on an outside interface?",
        true_examples=("Send a welcome email through Resend when a user signs up.", "Why does my FastAPI dependency run twice?"),
        false_examples=("Explain how binary search works.", "Should we use Postgres or MongoDB?"),
    ),
    _DocumentationText(
        key="outside_error",
        definition="An outside error is an error message, stack trace, warning, or failed response produced inside code or a service the user did not write.",
        markers="Stack frames under site-packages or node_modules, exception names that carry a package's name such as `stripe.error.CardError` or `PrismaClientKnownRequestError`, error codes returned by an API, and warnings printed by a build tool are outside errors.",
        boundary="An error that the user's own code raises for the user's own reasons, such as a failed assertion in their test, is not an outside error.",
        focus="Judge only error text that appears in `request`, and ignore the user's guess about the cause.",
        question="Does `request` contain an error, warning, or failed response produced by code or a service the user did not write?",
        true_examples=("ModuleNotFoundError: No module named 'langchain.chat_models'", "403 Resource not accessible by integration"),
        false_examples=("My test fails: expected 4, got 5.", "AssertionError in test_totals"),
    ),
    _DocumentationText(
        key="package_code",
        definition="Package code is code that imports, installs, or calls a package, SDK, or framework, such as import lines, require calls, install commands, or method calls on a client object that a package provides.",
        markers="`from openai import OpenAI`, `import { createClient } from '@supabase/supabase-js'`, `pip install polars`, and `client.messages.create(...)` are package code.",
        boundary="Code that uses only the language's core syntax and the user's own functions is not package code, and neither is pseudocode that names no real package.",
        focus="Judge the code and commands that appear in `request`, including short snippets inside sentences.",
        question="Does `request` contain code or commands that import, install, or call a package, SDK, or framework?",
        true_examples=("Why does `pd.merge(a, b, on='id')` duplicate rows?", "`npm i zod` then how do I validate this?"),
        false_examples=("Here's my loop: `for i in range(n): total += i`", "Write pseudocode for a queue."),
    ),
    _DocumentationText(
        key="tool_config",
        definition="A tool configuration is a file or block of settings whose keys are defined by an outside tool or platform rather than by the user.",
        markers="GitHub Actions workflows, Dockerfiles and compose files, Kubernetes manifests, Terraform resources, `tsconfig.json`, ESLint configs, `vercel.json`, and the tool sections of `pyproject.toml` are tool configurations.",
        boundary="A settings file whose keys the user invented for their own program is not a tool configuration.",
        focus="Judge whether the work reads, writes, or fixes such a configuration, even when the tool's name is not stated.",
        question="Does the work in `request` involve a configuration whose keys are defined by an outside tool or platform?",
        true_examples=("Add a matrix build for Python 3.11 and 3.12 to our CI.", "My Dockerfile rebuilds every layer."),
        false_examples=("Add a `theme` field to our app's settings JSON.", "Rename the keys in my config dict."),
    ),
    _DocumentationText(
        key="cli_command",
        definition="An outside command is a command-line invocation of a tool the user did not write, together with its subcommands and flags.",
        markers="`kubectl rollout restart`, `npx prisma migrate dev`, `ffmpeg -vf scale=...`, `gcloud run deploy --region`, and `git rebase --onto` are outside commands.",
        boundary="Running the user's own script, such as `python main.py`, or basic shell navigation such as `cd` and `ls`, is not an outside command.",
        focus="Judge both the commands shown in `request` and the commands the work would have to write.",
        question="Does the work in `request` need an outside command-line tool's subcommands or flags?",
        true_examples=("Trim the first 10 seconds off this video with ffmpeg.", "How do I roll back a Helm release?"),
        false_examples=("Run my script with a different input file.", "How do I list files in a folder?"),
    ),
    _DocumentationText(
        key="api_request",
        definition="An API request is a call to a web service's endpoint: a URL path, an HTTP method, headers, a request body, or the response the service returns, including webhooks the service sends.",
        markers="`POST /v1/checkout/sessions`, a curl command with an `Authorization: Bearer` header, a JSON body with vendor-named fields, a GraphQL query against a hosted API, and a webhook event such as `invoice.paid` are API requests.",
        boundary="Endpoints that the user's own server defines, when the work calls no outside service, are not outside API requests.",
        focus="Judge both what `request` shows and what the work would have to send or receive.",
        question="Does the work in `request` send requests to, or handle responses or webhooks from, a web service that someone else runs?",
        true_examples=("Handle the `customer.subscription.deleted` webhook.", "Paginate through the GitHub issues endpoint."),
        false_examples=("Add a `/health` route to our Express server.", "Return 404 from my own endpoint when the user is missing."),
    ),
    _DocumentationText(
        key="integration",
        definition="Integration work connects the user's system to an outside service so that the two exchange data or actions: setting it up, authenticating with it, deploying to it, or wiring its events into the user's code.",
        markers="Adding Google sign-in, sending texts through Twilio, deploying to Vercel, syncing orders to Shopify, storing files in S3, adding Sentry, and posting to Slack are integration work.",
        boundary="Work inside the user's own system that touches no outside service, such as refactoring a function or renaming a column, is not integration work.",
        focus='Judge the work being asked for, even when the service is described rather than named, such as "our payment provider".',
        question="Does `request` ask to connect, authenticate, deploy, or send data to an outside service?",
        true_examples=("Let users log in with GitHub.", "Push new signups into our CRM."),
        false_examples=("Split this component into two files.", "Speed up this SQL query."),
    ),
    _DocumentationText(
        key="version_change",
        definition="A request depends on a version change when it refers to a new, changed, removed, or specific version of an outside tool, or to moving from one tool to its replacement.",
        markers='Phrases such as "the new App Router", "after upgrading to v2", "the latest SDK", "this is deprecated", "migrate from Webpack to Vite", and pinned version numbers point to a version change.',
        boundary="A request that uses long-stable parts of a tool and names no version or change does not depend on one.",
        focus="Judge only what `request` says, and do not use your own knowledge of when anything was released.",
        question="Does `request` refer to a new, changed, removed, or specific version of an outside tool?",
        true_examples=("Upgrade us from pydantic 1 to 2.", "This says `datetime.utcnow` is deprecated."),
        false_examples=("Add a loading spinner.", "Write a function that parses dates."),
    ),
    _DocumentationText(
        key="exact_name",
        definition="An exact-name question asks for the precise name, spelling, or shape of something an outside tool defines: a function, method, parameter, option, flag, setting key, event name, environment variable, or error code.",
        markers='"What\'s the flag to skip tests in Maven?", "Which parameter sets the timeout in httpx?", and "What env var does the AWS SDK read for the region?" are exact-name questions.',
        boundary='Questions about ideas, trade-offs, or approaches, such as "how should I structure retries?", do not ask for an exact name.',
        focus="Judge what the answer must contain, not how technical the request sounds.",
        question="Does `request` ask for the exact name or shape of something an outside tool defines?",
        true_examples=("What's the option to make Prettier use single quotes?", "What event fires when a Stripe payment fails?"),
        false_examples=("Is it better to retry with backoff or a queue?", "What does idempotent mean?"),
    ),
    _DocumentationText(
        key="vendor_fact",
        definition="A vendor fact is a fact about an outside product that only its maker's documentation states with authority: limits, quotas, rate limits, pricing tiers, supported regions, formats or languages, required permissions or scopes, and whether a feature exists.",
        markers='"What is the max upload size for the Gemini Files API?", "Does Supabase support branching on the free plan?", and "Which OAuth scopes do I need to read Gmail labels?" depend on vendor facts.',
        boundary="Settled, widely known facts, such as how HTTP status codes work or what JSON is, are not vendor facts.",
        focus="Judge the fact the answer depends on, not whether the user sounds sure of it.",
        question="Does the answer to `request` depend on a fact that an outside product's maker documents?",
        true_examples=("How many requests per minute does the Notion API allow?", "Can Vercel cron jobs run every minute?"),
        false_examples=("What does a 429 status mean?", "What's the difference between TCP and UDP?"),
    ),
)

DOCUMENTATION_QUESTIONS: tuple[JevQuestion, ...] = tuple(text.to_jev_question() for text in _TEXTS)


__all__ = [
    "DOCUMENTATION_QUESTIONS",
    "DOCUMENTATION_QUESTION_PREFIX",
    "DOCUMENTATION_STATE_FIELD",
    "DOCUMENTATION_THRESHOLD",
]
