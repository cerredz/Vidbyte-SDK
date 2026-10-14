# Research: tools for LLM agents, and which fit as small, local, prebuilt Python tools

Stage: S0 research scout. Date: 2026-10-14. Scope: survey of tool-use research and vendor practice from 2023 to October 2026, plus evidence on what LLMs get wrong without tools. The output is a candidate catalogue of **461 candidates in 30 categories** for the S1 spec author to cut to 250 or more. Source numbers in square brackets refer to the Sources list.

Every candidate in section 4 is meant to be pure Python standard library (3.10+, with version notes), JSON-friendly in and out, with no network, no filesystem writes, no subprocesses, and no unseeded randomness. One tool, `current_datetime_in_timezone`, is flagged as time-dependent. `toml_to_json` needs Python 3.11 or later, and `query_records_with_sql` uses the in-memory `sqlite3` stdlib module; both are flagged.

## Sources

Every source below was opened during this run. The finding listed is the one this document uses.

1. **Toolformer: Language Models Can Teach Themselves to Use Tools.** Schick et al., Meta AI, 2023. https://arxiv.org/abs/2302.04761. The canonical tool set was a calculator, a calendar, QA, search, and translation. LMs "struggle with basic functionality, such as arithmetic or factual lookup, where much simpler and smaller models excel."
2. **PAL: Program-aided Language Models.** Gao et al., CMU, 2022–2023. https://arxiv.org/abs/2211.10435. Offloading the computation to a Python interpreter, while the LLM only decomposes the problem, beats chain-of-thought by 15 points top-1 on GSM8K (Codex vs PaLM-540B).
3. **Gorilla: Large Language Model Connected with Massive APIs.** Patil, Zhang, Wang, Gonzalez, UC Berkeley, 2023. https://arxiv.org/abs/2305.15334. Even GPT-4 often produces inaccurate API arguments and hallucinates API usage.
4. **CRAFT: Customizing LLMs by Creating and Retrieving from Specialized Toolsets.** Yuan et al., ICLR 2024. https://arxiv.org/abs/2309.17428. Builds reusable, validated, deduplicated code tools per domain and retrieves from those toolsets at inference. Substantial gains on tabular, math, and vision-language tasks.
5. **Executable Code Actions Elicit Better LLM Agents (CodeAct).** Wang et al., ICML 2024. https://arxiv.org/abs/2402.01030. Code as the action format gives up to 20% higher success than JSON or text tool calls across 17 LLMs.
6. **SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering.** Yang et al., Princeton, 2024. https://arxiv.org/abs/2405.15793 (HTML v. read for section 2 and Table 3). ACI principles: simple actions, compact actions, concise feedback, guardrails. Search is capped at 50 results (summarized search scored 18.0%, no search 15.7%, iterative search 12.0%). Removing linting on edit drops the score from 18.0% to 15.0%. A 100-line viewer window beats 30 lines (14.3%) and the full file (12.7%).
7. **The Berkeley Function Calling Leaderboard (BFCL).** Patil et al., UC Berkeley, 2024. https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html. Evaluates simple, multiple, parallel, and parallel-multiple calls, plus "relevance detection", which checks that the model makes no call when no offered function fits.
8. **ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities.** Lu et al., Apple, 2024. https://arxiv.org/abs/2408.04682 (HTML read). "Canonicalization", such as turning "1B" into a number or "this Friday" into a date, is a hard category for every model, worst for time arguments. GPT-4 computed wrong offsets for "next Friday 5PM", and GPT-4o hallucinated timestamps. Best canonicalization scores: GPT-4o 76.6, Claude-3-Opus 71.1.
9. **NESTFUL: A Benchmark for Evaluating LLMs on Nested Sequences of API Calls.** Basu et al., IBM, 2024. https://arxiv.org/abs/2409.03797. In 1,800+ sequences, one call's output feeds the next call. The best model (GPT-4o) reaches only 28% full-sequence match.
10. **ToolHop: A Query-Driven Benchmark for Evaluating LLMs in Multi-Hop Tool Use.** Ye et al., Fudan/ByteDance, ACL 2025. https://arxiv.org/abs/2501.02506. Uses 3,912 *locally executable* tools so answers are verifiable. The top model (GPT-4o) scores 49.04% on 995 multi-hop queries.
11. **Retrieval Models Aren't Tool-Savvy: Benchmarking Tool Retrieval (ToolRet).** Shi et al., ACL 2025. https://arxiv.org/abs/2503.01763. Over a 43k-tool corpus, strong IR models retrieve tools poorly, and "this low retrieval quality degrades the task pass rate."
12. **RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation.** Gan & Sun, 2025. https://arxiv.org/abs/2505.03275. Retrieving a tool shortlist raises selection accuracy from 13.62% to 43.13% and cuts prompt tokens by more than 50%.
13. **LiveMCPBench: Can Agents Navigate an Ocean of MCP Tools?** Mo et al., 2025 (rev. 2026). https://arxiv.org/abs/2508.01780. With 70 servers and 527 tools, the best model (Claude-Sonnet-4) reaches 78.95% and most models reach 30–50%. Retrieval errors cause nearly half of all failures.
14. **Benchmarking Single Agent Performance.** LangChain, 10 Feb 2025. https://www.langchain.com/blog/react-agent-benchmarking. As irrelevant domains (tools and instructions) were added, gpt-4o's calendar-scheduling score fell to 2% at 7 domains. More context and more tools both degraded performance, and longer tool trajectories (3+ calls) degraded fastest.
15. **Writing effective tools for agents — with agents.** Ken Aizawa, Anthropic Engineering, 11 Sep 2025. https://www.anthropic.com/engineering/writing-tools-for-agents. Recommendations: give each tool a clear, distinct purpose; avoid overlapping tools; use namespacing prefixes (whose effect varies by model); return high-signal fields; offer a `response_format` choice (detailed 206 tokens vs concise 72); paginate and truncate (Claude Code caps responses at 25,000 tokens); write errors that say how to fix the input; and describe tools as if for a new hire.
16. **Introducing advanced tool use on the Claude Developer Platform.** Anthropic Engineering, 24 Nov 2025. https://www.anthropic.com/engineering/advanced-tool-use. 58 tools from five servers cost about 55K tokens. Tool search cut about 77K tokens to 8.7K and raised Opus 4 from 49% to 74% and Opus 4.5 from 79.5% to 88.1% on MCP evals. Tool-use examples raised complex-parameter accuracy from 72% to 90%. Programmatic tool calling used 37% fewer tokens.
17. **Tool search tool (docs).** Anthropic, Claude Platform docs, 2025–2026. https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool. "Claude's ability to pick the right tool degrades once you exceed 30–50 available tools." The docs recommend tool search at 10 or more tools, keeping the 3–5 most-used tools loaded, returning 5 results per search by default, and using consistent prefixes "so one search matches the whole group".
18. **Function calling guide.** OpenAI API docs, 2026. https://developers.openai.com/api/docs/guides/function-calling. "Aim for fewer than 20 functions available at the start of a turn" (a soft suggestion). Other guidance: use tool search to defer rarely used tools, use enums so invalid states cannot be expressed, apply the "intern test", always enable strict mode, and combine functions that are always called in sequence.
19. **Tool-space interference in the MCP era.** Fourney, Payne, Murad, Amershi, Microsoft Research, 11 Sep 2025. https://www.microsoft.com/en-us/research/blog/tool-space-interference-in-the-mcp-era-designing-for-agent-compatibility-at-scale/. Across 1,470 servers, most have 4 or fewer tools. Name collisions span 775 tools ("search" appears in 32 servers). Tool outputs have a median of 98 tokens but a mean of 4,431, and 16 tools average over 128k tokens. GPT-4.1 judged 3,536 of 5,983 results not flagged as errors to contain errors. Recommendations: namespaces, and summarize or paginate long results.
20. **Model Context Protocol reference servers (incl. the Time server).** MCP steering group, GitHub, 2024–2026. https://github.com/modelcontextprotocol/servers and https://github.com/modelcontextprotocol/servers/tree/main/src/time. The reference set is Everything, Fetch, Filesystem, Git, Memory, Sequential Thinking, and Time. The Time server exposes `get_current_time(timezone)` and `convert_time(source_timezone, time, target_timezone)`, and requires exact IANA names (`Europe/Warsaw` is accepted, `europe/warsaw` is rejected).
21. **MCP Server Architecture Patterns for LLM-Integrated Applications.** Rodrigues & Vas, 2026. https://arxiv.org/abs/2606.30317 (HTML read). This is an observational study of production logs (200 turns per bucket). Tool-selection accuracy falls below 90% between 10 and 15 tools per context for Claude Haiku 4.5 (91% at 10, 87% at 15), and between 20 and 30 tools for Sonnet 4. The authors recommend 10–15 tools per context and selective, filtered exposure, and say that "plain static merging would make the problem worse".
22. **Why Do Large Language Models (LLMs) Struggle to Count Letters?** Fu et al., 2024. https://arxiv.org/abs/2412.18626. Models recognise letters but cannot count them. Errors grow with word length and with letters that repeat, and most models cannot count a letter that appears more than twice.
23. **Faith and Fate: Limits of Transformers on Compositionality.** Dziri et al., 2023. https://arxiv.org/abs/2305.18654 (HTML read). Off-the-shelf ChatGPT and GPT-4 reach only 55% and 59% on 3-digit by 3-digit multiplication. Accuracy decays "from near perfection to zero" as problem size grows, and the same pattern holds for multi-step puzzles and dynamic programming.
24. **Test of Time: A Benchmark for Evaluating LLMs on Temporal Reasoning.** Fatemi et al., Google, 2024 (ICLR 2025). https://arxiv.org/abs/2406.09170 (HTML read, Table 8). ToT-Arithmetic Duration accuracy is 15.0, 16.0, and 13.5% (Claude-3-Sonnet, GPT-4, Gemini 1.5 Pro), and the most common error is off by exactly one day. Schedule scores 29.6–43.6%, Compare 39.1–63.1%, and MultiOp 26.6–62.6%.
25. **NUMCoT: Numerals and Units of Measurement in Chain-of-Thought Reasoning.** Xu et al., Findings of ACL 2024. https://arxiv.org/abs/2406.02864. LLMs "still encounter difficulties in handling numeral and measurement conversions", and small perturbations of numbers or units change performance substantially.
26. **SortBench: Benchmarking LLMs based on their ability to sort lists.** Herbold, 2025. https://arxiv.org/abs/2504.08312. All seven models lose faithfulness on long lists: they drop items and insert items that were never there. Values that mix syntax and meaning (numbers written as words) mislead even o3-mini.
27. **Lissard: Long and Simple Sequential Reasoning Datasets.** Bueno, Lotufo, Nogueira, 2024. https://arxiv.org/abs/2402.07859. State-of-the-art LLMs "can find common items in two lists with up to 20 items but fail when lists have 80 items."
28. **Can We Count on LLMs? The Fixed-Effect Fallacy and Claims of GPT-4 Capabilities.** Ball, Chen, Herley (Microsoft), 2024. https://arxiv.org/abs/2409.07638. GPT-4's accuracy at counting items in a list swings with list length, list composition, and phrasing. "Seemingly trivial modifications" produce differences far beyond sampling noise.
29. **Base64Bench: How good are LLMs at base64, and why care about it?** richbc (MATS), LessWrong, 5 Oct 2025. https://www.lesswrong.com/posts/5F6ncBfjh2Bxnm6CJ/base64bench-how-good-are-llms-at-base64-and-why-care-about. Perfect round-trip rates without tools: Claude 3.7 Sonnet 75.9%, Sonnet 4 73.7%, and GPT-5 (minimal reasoning) 65.8%. "No models succeeded on any tasks involving very long random strings" when encoding. JWT-length random strings were encoded perfectly only 42% of the time, and an 8B model was "basically useless".
30. **Query4Regex: Verifiable Regex Transformation through Formal Operations.** Hahn & Han, Findings of EACL 2026. https://aclanthology.org/2026.findings-eacl.331/. Models "often generate plausible but unparsable outputs", semantic errors are common even among regexes that parse, and these failures are hard to detect without formal verification.

## What the research says about tool design

- **One clear, distinct purpose per tool, and no overlap.** Anthropic says each tool needs "a clear, distinct purpose" and that overlapping tools distract agents [15]. SWE-agent's first ACI principle is "actions should be simple and easy to understand", with few options and concise docs [6]. *Conflicting evidence:* Anthropic [15] and OpenAI [18] also recommend consolidating operations that are always chained (e.g. `schedule_event` instead of list plus create). That advice targets API wrappers, where each call costs a round trip. For deterministic utilities, single-purpose tools with few parameters match [6] best. Consolidate only where two tools would always be called back to back. That is why `fraction_arithmetic` takes an `operation` enum instead of shipping four separate fraction tools.
- **Distinct, namespaced names.** In the wild, name collisions span 775 tools, and "search" alone appears in 32 servers [19]. Prefix namespacing helps, but prefix versus suffix placement changed results differently across models [15]. Tool-search docs recommend consistent prefixes "so one search matches the whole group" [17]. Implication: make every name globally unique and descriptive (`csv_filter_rows`, not `filter`), and record the category as metadata even when it is not in the name.
- **Schemas that cannot express invalid states.** Models hallucinate API arguments [3]. OpenAI recommends enums, strict mode (`additionalProperties: false`, every property required, optionals typed as nullable), and the "intern test" [18]. Anthropic recommends unambiguous parameter names (`user_id`, not `user`) and strict data models [15]. Concrete input examples lifted complex-parameter accuracy from 72% to 90% [16]. Implication: use enum-typed `unit`, `mode`, and `algorithm` parameters, explicit formats ("ISO 8601 date"), and 1–3 examples only where the format is not obvious.
- **Concise, high-signal outputs with hard caps.** Tool outputs in the wild have a median of 98 tokens but a mean of 4,431, and 16 tools average over 128k tokens [19]. SWE-agent caps search at 50 results and finds a 100-line window better than showing the whole file [6]. Claude Code truncates tool responses at 25,000 tokens, and a concise format used 72 tokens where the detailed one used 206 [15]. Implication: every enumerating tool (primes in range, permutations, date ranges, CSV rows) needs a documented cap and a truncation notice that tells the agent how to narrow the request.
- **Errors that teach recovery.** Errors should say what to fix and show a correct input, not return codes or tracebacks [15]. SWE-agent's lint-on-edit guardrail is worth 3 points absolute (18.0 vs 15.0) [6]. Microsoft found 3,536 of 5,983 results that were not flagged as errors actually contained errors [19], so tools must set the error flag honestly. Implication: an unknown unit error lists the valid units, and a bad date error shows the expected format.
- **Tool count degrades selection: the evidence and its numbers.** Anthropic says selection degrades beyond 30–50 tools [17], and 58 tools cost about 55K tokens [16]. OpenAI suggests fewer than 20 functions per turn [18]. A production log study puts the 90% accuracy line at 10–15 tools for Haiku 4.5 and 20–30 for Sonnet 4 [21]. LangChain saw gpt-4o's scheduling score collapse to 2% when 7 domains were loaded [14]. *Caveat:* [21] is observational and covers one organisation's tools, and [14] used 30 tasks per domain. The direction is consistent across all of them; the exact threshold depends on the model and on how similar the tools are.
- **Retrieval or tool search is the main mitigation, and retrieval quality then becomes the bottleneck.** Tool search raised Opus 4 from 49% to 74% [16]. RAG-MCP raised selection from 13.62% to 43.13% [12]. CRAFT retrieves from specialised toolsets [4]. However, retrieval errors cause nearly half of LiveMCPBench failures [13], and off-the-shelf IR models are weak at tool retrieval [11]. Implication: descriptions must carry the words users actually say ("count letters", "how many days until"), because those words are what a search matches.
- **Outputs must chain.** Nested calls, where one output is the next call's input, are still hard: 28% full-sequence match on NESTFUL [9] and 49% on ToolHop [10]. Implication: return plain JSON with stable field names (`value`, `date`, `items`) so one tool's output drops straight into the next tool's input. Avoid prose-only outputs.
- **Do not offer irrelevant tools.** BFCL tests "relevance detection", where the model must abstain when nothing fits [7]. LangChain's results show irrelevant domains actively hurt [14]. Implication: attach categories that match the agent's job, not the whole library.
- **Code-as-action is a competing approach, so be honest about the overlap.** CodeAct beats JSON tool calls by up to 20% [5], PAL shows interpreters fix arithmetic [2], and programmatic tool calling saves 37% of tokens [16]. The SDK already ships `code_execution`, so an agent with a sandbox can compute many of these results itself. The case for small deterministic tools is that they work when no sandbox is allowed or available, they are typed, validated, and testable, and they are cheaper per call than writing code. They can also be called *from* code. ToolHop's design choice of locally executable tools for verifiability supports this [10].
- **Canonicalization tools pay off.** Turning surface forms ("1B", "this Friday", "next Friday 5PM") into canonical values is among the hardest tool-use skills, especially for time arguments [8]. Tools that canonicalize (relative-date resolution, abbreviated-number parsing, date normalization) directly target that weakness.
- **Reference servers lean toward a few general, local tools.** The MCP reference set is small: fetch, filesystem, git, memory, time, and sequential thinking [20]. Most real servers have 4 or fewer tools [19]. The only pure-computation tool in the reference set, Time, is exactly the kind of tool this catalogue generalizes [20].

## What LLMs are measurably bad at without a tool

- **Multi-digit arithmetic.** GPT-4 gets only 59% of 3-digit by 3-digit products right, and accuracy falls toward zero as digit count grows [23]. LMs "struggle with basic functionality, such as arithmetic" [1]. Moving the arithmetic into an interpreter adds about 15 points on GSM8K [2].
- **Counting characters in words.** Errors grow with word length and with repeated letters, and most models cannot count a letter that appears more than twice [22].
- **Counting items in lists.** GPT-4's counting accuracy depends on list length, on how often the target appears, and on phrasing, with swings well beyond sampling noise [28].
- **Sorting long lists faithfully.** Every model drops items and invents new ones on long lists, and numbers written as words mislead even reasoning models [26].
- **Matching and intersecting lists.** Models find common items between two lists at 20 items and fail at 80 [27].
- **Date durations and scheduling.** "Days between two dates" style questions score 13.5–16% across GPT-4, Claude-3-Sonnet, and Gemini 1.5 Pro, and the commonest error is off by one day. Finding shared free slots scores 29.6–43.6%, and ordering mixed-format dates scores 39–63% [24]. A calendar tool was one of Toolformer's original five tools [1].
- **Resolving relative time.** GPT-4 computed wrong offsets for "next Friday 5PM", and GPT-4o hallucinated timestamps instead of deriving them from the current time. Time arguments are the hardest canonicalization case [8].
- **Unit and numeral conversion.** Models struggle to remember conversion ratios and handle numeral formats, and small perturbations change results [25]. Surface-form numbers such as "1B" must be canonicalized before they can be used [8].
- **Exact encoding and decoding.** Without tools, the best model round-trips base64 perfectly only 75.9% of the time. No model could encode very long random strings, and JWT-length random strings succeed 42% of the time [29]. Agents meet exactly these kinds of strings: tokens, keys, and IDs.
- **Writing correct regular expressions.** Model-written regexes are often "plausible but unparsable" and semantically wrong in ways that are hard to see without formal checking [30]. A tool that compiles a pattern and tests it on samples closes the loop.
- **Long multi-step procedures.** Performance on compositional tasks such as dynamic programming and multi-step puzzles decays toward zero with depth [23]. Graph algorithms, amortization tables, and critical-path schedules all have this shape.
- **Producing exact API arguments.** Models hallucinate arguments [3]. Even when the arguments are right, chaining outputs into the next call succeeds in under a third of nested sequences [9].
- **Hashes and checksums.** No source was found that measures this, so this point is argued from first principles. Cryptographic digests (SHA-256, HMAC) and CRCs are designed so that the output cannot be predicted without running the algorithm, so a model can only guess. Any agent task that needs a digest, a signature check, or a checksum needs a tool.

## Candidate catalogue

Conventions:

- **Inputs:** numbers that may exceed float precision are passed as strings, and binary data is passed as base64 or hex strings.
- **Caps:** "cap" means the tool enforces a documented maximum size and returns a truncation notice [6][15][19].
- **Overlap check:** the existing built-ins (`calculator`, `code_execution`, `code_search`, `editing/patch`, `reasoning/*`, `document_retrieval`, `operations/fetch` and `search`, `memory`, `context*`, `sessions`, `output_schema`, `mcp`, `fork`, `handoff`, `pause`) were listed by name only, and no candidate below intentionally duplicates them. The one overlap the spec author must check is `calculator`. If it already evaluates integer expressions exactly at arbitrary size, drop the first five rows of category 1.
- **"Drop first" lines:** each category ends its header with the weakest candidates in it, to make the cut from 461 down to 250 or more easier.

### 1. Exact arithmetic and precise numbers

Gap: multi-digit and multi-step arithmetic fails in tokens [23][1], and offloading it to code fixes it [2]. Drop first: `compare_numbers`, `evaluate_polynomial`, `integer_nth_root`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| multiply_big_integers | Multiply two integers of any length exactly | a: str, b: str → product: str | GPT-4 gets only 59% of 3×3-digit products right [23] |
| divide_big_integers | Integer-divide two arbitrarily large integers | dividend: str, divisor: str → {quotient, remainder} | long division is a carry-heavy procedure that decays with length [23] |
| power_big_integer | Raise an integer to a whole-number power exactly (digit cap) | base: str, exponent: int → value: str | results with hundreds of digits cannot be produced reliably |
| integer_square_root | Exact floor square root of a huge integer | n: str → {root, is_perfect_square} | `math.isqrt` is exact; models approximate |
| integer_nth_root | Exact floor n-th root and whether it is exact | value: str, n: int → {root, is_exact} | perfect-power checks need exact integer math |
| fraction_arithmetic | Apply one operation to two exact fractions | a: "p/q", b: "p/q", operation: enum add/subtract/multiply/divide → reduced fraction | common-denominator work is a classic multi-step slip [23] |
| simplify_fraction | Reduce a fraction to lowest terms | numerator: str, denominator: str → "p/q" | needs an exact GCD of possibly large numbers |
| decimal_to_fraction | Convert a terminating decimal to an exact fraction | value: "0.375" → "3/8" | gives exact rational form, no float drift |
| repeating_decimal_to_fraction | Convert a repeating decimal such as 0.1(6) to a fraction | value: str → "1/6" | algebraic procedure rarely executed correctly in prose |
| fraction_to_decimal | Expand a fraction to decimals with the repeating cycle marked | fraction: str, max_digits: int → "0.(142857)" | long division over many digits [23] |
| best_rational_approximation | Closest fraction under a denominator limit | value: str, max_denominator: int → "355/113" | `Fraction.limit_denominator` is exact; no reliable in-token method |
| decimal_arithmetic | One base-10 operation at a chosen precision, without float error | a: str, b: str, operation: enum, precision: int → str | avoids 0.1+0.2 artifacts in money and measurement |
| round_decimal | Round with an explicit rounding mode | value: str, places: int, mode: enum half_up/half_even/floor/ceiling/down/up → str | half-even vs half-up is a silent, frequent error |
| round_significant_figures | Round to N significant figures | value: str, figures: int → str | sig-fig rules on very small/large magnitudes are easy to misapply |
| sum_decimal_list | Exact sum of a long list of decimal numbers | values: list[str] → {sum, count} | adding dozens of values in tokens drops or miscarries items [28] |
| compare_numbers | Decide exactly which of two numeric strings is larger | a: str, b: str → {result: less/equal/greater} | "9.11 vs 9.9"-style traps mix syntax and value [26] |
| evaluate_polynomial | Evaluate a polynomial at a point exactly | coefficients: list[str], x: str → value: str | Horner evaluation with large powers is multi-step arithmetic |
| solve_quadratic_equation | Real or complex roots of ax²+bx+c | a, b, c: number → {discriminant, roots} | sign and square-root slips are common |

### 2. Number theory and integer math

Gap: these are exact, multi-step integer procedures that decay with size [23], and long result lists get dropped or invented items [26]. Drop first: `fibonacci_number`, `count_primes_below`, `euler_totient`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| is_prime_number | Deterministic primality test | n: str → {is_prime} | primality of large n cannot be recalled or eyeballed |
| prime_factorize | Factor an integer into primes (size cap) | n: str → [{prime, exponent}] | trial division is long, error-prone work [23] |
| list_primes_in_range | List primes between two bounds (range cap) | start: int, end: int → primes[] | long generated lists skip or invent members [26] |
| nth_prime | Return the n-th prime (n cap) | n: int → prime | recall fails beyond small n |
| next_prime_after | Smallest prime greater than n | n: str → prime | requires repeated primality tests |
| count_primes_below | Count primes below n (cap) | n: int → count | counting is a known weak spot [28] |
| greatest_common_divisor | GCD of a list of integers | values: list[str] → gcd | Euclid on large numbers is many exact steps |
| least_common_multiple | LCM of a list of integers | values: list[str] → lcm | depends on exact GCD and big products [23] |
| list_divisors | All positive divisors of an integer | n: str → divisors[] | enumeration easily misses divisors |
| euler_totient | Count integers up to n that are coprime to n | n: str → phi | needs a correct factorization first |
| modular_exponentiation | Compute base^exponent mod m | base, exponent, modulus: str → value | impossible by hand for large exponents; core of crypto puzzles |
| modular_inverse | Inverse of a modulo m, or a clear error when none exists | a: str, m: str → inverse | extended-Euclid back-substitution is error-prone |
| extended_gcd | Bézout coefficients for two integers | a: str, b: str → {gcd, x, y} | same back-substitution weakness |
| chinese_remainder_solve | Solve a system of congruences | remainders: list, moduli: list → {value, modulus} | multi-step modular algebra [23] |
| fibonacci_number | Exact n-th Fibonacci number | n: int → value: str | exact large terms cannot be recalled |
| sum_of_digits | Sum the digits of a long integer | n: str → sum | digit-level counting over long strings fails [22] |

### 3. Number formatting, bases and numerals

Gap: canonicalizing numbers ("1B") is a hard tool-use category [8], and numeral conversions trip models [25]. Drop first: `ieee754_hex_to_float`, `format_number_abbreviated`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| convert_number_base | Convert an integer between bases 2 and 36 | value: str, from_base: int, to_base: int → str | long binary/hex conversions need exact repeated division |
| integer_to_roman_numeral | Convert 1–3999 to a Roman numeral | n: int → str | subtractive-notation slips (IL, XM) |
| roman_numeral_to_integer | Parse and validate a Roman numeral | text: str → n | rejects malformed numerals the model would accept |
| number_to_english_words | Spell a number in English words | value: str → str | cheque and legal text needs exact spellings for long numbers |
| english_words_to_number | Parse English number words into a number | text: "two hundred and five" → 205 | surface-form to canonical value is a hard category [8] |
| parse_abbreviated_number | Expand shorthand such as 1.5k, 2M, 3B | text: str → value: str | ToolSandbox's own example is "1B" to a number [8] |
| format_number_abbreviated | Abbreviate a large number (1534000 → 1.53M) | value: str, decimals: int → str | correct rounding at unit boundaries (999.95k → 1.00M) |
| format_number_with_separators | Format a number with chosen grouping and decimal marks | value: str, decimals: int, thousands_sep: str, decimal_sep: str → str | locale-free and deterministic; long numbers get misgrouped |
| parse_formatted_number | Parse "1.234.567,89"-style text using given separators | text: str, thousands_sep: str, decimal_sep: str → value: str | European vs US formats are ambiguous to models [25] |
| to_scientific_notation | Format a number in scientific or engineering notation | value: str, significant_figures: int, style: enum → str | exponent counting over many digits fails [22] |
| float_to_ieee754 | Show the IEEE-754 bit fields of a number | value: number, width: enum 32/64 → {hex, sign, exponent, mantissa} | explains float surprises exactly (via `struct`) |
| ieee754_hex_to_float | Decode an IEEE-754 hex pattern to a number | hex: str, width: enum 32/64 → value | bit-level decoding cannot be done reliably in prose |

### 4. Statistics and descriptive analytics

Gap: aggregating long numeric lists means exact counting and summing, which degrade with length [28][27]. Drop first: `coefficient_of_variation`, `harmonic_mean`, `geometric_mean`, `compute_covariance`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| summarize_numbers | Descriptive summary of a numeric list | values: list[number] → {count, sum, min, max, mean, median, stdev} | one call replaces many error-prone passes [28] |
| compute_mean | Arithmetic mean of a list | values → mean | long sums drift [28] |
| compute_median | Median of a list | values → median | requires an exact sort [26] |
| compute_mode | Most frequent value or values of a list | values → modes[] | requires exact counting [28] |
| compute_variance | Sample or population variance | values, kind: enum sample/population → variance | the n vs n−1 choice plus long sums |
| compute_standard_deviation | Sample or population standard deviation | values, kind: enum → stdev | same, plus a square root |
| compute_percentile | Value at a given percentile, with a stated interpolation | values, percentile: number, method: enum → value | interpolation rules are rarely applied consistently |
| compute_quartiles | Quartile cut points and IQR of a list | values → {q1, q2, q3, iqr} | sort plus interpolation [26] |
| weighted_mean | Weighted average | values, weights → mean | grade and score calculations miscarry |
| geometric_mean | Geometric mean of positive values | values → mean | needs logs or roots of products |
| harmonic_mean | Harmonic mean of positive rates | values → mean | commonly confused with the arithmetic mean |
| compute_z_scores | Standard score of each value | values → z_scores[] | one division per item over a long list |
| pearson_correlation | Pearson correlation of two equal-length lists | x, y → r | many cross-products [23] |
| spearman_rank_correlation | Rank correlation with averaged ties | x, y → rho | tie ranking is subtle; `statistics` only gained ranked correlation in 3.12, so implement manually |
| compute_covariance | Sample covariance of two lists | x, y → covariance | long sums of products |
| linear_regression_fit | Least-squares line through points | x, y → {slope, intercept, r_squared} | exact fit cannot be estimated visually |
| moving_average | Simple moving average over a window | values, window: int → averages[] | sliding sums over long lists drift |
| cumulative_sum | Running totals of a list | values → totals[] | errors compound item by item |
| detect_outliers_iqr | Flag values outside Tukey fences | values, k: number → {outliers, lower_fence, upper_fence} | needs exact quartiles first |
| normalize_min_max | Rescale values to a target range | values, new_min, new_max → values[] | per-item arithmetic over long lists |
| histogram_bin_counts | Count values per equal-width bin | values, bins: int → [{start, end, count}] | exact bucketing and counting [28] |
| rank_values | Rank each value with a tie method | values, method: enum average/min/dense → ranks[] | tie handling is error-prone |
| coefficient_of_variation | Standard deviation relative to the mean | values → cv | composite of two error-prone steps |
| mean_confidence_interval | Normal-approximation confidence interval for a mean | values, confidence: number → {low, high} | z-quantile from `statistics.NormalDist`; no t-table in the stdlib, so state "normal approximation" |

### 5. Probability, combinatorics and seeded randomness

Gap: exact large combinatorial counts and enumerations decay with size [23] and drop items [26]. LLMs also cannot produce *reproducible* randomness; that point has no source and is argued from first principles, since a seed makes sampling testable. Drop first: `convert_betting_odds`, `count_multiset_combinations`, `seeded_normal_samples`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| count_combinations | Exact n choose k | n: int, k: int → value: str | products of large factorials [23] |
| count_permutations | Exact ordered arrangements nPk | n, k → value: str | same |
| factorial_exact | Exact n! (cap) | n: int → value: str | hundreds of digits |
| multinomial_coefficient | Ways to split n items into groups of given sizes | group_sizes: list[int] → value: str | multi-factorial arithmetic |
| count_multiset_combinations | Combinations with repetition (stars and bars) | n, k → value: str | formula is often misremembered |
| binomial_probability | P(X = k) for a binomial distribution | n, k, p → probability | exact powers and combinations |
| binomial_cumulative_probability | P(X ≤ k) for a binomial distribution | n, k, p → probability | sums many binomial terms |
| poisson_probability | P(X = k) for a Poisson distribution | rate, k → probability | exponential and factorial arithmetic |
| hypergeometric_probability | P(k successes) drawing without replacement | population, successes, draws, k → probability | three large binomials |
| normal_cdf | P(X ≤ x) for a normal distribution | x, mean, stdev → probability | no lookup table in context |
| normal_quantile | x for a given cumulative probability | probability, mean, stdev → x | inverse CDF cannot be done mentally |
| birthday_collision_probability | Chance that n items collide among d equally likely values | n: int, d: str → probability | sizing hash and ID collision risk; the intuition is famously wrong |
| convert_betting_odds | Convert between decimal, fractional, American odds and implied probability | value: str, from_format: enum, to_format: enum → value | sign conventions of American odds |
| list_combinations | Enumerate k-item combinations of a list (cap) | items: list, k: int → combinations[] | long enumerations skip members [26] |
| list_permutations | Enumerate orderings of a list (cap) | items: list, k: int → permutations[] | same |
| cartesian_product | Enumerate every combination across several lists (cap) | lists: list[list] → tuples[] | same |
| seeded_random_integers | Reproducible random integers | count, min, max, seed → integers[] | models cannot generate reproducible randomness |
| seeded_shuffle_list | Reproducible shuffle of a list | items, seed → items[] | reproducible ordering for tests and fair assignment |
| seeded_sample_list | Reproducible sample without replacement | items, k, seed → items[] | unbiased selection that can be audited |
| seeded_weighted_choice | Reproducible weighted picks | items, weights, count, seed → items[] | weighting cannot be honoured mentally |
| seeded_normal_samples | Reproducible Gaussian samples | count, mean, stdev, seed → values[] | synthetic test data |
| roll_dice_notation | Roll dice written as NdM+K with a seed | notation: str, seed: int → {rolls, total} | parses notation and sums exactly |
| seeded_split_list | Split a list into partitions by ratios reproducibly | items, ratios: list[number], seed → partitions[][] | train/test style splits whose sizes add up exactly |
| generate_seeded_uuid4 | Reproducible version-4 UUIDs from a seed | count, seed → uuids[] | valid UUID bit layout (version and variant bits) |

### 6. Finance and business math

Gap: multi-period compounding and schedules are long, exact, multi-step procedures [23][2]. Drop first: `simple_interest`, `break_even_units`, `payback_period`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| compound_interest_future_value | Future value with periodic compounding | principal, annual_rate, years, periods_per_year → value | exponentiation over many periods [23] |
| present_value | Discount a future amount to today | future_value, rate, periods → value | same, inverted |
| loan_payment_amount | Fixed periodic payment of an amortizing loan | principal, annual_rate, periods → payment | annuity formula is easy to misapply |
| amortization_schedule | Per-period interest, principal and balance table (cap) | principal, annual_rate, periods → rows[] | each row depends on the last; errors compound [23] |
| net_present_value | NPV of a cash-flow series | rate, cash_flows: list → npv | many discounted terms |
| internal_rate_of_return | IRR of a cash-flow series by bracketed root-finding | cash_flows: list → rate | no closed form; requires iteration |
| compound_annual_growth_rate | CAGR between two values | start_value, end_value, years → rate | fractional exponent |
| percentage_change | Percent change from an old to a new value | old_value, new_value → percent | base and sign confusion |
| percentage_breakdown | Each item's share of the total, rounded so it sums to exactly 100 | values: list, decimals: int → percents[] | largest-remainder rounding is never done by hand |
| allocate_amount | Split money by weights so the cents add up exactly | total: str, weights: list, decimals: int → amounts[] | naive rounding loses or gains a cent |
| convert_markup_margin | Convert a markup percent to a margin percent or back | value, direction: enum → percent | the two are routinely confused |
| break_even_units | Units needed to cover fixed costs | fixed_costs, unit_price, unit_variable_cost → units | simple, but the rounding-up rule is often missed |
| simple_interest | Interest without compounding | principal, annual_rate, years → interest | completes the set; low gain on its own |
| effective_annual_rate | Convert a nominal rate to an effective annual rate | nominal_rate, periods_per_year → rate | compounding exponent |
| straight_line_depreciation | Yearly depreciation schedule | cost, salvage_value, years → rows[] | exact schedule that sums to cost minus salvage |
| payback_period | Time until cumulative cash flow turns non-negative | cash_flows: list → periods | running sums plus fractional period [28] |
| apply_successive_percentages | Apply a chain of percentage changes | value, percents: list → value | "20% off then 10% off" is not 30% off |
| split_tax_inclusive_amount | Separate net amount and tax from a gross amount | gross, tax_rate → {net, tax} | people and models subtract the rate from the gross |

### 7. Unit conversion

Gap: models misremember conversion ratios and struggle with measurement conversions [25]. Affine (temperature) and inverse (fuel economy) conversions are the worst traps. Drop first: `convert_frequency`, `convert_density`, `convert_force`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| convert_length | Convert between length units (m, km, mi, ft, in, yd, nmi, …) | value, from_unit: enum, to_unit: enum → value | ratio recall errors [25] |
| convert_mass | Convert between mass units (kg, g, lb, oz, st, t, …) | value, from_unit, to_unit → value | same |
| convert_temperature | Convert between Celsius, Fahrenheit, Kelvin, Rankine | value, from_unit, to_unit → value | affine offset is a classic slip |
| convert_volume | Convert between volume units (L, mL, US/UK gal, fl oz, cup, tbsp, m³, …) | value, from_unit, to_unit → value | US vs UK gallons |
| convert_area | Convert between area units (m², ha, acre, ft², km², …) | value, from_unit, to_unit → value | squared ratios are misapplied |
| convert_speed | Convert between speed units (m/s, km/h, mph, knots) | value, from_unit, to_unit → value | compound units |
| convert_time_unit | Convert between time units (ns … weeks, years) | value, from_unit, to_unit → value | long chains of multiplications |
| convert_pressure | Convert between pressure units (Pa, kPa, bar, psi, atm, mmHg) | value, from_unit, to_unit → value | obscure ratios [25] |
| convert_energy | Convert between energy units (J, kWh, cal, kcal, BTU, eV) | value, from_unit, to_unit → value | magnitudes span 20+ orders |
| convert_power | Convert between power units (W, kW, hp metric and mechanical, BTU/h) | value, from_unit, to_unit → value | two horsepower definitions |
| convert_angle | Convert between degrees, radians, gradians, turns, arcminutes | value, from_unit, to_unit → value | π arithmetic |
| convert_fuel_economy | Convert between mpg (US/UK) and L/100 km | value, from_unit, to_unit → value | inverse relationship, not a ratio |
| convert_force | Convert between force units (N, kN, lbf, kgf, dyn) | value, from_unit, to_unit → value | ratio recall |
| convert_frequency | Convert between Hz, kHz, MHz, GHz, rpm | value, from_unit, to_unit → value | rpm is a factor-of-60 trap |
| convert_density | Convert between density units (kg/m³, g/cm³, lb/ft³, lb/gal) | value, from_unit, to_unit → value | compound-unit ratios |

### 8. Dates and calendars

Gap: duration questions score 13.5–16% and are usually off by one day, scheduling scores 30–44%, and ordering mixed-format dates scores 39–63% [24]. Relative dates are the hardest canonicalization [8]. A calendar tool was a Toolformer original [1]. Drop first: `week_bounds_for_date`, `easter_sunday_date`, `format_date_pattern`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| days_between_dates | Number of days between two dates | start_date, end_date (ISO), inclusive: bool → days | Duration scores 13.5–16%, mostly off-by-one [24] |
| add_to_date | Add or subtract days, weeks, months or years, clamping month ends | date, amount: int, unit: enum → date | Jan 31 + 1 month, leap days [24] |
| years_months_days_between | Calendar difference in years, months and days (age-style) | start_date, end_date → {years, months, days} | borrow rules across months of different length |
| business_days_between | Count working days, excluding weekends and given holidays | start_date, end_date, holidays: list, weekend_days: list → count | requires iterating the calendar |
| add_business_days | Move N working days, skipping weekends and holidays | date, days: int, holidays: list → date | same |
| day_of_week | Weekday of a date | date → weekday | cannot be recalled for arbitrary dates |
| is_leap_year | Whether a year is a Gregorian leap year | year: int → bool | century rules (1900 vs 2000) |
| days_in_month | Number of days in a month of a year | year, month → days | February in leap years |
| iso_week_number | ISO-8601 year, week and weekday of a date | date → {iso_year, week, weekday} | ISO year differs from calendar year near New Year |
| date_from_iso_week | Date for an ISO year, week and weekday | iso_year, week, weekday → date | inverse of the above |
| day_of_year | Ordinal day number of a date | date → day_number | cumulative month sums |
| date_from_day_of_year | Date for an ordinal day of a year | year, day_number → date | same, inverted |
| nth_weekday_of_month | Date of the n-th (or last) given weekday in a month | year, month, weekday: enum, n: int (−1 = last) → date | "4th Thursday of November" style holidays |
| next_weekday_from_date | Next or previous given weekday relative to a date | date, weekday: enum, direction: enum, include_same_day: bool → date | "this Friday" is exactly the failing case [8] |
| resolve_relative_date_phrase | Turn "in 3 weeks", "next Monday", "yesterday" into a date | phrase: str, reference_date → date | GPT-4 miscomputed "next Friday" offsets [8] |
| render_month_calendar | Plain-text grid of a month | year, month, first_weekday: enum → text | lets the model *see* weekday layout (`calendar` module) |
| fiscal_quarter_of_date | Fiscal year and quarter of a date for a given FY start month | date, fiscal_year_start_month → {fiscal_year, quarter} | off-by-one quarter errors |
| easter_sunday_date | Western Easter Sunday for a year | year: int → date | computus algorithm cannot be recalled |
| normalize_date_to_iso | Parse a date string in a stated or common format to ISO 8601 | text, input_format: str or null, day_first: bool → date | canonicalization [8] and the 03/04 ambiguity |
| format_date_pattern | Format an ISO date with a strftime-style pattern (locale-free) | date, pattern → text | exact directives (%j, %U) |
| list_dates_in_range | Every date, or every N days, between two dates (cap) | start_date, end_date, step_days → dates[] | long enumerations skip items [26] |
| count_weekday_occurrences | How many times a weekday falls in a date range | start_date, end_date, weekday → count | counting over a calendar [28] |
| week_bounds_for_date | First and last day of the week containing a date | date, week_start: enum → {start, end} | week-start conventions differ |
| sort_date_strings | Sort dates given in mixed formats chronologically | dates: list[str], day_first: bool → dates[] | Compare scores 39–63% [24] |
| find_common_free_slots | Free windows shared by several busy calendars | busy: list of interval lists, window_start, window_end, min_minutes → slots[] | Schedule scores 29.6–43.6% [24] |
| merge_time_intervals | Merge overlapping or touching intervals | intervals: list[{start, end}] → merged[] | interval logic over long lists |
| generate_recurring_dates | Dates of a simple recurrence rule (cap) | start_date, frequency: enum, interval, count, weekdays → dates[] | "every 2nd Tuesday" enumeration |

### 9. Time zones, timestamps and durations

Gap: models hallucinate timestamps and miscompute offsets [8], and MultiOp time questions score 27–63% [24]. A time server is one of only seven MCP reference servers [20]. Drop first: `parse_http_date`, `datetime_in_multiple_timezones`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| convert_datetime_timezone | Convert a wall-clock datetime between IANA zones | datetime, from_timezone, to_timezone → {datetime, utc_offset, is_dst} | DST rules change by date; mirrors MCP `convert_time` [20] |
| datetime_in_multiple_timezones | Show one instant in several zones | datetime, from_timezone, timezones: list → rows[] | meeting planning across regions |
| timezone_offset_at | UTC offset, DST flag and abbreviation for a zone at an instant | timezone, datetime → {utc_offset, is_dst, abbreviation} | historical and future DST transitions |
| current_datetime_in_timezone | **Time-dependent:** current date and time in a zone | timezone → {datetime, is_dst, weekday} | models do not know "now"; GPT-4o hallucinated timestamps [8] |
| unix_timestamp_to_datetime | Convert epoch seconds or milliseconds to an ISO datetime | timestamp: number, unit: enum s/ms, timezone → datetime | 10-digit arithmetic plus zone |
| datetime_to_unix_timestamp | Convert an ISO datetime to epoch seconds | datetime, timezone → timestamp | inverse of the above |
| duration_between_datetimes | Exact elapsed time between two zone-aware datetimes | start, end → {seconds, human} | DST makes "a day" 23 or 25 hours |
| add_duration_to_datetime | Add a duration to a datetime in a zone, DST-aware | datetime, timezone, hours, minutes, seconds → datetime | wall-clock vs absolute time |
| format_duration_human | Render seconds as "1h 2m 5s" or "2 days 3 hours" | seconds: number, style: enum → text | division with remainders |
| parse_duration_text | Parse "1h30m", "90 min" or ISO-8601 "PT1H30M" into seconds | text → seconds | canonicalization [8] |
| search_timezone_names | Find IANA zone names matching text | query: str → names[] | exact IANA keys are case-sensitive [20] |
| cron_next_run_times | Next N fire times of a 5-field cron expression after a datetime | expression, after, count, timezone → datetimes[] | cron semantics (day-of-month OR day-of-week) are subtle |
| parse_http_date | Parse an RFC 2822/HTTP date header to ISO 8601 | text → datetime | `email.utils.parsedate_to_datetime` is exact |

### 10. Text measurement and counting

Gap: models cannot count letters in a word reliably [22], and item counts swing with length and phrasing [28]. Drop first: `reading_time_estimate`, `count_paragraphs`, `lexical_diversity`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| count_characters | Count characters, with and without whitespace | text → {total, without_whitespace} | character length is invisible through tokens [22] |
| count_character_occurrences | Count how many times one character appears | text, character, case_sensitive: bool → count | the "strawberry" failure [22] |
| count_substring_occurrences | Count occurrences of a substring, optionally overlapping | text, substring, overlapping: bool → count | overlapping counts are subtle |
| count_words | Count words | text → count | long-text counts drift [28] |
| count_sentences | Count sentences with a stated heuristic splitter | text → count | abbreviations and decimals confuse |
| count_lines | Count total, blank and non-blank lines | text → {total, blank, non_blank} | long counts [28] |
| count_paragraphs | Count blank-line-separated paragraphs | text → count | low gain; drop first |
| word_frequencies | Top-N word counts | text, top_n, case_insensitive: bool, stopwords: list → [{word, count}] | exact counting over long text [28] |
| character_frequencies | Count every character | text, top_n → [{character, count}] | [22] |
| ngram_frequencies | Top-N word n-grams | text, n, top_n → [{ngram, count}] | combinatorial counting |
| find_substring_positions | All start indices of a substring | text, substring → positions[] | models cannot index characters [22] |
| character_at_position | Character and code point at an index (negatives allowed) | text, index → {character, code_point} | positional lookup through tokens fails [22] |
| word_at_position | The n-th word of a text | text, index → word | positional lookup over long text |
| lines_longer_than | Lines exceeding a length limit, with line numbers | text, max_length → [{line_number, length}] | exact per-line length |
| count_bytes_in_encoding | Size of text in UTF-8, UTF-16 or Latin-1 bytes | text, encoding: enum → bytes | database and API byte limits; multibyte characters |
| sms_segment_count | Number of SMS segments (GSM-7 vs UCS-2 rules) | text → {encoding, characters, segments} | 160/153 vs 70/67 rules |
| readability_scores | Flesch reading ease and Flesch–Kincaid grade (heuristic syllables) | text → {reading_ease, grade_level, words, sentences, syllables} | needs exact word/sentence/syllable counts |
| lexical_diversity | Unique-word count and type-token ratio | text → {unique_words, total_words, ratio} | exact counting [28] |
| reading_time_estimate | Minutes to read a text at a given speed | text, words_per_minute → minutes | depends on an exact word count; low gain |
| check_palindrome | Whether text reads the same reversed, with optional normalization | text, ignore_case_and_punctuation: bool → bool | character-level reversal of long strings [22] |
| check_anagram | Whether two strings are anagrams | a, b, ignore_case_and_spaces: bool → bool | letter-multiset counting [22] |

### 11. String transformation

Gap: character-exact transformations of long text are unreliable through tokens [22]. Line-numbered windows help agents reference text precisely [6]. Drop first: `pad_text`, `reverse_word_order`, `mask_text_characters`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| reverse_text | Reverse the characters of a text | text → text | character-level reversal fails on long strings [22] |
| reverse_word_order | Reverse the order of words | text → text | long inputs drop words [26] |
| convert_identifier_case | Convert between snake_case, camelCase, PascalCase, kebab-case, CONSTANT_CASE | text, target_case: enum → text | acronym and digit boundaries (HTTPServer2) |
| slugify_text | Make a URL slug from text | text, separator, max_length → slug | Unicode folding and exact rules |
| truncate_text | Cut text to a character or word limit at a boundary, with an ellipsis | text, max_length, unit: enum characters/words, ellipsis → text | hitting an exact limit (280 chars) [22] |
| wrap_text_to_width | Hard-wrap text to a column width | text, width → text | exact column counting (`textwrap`) |
| indent_text_block | Prefix every line with an indent | text, prefix → text | exact, long-text edits |
| dedent_text_block | Remove the common leading whitespace from all lines | text → text | exact whitespace arithmetic |
| pad_text | Pad text to a width, left, right or centred | text, width, align: enum, fill_character → text | exact column counting |
| replace_all_occurrences | Literal find-and-replace that reports a count | text, find, replace, max_replacements → {text, replacements} | silent misses in long text; the count lets the agent verify |
| deduplicate_lines | Remove duplicate lines, keeping the first occurrence | text, case_sensitive: bool → {text, removed} | long lists drop and invent items [26] |
| sort_text_lines | Sort lines alphabetically, naturally or numerically | text, mode: enum, reverse: bool, unique: bool → text | faithful sorting of long lists [26] |
| strip_html_tags | Convert HTML to visible plain text | html → text | tag and entity noise (`html.parser`) |
| normalize_whitespace | Collapse whitespace runs, trim, unify line endings | text, keep_newlines: bool → text | invisible whitespace differences |
| extract_between_markers | All substrings between a start and an end marker | text, start_marker, end_marker → items[] | exact scanning of long text |
| split_text_into_chunks | Split text into fixed-size chunks with overlap at word boundaries | text, max_characters, overlap → chunks[] | exact size budgeting |
| add_line_numbers | Prefix each line with its number | text, start: int → text | SWE-agent's viewer shows numbered lines [6] |
| extract_line_range | Return lines i to j of a text | text, start_line, end_line → text | windowed viewing beats whole files [6] |
| mask_text_characters | Mask all but the last N characters | text, visible_count, mask_character → text | exact counts for IDs and cards |
| fill_text_template | Fill ${name} placeholders and report missing ones | template, values: object → {text, missing} | silent omissions in long templates (`string.Template`) |

### 12. Unicode and character inspection

Gap: characters are invisible behind tokens [22]. Invisible and look-alike characters cannot be seen by the model at all, so this point is argued from first principles with no source. Drop first: `code_points_to_text`, `display_width_of_text`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| unicode_character_info | Name, code point and category of each character | text (cap) → [{character, code_point, name, category}] | exact Unicode data (`unicodedata`) |
| find_unicode_character_by_name | Character for a Unicode name such as "EM DASH" | name → {character, code_point} | exact lookup, no recall |
| normalize_unicode_form | Apply NFC, NFD, NFKC or NFKD normalization | text, form: enum → text | invisible composed vs decomposed forms |
| remove_diacritics | Strip accents (é → e) | text → text | decomposition plus filtering |
| detect_invisible_characters | Find zero-width, bidi-control, BOM and non-breaking characters with positions | text → [{position, code_point, name}] | the model literally cannot see them; hidden-text hygiene |
| find_non_ascii_characters | List non-ASCII characters with positions | text → [{position, character, code_point}] | smart quotes and look-alikes |
| detect_scripts_in_text | Count characters per Unicode script (Latin, Cyrillic, …) | text → [{script, count}] | homoglyph spotting (Cyrillic "а" vs Latin "a") |
| text_to_code_points | Convert text to U+XXXX code points | text → code_points[] | exact code points |
| code_points_to_text | Convert U+XXXX code points to text | code_points: list[str] → text | inverse of the above |
| display_width_of_text | Terminal column width, counting wide East-Asian characters as 2 | text → width | table alignment with CJK text |

### 13. Regular expressions

Gap: model-written regexes are often unparsable or semantically wrong, and the errors cannot be seen without checking [30]. Guardrails that check work help agents recover [6]. Drop first: `glob_to_regex`, `regex_escape_literal`. Safety note: Python's `re` has no timeout, so cap the input size and the pattern length (catastrophic backtracking).

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| regex_find_all | All matches of a pattern, with spans and groups (cap) | text, pattern, flags: list[enum] → matches[] | running a regex mentally is unreliable [30] |
| regex_full_match | Whether a whole string matches a pattern | text, pattern, flags → {matches, groups} | anchoring mistakes |
| regex_replace | Substitute matches using a replacement template | text, pattern, replacement, count, flags → {text, replacements} | backreference syntax slips |
| regex_split | Split text on a pattern | text, pattern, max_splits → parts[] | exact boundaries |
| validate_regex_pattern | Compile a pattern and report the error position if it is invalid | pattern → {valid, error, position} | "plausible but unparsable" patterns [30] |
| regex_extract_groups | Named and numbered groups of the first match | text, pattern → {groups, named_groups} | structured extraction |
| regex_escape_literal | Escape a literal string for use inside a regex | text → pattern | metacharacter escaping slips |
| regex_test_samples | Report which sample strings a pattern matches | pattern, samples: list[str], full_match: bool → [{sample, matched}] | the verification loop that [30] says is missing |
| wildcard_match_names | Filter names by a shell-style wildcard pattern | names: list[str], pattern, case_sensitive: bool → names[] | `fnmatch` semantics; long-list filtering [26] |
| glob_to_regex | Translate a shell-style wildcard pattern into a regex | pattern → regex | exact translation |

### 14. Text comparison and similarity

Gap: aligning long lists and texts item by item fails beyond about 20 items [27]. Exact diffs give agents concise, checkable feedback [6]. Drop first: `bag_of_words_cosine_similarity`, `hamming_distance`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| unified_diff_text | Unified diff between two texts | old_text, new_text, context_lines → diff | exact line alignment (`difflib`) |
| diff_words | Word-level insertions and deletions between two texts | old_text, new_text → [{op, text}] | prose edits are hard to spot |
| diff_characters | Character-level differences between two short strings | a, b → [{op, position, text}] | near-identical IDs and keys [22] |
| similarity_ratio | Similarity ratio between two texts (0–1) | a, b → ratio | `difflib.SequenceMatcher` is exact |
| levenshtein_distance | Edit distance between two strings | a, b → distance | dynamic programming [23] |
| hamming_distance | Number of differing positions in equal-length strings | a, b → distance | exact positional comparison [22] |
| jaro_winkler_similarity | Jaro–Winkler similarity for short strings such as names | a, b → score | fuzzy name matching |
| closest_string_matches | Closest candidates to a query string | query, candidates: list, limit, cutoff → matches[] | "which option did the user mean" over long lists [27] |
| longest_common_substring | Longest shared contiguous substring | a, b → {substring, a_index, b_index} | DP over characters [23] |
| jaccard_similarity | Jaccard index of two token sets or lists | a: list or text, b: list or text → score | exact set counting [27] |
| bag_of_words_cosine_similarity | Cosine similarity of word-count vectors | a, b → score | lexical overlap without embeddings |

### 15. JSON manipulation and validation

Gap: chaining structured outputs is weak (28% full-sequence on NESTFUL [9], 49% on ToolHop [10]), models hallucinate arguments [3], and filtering and aggregating long arrays drops items [26][28]. Drop first: `repair_json_text` (heuristic), `json_delete_at_path`, `unflatten_json`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| validate_json_syntax | Check JSON text and report the error line and column | text → {valid, error, line, column} | one stray comma breaks a pipeline |
| pretty_print_json | Re-indent JSON, optionally sorting keys | text, indent, sort_keys → text | exact reformatting of large docs |
| minify_json | Compact JSON to the smallest text | text → text | exact, and saves tokens |
| json_get_value_at_path | Read the value at a dot or JSON-Pointer path | document, path → value | deep lookups in large documents |
| json_set_value_at_path | Return a copy of the document with a value set at a path | document, path, value → document | exact edits without retyping the whole doc |
| json_delete_at_path | Return a copy of the document with the path removed | document, path → document | same |
| list_json_paths | List every leaf path in a document (cap) | document → paths[] | shape discovery in large docs |
| flatten_json | Flatten nested JSON to dotted keys | document, separator → object | exact key construction |
| unflatten_json | Rebuild nested JSON from dotted keys | object, separator → document | inverse of the above |
| diff_json_documents | Added, removed and changed paths between two documents | a, b → [{op, path, old, new}] | silent changes in large docs |
| apply_json_merge_patch | Apply an RFC 7386 merge patch | document, patch → document | null-deletes semantics |
| apply_json_patch | Apply RFC 6902 operations (add, remove, replace, move, copy, test) | document, operations → document | ordered pointer edits |
| infer_json_schema | Infer a JSON Schema from an example document | document → schema | exact type census over arrays |
| validate_json_schema_subset | Validate a document against a documented subset of JSON Schema | document, schema → {valid, errors[{path, message}]} | must name the supported keywords; full JSON Schema is not stdlib |
| filter_json_array | Keep objects whose field satisfies a comparison | items, field, operator: enum, value → items[] | long-list filtering drops items [26] |
| pluck_json_field | Extract one field from every object in an array | items, field → values[] | long-list extraction [26] |
| group_json_array_by_field | Group objects by a field value, with counts | items, field → [{key, count, items}] | exact grouping [28] |
| aggregate_json_field | Sum, mean, min, max or count of a field across objects | items, field, aggregate: enum → value | long sums [28] |
| sort_json_array_by_fields | Sort objects by one or more fields | items, keys: list[{field, descending}] → items[] | faithful multi-key sorting [26] |
| top_n_records_by_field | The N objects with the largest or smallest field value | items, field, n, largest: bool → items[] | selection over long lists |
| summarize_json_structure | Concise shape summary: depth, key counts, array lengths, types | document → summary | a concise view instead of a 50k-token dump [15][19] |
| repair_json_text | Fix common near-JSON defects (trailing commas, single quotes, comments) | text → {text, fixes} | heuristic; flag as best-effort |

### 16. CSV and tabular data

Gap: models sort, count and match rows poorly beyond a few dozen [26][27][28]. CRAFT showed tabular processing gains from reusable code tools [4]. Drop first: `transpose_table`, `csv_deduplicate_rows`. `query_records_with_sql` uses `sqlite3` in memory, read-only; the spec author must confirm it fits "simple".

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| csv_to_json_records | Parse CSV text into a list of row objects | text, delimiter, has_header → records[] | quoting and escaped newlines (`csv`) |
| json_records_to_csv | Render row objects as CSV text | records, columns → text | exact quoting |
| detect_csv_dialect | Guess the delimiter, quote character and header presence | text → {delimiter, quotechar, has_header} | `csv.Sniffer` |
| profile_csv_columns | Per-column inferred type, null count, unique count, min and max | text → columns[] | exact census of a table [28] |
| csv_select_columns | Keep chosen columns in a chosen order | text, columns → text | exact, long |
| csv_filter_rows | Keep rows where a column satisfies a comparison | text, column, operator: enum, value → text | long-table filtering [26] |
| csv_sort_rows | Sort rows by one or more columns | text, keys → text | faithful sorting [26] |
| csv_aggregate_column | Sum, mean, min, max or count of a column | text, column, aggregate: enum → value | long sums [28] |
| csv_group_by_aggregate | Aggregate a column per group of another column | text, group_column, value_column, aggregate → rows[] | exact grouping [28] |
| csv_join_tables | Inner or left join two CSV tables on key columns | left, right, left_key, right_key, how: enum → text | matching fails beyond ~20 items [27] |
| csv_deduplicate_rows | Remove duplicate rows, optionally by key columns | text, key_columns → {text, removed} | [26] |
| csv_value_counts | Frequency of each value in a column | text, column, top_n → [{value, count}] | [28] |
| csv_pivot_table | Cross-tabulate one column against another with an aggregate | text, row_column, column_column, value_column, aggregate → table | multi-step grouping |
| transpose_table | Swap the rows and columns of a table | rows: list[list] → rows[] | exact, long |
| csv_to_markdown_table | Render CSV as an aligned Markdown table | text, max_rows → markdown | column padding |
| query_records_with_sql | Run one read-only SQL SELECT over records loaded into an in-memory table | records, sql → rows[] | expressive and exact; reject non-SELECT statements |

### 17. Structured formats, URLs and headers

Gap: the exact parsing rules of these formats are what models get subtly wrong (canonicalization [8], argument hallucination [3]). Drop first: `json_to_ini`, `parse_cookie_header`. Safety notes: `xml.etree` must reject DTDs/entities (billion-laughs). `toml_to_json` needs Python 3.11+ (`tomllib`, read-only).

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| xml_to_json | Convert XML into a JSON structure | xml_text → document | exact attribute and child mapping |
| xml_find_elements | Find elements with ElementTree's limited XPath | xml_text, path → [{tag, attributes, text}] | deep lookups in large XML |
| validate_xml_wellformed | Check XML well-formedness and report the error position | xml_text → {valid, error, line, column} | one unclosed tag breaks parsing |
| pretty_print_xml | Re-indent XML | xml_text, indent → text | exact reformatting |
| ini_to_json | Parse INI/config text into sections and keys | text → document | `configparser` interpolation and defaults rules |
| json_to_ini | Render a sections-and-keys object as INI text | document → text | exact format |
| toml_to_json | Parse TOML text into JSON (Python 3.11+) | text → document | TOML typing rules (dates, inline tables) |
| parse_url_components | Split a URL into scheme, host, port, path, query and fragment | url → components | userinfo and port edge cases |
| resolve_relative_url | Resolve a relative reference against a base URL | base_url, reference → url | "../" and leading-slash semantics are often wrong |
| parse_url_query_string | Parse a query string into keys and value lists | query → object | repeated keys and percent-decoding |
| build_url_query_string | Build a percent-encoded query string from an object | params: object → query | exact encoding |
| parse_http_header_block | Parse raw HTTP or email headers into a field list | text → [{name, value}] | folding and duplicate headers |
| parse_content_type_header | Split a Content-Type header into type, subtype and parameters | header → {media_type, parameters} | quoted parameter values |
| parse_cookie_header | Parse a Cookie or Set-Cookie header | header → cookies[] | attribute parsing (`http.cookies`) |
| parse_dotenv_text | Parse KEY=VALUE lines into an object | text → object | quoting and comments; local text only |
| parse_email_address_list | Split "Name <a@b>, c@d" lists into names and addresses | text → [{name, address}] | quoted commas (`email.utils.getaddresses`) |

### 18. Encoding and decoding

Gap: without tools the best models round-trip base64 perfectly only 66–76% of the time and fail on long random strings [29]. These strings (tokens, keys, payloads) are exactly what agents handle. Drop first: `caesar_shift_text`, `base32_decode_text`, `gzip_compress_to_base64`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| base64_encode_text | Base64-encode UTF-8 text (standard or URL-safe) | text, url_safe: bool → encoded | 66–76% perfect at best without tools [29] |
| base64_decode_text | Decode base64 to UTF-8 text, or report invalid input | encoded, url_safe: bool → text | long random strings fail [29] |
| base32_encode_text | Base32-encode UTF-8 text | text → encoded | exact bit regrouping |
| base32_decode_text | Decode base32 to text | encoded → text | same |
| hex_encode_text | Hex-encode the UTF-8 bytes of text | text → hex | byte-exact |
| hex_decode_text | Decode hex bytes to text in a stated encoding | hex, encoding: enum → text | byte-exact |
| url_encode_component | Percent-encode a string for a URL component | text, safe_characters → encoded | reserved-character rules |
| url_decode_component | Decode a percent-encoded string | encoded, plus_as_space: bool → text | `+` vs `%20` |
| html_escape_text | Escape &, <, > and quotes for HTML | text, quote: bool → text | exact |
| html_unescape_text | Decode HTML entities (named and numeric) | text → text | hundreds of named entities |
| punycode_encode_domain | Convert an internationalized domain to its ASCII (xn--) form | domain → ascii_domain | IDNA algorithm cannot be done mentally |
| punycode_decode_domain | Convert an xn-- domain back to Unicode | ascii_domain → domain | phishing look-alike checks |
| decode_jwt_payload | Decode a JWT's header and payload without verifying it | token → {header, payload, signature_verified: false} | base64url plus JSON in one exact step [29] |
| decode_quoted_printable | Decode quoted-printable text (email bodies) | text, charset → text | soft line breaks and =XX bytes |
| decode_mime_encoded_header | Decode RFC 2047 =?utf-8?b?…?= header words | header → text | email subject decoding |
| escape_string_literal | Escape text as a JSON string literal | text → literal | control and Unicode escapes |
| unescape_string_literal | Turn \n, \t and \uXXXX escapes back into characters | literal → text | exact unescaping of logs |
| caesar_shift_text | Shift letters by N positions (ROT13 when N=13) | text, shift: int → text | per-letter modular arithmetic [22] |
| gzip_base64_decompress | Decompress gzip or zlib data given as base64 into text | data_base64, encoding → text | impossible in tokens |
| gzip_compress_to_base64 | Compress text with gzip and return base64 and sizes | text → {data_base64, original_bytes, compressed_bytes} | payload size estimates; low gain |
| repair_mojibake_text | Fix UTF-8 text that was mis-decoded as Latin-1 or CP1252 | text → {text, changed} | "Ã©" → "é" requires byte-level re-decoding |

### 19. Hashing and checksums

Gap: digests are designed to be unpredictable, so a model can only guess them. No measuring source was found; the case is argued from first principles. Drop first: `adler32_checksum`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| compute_text_hash | Hash UTF-8 text with a chosen algorithm | text, algorithm: enum md5/sha1/sha256/sha512/sha3_256/blake2b → hex | impossible in tokens |
| compute_base64_content_hash | Hash binary content given as base64 | data_base64, algorithm: enum → hex | verifying downloaded or attached content |
| compute_hmac_signature | HMAC of a message with a key | message, key, algorithm: enum → hex | webhook signature checks |
| verify_hash_value | Compare a text's digest with an expected digest in constant time | text, expected_hex, algorithm → {matches} | avoids hand-comparing 64-character hex strings [22] |
| crc32_checksum | CRC-32 of text | text → {decimal, hex} | impossible in tokens |
| adler32_checksum | Adler-32 of text | text → {decimal, hex} | low gain; completes the set |
| compute_git_blob_hash | Git blob object id (SHA-1) of text | text → hex | checks file identity against `git ls-files -s` output |
| assign_stable_bucket | Deterministic bucket for an id (A/B tests, sharding) | key, buckets: int, salt → bucket | stable across runs; models cannot hash |

### 20. Identifiers and format validation

Gap: checksum digits and version-ordering rules are exact procedures that models fake. Version strings mislead because syntax and value mix [26]. Drop first: `validate_e164_phone_format`, `convert_isbn10_to_isbn13`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| luhn_check | Validate a number with the Luhn checksum | number: str → {valid} | digit-doubling arithmetic [22] |
| luhn_check_digit | Compute the Luhn check digit to append | partial_number: str → digit | same |
| validate_isbn | Validate an ISBN-10 or ISBN-13 checksum | isbn → {valid, kind} | weighted mod-11/mod-10 sums |
| convert_isbn10_to_isbn13 | Convert an ISBN-10 to ISBN-13 | isbn10 → isbn13 | recomputes the check digit |
| validate_iban | Validate an IBAN's mod-97 checksum and length | iban → {valid, country, reason} | 30-digit modular arithmetic |
| validate_ean13_barcode | Validate an EAN-13/UPC-A check digit | code → {valid} | weighted sums |
| validate_email_syntax | Check email address syntax (no network lookup) | address → {valid, reason, normalized} | consistent, documented rules |
| validate_url_syntax | Check URL syntax, scheme and host | url, allowed_schemes → {valid, reason} | documented rules |
| validate_e164_phone_format | Check a phone number is valid E.164 syntax | number → {valid, normalized} | syntax only; low gain |
| validate_uuid | Validate a UUID and report its version and variant | text → {valid, version, variant} | bit-level fields |
| generate_name_based_uuid | Deterministic UUID v3 or v5 from a namespace and a name | namespace, name, version: enum 3/5 → uuid | requires hashing |
| compare_semantic_versions | Compare two SemVer 2.0 versions, including prerelease rules | a, b → {result} | prerelease and numeric ordering traps |
| semver_satisfies_range | Whether a version satisfies a range such as ^1.2, ~1.2 or >=1.0 <2 | version, range → {satisfies} | caret/tilde rules are subtle |
| bump_semantic_version | Increment the major, minor or patch part | version, part: enum → version | resets lower parts |
| sort_semantic_versions | Sort SemVer strings correctly | versions: list → versions[] | "1.10" after "1.9" [26] |
| compare_dotted_versions | Compare generic dotted version strings numerically | a, b → {result} | the "1.10 vs 1.9" trap [26] |

### 21. Lists, sets and sequences

Gap: list intersection fails at 80 items [27], sorting drops and invents items [26], and counting swings with length [28]. Drop first: `zip_lists`, `flatten_nested_list`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| sort_list_values | Sort values alphabetically, numerically or naturally | items, mode: enum, reverse: bool, case_insensitive: bool → items[] | faithful sorting [26] |
| deduplicate_list_items | Remove duplicates, keeping first occurrences in order | items, case_insensitive: bool → {items, removed} | [26] |
| count_item_frequencies | Count each distinct item | items, top_n → {total, counts[]} | [28] |
| find_duplicate_items | Items that appear more than once, with counts | items → [{item, count}] | [28] |
| compare_two_lists | Items only in A, only in B, and in both | a, b → {only_in_a, only_in_b, in_both} | fails at 80 items [27] |
| intersect_multiple_lists | Items present in every one of several lists | lists → items[] | [27] |
| union_multiple_lists | Distinct items across several lists, in first-seen order | lists → items[] | [26] |
| chunk_list_into_batches | Split a list into batches of size N | items, size → batches[] | exact boundaries |
| flatten_nested_list | Flatten nested lists to a given depth | items, depth → items[] | low gain; drop first |
| zip_lists | Pair items from several lists position by position | lists, fill_value → tuples[] | alignment errors on long lists |
| select_top_n_values | The N largest or smallest numbers | values, n, largest: bool → values[] | selection over long lists |
| find_item_positions | All indices where an item occurs | items, item → indices[] | positional indexing [22] |
| find_missing_integers | Integers missing from a sequence or a range | values, start, end → missing[] | gap-spotting in long sequences [27] |
| compress_integer_ranges | Collapse integers into ranges ("1-3,7-8") | values → text | exact run detection |
| expand_integer_ranges | Expand "1-3,7,10-12" into integers (cap) | text → values[] | page and line range expansion |

### 22. Graphs and dependencies

Gap: multi-step search procedures such as dynamic programming collapse with depth [23]. Dependency ordering underlies the nested tool chains that agents fail at [9]. Drop first: `node_degree_summary`, `minimum_spanning_tree`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| topological_sort | Order nodes so every dependency comes first | edges: list[[from, to]] → order[] | build/run order planning (`graphlib`) |
| detect_graph_cycle | Find a cycle in a directed graph, if any | edges → {has_cycle, cycle} | circular-dependency diagnosis |
| shortest_path_unweighted | Fewest-hop path between two nodes | edges, start, end, directed: bool → path[] | BFS over many nodes [23] |
| shortest_path_weighted | Lowest-cost path between two nodes | edges with weights, start, end, directed → {path, cost} | Dijkstra by hand is error-prone [23] |
| find_connected_components | Groups of nodes connected to each other | edges, nodes → components[][] | exact traversal |
| list_reachable_nodes | Everything reachable from a node (transitive dependencies) | edges, start → nodes[] | transitive closure |
| critical_path_schedule | Earliest finish and critical path of tasks with durations and dependencies | tasks: [{id, duration, depends_on}] → {total_duration, critical_path, schedule} | project-schedule math [23] |
| minimum_spanning_tree | Minimum spanning tree of a weighted undirected graph | weighted edges → {edges, total_weight} | Kruskal by hand |
| node_degree_summary | In-degree and out-degree of every node | edges → [{node, in_degree, out_degree}] | exact counting [28] |

### 23. Geometry and geography

Gap: these are trigonometric, multi-step computations [23]. Coordinates are a canonical tool argument [8]. Drop first: `convex_hull_points`, `solve_triangle_from_sides`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| haversine_distance | Great-circle distance between two coordinates | lat1, lon1, lat2, lon2, unit: enum km/mi/nmi → distance | spherical trig [23] |
| initial_bearing | Initial compass bearing from one coordinate to another | lat1, lon1, lat2, lon2 → degrees | atan2 sign handling |
| destination_point | Coordinate reached by travelling a distance on a bearing | lat, lon, bearing, distance, unit → {lat, lon} | spherical trig |
| geographic_midpoint | Midpoint of two or more coordinates | points: list[{lat, lon}] → {lat, lon} | naive averaging is wrong near the antimeridian |
| dms_to_decimal_degrees | Convert degrees-minutes-seconds to decimal degrees | text such as 40°26′46″N → value | parsing plus sign from hemisphere |
| decimal_degrees_to_dms | Convert decimal degrees to degrees-minutes-seconds | value, axis: enum lat/lon → text | base-60 remainders |
| polygon_area_planar | Area of a planar polygon (shoelace formula) | points: list[[x, y]] → area | many cross-products |
| point_in_polygon | Whether a point lies inside a planar polygon | point, polygon → {inside} | ray-casting by hand |
| bounding_box_of_points | Minimum and maximum of x/y or lat/lon over points | points → {min_x, min_y, max_x, max_y} | long-list min/max [28] |
| euclidean_distance | Distance between two points in N dimensions | a: list, b: list → distance | square roots of sums |
| solve_triangle_from_sides | Angles and area of a triangle from three sides | a, b, c → {angles, area, valid} | law of cosines and Heron |
| convex_hull_points | Convex hull of a set of 2-D points | points → hull[] | algorithmic |
| geohash_encode | Encode a coordinate as a geohash | lat, lon, precision → geohash | bit interleaving |
| geohash_decode | Decode a geohash to a coordinate and error bounds | geohash → {lat, lon, lat_error, lon_error} | same |

### 24. Color

Gap: these are exact numeric colour-space and contrast formulas (WCAG), which are multi-step arithmetic [23]. No direct agent-failure study was found. Drop first: `color_harmony_palette`, `rgb_to_cmyk`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| hex_color_to_rgb | Convert #RRGGBB or #RGB to RGB components | hex → {r, g, b} | hex arithmetic |
| rgb_to_hex_color | Convert RGB components to a hex colour | r, g, b → hex | same |
| rgb_to_hsl | Convert RGB to hue, saturation, lightness | r, g, b → {h, s, l} | piecewise formulas (`colorsys`) |
| hsl_to_rgb | Convert HSL to RGB | h, s, l → {r, g, b} | same |
| rgb_to_hsv | Convert RGB to hue, saturation, value | r, g, b → {h, s, v} | same |
| rgb_to_cmyk | Convert RGB to naive CMYK percentages | r, g, b → {c, m, y, k} | low gain |
| wcag_contrast_ratio | WCAG contrast ratio of two colours and AA/AAA pass status | foreground, background → {ratio, aa_normal, aa_large, aaa} | gamma-corrected luminance is never computed correctly by eye |
| mix_two_colors | Blend two colours by a ratio | color_a, color_b, ratio → hex | per-channel arithmetic |
| adjust_color_lightness | Lighten or darken a colour by a signed amount in HSL | color, amount → hex | colour-space round trip |
| color_harmony_palette | Complementary, triadic or analogous colours for a base colour | color, scheme: enum → colors[] | hue rotation arithmetic |
| nearest_css_color_name | Closest CSS named colour to a colour | color → {name, hex, distance} | needs the 148-name table plus distance |

### 25. Matrices and vectors (small inputs)

Gap: matrix operations are long, compositional arithmetic [23], and code offloading wins on such math [2]. Use `Fraction` for exact results. Drop first: `matrix_transpose`, `cross_product_3d`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| matrix_multiply | Multiply two matrices (size cap) | a: list[list], b: list[list] → matrix | many dot products [23] |
| matrix_transpose | Transpose a matrix | matrix → matrix | low gain for small matrices |
| matrix_determinant | Exact determinant | matrix → value | cofactor expansion |
| matrix_inverse | Exact inverse, or an error for singular matrices | matrix → matrix | Gauss-Jordan with fractions |
| solve_linear_system | Solve Ax = b exactly | a: matrix, b: list → {solution, unique} | elimination steps compound [23] |
| matrix_rank | Rank of a matrix | matrix → rank | row reduction |
| dot_product | Dot product of two vectors | a, b → value | long sums of products |
| cross_product_3d | Cross product of two 3-D vectors | a, b → vector | sign pattern slips |
| vector_magnitude | Euclidean norm of a vector | vector → value | square root of sums |
| vector_cosine_similarity | Cosine similarity of two numeric vectors | a, b → value | composite arithmetic |

### 26. Bits, bytes and binary data

Gap: these are byte-level and bit-level exact operations, which are invisible through tokens [22]. Data-size unit confusion (KB vs KiB) is a ratio problem [25]. Drop first: `estimate_transfer_time`, `swap_byte_order`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| convert_data_size | Convert between bits, bytes and SI or IEC multiples (kB, KiB, MB, MiB, …) | value, from_unit, to_unit → value | 1000 vs 1024 confusion [25] |
| format_bytes_human | Render a byte count as "1.5 KiB" or "1.5 kB" | bytes, standard: enum si/iec → text | exact boundaries |
| parse_human_data_size | Parse "1.5GB" or "512 MiB" into bytes | text → bytes | canonicalization [8] |
| bitwise_operation | Apply AND, OR, XOR, NOT or shifts at a bit width | a, b, operation: enum, width → {decimal, hex, binary} | bit-level arithmetic |
| count_set_bits | Number of 1 bits in an integer | value → count | counting [22] |
| integer_to_twos_complement | Two's-complement bit pattern of a signed integer | value, width → {binary, hex} | sign-extension slips |
| twos_complement_to_integer | Signed value of a two's-complement pattern | bits_or_hex, width → value | same |
| pack_binary_values | Pack values into bytes using a struct format | format, values → hex | endianness and padding (`struct`) |
| unpack_binary_values | Unpack hex bytes using a struct format | format, hex → values[] | protocol and file-header debugging |
| swap_byte_order | Reverse the byte order of a hex value | hex → hex | low gain |
| convert_unix_permissions | Convert between octal (755) and symbolic (rwxr-xr-x) permissions | value → {octal, symbolic} | bit masks |
| estimate_transfer_time | Time to move a data size at a bandwidth | size, size_unit, bandwidth, bandwidth_unit → {seconds, human} | bits vs bytes trap |
| image_dimensions_from_base64 | Width, height and format from a PNG, GIF, JPEG or BMP header given as base64 | data_base64 → {format, width, height} | header bytes cannot be read in tokens |

### 27. Markdown and HTML structure

Gap: concise, structured views of documents beat whole-document dumps [6][15][19]. Extracting structure from long text exactly is a counting and indexing task [22][28]. Drop first: `markdown_to_plain_text`, `render_text_table`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| extract_markdown_headings | Outline of headings with levels and line numbers | markdown → [{level, text, line}] | concise structure instead of the full doc [15] |
| build_markdown_table | Render rows as an aligned Markdown table | headers, rows, alignments → markdown | column padding and escaping pipes |
| parse_markdown_table | Parse a Markdown table into row objects | markdown → records[] | exact cell splitting |
| extract_markdown_links | All links with their text and target | markdown → [{text, url, line}] | exhaustive extraction |
| extract_fenced_code_blocks | Code blocks with their language tags | markdown → [{language, code, start_line}] | exact boundaries |
| generate_markdown_toc | Table of contents with GitHub-style anchors | markdown, max_level → markdown | anchor slug rules |
| markdown_to_plain_text | Strip Markdown syntax to plain text | markdown → text | low gain |
| split_markdown_by_heading | Split a document into sections at a heading level | markdown, level → [{heading, content}] | exact chunking |
| render_text_table | Render rows as a fixed-width plain-text table | headers, rows → text | column-width arithmetic |
| html_table_to_records | Parse HTML tables into row objects | html, table_index → records[] | nested tags (`html.parser`) |
| extract_html_links | All anchor links with text from HTML | html, base_url → [{text, url}] | exhaustive extraction; resolves relatives |

### 28. Pattern extraction from text

Gap: exhaustive extraction over long text drops and invents items [26][28], and canonical values are needed downstream [8]. Drop first: `extract_quoted_strings`, `extract_mentions`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| extract_urls | All URLs in a text | text → urls[] | exhaustive, exact [26] |
| extract_email_addresses | All email addresses in a text | text → addresses[] | same |
| extract_numbers | All numbers, with signs, decimals and grouping | text, decimal_separator → values[] | canonicalization [8] |
| extract_dates | All date mentions normalized to ISO 8601 | text, day_first: bool → [{text, date}] | canonicalization [8][24] |
| extract_hashtags | All #hashtags | text → tags[] | exhaustive |
| extract_mentions | All @mentions | text → mentions[] | exhaustive |
| extract_ip_addresses | All valid IPv4 and IPv6 addresses | text → addresses[] | validates, not just pattern-matches |
| extract_json_from_text | JSON objects or arrays embedded in prose or code fences | text → documents[] | balanced-brace scanning plus parsing |
| extract_quoted_strings | All quoted substrings | text, quote_characters → strings[] | escaped quotes |
| extract_phone_numbers | Phone-number-like sequences | text → numbers[] | heuristic; flag as such |
| extract_money_amounts | Currency amounts with symbol or code | text → [{currency, amount}] | canonicalization ("$1.2k") [8] |
| extract_key_value_pairs | "key: value" or "key=value" pairs from lines | text, separator → object | exact parsing of logs and config dumps |

### 29. Source code analysis (Python `ast`, `tokenize`, `shlex`; never executes code)

Gap: guardrails such as syntax checking on edit improve agents (18.0% vs 15.0%) [6], and concise structural views beat whole files [6][15]. Drop first: `strip_python_comments`, `list_todo_comments`. No overlap with `code_execution` (nothing runs) or `code_search` (operates on given text, not files).

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| check_python_syntax | Parse Python source and report the first syntax error | source → {valid, error, line, column} | the lint-on-edit guardrail [6] |
| list_python_functions | Functions and methods with arguments, decorators and lines | source → [{name, args, line, decorators}] | concise structure [15] |
| list_python_classes | Classes with bases and method names | source → [{name, bases, methods, line}] | same |
| list_python_imports | All imported modules and names | source → imports[] | exhaustive |
| count_lines_of_code | Code, comment, docstring and blank line counts | source → {code, comment, blank, total} | counting [28] |
| extract_python_docstrings | Module, class and function docstrings | source → [{name, docstring}] | exact extraction |
| get_python_function_signature | Signature of a named function | source, function_name → signature | precise defaults and annotations |
| find_python_name_usages | Lines where an identifier is referenced | source, name → [{line, column, context}] | exhaustive [28] |
| python_cyclomatic_complexity | Cyclomatic complexity per function | source → [{name, complexity}] | branch counting [28] |
| is_valid_python_identifier | Whether a string is a valid, non-keyword identifier | text → {valid, reason} | soft keywords and Unicode rules |
| python_literal_to_json | Convert a Python literal (repr of dict/list) to JSON safely | text → document | `ast.literal_eval`; True/None/tuple handling |
| strip_python_comments | Remove comments while keeping strings intact | source → source | `tokenize`-exact |
| find_unused_python_imports | Imported names never referenced | source → names[] | static check |
| list_todo_comments | TODO/FIXME/XXX comments with line numbers in any source text | source, tags → [{tag, line, text}] | exhaustive scan |
| shell_split_command | Split a shell command line into arguments | command → args[] | POSIX quoting rules (`shlex`) |
| shell_quote_arguments | Join arguments into a safely quoted shell command line | args → command | quoting bugs are security bugs |

### 30. Network address math (`ipaddress`)

Gap: subnet math is bit-level arithmetic [22][23] that operators routinely get wrong, and exact containment checks matter for security. Drop first: `ip_to_reverse_dns_name`, `normalize_mac_address`.

| tool name (snake_case) | one-line purpose | inputs → output | why an agent needs it (what it does badly in tokens) |
|---|---|---|---|
| validate_ip_address | Validate an IPv4 or IPv6 address and report its version | text → {valid, version, normalized} | leading zeros, scoped IPv6 |
| cidr_network_details | Network, broadcast, netmask, host count and host range of a CIDR | cidr → details | bit masks |
| check_ip_in_networks | Which of several CIDRs contain an address | ip, networks → matches[] | containment math |
| split_cidr_into_subnets | Split a network into subnets of a new prefix (cap) | cidr, new_prefix → subnets[] | enumeration [26] |
| ip_range_to_cidrs | Minimal CIDR blocks covering a start-to-end range | start_ip, end_ip → cidrs[] | algorithmic |
| collapse_cidr_list | Merge overlapping and adjacent networks | cidrs → cidrs[] | exact aggregation |
| classify_ip_address | Private, loopback, link-local, multicast, reserved or global | ip → {category} | RFC tables |
| normalize_ipv6_address | Compressed and exploded forms of an IPv6 address | ip → {compressed, exploded} | zero-run rules |
| ip_to_reverse_dns_name | Reverse-DNS (PTR) name of an address | ip → name | nibble reversal for IPv6 |
| convert_ip_to_integer | Convert an IP address to its integer value | ip → integer | 32/128-bit arithmetic |
| netmask_to_prefix_length | Convert a dotted netmask to a prefix length | netmask → prefix | bit counting [22] |
| normalize_mac_address | Validate and reformat a MAC address | text, style: enum colon/hyphen/dot → mac | low gain |

### Out of default scope (needs network/filesystem)

These do not count toward the 461. Evidence that agents use them: they dominate the MCP reference set (Fetch, Filesystem, Git) [20] and real servers [19]. The SDK already ships `operations` (fetch, search), `code_search`, `bash`, and filesystem tools, so most would duplicate existing built-ins.

| tool name (snake_case) | one-line purpose | inputs → output | why it is out of scope |
|---|---|---|---|
| http_get_json | Fetch a URL and parse JSON | url → document | network; overlaps `operations/fetch` |
| resolve_hostname | DNS lookup of a hostname | host → addresses[] | network; nondeterministic |
| check_url_status | HTTP status of a URL | url → status | network |
| currency_exchange_convert | Convert money using live rates | amount, from, to → amount | network; rates change |
| public_holidays_for_country | Holidays for a country and year | country, year → dates[] | needs maintained data or network; `business_days_between` takes a holiday list instead |
| read_text_file_lines | Read a line range from a file | path, start, end → text | filesystem; duplicates existing filesystem tools |
| hash_file | Hash a file on disk | path, algorithm → hex | filesystem read; `compute_base64_content_hash` covers content passed in |
| list_directory_tree | Tree listing of a directory | path, depth → tree | filesystem; duplicates `code_search` glob |

## Recommended grouping for an SDK

- **Ship category toolsets, not one flat list, and never attach the whole library by default.** Selection accuracy degrades past 30–50 tools [17], and one production study puts the 90% line at 10–15 tools for small models [21]. LangChain saw a 2% collapse when 7 unrelated domains were loaded [14]. The 30 categories above map naturally onto toolsets a developer attaches selectively.
- **Keep each attachable toolset at or under about 15–20 tools.** OpenAI suggests fewer than 20 functions per turn [18], and [21] recommends 10–15 per context. Larger categories (dates with 27, statistics with 24, randomness folded into probability with 24, JSON with 22, encoding with 21) should be split into sub-toolsets (e.g. `dates_core` and `dates_scheduling`) or trimmed.
- **Offer a lookup or search over the prebuilt catalogue, with deferred loading.** Tool search lifted accuracy from 49% to 74% and cut definitions by about 85% [16]. RAG-MCP tripled selection accuracy [12]. Anthropic recommends tool search at 10+ tools and keeping the 3–5 most-used tools always loaded [17]. The SDK's existing `mcp/search` and `tools/catalog.py` may already provide the mechanism, which is for the spec author to check.
- **Write descriptions for retrieval as well as for the model.** Retrieval errors cause nearly half of failures on large toolsets [13], and generic IR models are weak at tool retrieval [11]. Include the plain words users say ("how many days", "count letters", "decode base64") and keep a category prefix or tag "so one search matches the whole group" [17].
- **Use unique, descriptive names and record the category as metadata.** Collisions are rife in the wild [19], and whether a prefix or a suffix works better varies by model [15]. Verb-object names (`count_words`, `csv_filter_rows`) are unambiguous without forcing a namespace prefix onto every tool.
- **Avoid putting overlapping tools in one toolset.** Overlap causes tool-space interference [19] and distracts agents [15]. In particular, do not place `calculator` in the same default set as `decimal_arithmetic` and the big-integer tools without descriptions that clearly say when to use each.
- **Provide a small "essentials" toolset.** A starter set of about 10–15 of the highest-evidence tools (e.g. `days_between_dates`, `add_to_date`, `convert_datetime_timezone`, `count_character_occurrences`, `count_words`, `sum_decimal_list`, `compare_two_lists`, `sort_list_values`, `json_get_value_at_path`, `base64_decode_text`, `regex_test_samples`, `convert_length`) mirrors "keep the 3–5 most-used tools loaded" [17] and the evidence in section 3.
- **Make every tool callable as a plain Python function as well as a model tool.** Code-as-action [5] and programmatic tool calling (37% fewer tokens) [16] mean an agent using `code_execution` benefits from importing the same functions. CRAFT's toolsets are code snippets [4].
- **Cap and summarise outputs uniformly.** A shared cap (e.g. a maximum item count plus a truncation notice that suggests a narrower query) follows [6][15][19]. It belongs in one canonical helper rather than in each tool.
- **Attach only relevant categories.** Models must abstain when no tool fits [7], and irrelevant domains reduce accuracy [14]. Documentation should say "attach the categories your agent needs".

## Candidates I rejected

| idea | reason rejected |
|---|---|
| evaluate_math_expression | duplicates the existing `calculator` built-in |
| run_python_snippet | duplicates `code_execution`; unsafe as a "simple" tool |
| apply_unified_patch_to_text | overlaps `editing/patch` |
| grep_text_files / glob_files | duplicates `code_search` (grep, glob) |
| fetch_url / web_search | network; duplicates `operations/fetch` and `operations/search` |
| read_file / list_directory | filesystem; duplicates existing filesystem tools |
| bayes_posterior_probability | likely overlaps `reasoning/bayesian_update` |
| expected_value | likely overlaps `reasoning/expected_value_trace` |
| weighted_decision_matrix | likely overlaps `reasoning/decision_matrix_trace` |
| fermi_estimate | overlaps `reasoning/fermi_estimate`; not deterministic computation |
| estimate_token_count | heuristic, provider-specific, and likely overlaps context stats tools |
| parse_yaml / yaml_to_json | YAML is not in the standard library (PyYAML) |
| generate_secure_token / generate_password | `secrets` cannot be seeded, so it is nondeterministic and untestable by value; the spec author may admit one as an explicitly flagged exception |
| generate_totp_code | handles credentials (shared secrets) |
| service_port_lookup | `socket.getservbyname` reads the OS services file, so it is platform-dependent |
| guess_mime_type_from_filename | `mimetypes.guess_type` reads system files and the Windows registry after `init()`, so it is platform-dependent; it is only acceptable with a fixed built-in table |
| utm_coordinate_conversion | not simple; error-prone to implement correctly |
| detect_language / spell_check / sentiment | needs models or dictionaries; not stdlib or deterministic |
| html_to_markdown | ambiguous mapping; not simple |
| pdf_text_extract / docx_to_text | not stdlib |
| uppercase_text / lowercase_text / echo_text | trivially done in-context; no capability gain |
| ordinal_suffix (22 → "22nd") | trivially done in-context |
| add_two_numbers | trivial for small numbers; the big-integer and decimal tools cover the hard cases |
| currency_exchange_convert | needs live rates (network); listed out of scope above |
| holiday_lookup_by_country | needs maintained data; `business_days_between` accepts a caller-supplied holiday list instead |
