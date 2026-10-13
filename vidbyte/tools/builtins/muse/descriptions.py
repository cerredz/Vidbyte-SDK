"""FILE: vidbyte/tools/builtins/muse/descriptions.py

PURPOSE: Holds the model-facing description text of the twelve Muse host tools (check_muse_ready through track_muse_session_usage) and of their parameters.
ROLE IN CODEBASE: Read by the tool classes in vidbyte/tools/builtins/muse/tools.py when they declare their ToolSpec and ToolParameter values.
ARCHITECTURE NOTE: Plain string constants, each at least four general sentences with no concrete example values, so lint rule S025 can resolve and count them statically. Parameters whose meaning differs between tools (the cursor and the limit of a session list and of a view page) get one constant each.
FUNCTION INVENTORY: No functions. One description per tool and one per parameter meaning.
COMMON MODIFICATION PATTERNS: When a tool's behaviour changes, update its description here in the same change, keeping at least four sentences.
WHAT NOT TO DO IN THIS FILE: 1. Do not put a concrete example value, a path or a credential in a description. 2. Do not join adjacent string literals implicitly (S062); write each constant as one parenthesised expression with explicit spaces.
KNOWN EDGE CASES: The descriptions name limits by their meaning; the exact bounds are enforced by the records and the host, which name the refused argument.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 29-40; field guide model-facing-tool-contracts.md
TESTS: tests/features/muse_host/test_muse_host_tools.py
"""

from __future__ import annotations

CHECK_MUSE_READY_DESCRIPTION = (
    "Checks that Muse Code on this machine, or inside the configured WSL distro, can be used by this host. "
    + "It reads the installed version and runs the session protocol handshake on a short-lived process. "
    + "The answer reports the version, the protocol schema version and the command used to launch Muse; whether Muse is signed in is reported as unknown. "
    + "Run it first when a Muse call fails, because its error names the missing install, the missing distro or the upgrade that is needed."
)
LIST_MUSE_MODELS_DESCRIPTION = (
    "Lists the models Muse Code offers on this machine, with the provider, the profile and where the list came from. "
    + "The list comes from a short-lived Muse process and costs nothing. "
    + "An empty list is a normal answer, and then any model id you name is passed through to Muse unchecked. "
    + "Use it before naming a model, because an unknown model is refused before any session is created."
)
SPAWN_MUSE_SESSION_DESCRIPTION = (
    "Starts a new Muse Code session in this host's workspace with one prompt and returns a turn handle at once. "
    + "The turn keeps running on its own Muse process after the call returns, so pass the handle to wait_muse_turn for its result, to steer_muse_turn to add guidance or to interrupt_muse_turn to stop it. "
    + "Every approval request the user's own Muse rules do not already settle is denied, and every question to the user is cancelled, for turns started through this tool. "
    + "The turn is stopped when it reaches its time ceiling, and each host runs only a limited number of live turns at once."
)
CONTINUE_MUSE_SESSION_DESCRIPTION = (
    "Sends one more prompt to an existing Muse Code session in this host's workspace and returns a turn handle at once. "
    + "The session keeps its earlier conversation, and the new turn runs on its own Muse process after the call returns. "
    + "Pass the handle to wait_muse_turn for the result, and note that a session takes only one live turn at a time, here or in any other Muse client. "
    + "Approval requests outside the user's own Muse rules are denied and questions to the user are cancelled, as for a new session."
)
FORK_MUSE_SESSION_DESCRIPTION = (
    "Copies an existing Muse Code session into a new session and returns the new session, leaving the original untouched. "
    + "Without a last turn id the whole session is copied; with one, the copy ends after that turn. "
    + "No prompt is sent, so the fork costs nothing, and you can continue the copy with continue_muse_session. "
    + "A session that has a live turn on this host is refused until that turn ends."
)
LIST_MUSE_SESSIONS_DESCRIPTION = (
    "Lists one page of the Muse Code sessions that belong to this host's workspace. "
    + "Each entry gives the session id, its status, its model and provider, its turn count and its creation and update times. "
    + "When more sessions exist the answer carries a cursor, which you pass back unchanged to read the next page. "
    + "Use the listed ids with continue_muse_session, fork_muse_session, read_muse_session or page_muse_session."
)
READ_MUSE_SESSION_DESCRIPTION = (
    "Reads the metadata of one Muse Code session without its conversation items. "
    + "The answer gives the status, the id of a turn that is running, the model and provider, the session it was forked from, the turn count and its times. "
    + "A session Muse has not loaded yet is loaded once and read again. "
    + "Use page_muse_session to read what happened inside the session."
)
PAGE_MUSE_SESSION_DESCRIPTION = (
    "Reads one page of a Muse Code session's event view, oldest first within the page. "
    + "Each event is returned as compact JSON text with its method name, and an event too long for the result is cut and marked as truncated. "
    + "When more events exist the answer carries a cursor, which you pass back unchanged with the same direction to read the next page. "
    + "Page backward to read the most recent events first."
)
STEER_MUSE_TURN_DESCRIPTION = (
    "Adds guidance text to a running Muse turn without starting a new turn. "
    + "The text is delivered to the turn the handle names, and the answer gives Muse's acceptance status verbatim. "
    + "A turn that already finished cannot be steered; send a new prompt with continue_muse_session instead. "
    + "Very long text is refused before anything is sent."
)
INTERRUPT_MUSE_TURN_DESCRIPTION = (
    "Asks a running Muse turn to stop and returns at once with whether the turn was still running. "
    + "Muse is asked to interrupt the turn, and its process is stopped shortly afterwards if the turn does not end by itself. "
    + "A turn that already finished is left alone and nothing is sent. "
    + "Call wait_muse_turn afterwards to collect the interrupted turn's partial answer."
)
WAIT_MUSE_TURN_DESCRIPTION = (
    "Waits for a Muse turn to finish and returns its result, or reports that it is still running when the wait time runs out. "
    + "The result gives the status, the stop reason, the agent's reply text, the token usage when Muse reported it and every approval or question the host answered. "
    + "A wait that times out leaves the turn running, so you can wait again or interrupt it. "
    + "A turn that failed reports the same error on every wait."
)
TRACK_MUSE_SESSION_USAGE_DESCRIPTION = (
    "Reports the latest cumulative token usage of one Muse Code session. "
    + "It reads the session's event view backward until it finds a usage event, up to a fixed number of pages. "
    + "When no usage event appears within those pages the totals are empty and the answer is marked truncated. "
    + "Muse reports no cost, so the cost field is always empty."
)
PROMPT_PARAMETER_DESCRIPTION = (
    "The instruction Muse works on in this turn, written as plain text. "
    + "It is sent to Muse as one text part of the turn's input. "
    + "It must not be blank, and text Muse finds too large is refused without starting the turn. "
    + "Describe the task and the result you expect, because questions Muse asks the user are cancelled while the turn runs."
)
MODEL_PARAMETER_DESCRIPTION = (
    "The id of the Muse model the session should use, as list_muse_models returns it. "
    + "Leave it out to use the model Muse is configured with. "
    + "An id that is not in a non-empty model list is refused before any session is created. "
    + "When Muse lists no models, the id is passed through unchecked."
)
REASONING_EFFORT_PARAMETER_DESCRIPTION = (
    "How much reasoning Muse should spend on this turn. "
    + "It must be one of the reasoning effort values the Muse session protocol defines, written in lower case. "
    + "Leave it out to use Muse's own default for the model. "
    + "Any other value is refused before the turn starts."
)
TURN_SECONDS_PARAMETER_DESCRIPTION = (
    "The longest the turn may run, in seconds, before the host interrupts it. "
    + "It is a ceiling on the turn itself, not on this tool call, which returns as soon as the turn has started. "
    + "Leave it out to use the host's default ceiling. "
    + "It must be a positive number no larger than the host's maximum."
)
SESSION_ID_PARAMETER_DESCRIPTION = (
    "The id of an existing Muse session in this host's workspace. "
    + "Take it from list_muse_sessions or from the handle a spawn or continue call returned. "
    + "It must be a UUID in its usual dashed form. "
    + "A session Muse does not know is reported as not found."
)
LAST_TURN_ID_PARAMETER_DESCRIPTION = (
    "The id of the last turn the copy should keep, as Muse names it in the session's events. "
    + "Leave it out to copy the whole session. "
    + "It must not be blank, and an id that is not a turn of the session is refused. "
    + "The turn ids in a handle are this host's own ids and are not Muse turn ids."
)
LIST_CURSOR_PARAMETER_DESCRIPTION = (
    "The cursor from the previous page of this session list, passed back unchanged. "
    + "Leave it out to read the first page. "
    + "A cursor Muse no longer accepts is refused, and the list must then be started again without one. "
    + "Never build or edit a cursor yourself."
)
LIST_LIMIT_PARAMETER_DESCRIPTION = (
    "The largest number of sessions this page may hold. "
    + "Leave it out to use the host's default page size. "
    + "It must be a whole number of at least one and at most the host's maximum page size. "
    + "Muse may return fewer sessions than the limit even when more pages follow."
)
PAGE_CURSOR_PARAMETER_DESCRIPTION = (
    "The cursor from the previous page of this session's event view, passed back unchanged. "
    + "Leave it out to start at the beginning or, when paging backward, at the end of the view. "
    + "Use it with the same direction as the page it came from. "
    + "Never build or edit a cursor yourself."
)
PAGE_LIMIT_PARAMETER_DESCRIPTION = (
    "The largest number of events this page may hold. "
    + "Leave it out to use the host's default page size. "
    + "It must be a whole number of at least one and at most Muse's maximum page size. "
    + "Muse may return fewer events than the limit even when more pages follow."
)
DIRECTION_PARAMETER_DESCRIPTION = (
    "Which way to page through the session's event view. "
    + "It is forward to read from the oldest events on, or backward to read from the newest events back. "
    + "Leave it out to page forward. "
    + "Any other value is refused before anything is read."
)
HANDLE_PARAMETER_DESCRIPTION = (
    "The turn handle a spawn_muse_session or continue_muse_session call returned, passed back unchanged. "
    + "It is an object with the harness, the session id and the turn id, all as strings. "
    + "A handle from another host or another harness is reported as not found. "
    + "Finished turns are remembered for a limited number of turns only."
)
STEER_TEXT_PARAMETER_DESCRIPTION = (
    "The guidance to add to the running turn, written as plain text. "
    + "It is sent to Muse as one text part for the turn the handle names. "
    + "It must not be blank, and very long text is refused before anything is sent. "
    + "Keep it short and specific, because the turn is already working on its prompt."
)
TIMEOUT_PARAMETER_DESCRIPTION = (
    "The longest this call waits for the turn to finish, in seconds. "
    + "Leave it out to wait the default time. "
    + "It must be a positive number no larger than the tool's wait cap, which keeps the call under the calling agent's own tool time limit. "
    + "When the time runs out the turn keeps running, and you can wait again."
)
