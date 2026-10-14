# S0 research scout report: prebuilt agent tools

- **Stage:** S0 research scout
- **Date:** 2026-10-14
- **Produced:** `docs/spec/prebuilt-agent-tools/context/research.md`
- **Repository files read:** `request.md` only.
- **Directory listings:** `vidbyte/tools/builtins/` and its subfolders, names only. No source file in the repo was opened, and nothing under `docs/` other than `request.md` was read. No git commands were run.

## Result

- **Sources:** 30 cited in research.md, all opened during this run. 11 more were opened but not cited (listed below).
- **Catalogue:** 461 candidates in 30 categories. A script check confirmed that all names are unique, snake_case ASCII, start with a letter, are 64 characters or fewer, and that every table has exactly 4 columns.
- **Out-of-scope and rejected lists:** a separate 8-row table of network/filesystem tools, which do not count toward the 461, and a rejected-ideas table with 25 rows.
- **"Drop first" hints:** each category names its weakest candidates so the spec author can cut toward 250 or more quickly.

## Searches run (WebSearch)

1. `LLM tool selection accuracy degrades number of tools study 2025 arXiv "too many tools"`. This turned up secondary blogs, which pointed to arXiv 2606.30317 and RAG-MCP.
2. `Microsoft Research "tool-space interference" MCP era blog 2025`
3. `arXiv why do large language models struggle to count letters strawberry tokenization 2024`
4. `arXiv benchmark LLM date arithmetic calendar reasoning "Test of Time" temporal reasoning 2024`
5. `arXiv 2025 "Lost in Time" clock and calendar understanding multimodal LLM date arithmetic`
6. `arXiv LLM unit conversion benchmark errors physical units dimensional reasoning 2024 2025`
7. `arXiv LLMs base64 decoding encoding ability evaluation cipher tasks accuracy 2024 2025`
8. `arXiv large language models sorting long lists counting items accuracy degrades length benchmark 2024 2025`
9. `LangChain blog benchmarking agent tool calling performance many tools many domains react agent 2025`
10. `ToolHop arXiv 2025 multi-hop tool use benchmark locally executable tools`
11. `strands-agents-tools list of prebuilt tools calculator current_time github`
12. `MCP-Bench OR LiveMCPBench OR MCP-Universe arXiv 2025 benchmark many MCP tools agent performance`
13. `arXiv LLM regular expression generation correctness semantic equivalence benchmark errors 2024 2025`

## Pages opened (WebFetch)

**Cited in research.md (30):** Toolformer, PAL, Gorilla, CRAFT, CodeAct, SWE-agent (abstract and HTML), BFCL blog, ToolSandbox (abstract and HTML), NESTFUL, ToolHop, ToolRet, RAG-MCP, LiveMCPBench, LangChain single-agent benchmarking, Anthropic "Writing effective tools for agents", Anthropic "Advanced tool use", Anthropic tool-search docs, OpenAI function-calling guide, Microsoft tool-space interference blog, MCP servers repo and Time server README, MCP Server Architecture Patterns (abstract and HTML), Fu et al. letter counting, Faith and Fate (HTML), Test of Time (abstract and HTML Table 8), NUMCoT, SortBench, Lissard, Can We Count on LLMs, Base64Bench (LessWrong), Query4Regex (ACL Anthology).

**Opened but not cited (to stay at 30 or fewer, or because they were not needed):**
- tau-bench (arXiv 2406.12045): gpt-4o succeeds on less than 50% of tasks, and pass^8 is below 25% in retail.
- ToolLLM (2307.16789): 16,464 APIs across 49 categories, with an API retriever.
- LATM (2305.17126): tool maker/tool user; GPT-4 makes the tools and GPT-3.5 uses them, matching GPT-4 at lower cost.
- ToolACE (2409.00920): a pool of 26,507 APIs.
- API-Bank (2304.08244): 73 runnable API tools.
- MCP-Bench (2508.20453): 28 servers and 250 tools; the abstract reports no specific selection numbers.
- Counting Ability and Tokenization (2410.19730): tokenization causes substantial variation in counting results.
- Secret Collusion (2402.07510): the abstract has **no** base64 numbers. The "GPT-4 92% base64" figure appeared only in a search summary, so it was not cited.
- strands-agents/tools README: lists AWS Strands' prebuilt tools. Only `calculator` and `current_time` are pure-compute, and both are marked deprecated. Everything else is network, filesystem, or agent-control.
- Python docs for `zoneinfo` and `tomllib`: used for the niche facts below.

## Sources not opened, or unverified (none of these is cited in research.md)

- **Lost in Time (arXiv 2502.05092)** and the calendar-QA benchmark: seen in search results only.
- **RegexPSPACE (2025):** search results only.
- **MultiTempBench (2603.19017)** and **"Not All Time Is Gregorian" (ICLR 2026):** search results only.
- **DimEval (2312.17532):** search results only.
- **Mechanistic Interpretability of Large-Scale Counting (2601.02989):** search results only.
- **"BFCL: accuracy 43% → 2% when tools expanded 4 → 51":** this figure comes from secondary blogs (tianpan.co, stackone) and is unverified. LangChain's own post [14] is the primary source for the 2% figure, and it frames the cause as 7 *domains*, not 51 tools.
- **"Gan & Sun: >90% only up to ~30 tools, degrading beyond ~100":** this claim is cited secondhand inside arXiv 2606.30317. The RAG-MCP abstract page does not show it, so it is unverified.
- **MCP-Universe:** not found.
- **Remembered but not opened:** ToolkenGPT, AnyTool, "Less is More: optimizing function calling on edge devices" (2411.15399), and the Anthropic "Effective context engineering" post. These are unverified and were not cited.
- **Two URL changes:** the first OpenAI docs URL (`platform.openai.com`) redirected and was opened at `developers.openai.com`. The Query4Regex `preview.aclanthology.org` URL returned 404 and was opened at `aclanthology.org`.

## Confidence per section

| section | confidence | why |
|---|---|---|
| Sources | High | Every cited source was opened. Findings come from abstracts or HTML sections through a summarizing fetch, so exact wording can be paraphrased. Key numbers were read from tables where possible: ToT Table 8, SWE-agent Table 3, and the 2606.30317 tool-count study. |
| Tool design | High on direction, medium on thresholds | All sources agree that more tools means worse selection. The thresholds differ (10–15 [21], 20 or fewer [18], 30–50 [17]). [21] is observational and single-organisation, and [14] used 30 tasks per domain. The conflict between consolidation and single-purpose tools is stated explicitly. |
| Capability gaps | High for arithmetic, letter and list counting, sorting, list matching, date durations, base64, and regex. Medium for unit conversion (abstract-level). | The hashing and invisible-character gaps are argued from first principles, with no measuring source found. This is stated in research.md. |
| Catalogue | Medium-high | Stdlib feasibility was judged from knowledge of the standard library, not by writing code. Heuristic tools are flagged: `repair_json_text`, `extract_phone_numbers`, `count_sentences`, `readability_scores` (syllables), and the limited grammar of `resolve_relative_date_phrase`. Overlap with built-ins was judged from file names only (see open items). |
| Recommended grouping | Medium-high | Directly supported by [12][13][16][17][18][21]. Whether the SDK's `catalog.py` or `mcp/search` can host catalogue search is for the spec author to check. |
| Rejected candidates | High | Reasons are factual (not stdlib, network, duplicate name, platform-dependent). |

## Niche facts for the spec author

1. **`zoneinfo` on Windows needs the `tzdata` PyPI package.** Windows has no system IANA database, so without `tzdata` every `ZoneInfo(...)` raises `ZoneInfoNotFoundError` (Python docs). This affects about 8 timezone tools, and this machine is Windows. Either declare `tzdata` as a dependency (a first-party package, data only) or ship timezone tools that fail with a clear error.
2. **Python's integer-to-string limit.** Since 3.11, and backported to 3.10.7, converting an `int` with more than 4,300 decimal digits to `str` (or the reverse) raises `ValueError` (`sys.int_info.str_digits_check_threshold`). Big-integer, factorial, power, and Fibonacci tools need a digit cap below that, or a deliberate decision. Do not call `sys.set_int_max_str_digits`, because it is global state. This comes from memory of the CPython change (CVE-2020-10735) and was not re-opened this run.
3. **Stdlib version gates.**
   - `tomllib` is 3.11+ and read-only.
   - `statistics.correlation`, `covariance`, and `linear_regression` are 3.10+, but `correlation(method="ranked")` is 3.12+, so implement Spearman by hand.
   - `graphlib.TopologicalSorter` is 3.9+.
   - `math.comb`, `math.perm`, and `math.isqrt` are 3.8+.
   - The local interpreter here is 3.11.0. The SDK's minimum version is unknown to this scout.
4. **Platform-dependent stdlib to avoid.** `mimetypes.guess_type` reads system files and the Windows registry after `init()`. `socket.getservbyname` reads the OS services file. `locale` is global state.
5. **Safety caps.** `re` has no timeout (catastrophic backtracking), so cap the pattern and input length. `xml.etree` can be fed entity-expansion bombs, so reject DOCTYPE. Every enumerating tool (primes, permutations, dates, subnets, amortization rows) needs a documented maximum and a truncation notice [6][15][19].
6. **Built-in name overlap to check.** If `calculator` already does exact big-integer math, drop the first five rows of category 1. `reasoning/` contains `bayesian_update`, `expected_value_trace`, `decision_matrix_trace`, and `fermi_estimate`, so the matching computational tools were rejected. The context tools may already count tokens, so `estimate_token_count` was rejected.
7. **Category sizes that exceed the evidence-based per-attach limit of about 15–20:** dates (27), statistics (24), probability and randomness (24), JSON (22), text counting (21), encoding (21), and string transformation (20). Split or trim these.
8. **One time-dependent tool:** `current_datetime_in_timezone`. Tests need an injectable clock.
