LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — The core is sound: the journal, batch admission, the cap arithmetic under one lock, and cancellation all hold up. But one Blocker lets a pair escape its own error guard and lose its siblings' cards, and three Majors need small local fixes.

Reviewed: `git diff origin/main...def85360`. HEAD `857921bc` differs from `def85360` only in `docs/spec/infinite-memory-agent/pipeline.md`. Scratch scripts are under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/316f126c-6db0-45d5-b506-cdb76c0921d5/scratchpad/s4-engineering/` (abbreviated `$S` below). Every `python` command runs from the worktree with `PYTHONPATH=$(pwd)` (`PYTHONPATH="$(pwd);$S"` for the mutation runs).

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The journal is a correct write-ahead log.**
  - Each record is opened, written, flushed, fsynced and closed under a class lock (`journal.py:180-189`).
  - A torn tail is skipped on read and truncated before the next append. A complete last line that lacks its newline gets a `\n` prefix (`journal.py:129-142`, `181-185`).
  - `find` checks the run id against the pattern before it builds a path (`journal.py:78`).
  - AC-21's path-escape case plants a decoy journal, so it would catch a regression.
- **Batch admission is check-then-reserve with no `await` in between.** `_check` and the `pair_started` loop run back to back (`launch.py:124-133`). Sibling generators that launch nested batches therefore cannot interleave past `max_agents`. A batch of replays only skips `ParallelPipeline` (`launch.py:137`).
- **Every workspace write is synchronous under one class-level lock.** Usage is recounted from disk inside the lock (`workspace.py:112-147`, `152-173`), and ids are `max(live ∪ superseded) + 1`, so concurrent pairs never share an id (AC-5 asserts this).
- **Path rules hold on Windows.** The probe refused all of these: `SEED/brief.md`, `Seed/new.md`, `ENTRIES.JSONL`, `Files.jsonl`, `.RUNS/x.md`, `notes/../seed/brief.md`, `../x.md`, `D:x.md` and `/x.md`. `resolve()` normalises case for existing components, and nothing outside the root was written.
- **Cancellation propagates.** The guard tuple `(VidbyteSdkError, OSError, ValueError)` leaves `BaseException` alone. AC-23 proves the generator sees `CancelledError` and the journal stays resumable.

## FINDINGS (ranked)

### R-E1 [Blocker] [failure modes] Card build and journal write run outside the pair guard

`vidbyte/agents/infinite/launch.py:249-253`, with `vidbyte/agents/infinite/journal.py:187` and `vidbyte/agents/infinite/memory.py:98-99`.

A pair's own result card and `pair_finished` record are built and written after the guard. Any error there escapes the stage. The parent loses every sibling's card, contrary to INV-29 and the field-guide stage rule.

**Evidence.** The guard ends at `launch.py:244`:
```
except (VidbyteSdkError, OSError, ValueError) as exc:
    verdict, review = InfiniteVerdict.UNCHECKED, self._error_text(exc)
...
self.result = InfiniteResultCard(name=..., files=files)   # line 252, unguarded
launch.journal.pair_finished(self.key, self.result)        # line 253, unguarded
```
Two triggers make it fail:
- `InfiniteResultCard` validates `files` with `_text_items(... one_line)` (`lib/dataclasses/infinite.py:208`). But `memory.py:98` stores the model's raw `path`, and `_note_path` never checks it for line breaks.
- The journal writes `json.dumps(record, ensure_ascii=False)` as UTF-8, which raises on a lone surrogate. A broken emoji in model output is legal JSON (`"\ud83d"`) and decodes to one.

**Reproduction 1.**
```
python $S/repro_card_outside_guard.py
```
Generator `a` writes `notes/a\u2028b.md`, a legal file name on Windows and POSIX.
```
launch_subagent result: [tool_error kind=execution_error] | Tool execution failed: Each item of InfiniteResultCard.files must be one line of non-blank text; got 'notes/a\u2028b.md'.
journal events: ['run_started', 'pair_started', 'pair_started', 'pair_finished', 'run_finished']
pair_finished keys: ['root/b']
```

**Reproduction 2.**
```
python $S/repro_surrogate.py
```
Generator `a` replies `"Prices found \ud83d"`.
```
case1 launch result: [tool_error kind=execution_error] | Tool execution failed: 'utf-8' codec can't encode character '\ud83d' ... surrogates not allowed
```

**Failure.** A batch of two pairs where one pair's card text holds a line separator or a lone surrogate:
- `gather` re-raises, and `launch_subagent` returns a tool error.
- The root never sees `b`'s finished card, and `a` has no `pair_finished`.
- If the error comes first, siblings still running become orphans (EC-41).
- Relaunching `a` runs the whole pair again and commits near-duplicate memories.

A staged entry holding a broken emoji takes the same route. Its commit fails inside the guard, and its text then lands in `dropped`, which is serialized outside the guard. On POSIX, `notes/x\n- fake.md (0 tokens): <instruction>` also injects a forged line into the map that every agent's system string carries.

This contradicts INV-29: "If anything after the generator returns raises, such as ... building the card ... pair_finished is written, the pair's card and every sibling's card are returned, and the launch_subagent call does not raise". It also contradicts field guide `jev-capability-layout.md:207`: "The stage catches `VidbyteSdkError` and reports that task failed, so `gather` keeps its siblings' work". `ConfigurationError` is a `VidbyteSdkError`.

**Smallest fix.** Three changes:
1. In `_note_path`, refuse a path whose `splitlines() != [path]`.
2. In `journal._append`, drop `ensure_ascii=False`. The journal is never grepped, so escaping is harmless.
3. Build the card and write `pair_finished` inside a `try`. On failure, fall back to a card with the error as its review, with `files=()` if needed.

**Spec IDs:** INV-29, INV-25, EC-9, FR-12, T-2.

### R-E2 [Major] [failure modes / Windows] A failed write leaks its temp file, and on Windows every append fails while another process reads the file

`vidbyte/agents/infinite/workspace.py:299-307`, with `memory.py:160,208,241` and `launch.py:338`.

Two problems combine here. `_replace` never removes its temp file when the write fails, and leaked temps count toward the caps. Deviation 5 sends every append through `os.replace`, which on Windows fails whenever another process holds the file open.

**Evidence.**
```
handle, temporary = tempfile.mkstemp(dir=target.parent, ...)
with os.fdopen(handle, "w", ...) as file: file.write(text)
os.replace(temporary, target)          # no try/finally; nothing unlinks on failure
```

**Reproduction 1, lone surrogate.**
```
python $S/repro_surrogate.py
```
Case 2 runs three root `remember` calls with a broken emoji, then one valid `write_note` at `max_files=5`:
```
case2 after call 4: ... This write would make 7 files, over max_files (5)
case2 files on disk: ['.entries.jsonl.0_uunk7t.tmp', '.entries.jsonl.vafrjk5g.tmp', '.entries.jsonl.ye73j1z5.tmp', 'entries.jsonl', ...]
```

**Reproduction 2, Windows reader.**
```
python $S/repro_replace_while_open.py
```
A separate Windows-native reader process holds `entries.jsonl` open:
```
commit: PermissionError [WinError 5] Access is denied: '...\memory\.entries.jsonl.77il...'
files now: ['.entries.jsonl.77ilgw3d.tmp', 'entries.jsonl', 'files.jsonl', 'superseded.jsonl']
```

**Reproduction 3, colon path.**
```
python $S/probe_paths.py
```
`write_note("entries.jsonl:evil.md")` returns `OSError [WinError 87]` and leaves a stray `.entries.jsonl` in the workspace root.

**Failure.**
- **Leaked files count.** Each failed write leaves a file that counts toward `max_files` and `max_tokens` and shows up in the map. A temp from a failed `entries.jsonl` rewrite is a full copy of the file. A refused or failed call has changed the disk.
- **Windows readers break commits.** Python, `findstr` or PowerShell run by a sibling's bash, the developer's editor, antivirus or the indexer can hold the file open. A plain append, which the spec designed (row 17: "appends the line"), would succeed.
- **One failed commit drops everything staged.** Inside a pair, `PermissionError` is an `OSError`, not a `ToolExecutionError`. `_commit` (`launch.py:338`) does not catch it, so the pair guard fires: verdict UNCHECKED, and every remaining staged entry is dropped.
- **Root tools return raw errors.** In the root's memory tools, the raw `OSError`/`ValueError` escapes `execute` and arrives as `Tool execution failed: ...`. That message has no quota line and no "what to fix", which INV-32 requires.

**Smallest fix.**
1. In `_replace`, wrap the write and `os.replace` in `try/except BaseException`: unlink the temp file, then re-raise.
2. Catch `OSError` and `ValueError` beside `ToolExecutionError` in the four memory-tool `execute` methods and in `_commit`.
3. Optionally, go back to append mode for plain appends, as spec row 17 says, and keep `os.replace` for the supersede rewrite and `edit_file`.

**Spec IDs:** INV-19 ("A refused write changes nothing on disk"), INV-32, INV-16, §12.3 row 17.

### R-E3 [Major] [idempotency] Replays are validated like new pairs

`vidbyte/agents/infinite/launch.py:124-125, 180-186`.

A finished task cannot be replayed once its own work superseded an entry its card names. The refusal also blocks every new task in the same batch.

**Evidence.**
```
pairs = {key: InfinitePair(...) for ... if self.journal.finished(key) is None}
self._check(cards, len(pairs))      # checks tools and "#N" context of ALL cards, replays included
```

**Reproduction.**
```
python $S/repro_replay_rejected.py
```
Task `a` has `context=["#1"]`, and its generator supersedes `#1` (passed). The root then relaunches `a` together with a new task `b`:
```
second launch (a replay + new b): [tool_error kind=execution_error] | No task was started, because the batch needs a change: Memory entry #1 is not a live entry in entries.jsonl ...
b's generator called: False
```

**Failure.** The scenario is a pair whose job was to update entry `#N`, which its card named as context, followed by a relaunch of the same card:
- The relaunch might happen after history trimming (INV-23), or after `resume()`, whose briefing says that relaunching a finished name replays it.
- The relaunch is refused instead of replayed, and any new sibling task in that call never starts.
- A grant the root no longer holds, such as an MCP server that was not reattached, refuses the replay the same way.

Spec row 20 orders "check the batch" before "split replays". That conflicts with INV-26, and Part B governs.

**Smallest fix.** Keep the size and duplicate-name checks over every card. Run the tools, context and `max_agents` checks only over the new cards: `_check(tuple(p.card for p in pairs.values()), len(pairs))` plus the duplicate check on `cards`.

**Spec IDs:** INV-26, D-22, AC-31, INV-28.

### R-E4 [Major] [test quality] Three guardrail rules have no test

`tests/features/infinite_memory_agent/test_infinite_memory_workspace.py:251-281`, `test_infinite_memory_acceptance.py:125`, and the absence of any pair-staging refusal test.

Mutations that delete each rule still pass 89/89.

**Evidence.** The plugin `$S/mutplug.py` applies one in-memory mutation through `-p mutplug`; nothing in the worktree is edited:
```
MUT=M1 python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider -p mutplug   → 89 passed
MUT=M2 ...                                                                                       → 89 passed
MUT=M3 ...                                                                                       → 89 passed
```

| Mutation | What it breaks | Why no test sees it |
|---|---|---|
| M1 | `InfiniteWorkspace.check_entry` is a no-op, so a pair agent's `remember` skips INV-17's token-cap, live-duplicate, "already staged as sN" and `supersedes` rules at stage time | No test calls `remember` from a pair agent with a rule-breaking entry. `grep "already staged"` over the pack finds nothing. |
| M2 | `edit_file` loses its `max_file_tokens` and `_room` caps | The AC-17 test checks only match counting |
| M3 | Every committed entry is stamped `by=<key>/gen`, even when the verifier staged it | No test has a verifier stage an entry; only `acceptance.py:125` checks `by`, and only for generator entries |

**Failure.** A regression that removes a guardrail on the edit path, or lets pair agents stage oversized or duplicate entries unchecked, ships green. These are the user's "deterministic guardrails" and "impose file limits", applied to INV-19's "every tool write". R-E1 and R-E3 also have no test that would catch them.

**Smallest fix.** Add three small cases:
1. `edit_file` whose replacement pushes the note over `max_file_tokens`, refused with bytes unchanged.
2. A generator `remember` with over-cap text, then the same text twice, refused with "already staged as s1".
3. A verifier that stages one entry and passes, with `by == "root/<name>/ver"`.

**Spec IDs:** INV-17, INV-19, INV-16, AC-14, AC-17.

### R-E5 [Minor] [test quality / ordering] The `asyncio.sleep(0)` exists only to set up AC-37

`vidbyte/agents/infinite/launch.py:227-231`.

The yield exists only to make AC-37's test setup reachable. Its `@intent` comment promises an ordering that real runners do not get.

**Evidence.** The comment reads: "...every generator has staged before a verdict." With `MUT=M4`, which removes the yield:
```
FAILED test_infinite_memory_verification.py::test_a_malformed_entries_line_drops_each_pairs_entries_but_the_run_finishes
1 failed, 88 passed
```
The AC-5 test still passes, so S3's claim that "AC-5's concurrency test also relies on it" is false.

**Failure.**
- With runners that really suspend (network calls), pair A can verify and commit while pair B's generator is still running. The comment describes a barrier that does not exist, and a maintainer may rely on it.
- AC-37 passes because production code was shaped to fit the test's scheduling. The test does not create the ordering it needs.

**Smallest fix.** Remove the sleep and make AC-37 order itself, for example both generators answering `after(Gate(2), reply(...))`. Or, if the S2 tests may not change, reword the comment to "lets non-suspending runners interleave; no ordering guarantee".

**Spec IDs:** AC-37, INV-12.

### R-E6 [Minor] [data/scale] Every write and every map render reads every workspace file in full

`vidbyte/agents/infinite/workspace.py:116-119, 143, 220-229` and `runtime.py:108-114`.

On top of the full reads, deviation 5 turned each append into a rewrite of the whole file.

**Evidence.**
- `commit_entry` reads `entries.jsonl` and `superseded.jsonl` (lines 116-119), then `_file_tokens()` reads them again with every other file (line 143). `write_note` reads the note and `files.jsonl` twice the same way.
- `_file_tokens` calls `path.read_text()` on every file, including binaries that bash dropped.
- `map_text` repeats the full read after every root tool iteration and for every child build.

**Failure.**
- NFR-4 ("one tool write reads the workspace at most once") is not met.
- Cost per write is O(workspace) reads plus an O(`entries.jsonl`) rewrite, while holding the lock on the event-loop thread.
- At 100× the default cap (about 100 MB), each `remember` reads about 200 MB and writes about 100 MB.
- A multi-GB file written by bash (T-1) is decoded in full on every root iteration. A `MemoryError` there is raised from the unguarded `_after_tool_iteration` (`agents/runtime.py:696`) and ends the run on every resume until the file is removed.

**Smallest fix.**
1. Pass the already-read bookkeeping texts into the usage count instead of re-reading them.
2. Count files above `max_tokens × 4` bytes from `stat().st_size` without decoding them; they are over the cap either way.

**Spec IDs:** NFR-4, T-1, EC-23.

### R-E7 [Minor] [context bound] The card's `dropped` and `files` lists are not capped

`vidbyte/agents/infinite/launch.py:362`.

The cards are exempt from `result_max_chars` (INV-38), so only INV-4's caps should bound them. Only `summary` and `review` are capped.

**Evidence.** `render` joins `card.dropped` and `card.files` in full. `dropped` items carry the full entry text plus the error message. `files` lists every path an agent appended to, which can reach about `max_files`.

**Failure.**
- A generator that appends to many notes, or a pair whose 10 staged entries all fail at commit, puts uncapped text into the root's conversation for each of up to `max_parallel` cards.
- This weakens NFR-7, which serves "treating the main agent's context window as somethingg that is VERY limitied".
- `max_entry_tokens` is developer-configurable without an upper bound, which makes it worse.

**Smallest fix.** Run the joined `dropped` and `files` strings through `_capped` in `render`.

**Spec IDs:** NFR-7, INV-4.

### R-E8 [Minor] [security] The settings-type refusal puts the full `repr` of the object into the error

`vidbyte/agents/infinite/agent.py:49`.

**Evidence.**
```
raise ConfigurationError(f"InfiniteMemoryAgent requires an InfiniteMemoryAgentSettings instance; got {type(settings).__name__}: {settings!r}.")
```
The JevAgent precedent (`agents/jev/agent.py:40`) names only the type.

**Failure.** A developer passes `InfiniteMemoryAgent({"name": ..., "api_key": os.environ[...]})`. The key ends up in the exception text, and so in tracebacks, CI logs and error trackers. This defeats T-3's `repr=False` convention. The INV-2 test (`contract.py:301`) accepts `"dict" in text`, so dropping the repr keeps it green.

**Smallest fix.** Remove `: {settings!r}` from the message.

**Spec IDs:** T-3, INV-2.

### R-E9 [Minor] [security, pre-existing helper] A UNC note path makes the host reach out to a remote server during path resolution

`vidbyte/agents/infinite/workspace.py:278` → `vidbyte/lib/tools/filesystem/permissions.py:16`.

**Evidence.** In `python $S/probe_paths.py`, `write_note("\\\\server\\share\\x.md")` returned:
```
FileNotFoundError: [WinError 53] The network path was not found
```
`resolve()` ran an SMB lookup before the scope check.

**Failure.** T-2 names a "stricter policy [that] denies EXECUTE" as a control. Under that policy, prompt-injected `write_note` (WRITE) or `read_lines` (READ) can still make Windows contact an attacker's host and offer NTLM credentials. That is a shorter path than T-2 traces.

**Smallest fix.** Refuse anchored paths (`PurePath(path).anchor`) before resolving. The real fix belongs in `resolve_scoped_path`, which every SDK filesystem tool uses, so this is a follow-up outside this PR.

**Spec IDs:** T-2, INV-20.

## VERIFIED CLAIMS

- **S3: "89 passed".** Held. The re-run gave `89 passed in 2.27s`.
- **S3 and spec §6.1: each pair writes `pair_finished` exactly once, and the launch call does not raise (INV-29).** Did not hold. A card-build or journal-encoding failure writes zero records, and the call returns a tool error (R-E1, reproduced).
- **S3 deviation 5: "a refused or interrupted write leaves the old file".** Partly held. The old file survives, but a temp file is leaked and counts toward the caps (R-E2, reproduced).
- **S3: "AC-5's concurrency test also relies on [the sleep]".** Did not hold. With the yield removed, only AC-37 fails (R-E5).
- **INV-26 / D-22: a finished name replays.** Did not hold when its context entry was superseded (R-E3, reproduced).
- **INV-24: ids never collide.** Held. Line 127 uses `max` over live plus superseded, and AC-5 asserts two distinct ids.
- **INV-31: `CancelledError` propagates.** Held. The guard excludes `BaseException`, and AC-23 passes.
- **NFR-3: one fsync per record.** Held (`journal.py:186-189`).
- **INV-38: `launch_subagent` is internal.** Held (`launch.py:109`).
- **INV-20: path safety on Windows.** Held for case variants, traversal, other drives and root-relative paths. The UNC path triggers a network lookup (R-E9), and a colon path raises a raw `OSError` and leaks a file (R-E2).
- **Torn journal tail; `run_finished` on its own line.** Held (`journal.py:129-142`, `181-185`; AC-22 green).
- **S3: "launch.py at 358 lines" after its header.** Held (`awk 'NR>12' | wc -l` gives 358).
- **S3: "Files outside §12.3: none".** Held. Every path in the diff stat maps to a row of §12.3.
- **Runtime stop reason serialized as a plain string.** Held. `_runtime_metadata` stores `stop_reason.value`.

## COMMANDS RUN

| Command | Final lines |
|---|---|
| `git status --porcelain; git log --oneline def85360..HEAD; git diff def85360 HEAD --stat` | Only `pipeline.md` differs. The one untracked file belongs to the sibling reviewer. |
| `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | `89 passed in 2.27s` |
| `python $S/repro_card_outside_guard.py` | `pair_finished keys: ['root/b']`; launch result `[tool_error ...] InfiniteResultCard.files must be one line` |
| `python $S/repro_surrogate.py` | case 1: `[tool_error] ... surrogates not allowed`; case 2: three `.entries.jsonl.*.tmp` files, then `would make 7 files, over max_files (5)` |
| `python $S/repro_replace_while_open.py` | `commit: PermissionError [WinError 5]`; `files now: ['.entries.jsonl.77ilgw3d.tmp', ...]` |
| `python $S/repro_replay_rejected.py` | `No task was started ... Memory entry #1 is not a live entry`; `b's generator called: False` |
| `python $S/probe_paths.py` | Protected and outside paths refused; `entries.jsonl:evil.md -> OSError [WinError 87]` plus a stray `.entries.jsonl`; UNC path gives `[WinError 53]` |
| `MUT=M1\|M2\|M3 python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider -p mutplug` | `89 passed` each |
| `MUT=M4 ... -p mutplug` | `1 failed, 88 passed` (AC-37 only) |
| `awk 'NR>12' vidbyte/agents/infinite/launch.py \| wc -l` | `358` |
| `grep -n "ensure_ascii=False" vidbyte/agents/infinite/*.py` | `journal.py:187`, `workspace.py:170`, `workspace.py:329` |
