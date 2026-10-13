"""FILE: vidbyte/tools/builtins/opencode/descriptions.py

PURPOSE: Holds the model-facing description text of the 18 opencode tools and of their parameters.
ROLE IN CODEBASE: Read by the tool classes in vidbyte/tools/builtins/opencode/read_tools.py and session_tools.py when they declare their ToolSpec and ToolParameter values.
ARCHITECTURE NOTE: Plain string constants, each at least four general sentences with no concrete example values, so lint rule S025 can resolve and count them statically. A parameter whose meaning differs between tools (a message id, a limit) has one constant per meaning.
FUNCTION INVENTORY: No functions. One description per tool and one per parameter meaning.
COMMON MODIFICATION PATTERNS: When a tool's behaviour changes, update its description here in the same change, keeping at least four sentences.
WHAT NOT TO DO IN THIS FILE: 1. Do not put an id, a model name, a URL, a key or any other concrete example in a description. 2. Do not join adjacent string literals implicitly (S062); write each constant as one parenthesised expression with explicit spaces. 3. Do not promise a parameter the tool does not accept; rules, folders and MCP commands are the developer's to set.
KNOWN EDGE CASES: Descriptions name other tools by their exact names so a model can chain them; they never name a credential's value.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.2 (Tools, rows 11-28); field guide model-facing-tool-contracts.md
TESTS: tests/features/opencode_host/test_opencode_host_tools.py
"""

from __future__ import annotations

CHECK_OPENCODE_READY_DESCRIPTION = (
    "Checks that the opencode server behind this host is healthy, recent enough, and able to run turns. "
    + "It reports the server version, the server address without any credentials, the providers that are connected, and the default model of each provider. "
    + "A server with no connected provider is reported as not signed in, together with the step that connects one. "
    + "Run it first when a session call fails in a way that suggests the server or its providers are not ready."
)
LIST_OPENCODE_MODELS_DESCRIPTION = (
    "Lists the models that the connected opencode providers offer, with their display names, status and context and output limits. "
    + "Only providers that are connected can serve a turn, so only their models are listed. "
    + "An optional provider id narrows the list to one provider, and an unknown provider id is reported with the ids that do exist. "
    + "Use the provider and model ids from this list, joined by a slash, as the model argument of spawn_opencode_session or continue_opencode_session."
)
LIST_OPENCODE_PROVIDERS_DESCRIPTION = (
    "Lists every model provider the opencode server knows, whether or not it is connected. "
    + "Each entry gives the provider id and name, where its configuration came from, the environment variables it reads, whether it is connected, its model ids and its default model. "
    + "Keys and provider options are never part of the result. "
    + "Use it to see which providers could be connected and to find a provider id for list_opencode_models."
)
GET_OPENCODE_PROVIDER_AUTH_DESCRIPTION = (
    "Lists the ways each opencode provider can be connected, such as an API key or a browser login. "
    + "The method types and labels are copied exactly as the server reports them, because that set of methods is open. "
    + "The call only reads the server's catalogue and connects nothing. "
    + "Use it to tell a person how a provider that is not connected yet can be connected outside this tool."
)
SPAWN_OPENCODE_SESSION_DESCRIPTION = (
    "Creates a new opencode session in this host's workspace and starts its first turn with the given prompt. "
    + "It returns a turn handle as soon as the server accepted the prompt, while the turn keeps running in the background. "
    + "Pass that handle to wait_opencode_turn to collect the reply text and usage, or to interrupt_opencode_turn to stop the turn. "
    + "Permission rules and the working folder are fixed by the developer who configured the host, and any permission request the turn raises is rejected."
)
CONTINUE_OPENCODE_SESSION_DESCRIPTION = (
    "Starts a new turn in an existing opencode session with the given prompt, so the agent keeps the session's earlier conversation. "
    + "It returns a turn handle as soon as the server accepted the prompt, while the turn keeps running in the background. "
    + "A session that already has a running turn is refused as busy, and a session id the server does not know is reported as not found. "
    + "Collect the outcome with wait_opencode_turn, or stop the turn with interrupt_opencode_turn."
)
FORK_OPENCODE_SESSION_DESCRIPTION = (
    "Creates a new opencode session that copies an existing session's conversation, either whole or up to one of its messages. "
    + "The original session is left unchanged, so the fork can try a different direction from the same starting point. "
    + "A session with a running turn is refused as busy, and a message id that is not in the session is reported as not found. "
    + "The result is the new session, whose id can be passed to continue_opencode_session."
)
REVERT_OPENCODE_SESSION_DESCRIPTION = (
    "Marks an opencode session as reverted to one of its messages, or to one part of that message, hiding everything after it. "
    + "The server records the revert point on the session, and the next turn continues from there. "
    + "A session with a running turn is refused as busy, and an unknown message is reported as not found. "
    + "The result is the session with its revert point as the server reports it, and unrevert_opencode_session undoes the revert."
)
UNREVERT_OPENCODE_SESSION_DESCRIPTION = (
    "Undoes the revert point of an opencode session, so the messages it hid count again. "
    + "A session without a revert point comes back unchanged, which is not an error. "
    + "A session with a running turn is refused as busy, and an unknown session is reported as not found. "
    + "The result is the session as the server reports it after the change."
)
LIST_OPENCODE_SESSIONS_DESCRIPTION = (
    "Lists the opencode sessions on this server, most recently updated first. "
    + "Each entry gives the session id, title, folder, parent session, creation and update times, usage totals and any revert point. "
    + "The optional limit bounds how many sessions the server returns, so a long history stays small. "
    + "Use the ids it returns with get_opencode_session, continue_opencode_session or fork_opencode_session."
)
GET_OPENCODE_SESSION_DESCRIPTION = (
    "Reads one opencode session by its id. "
    + "The result gives the session's title, folder, parent session, creation and update times, usage totals and any revert point. "
    + "A session id the server does not know is reported as not found, with the step that lists the known sessions. "
    + "Use it to confirm a session before continuing, forking or reverting it."
)
GET_OPENCODE_SESSION_MESSAGES_DESCRIPTION = (
    "Reads one page of an opencode session's messages, oldest first within the page. "
    + "Each message gives its id, role, times, joined text, parent message, model, finish reason, error and usage. "
    + "When the page is full, the result names the oldest message id, which can be passed back as the before argument to read the page before it. "
    + "Use it to review what a session said and to find message ids for forking, reverting or diffs."
)
GET_OPENCODE_MESSAGE_DESCRIPTION = (
    "Reads one message of an opencode session by its id. "
    + "The result gives the message's role, times, joined text, parent message, model, finish reason, error and usage. "
    + "The session is checked first, so an unknown session and an unknown message are reported separately. "
    + "Use it to inspect one reply in detail after finding its id in get_opencode_session_messages."
)
GET_OPENCODE_SESSION_DIFF_DESCRIPTION = (
    "Lists the files an opencode session changed, with each file's status, added and deleted line counts, and patch. "
    + "An optional message id narrows the diff to the changes made by that message. "
    + "A long patch is cut and marked as truncated, so the result stays within the output limit. "
    + "Use it to review what a turn changed before keeping, reverting or reporting the work."
)
WAIT_OPENCODE_TURN_DESCRIPTION = (
    "Waits for a turn started by spawn_opencode_session or continue_opencode_session and returns its outcome. "
    + "A finished turn returns its status, the reply text, the stop reason, the usage summed over every model step, and the permission and question requests the host rejected. "
    + "A turn still running when the wait ends is reported as timed out and keeps running, so the wait can simply be repeated. "
    + "A failed turn reports the same failure on every wait, with the step that fixes it."
)
INTERRUPT_OPENCODE_TURN_DESCRIPTION = (
    "Stops a running opencode turn by asking the server to abort it. "
    + "The result says whether the turn was still running; a turn that had already finished is left as it was. "
    + "After an interrupt, wait_opencode_turn returns the turn as interrupted by the caller, with whatever text it had produced. "
    + "Use it when a turn goes in the wrong direction or takes longer than the task allows."
)
TRACK_OPENCODE_SESSION_USAGE_DESCRIPTION = (
    "Reports the token and cost usage of an opencode session. "
    + "The totals come from the session itself, and the breakdown lists the usage of each assistant message. "
    + "A very long session has its breakdown cut to the newest messages and marked as truncated, while the totals stay complete. "
    + "Use it to watch spending across turns or to explain which turn used the most."
)
ADD_OPENCODE_MCP_SERVER_DESCRIPTION = (
    "Adds one MCP server to the opencode server, so its tools become available to later turns. "
    + "Only servers that the developer registered on this host by name can be added, and their command, address, environment and headers come from that registration. "
    + "The result is the connection status the server reports; a server that fails to start or needs a login is reported as an error. "
    + "Servers that require an OAuth login are not supported through this tool."
)

PROVIDER_ID_PARAMETER_DESCRIPTION = (
    "The id of one connected provider whose models should be listed. "
    + "It is the provider part of a model id and never contains a slash. "
    + "Leave it out to list the models of every connected provider. "
    + "An id the server does not offer is refused with the provider ids that do exist."
)
PROMPT_PARAMETER_DESCRIPTION = (
    "The instruction the opencode agent should work on in this turn, written as plain text. "
    + "It is sent as the turn's only user message, and the agent works in the host's workspace with the rules the developer configured. "
    + "It must not be empty, and very long prompts are refused before anything is sent. "
    + "State the task, the constraints and the expected result clearly, because the agent cannot ask follow-up questions here."
)
MODEL_PARAMETER_DESCRIPTION = (
    "The model to run this turn on, written as the provider id and the model id joined by a slash. "
    + "Only models that list_opencode_models reports are accepted, and an unknown one is refused before any session is created. "
    + "Leave it out to use the server's default model. "
    + "The value must not contain spaces or start with a dash."
)
AGENT_PARAMETER_DESCRIPTION = (
    "The name of the opencode agent profile that should handle this turn. "
    + "Agent profiles are defined in the server's own configuration and decide the instructions and tools the agent uses. "
    + "Leave it out to use the server's default agent. "
    + "An agent the server does not know makes the call fail with the server's own error."
)
TITLE_PARAMETER_DESCRIPTION = (
    "A short human-readable title for the new session. "
    + "It is shown in session lists and makes the session easier to find later. "
    + "Leave it out to let the server choose a title. "
    + "It must not be empty when given and is limited to a short length."
)
MAX_TURN_SECONDS_PARAMETER_DESCRIPTION = (
    "The longest time in seconds this turn may run before the host aborts it. "
    + "A turn that reaches this ceiling ends as interrupted by the deadline, keeping the text it produced so far. "
    + "Leave it out to use the host's default ceiling. "
    + "It must be a positive number within the host's maximum turn length."
)
SESSION_ID_PARAMETER_DESCRIPTION = (
    "The id of an opencode session on this server, exactly as list_opencode_sessions or a previous result reported it. "
    + "Session ids have a fixed shape, and any other text is refused before a request is sent. "
    + "The session must belong to the server this host is connected to. "
    + "Use list_opencode_sessions to find the id when it is not known."
)
FORK_MESSAGE_ID_PARAMETER_DESCRIPTION = (
    "The id of the message in the session up to which the fork copies the conversation. "
    + "The message must belong to the session, and an unknown id is reported as not found. "
    + "Leave it out to copy the whole conversation. "
    + "Use get_opencode_session_messages to find the id of the message to fork at."
)
REVERT_MESSAGE_ID_PARAMETER_DESCRIPTION = (
    "The id of the message in the session that becomes the session's revert point. "
    + "Everything after that message is hidden until the revert is undone. "
    + "The message must belong to the session, and an unknown id is reported as not found. "
    + "Use get_opencode_session_messages to find the id of the message to revert to."
)
MESSAGE_ID_PARAMETER_DESCRIPTION = (
    "The id of the message to read, exactly as get_opencode_session_messages reported it. "
    + "Message ids have a fixed shape, and any other text is refused before a request is sent. "
    + "The message must belong to the given session, and an unknown id is reported as not found. "
    + "Pass the session id that holds the message together with it."
)
DIFF_MESSAGE_ID_PARAMETER_DESCRIPTION = (
    "The id of one message whose changes the diff should show. "
    + "The message must belong to the session, and an unknown id is reported as not found. "
    + "Leave it out to see every change the session made. "
    + "Use get_opencode_session_messages to find the id of the message to inspect."
)
PART_ID_PARAMETER_DESCRIPTION = (
    "The id of one part of the revert message, when the revert point should be inside that message. "
    + "Part ids have a fixed shape, and any other text is refused before a request is sent. "
    + "Leave it out to revert to the whole message. "
    + "Only pass a part id that was reported for that message."
)
SESSIONS_LIMIT_PARAMETER_DESCRIPTION = (
    "The largest number of sessions to return, counted from the most recently updated. "
    + "It must be a whole number from one up to the host's listing maximum. "
    + "Leave it out to use the host's default page size. "
    + "A smaller limit keeps the result short when only recent sessions matter."
)
MESSAGES_LIMIT_PARAMETER_DESCRIPTION = (
    "The largest number of messages to return in this page. "
    + "It must be a whole number from one up to the host's listing maximum. "
    + "Leave it out to use the host's default page size. "
    + "A page that holds exactly this many messages offers the id needed to read the page before it."
)
BEFORE_PARAMETER_DESCRIPTION = (
    "The message id to page back from, taken from the previous page's next before value. "
    + "Only messages older than this id are returned. "
    + "Leave it out to read the newest page. "
    + "Message ids have a fixed shape, and any other text is refused before a request is sent."
)
HANDLE_PARAMETER_DESCRIPTION = (
    "The turn handle returned by spawn_opencode_session or continue_opencode_session, passed back unchanged as an object. "
    + "It holds the harness, the session id and the turn id as text, and all three must match a turn this host started. "
    + "A handle from another host or another harness is reported as not found. "
    + "Finished turns stay available for a limited number of later turns."
)
TIMEOUT_SECONDS_PARAMETER_DESCRIPTION = (
    "The longest time in seconds to wait for the turn to finish during this call. "
    + "When it passes, the call reports the turn as still running and the turn itself is not touched. "
    + "Leave it out to use the default wait; values above the tool's waiting cap are refused. "
    + "Call the wait again with the same handle to keep waiting."
)
MCP_NAME_PARAMETER_DESCRIPTION = (
    "The name under which the developer registered the MCP server on this host. "
    + "Only registered names are accepted, and the server's command, address, environment and headers come from the registration. "
    + "A name that was not registered is refused before anything is sent. "
    + "Ask the developer to register a server when the one needed is missing."
)

__all__ = [
    "ADD_OPENCODE_MCP_SERVER_DESCRIPTION",
    "AGENT_PARAMETER_DESCRIPTION",
    "BEFORE_PARAMETER_DESCRIPTION",
    "CHECK_OPENCODE_READY_DESCRIPTION",
    "CONTINUE_OPENCODE_SESSION_DESCRIPTION",
    "DIFF_MESSAGE_ID_PARAMETER_DESCRIPTION",
    "FORK_MESSAGE_ID_PARAMETER_DESCRIPTION",
    "FORK_OPENCODE_SESSION_DESCRIPTION",
    "GET_OPENCODE_MESSAGE_DESCRIPTION",
    "GET_OPENCODE_PROVIDER_AUTH_DESCRIPTION",
    "GET_OPENCODE_SESSION_DESCRIPTION",
    "GET_OPENCODE_SESSION_DIFF_DESCRIPTION",
    "GET_OPENCODE_SESSION_MESSAGES_DESCRIPTION",
    "HANDLE_PARAMETER_DESCRIPTION",
    "INTERRUPT_OPENCODE_TURN_DESCRIPTION",
    "LIST_OPENCODE_MODELS_DESCRIPTION",
    "LIST_OPENCODE_PROVIDERS_DESCRIPTION",
    "LIST_OPENCODE_SESSIONS_DESCRIPTION",
    "MAX_TURN_SECONDS_PARAMETER_DESCRIPTION",
    "MCP_NAME_PARAMETER_DESCRIPTION",
    "MESSAGES_LIMIT_PARAMETER_DESCRIPTION",
    "MESSAGE_ID_PARAMETER_DESCRIPTION",
    "MODEL_PARAMETER_DESCRIPTION",
    "PART_ID_PARAMETER_DESCRIPTION",
    "PROMPT_PARAMETER_DESCRIPTION",
    "PROVIDER_ID_PARAMETER_DESCRIPTION",
    "REVERT_MESSAGE_ID_PARAMETER_DESCRIPTION",
    "REVERT_OPENCODE_SESSION_DESCRIPTION",
    "SESSIONS_LIMIT_PARAMETER_DESCRIPTION",
    "SESSION_ID_PARAMETER_DESCRIPTION",
    "SPAWN_OPENCODE_SESSION_DESCRIPTION",
    "TIMEOUT_SECONDS_PARAMETER_DESCRIPTION",
    "TITLE_PARAMETER_DESCRIPTION",
    "TRACK_OPENCODE_SESSION_USAGE_DESCRIPTION",
    "UNREVERT_OPENCODE_SESSION_DESCRIPTION",
    "WAIT_OPENCODE_TURN_DESCRIPTION",
]
