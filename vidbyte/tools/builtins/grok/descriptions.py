"""FILE: vidbyte/tools/builtins/grok/descriptions.py

PURPOSE: Holds the model-facing description text of the ten Grok host tools (check_grok_ready through interrupt_grok_turn) and of their parameters.
ROLE IN CODEBASE: Read by the tool classes in vidbyte/tools/builtins/grok/tools.py when they declare their ToolSpec and ToolParameter values.
ARCHITECTURE NOTE: Plain string constants, each at least four general sentences with no concrete example values, so lint rule S025 can resolve and count them statically. Parameters whose meaning differs between a live turn and a one-shot run get one constant each.
FUNCTION INVENTORY: No functions. One description per tool and one per parameter meaning.
COMMON MODIFICATION PATTERNS: When a tool's behaviour changes, update its description here in the same change, keeping at least four sentences.
WHAT NOT TO DO IN THIS FILE: 1. Do not put a concrete example value, a path or a credential in a description. 2. Do not join adjacent string literals implicitly (S062); write each constant as one parenthesised expression with explicit spaces.
KNOWN EDGE CASES: The descriptions name limits by their meaning; the exact bounds are enforced by the records and the host, which name the refused argument.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 1-10; field guide model-facing-tool-contracts.md
TESTS: tests/features/grok_host/test_grok_host_tools.py
"""

from __future__ import annotations

CHECK_GROK_READY_DESCRIPTION = (
    "Checks that the Grok Build command-line agent on this machine can be used by this host. "
    + "It reads the installed version, runs the agent protocol handshake on a short-lived process and asks the command line whether it is signed in. "
    + "The answer reports the version, the protocol and agent versions, the sign-in methods and the model Grok uses by default. "
    + "Run it first when a Grok call fails, because its error names the missing install, the sign-in or the update that is needed."
)
LIST_GROK_MODELS_DESCRIPTION = (
    "Lists the models Grok Build offers on this machine, together with the model it uses by default. "
    + "Each model comes with the reasoning efforts it accepts, which are the only effort values the other Grok tools take for that model. "
    + "The list comes from a short-lived agent process and costs nothing. "
    + "Use it before naming a model or an effort, because an unknown model or effort is refused before any work starts."
)
SPAWN_GROK_SESSION_DESCRIPTION = (
    "Starts a new Grok Build session in this host's workspace with one prompt and returns a turn handle at once. "
    + "The turn keeps running on its own agent process after the call returns, so pass the handle to wait_grok_turn to collect its result or to interrupt_grok_turn to stop it. "
    + "Permission requests for edits, commands and other tool kinds are refused for turns started through this tool. "
    + "The turn is stopped when it reaches its time ceiling, and each host runs only a limited number of live turns at once."
)
RUN_GROK_ONCE_DESCRIPTION = (
    "Runs one headless Grok Build prompt in this host's workspace and waits for its final answer. "
    + "The run uses Grok's default permission mode and creates a new session, whose id is returned with the answer text and the stop reason. "
    + "The call blocks until the run ends, and a run that passes its time limit is stopped and reported as timed out. "
    + "Prefer spawn_grok_session for long work that should keep running while you do other things."
)
CONTINUE_GROK_SESSION_DESCRIPTION = (
    "Sends one more prompt to an existing Grok Build session in this host's workspace and returns a turn handle at once. "
    + "The session keeps its earlier conversation, and the new turn runs on its own agent process after the call returns. "
    + "Pass the handle to wait_grok_turn for the result or to interrupt_grok_turn to stop the turn, and note that one session takes only one live turn at a time. "
    + "Permission requests for edits, commands and other tool kinds are refused for turns started through this tool."
)
FORK_GROK_SESSION_DESCRIPTION = (
    "Copies an existing Grok Build session into a new session and runs one headless prompt on the copy, leaving the original untouched. "
    + "The source session must appear in this workspace's session list, and an optional new session id must not name an existing session. "
    + "The call blocks until the run ends and returns the answer text, the stop reason and the new session's id. "
    + "A run that passes its time limit is stopped and reported as timed out."
)
LIST_GROK_SESSIONS_DESCRIPTION = (
    "Lists one page of the Grok Build sessions that belong to this host's workspace. "
    + "Each entry gives the session id, its working folder and, when Grok has them, its title and last update time. "
    + "When more sessions exist the answer carries a cursor, which you pass back unchanged to read the next page. "
    + "Use the listed ids with continue_grok_session or fork_grok_session."
)
SEARCH_GROK_SESSIONS_DESCRIPTION = (
    "Finds the Grok Build sessions of this host's workspace whose title contains a query, ignoring letter case. "
    + "It reads the session list page by page up to a fixed page cap and returns the matches in listing order. "
    + "When the cap stopped the scan before the end of the list, the answer says the result may be incomplete. "
    + "Sessions without a title never match, so use list_grok_sessions to see every session."
)
WAIT_GROK_TURN_DESCRIPTION = (
    "Waits for a live Grok turn to finish and returns its result, or reports that it is still running when the wait time runs out. "
    + "The result gives the status, the stop reason, the agent's answer text, the usage when Grok reported it and every permission decision the host made. "
    + "A wait that times out leaves the turn running, so you can wait again or interrupt it. "
    + "A turn that failed reports the same error on every wait."
)
INTERRUPT_GROK_TURN_DESCRIPTION = (
    "Asks a live Grok turn to stop and returns at once with whether the turn was still running. "
    + "Grok is asked to cancel the turn, and its agent process is stopped shortly afterwards if it does not end by itself. "
    + "A turn that already finished is left alone and nothing is sent. "
    + "Call wait_grok_turn afterwards to collect the interrupted turn's partial answer."
)
TURN_PROMPT_PARAMETER_DESCRIPTION = (
    "The instruction Grok works on in this turn, written as plain text. "
    + "It is sent to Grok as one text message inside the session. "
    + "It must not be blank, and very long text is refused before any work starts. "
    + "Describe the task and the result you expect, because Grok cannot ask you questions while the turn runs."
)
ONE_SHOT_PROMPT_PARAMETER_DESCRIPTION = (
    "The instruction Grok works on in this headless run, written as plain text. "
    + "It reaches Grok on its command line, so it is limited to a moderate length and longer text is refused before the run starts. "
    + "It must not be blank. "
    + "Describe the task and the result you expect, because Grok cannot ask you questions during the run."
)
MODEL_PARAMETER_DESCRIPTION = (
    "The id of the Grok model to use, exactly as list_grok_models returns it. "
    + "Leave it out to use the model Grok uses by default. "
    + "The host confirms the model with Grok before any work starts and refuses an id Grok does not offer. "
    + "Ids that look like command-line flags or contain spaces are refused."
)
REASONING_EFFORT_PARAMETER_DESCRIPTION = (
    "How much reasoning the model should spend, as one of the effort values list_grok_models shows for the chosen model. "
    + "Leave it out to use the model's own default effort. "
    + "An effort the model does not list is refused before any work starts. "
    + "Higher efforts usually take longer and cost more."
)
TURN_SECONDS_PARAMETER_DESCRIPTION = (
    "The longest time in seconds this live turn may run before the host interrupts it. "
    + "Leave it out to use the host's default ceiling for live turns. "
    + "When the ceiling passes, Grok is asked to stop and the turn ends as interrupted by its deadline. "
    + "It must be a positive number within the host's maximum turn length."
)
ONE_SHOT_SECONDS_PARAMETER_DESCRIPTION = (
    "The longest time in seconds this headless run may take before it is stopped. "
    + "Leave it out to use the longest time a single tool call may block. "
    + "A run that passes it is stopped with all its processes and reported as timed out. "
    + "It must be a positive number no greater than that blocking limit, so use spawn_grok_session for longer work."
)
MAX_TURNS_PARAMETER_DESCRIPTION = (
    "The largest number of agent steps Grok may take in this headless run. "
    + "Leave it out to let Grok use its own step limit. "
    + "It must be a whole number within the host's allowed range. "
    + "A lower value keeps a run short and cheap, at the cost of possibly unfinished work."
)
SESSION_ID_PARAMETER_DESCRIPTION = (
    "The id of an existing Grok session in this host's workspace, exactly as list_grok_sessions or an earlier answer returned it. "
    + "It must be a dashed hexadecimal session id, and any other text is refused before any work starts. "
    + "A session that already has a live turn on this host is refused until that turn ends. "
    + "Find ids with list_grok_sessions or search_grok_sessions."
)
NEW_SESSION_ID_PARAMETER_DESCRIPTION = (
    "An optional id for the new session the fork creates, in the same dashed hexadecimal form as other session ids. "
    + "Leave it out to let Grok choose a new id, which the answer then reports. "
    + "It must differ from the source session id and must not name a session that already exists in this workspace. "
    + "Choosing it yourself lets you continue the fork later without reading the answer first."
)
CURSOR_PARAMETER_DESCRIPTION = (
    "The cursor from an earlier list_grok_sessions answer, passed back unchanged to read the next page. "
    + "Leave it out to start from the first page. "
    + "A cursor Grok no longer accepts is refused, and listing again without a cursor starts over. "
    + "Never build a cursor yourself, because its form belongs to Grok."
)
QUERY_PARAMETER_DESCRIPTION = (
    "The text to look for in session titles, matched without regard to letter case. "
    + "It must contain visible characters and stay short. "
    + "A session matches when its title contains the whole query as one piece of text. "
    + "Use a distinctive word or phrase from the title you remember."
)
LIMIT_PARAMETER_DESCRIPTION = (
    "The largest number of matching sessions to return. "
    + "Leave it out to use the host's default number of matches. "
    + "It must be a whole number from one up to the host's maximum. "
    + "Matches beyond the limit are left out in listing order."
)
HANDLE_PARAMETER_DESCRIPTION = (
    "The turn handle that spawn_grok_session or continue_grok_session returned, passed back as the same object. "
    + "It holds the harness name, the session id and the turn id, all as text. "
    + "A handle from another host or one dropped from the finished-turn history is reported as not found. "
    + "Do not edit any of its fields."
)
TIMEOUT_PARAMETER_DESCRIPTION = (
    "The longest time in seconds to wait for the turn before reporting that it is still running. "
    + "Leave it out to use the host's default wait time. "
    + "It must be a positive number no greater than the longest time a single tool call may block. "
    + "Waiting out this time never stops the turn, so you can wait again."
)

__all__ = [
    "CHECK_GROK_READY_DESCRIPTION",
    "CONTINUE_GROK_SESSION_DESCRIPTION",
    "CURSOR_PARAMETER_DESCRIPTION",
    "FORK_GROK_SESSION_DESCRIPTION",
    "HANDLE_PARAMETER_DESCRIPTION",
    "INTERRUPT_GROK_TURN_DESCRIPTION",
    "LIMIT_PARAMETER_DESCRIPTION",
    "LIST_GROK_MODELS_DESCRIPTION",
    "LIST_GROK_SESSIONS_DESCRIPTION",
    "MAX_TURNS_PARAMETER_DESCRIPTION",
    "MODEL_PARAMETER_DESCRIPTION",
    "NEW_SESSION_ID_PARAMETER_DESCRIPTION",
    "ONE_SHOT_PROMPT_PARAMETER_DESCRIPTION",
    "ONE_SHOT_SECONDS_PARAMETER_DESCRIPTION",
    "QUERY_PARAMETER_DESCRIPTION",
    "REASONING_EFFORT_PARAMETER_DESCRIPTION",
    "RUN_GROK_ONCE_DESCRIPTION",
    "SEARCH_GROK_SESSIONS_DESCRIPTION",
    "SESSION_ID_PARAMETER_DESCRIPTION",
    "SPAWN_GROK_SESSION_DESCRIPTION",
    "TIMEOUT_PARAMETER_DESCRIPTION",
    "TURN_PROMPT_PARAMETER_DESCRIPTION",
    "TURN_SECONDS_PARAMETER_DESCRIPTION",
    "WAIT_GROK_TURN_DESCRIPTION",
]
