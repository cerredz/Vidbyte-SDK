"""FILE: vidbyte/tools/builtins/claude/descriptions.py

PURPOSE: Holds the model-facing text of the fifteen Claude tools: one description per tool and one per parameter, each a few general sentences on what it does, when to use it, what it returns and how it fails.
ROLE IN CODEBASE: Read by the spec() of every tool in readiness.py, sessions.py, history.py and turns.py; a parameter shared by several tools, such as session_id or handle_id, has one description they all use.
ARCHITECTURE NOTE: Every value is one string literal, so a reader sees each text whole and the model reads exactly what is written here. The text names the tools and failure codes the model can act on and gives no example inputs.
COMMON MODIFICATION PATTERNS: A new tool adds one description constant here and one constant per new parameter; a changed behaviour updates the text of every tool it touches in the same edit.
KNOWN EDGE CASES: The steer and interrupt texts say that the call also stops any background tasks the turn started, because the SDK's interrupt stops them (D-3). The steer texts say that a steer whose interrupt is never answered ends the turn interrupted without sending the message.
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

CHECK_CLAUDE_READY_DESCRIPTION = "Checks whether Claude Code can run on this machine: that the claude extra is installed, the claude executable is found, its version is new enough, and an account or API key is signed in. Use it before starting the first session, or after a session fails to start, to learn what to fix. It starts Claude Code once without sending any prompt, so it costs nothing, and closes it again before it returns. It returns the executable's path, its version and whether it is signed in, together with the first problem found and its next step, or no failure when everything is ready."

LIST_CLAUDE_MODELS_DESCRIPTION = "Lists the models Claude Code offers the signed-in account, with each model's display name, description and supported effort levels. Use it to pick a model that exists, or after a turn fails because its model is unknown. It starts Claude Code once without sending any prompt and closes it again before it returns. When Claude Code is missing, too old or not signed in, the call fails with that problem's code and next step instead of returning a list."

GET_CLAUDE_RATE_LIMITS_DESCRIPTION = "Returns the latest rate-limit window of each kind that Claude Code reported during this host's sessions, with its status, its reset time and how much of it is used. Use it to judge how much capacity remains before starting more work, or after a turn failed because usage was limited. The windows come only from sessions this host ran, so the list is empty until the first turn reports one. While a window is rejected with a reset time still ahead and no allowed overage, new sessions are refused until it resets."

SPAWN_CLAUDE_SESSION_DESCRIPTION = "Starts a new Claude Code session that works on the prompt in the background, and returns its handle at once, before the work finishes. Use it to hand Claude Code one self-contained coding task, then call wait_claude_turn with the handle to collect the result. The session's folder, model, permissions, budget and every other setting are fixed by the developer, so only the prompt comes from this call. It fails without starting anything when Claude Code is not installed, the cap on live sessions is reached or the usage limit is reached, and the error names the next step."

CONTINUE_CLAUDE_SESSION_DESCRIPTION = "Sends a new prompt to an existing Claude Code session as a new turn that remembers everything the session did before. Use it to follow up on finished work in the same conversation, passing the session_id that a handle, a fork or list_claude_sessions returned. It returns a new handle at once while the turn runs in the background, so call wait_claude_turn to collect its result. It fails when the session is unknown, or when a turn in this host is still running in that session, in which case steer that turn or fork the session instead."

FORK_CLAUDE_SESSION_DESCRIPTION = "Copies an existing Claude Code session into a new session, whole or up to one message, and returns the new session's id. Use it to try another direction without changing the original, or to build on a session that a running turn is still using. The copy is made from the session files on disk, so it starts no Claude Code process, sends no prompt and costs nothing. Continue the new session with continue_claude_session; the call fails when the session or the message cannot be found."

LAUNCH_CLAUDE_SUBAGENTS_DESCRIPTION = "Starts one new Claude Code session for each prompt, all with the developer's settings, and returns one handle per prompt at once. Use it to run several independent tasks in parallel, then call wait_claude_turn on each handle to collect the results. At most limit of these sessions run at the same time, and the rest wait without starting until one finishes. Either every session is admitted or none is, and the call fails without starting anything when the cap on live sessions or the usage limit would be exceeded."

LIST_CLAUDE_SESSIONS_DESCRIPTION = "Lists the Claude Code sessions saved on this machine, most recent first, with each session's id, summary, folder, branch and timestamps. Use it to find the session_id of earlier work before continuing, forking or reading it. It reads the session files on disk without starting Claude Code, so it costs nothing. Give a directory to list only that project's sessions, and use limit and offset to read a long list in pages."

GET_CLAUDE_SESSION_INFO_DESCRIPTION = "Returns the summary of one Claude Code session: its title, first prompt, folder, branch, size and timestamps. Use it to check what a session was about, or that it still exists, before continuing or forking it. It reads the session files on disk without starting Claude Code. It fails with claude.session_not_found when the id is unknown, belongs to a subagent, or names a session that has no summary yet."

GET_CLAUDE_SESSION_MESSAGES_DESCRIPTION = "Returns one page of a Claude Code session's transcript, oldest first, with each message rendered as plain text. Use it to read what a session was asked and what it answered before deciding how to continue it. Tool calls, tool results and thinking appear as short markers rather than their full content. It reads the session files on disk without starting Claude Code, and fails with claude.session_not_found when the session does not exist."

WAIT_CLAUDE_TURN_DESCRIPTION = "Waits up to timeout_seconds for a turn to finish and returns its result. Use it after spawning, continuing, launching or steering to collect what Claude Code produced. If the time runs out first, it returns the turn's current state, still queued or running, and the turn keeps going, so wait again later. A finished result carries the status, the final text, any structured output and the cost, and a failed turn also carries its failure code and next step."

GET_CLAUDE_TURN_RESULT_DESCRIPTION = "Returns the current state of a turn without waiting: queued, running, completed, failed or interrupted. Use it to check on a turn between other work, or to read a finished turn's result again. A finished result carries the final text, any structured output and the cost, and a failed turn also carries its failure code and next step. It fails with claude.session_not_found when this host did not issue the handle_id."

STEER_CLAUDE_SESSION_DESCRIPTION = "Redirects a running turn with a new message: the call stops the turn's current step, and any background tasks the turn started, and the message then runs as the next turn in the same session. Use it when a turn is heading the wrong way and should change course without losing the work it has done. Only a running turn with no other steer pending can be steered, and the handle's final result is the result of the steered turn. If Claude Code never answers the stop, the turn ends interrupted and the message is never sent."

INTERRUPT_CLAUDE_TURN_DESCRIPTION = "Stops a turn: the call stops the turn's current step, and any background tasks the turn started, and returns the turn's state at once without waiting. Use it when the work is no longer needed or is going wrong and should not be redirected. A queued turn ends at once without starting, and a running turn ends interrupted once Claude Code answers or a short grace period passes. A turn that has already finished comes back unchanged, so calling it twice does no harm."

TRACK_CLAUDE_SESSION_USAGE_DESCRIPTION = "Returns what a session has used so far: its total cost in dollars, the tokens each model used, and the latest figures of each background task. Use it to watch spending while work runs, or to report the cost when it is done. The figures are the session's running totals from its latest result, so they are never added up across turns. Until the first result arrives, the total cost is empty and no models are listed."

PROMPT_DESCRIPTION = "The task for Claude Code to work on in this turn, written as complete instructions. Claude Code sees only this text and what the session already holds, so name every goal, file and constraint the work needs. The turn runs in the folder and with the settings the developer chose for these tools. It must not be empty."

SESSION_ID_DESCRIPTION = "The id of an existing Claude Code session, exactly as a handle, a fork or list_claude_sessions returned it. One session id names a whole conversation, with every turn it has had. Ids are not invented or guessed; take them from an earlier result. An unknown id fails with claude.session_not_found."

UP_TO_MESSAGE_ID_DESCRIPTION = "The id of the last message to keep in the copy, as get_claude_session_messages returned it. The new session holds the conversation up to and including that message, and nothing after it. Leave it out to copy the whole session. An id that does not belong to the session fails the call."

TITLE_DESCRIPTION = "A short title for the new session, shown when sessions are listed. It only labels the copy and changes nothing in its content. Leave it out to keep the title Claude Code would give it. It does not need to be unique."

PROMPTS_DESCRIPTION = "The tasks to start, one new session for each entry, each written as complete instructions. Every session sees only its own prompt, so each entry must stand on its own. The handles come back in the same order as the prompts. The list must not be empty, and neither may any entry."

LAUNCH_LIMIT_DESCRIPTION = "The largest number of these sessions that may run at the same time. The other sessions wait without starting until a running one finishes. A small number keeps the cost and the load on the machine bounded. It must be a whole number of at least one."

DIRECTORY_DESCRIPTION = "The project folder whose sessions to list, as an absolute path. Leave it out to list the sessions of every project on this machine. With a folder given, include_worktrees decides whether the folder's git worktrees count too. A folder with no saved sessions gives an empty list."

PAGE_LIMIT_DESCRIPTION = "The largest number of items to return in one page. Leave it out to return every item after offset. Use it together with offset to read a long list in pages. It must be a whole number of at least one."

OFFSET_DESCRIPTION = "How many items to skip before the page starts, counting from the first item. Leave it out to start at the first item. Add the size of the previous page to read the next one. It must be a whole number of zero or more."

INCLUDE_WORKTREES_DESCRIPTION = "Whether the sessions of the directory's git worktrees are listed too. It applies only when a directory is given. Leave it out to include them. Set it to false to list only the folder itself."

HANDLE_ID_DESCRIPTION = "The handle_id of a turn this host started, exactly as spawning, continuing or launching returned it. It names one turn of one session and stays valid after the turn finishes. A handle_id from another host, or one never issued, fails with claude.session_not_found. Pass it unchanged."

TIMEOUT_SECONDS_DESCRIPTION = "The longest time to wait, in seconds, before returning the turn's current state. Waiting never changes or stops the turn, so a short wait is safe. When the time runs out the turn keeps running and can be waited on again. It must be a number above zero."

MESSAGE_DESCRIPTION = "The new instructions for the turn. The steer stops the turn's current step, and any background tasks the turn started, and this message then runs as the next turn in the same session. Write it as a complete correction, because Claude Code reads it after stopping. If Claude Code never answers the stop, the turn ends interrupted and this message is never sent. It must not be empty."
