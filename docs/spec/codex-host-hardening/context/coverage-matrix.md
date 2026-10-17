| # | Method | Stability | Status | PR function | Proposed | Pri |
|---|---|---|---|---|---|---|
| 1 | `initialize` | stable | INTERNAL | CodexHost.__aenter__ (version check only) | get_codex_version (deferred catalog row) | P2 |
| 2 | `server/diagnostics` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 3 | `userVerification/status` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 4 | `userVerification/enroll` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 5 | `userVerification/delete` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 6 | `userVerification/verify` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 7 | `userVerification/cancel` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 8 | `thread/start` | stable | PARTIAL | spawn_codex_thread, launch_codex_subagents, run_codex_goal, run_codex_skill, run_codex_openai_docs | see settings matrix | P0 |
| 9 | `thread/resume` | stable | PARTIAL | continue_codex_thread, compact_codex_thread (load) | resume_codex_thread (attach without a turn) | P1 |
| 10 | `thread/fork` | stable | PARTIAL | fork_codex_thread (lastTurnId only) | before_turn_id, defer_goal_continuation, start_codex_side_chat | P1 |
| 11 | `thread/archive` | stable | DEFERRED (spec) | - | archive_codex_thread | P1 |
| 12 | `thread/delete` | stable | COVERED | delete_codex_thread (plain fn, no tool) |  |  |
| 13 | `thread/unsubscribe` | stable | MISSED | - | release_codex_thread (unload after use) | P1 |
| 14 | `thread/increment_elicitation` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 15 | `thread/decrement_elicitation` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 16 | `thread/name/set` | stable | PARTIAL | spawn/fork via request.name only | rename_codex_thread | P1 |
| 17 | `thread/prediction/request` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 18 | `thread/goal/set` | stable | PARTIAL | run_codex_goal / spawn goal (objective+active, tokenBudget) | set/pause/resume/edit goal | P1 |
| 19 | `thread/goal/get` | stable | COVERED | get_codex_goal |  |  |
| 20 | `thread/goal/clear` | stable | INTERNAL | only inside openai-codex start_goal_operation | clear_codex_goal | P1 |
| 21 | `thread/queue/add` | EXPERIMENTAL | MISSED | - | queue_codex_message (codex queue) | P1 |
| 22 | `thread/queue/list` | EXPERIMENTAL | MISSED | - | list_codex_queue | P1 |
| 23 | `thread/queue/update` | EXPERIMENTAL | MISSED | - | update_codex_queued_message | P2 |
| 24 | `thread/queue/delete` | EXPERIMENTAL | MISSED | - | delete_codex_queued_message | P2 |
| 25 | `thread/queue/reorder` | EXPERIMENTAL | MISSED | - | reorder_codex_queue | P2 |
| 26 | `thread/queue/start` | EXPERIMENTAL | MISSED | - | start_codex_queued_message | P1 |
| 27 | `thread/metadata/update` | stable | DEFERRED (spec) | - | set_codex_thread_git_info | P2 |
| 28 | `thread/attachment/add` | stable | DEFERRED (spec) | - | attach_to_codex_thread | P2 |
| 29 | `thread/attachment/list` | stable | DEFERRED (spec) | - | list_codex_thread_attachments | P2 |
| 30 | `thread/attachmentOwner/list` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 31 | `thread/attachment/remove` | stable | DEFERRED (spec) | - | detach_from_codex_thread | P2 |
| 32 | `thread/section/move` | stable | DEFERRED (spec) | - | move_codex_thread_to_section | P2 |
| 33 | `thread/settings/update` | EXPERIMENTAL | MISSED | - | update_codex_thread_settings (/model, /fast, /plan, /permissions, /cd without a turn) | P0 |
| 34 | `thread/memoryMode/set` | EXPERIMENTAL | MISSED | - | set_codex_thread_memory_mode (/memories, per thread) | P1 |
| 35 | `memory/status` | EXPERIMENTAL | MISSED | - | get_codex_memory_status | P2 |
| 36 | `memory/reset` | EXPERIMENTAL | MISSED | - | reset_codex_memories (never a tool) | P2 |
| 37 | `rollout/compress` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 38 | `thread/unarchive` | stable | DEFERRED (spec) | - | unarchive_codex_thread | P1 |
| 39 | `thread/compact/start` | stable | COVERED | compact_codex_thread (completion not tracked, NG-12) |  |  |
| 40 | `thread/shellCommand` | stable | DEFERRED (spec) | - | run_codex_thread_shell (unsandboxed; never a tool) | P2 |
| 41 | `thread/approveGuardianDeniedAction` | stable | DEFERRED (spec) | - | approve_codex_guardian_denied (/approve) | P2 |
| 42 | `thread/backgroundTerminals/clean` | EXPERIMENTAL | MISSED | - | stop_codex_background_terminals (/stop) | P1 |
| 43 | `thread/backgroundTerminals/list` | EXPERIMENTAL | MISSED | - | list_codex_background_terminals (/ps) | P1 |
| 44 | `thread/backgroundTerminals/terminate` | EXPERIMENTAL | MISSED | - | terminate_codex_background_terminal | P2 |
| 45 | `thread/revert` | stable | DEFERRED (spec) | - | revert_codex_thread | P1 |
| 46 | `thread/list` | stable | PARTIAL | list_codex_threads and the list_recent/since/search helpers | parent/ancestor filters, excludedThreadIds, modelProviders, sectionId | P1 |
| 47 | `project/list` | EXPERIMENTAL | MISSED | - | list_codex_projects | P2 |
| 48 | `project/read` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 49 | `project/create` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 50 | `project/import` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 51 | `project/update` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 52 | `project/move` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 53 | `project/delete` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 54 | `threadSection/list` | stable | DEFERRED (spec) | - | list_codex_sections | P2 |
| 55 | `threadSection/create` | stable | DEFERRED (spec) | - | create_codex_section | P2 |
| 56 | `threadSection/update` | stable | DEFERRED (spec) | - | update_codex_section | P2 |
| 57 | `threadSection/delete` | stable | DEFERRED (spec) | - | delete_codex_section | P2 |
| 58 | `thread/search` | EXPERIMENTAL | MISSED | - | search_codex_thread_content (full text) | P1 |
| 59 | `thread/searchOccurrences` | EXPERIMENTAL | MISSED | - | find_codex_thread_occurrences | P2 |
| 60 | `thread/loaded/list` | stable | DEFERRED (spec) | - | list_loaded_codex_threads | P2 |
| 61 | `thread/read` | stable | COVERED | read_codex_thread, get_codex_thread_lineage, preflight |  |  |
| 62 | `thread/readState/update` | EXPERIMENTAL | MISSED | - | mark_codex_thread_read | P2 |
| 63 | `thread/turns/list` | stable | COVERED | list_codex_turns, run_codex_skill read-back |  |  |
| 64 | `thread/items/list` | stable | DEFERRED (spec) | - | list_codex_items | P2 |
| 65 | `thread/items/read` | EXPERIMENTAL | MISSED | - | read_codex_items | P2 |
| 66 | `thread/inject_items` | stable | DEFERRED (spec) | - | inject_codex_items | P1 |
| 67 | `skills/list` | stable | PARTIAL | list_codex_skills (one cwd, no forceReload) | force_reload, many cwds | P2 |
| 68 | `skills/extraRoots/set` | stable | DEFERRED (spec) | - | add_codex_skill_roots | P1 |
| 69 | `hooks/list` | stable | DEFERRED (spec) | - | list_codex_hooks | P2 |
| 70 | `marketplace/add` | stable | MISSED | - | add_codex_marketplace (never a tool) | P2 |
| 71 | `marketplace/remove` | stable | MISSED | - | remove_codex_marketplace | P2 |
| 72 | `marketplace/upgrade` | stable | MISSED | - | upgrade_codex_marketplace | P2 |
| 73 | `plugin/list` | stable | DEFERRED (spec) | - | list_codex_plugins (/plugins) | P1 |
| 74 | `plugin/search` | EXPERIMENTAL | MISSED | - | search_codex_plugins | P2 |
| 75 | `plugin/installed` | stable | MISSED | - | list_installed_codex_plugins | P1 |
| 76 | `plugin/reconcile` | stable | MISSED | - | reconcile_codex_plugins | P2 |
| 77 | `plugin/read` | stable | DEFERRED (spec) | - | read_codex_plugin | P2 |
| 78 | `plugin/skill/read` | stable | DEFERRED (spec) | - | read_codex_plugin_skill | P2 |
| 79 | `plugin/share/save` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 80 | `plugin/share/updateTargets` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 81 | `plugin/share/list` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 82 | `plugin/share/checkout` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 83 | `plugin/share/delete` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 84 | `app/read` | stable | DEFERRED (spec) | - | read_codex_app | P2 |
| 85 | `app/list` | stable | DEFERRED (spec) | - | list_codex_apps | P2 |
| 86 | `app/installed` | stable | DEFERRED (spec) | - | list_installed_codex_apps | P2 |
| 87 | `fs/readFile` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 88 | `fs/writeFile` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 89 | `fs/createDirectory` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 90 | `fs/getMetadata` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 91 | `fs/readDirectory` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 92 | `fs/remove` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 93 | `fs/copy` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 94 | `fs/watch` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 95 | `fs/unwatch` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 96 | `skills/config/write` | stable | DEFERRED (spec) | - | set_codex_skill_enabled | P2 |
| 97 | `plugin/install` | stable | DEFERRED (spec) | - | install_codex_plugin (never a tool; docs say not for prod yet) | P2 |
| 98 | `plugin/uninstall` | stable | DEFERRED (spec) | - | uninstall_codex_plugin (never a tool) | P2 |
| 99 | `turn/start` | stable | PARTIAL | spawn/continue/launch/skill | see settings matrix | P0 |
| 100 | `turn/settings/update` | EXPERIMENTAL | MISSED | - | update_codex_turn_settings (change the running turn) | P1 |
| 101 | `turn/steer` | stable | COVERED | steer_codex_turn |  |  |
| 102 | `turn/interrupt` | stable | COVERED | interrupt_codex_turn, close, Vidbyte caps |  |  |
| 103 | `thread/realtime/start` | EXPERIMENTAL | MISSED | - | start_codex_voice (/voice) | P2 |
| 104 | `thread/realtime/appendAudio` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 105 | `thread/realtime/appendText` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 106 | `thread/realtime/appendSpeech` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 107 | `thread/realtime/stop` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 108 | `thread/timeline/list` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 109 | `thread/realtime/listVoices` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 110 | `review/start` | stable | COVERED | start_codex_review (DETACHED delivery is deprecated in 0.163) |  |  |
| 111 | `model/list` | stable | PARTIAL | list_codex_models (drops serviceTiers, defaultServiceTier, inputModalities, upgrade) | extend CodexModelInfo with service tiers | P0 |
| 112 | `account/gatewayOAuth/read` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 113 | `account/gatewayOAuth/login` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 114 | `account/gatewayOAuth/cancel` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 115 | `modelProvider/capabilities/read` | stable | DEFERRED (spec) | - | get_codex_provider_capabilities | P2 |
| 116 | `experimentalFeature/list` | stable | DEFERRED (spec) | - | list_codex_features | P1 |
| 117 | `permissionProfile/list` | stable | DEFERRED (spec) | - | list_codex_permission_profiles | P1 |
| 118 | `experimentalFeature/enablement/set` | stable | DEFERRED (spec) | - | set_codex_features (process-wide; never a tool) | P2 |
| 119 | `remoteControl/enable` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 120 | `remoteControl/disable` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 121 | `remoteControl/status/read` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 122 | `remoteControl/pairing/start` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 123 | `remoteControl/pairing/status` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 124 | `remoteControl/client/list` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 125 | `remoteControl/client/revoke` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 126 | `collaborationMode/list` | EXPERIMENTAL | MISSED | - | list_codex_collaboration_modes (/plan presets) | P0 |
| 127 | `mock/experimentalMethod` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 128 | `environment/add` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 129 | `environment/info` | EXPERIMENTAL | MISSED | - | get_codex_environment | P2 |
| 130 | `environment/status` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 131 | `mcpServer/oauth/login` | stable | DEFERRED (spec) | - | login_codex_mcp_oauth (/mcp login; never a tool) | P2 |
| 132 | `config/mcpServer/reload` | stable | DEFERRED (spec) | - | reload_codex_mcp_servers | P1 |
| 133 | `mcpServerStatus/list` | stable | DEFERRED (spec) | - | list_codex_mcp_servers (/mcp) | P0 |
| 134 | `mcpServer/resource/read` | stable | DEFERRED (spec) | - | read_codex_mcp_resource | P2 |
| 135 | `mcpServer/event/stream/start` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 136 | `mcpServer/event/stream/stop` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 137 | `mcpServer/tool/call` | stable | DEFERRED (spec) | - | call_codex_mcp_tool | P1 |
| 138 | `windowsSandbox/setupStart` | stable | DEFERRED (spec) | - | setup_codex_windows_sandbox | P1 |
| 139 | `windowsSandbox/readiness` | stable | COVERED | check_codex_ready, preflight |  |  |
| 140 | `account/login/start` | stable | DEFERRED (spec) | - | login fns (catalog: never a tool) | P2 |
| 141 | `account/bedrock/discover` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 142 | `account/bedrock/setup` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 143 | `account/bedrock/checkGovCloudRequirements` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 144 | `account/login/cancel` | stable | DEFERRED (spec) | - | cancel_codex_login | P2 |
| 145 | `account/logout` | stable | DEFERRED (spec) | - | logout_codex | P2 |
| 146 | `account/rateLimits/read` | stable | COVERED | get_codex_rate_limits, preflight |  |  |
| 147 | `account/rateLimitResetCredit/consume` | stable | MISSED | - | use_codex_rate_limit_reset (/usage; never a tool) | P2 |
| 148 | `account/usage/read` | stable | DEFERRED (spec) | - | get_codex_account_usage | P1 |
| 149 | `account/workspaceMessages/read` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 150 | `account/sendAddCreditsNudgeEmail` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 151 | `feedback/upload` | stable | MISSED | - | upload_codex_feedback (/feedback) | P2 |
| 152 | `command/exec` | stable | DEFERRED (spec) | - | exec_in_codex_sandbox | P1 |
| 153 | `command/exec/write` | stable | DEFERRED (spec) | - | write_codex_exec_stdin | P2 |
| 154 | `command/exec/terminate` | stable | DEFERRED (spec) | - | terminate_codex_exec | P2 |
| 155 | `command/exec/resize` | stable | DEFERRED (spec) | - | resize_codex_exec | P2 |
| 156 | `process/spawn` | EXPERIMENTAL | MISSED | - | spawn_codex_process (UNSANDBOXED; never a tool) | P2 |
| 157 | `process/writeStdin` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 158 | `process/kill` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 159 | `process/resizePty` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 160 | `config/read` | stable | DEFERRED (spec) | - | read_codex_config | P1 |
| 161 | `externalAgentConfig/detect` | stable | MISSED | - | detect_codex_import_sources (/import) | P2 |
| 162 | `externalAgentConfig/import` | stable | MISSED | - | import_codex_agent_config | P2 |
| 163 | `externalAgentConfig/import/recordHistory` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 164 | `externalAgentConfig/import/readHistories` | stable | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 165 | `config/value/write` | stable | DEFERRED (spec) | - | write_codex_config (never a tool) | P1 |
| 166 | `config/batchWrite` | stable | DEFERRED (spec) | - | write_codex_config_batch (never a tool) | P1 |
| 167 | `configRequirements/read` | stable | DEFERRED (spec) | - | read_codex_config_requirements | P2 |
| 168 | `account/read` | stable | INTERNAL | check_codex_ready, preflight | get_codex_account (deferred catalog row) | P2 |
| 169 | `fuzzyFileSearch` | stable | DEFERRED (spec) | - | fuzzy_find_codex_files | P2 |
| 170 | `fuzzyFileSearch/sessionStart` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 171 | `fuzzyFileSearch/sessionUpdate` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |
| 172 | `fuzzyFileSearch/sessionStop` | EXPERIMENTAL | MISSED | - | (niche, admin or internal; no wrapper proposed) | - |

Counts: {'INTERNAL': 3, 'MISSED': 99, 'PARTIAL': 9, 'DEFERRED (spec)': 51, 'COVERED': 10} total 172
By stability: {('INTERNAL', 'stable'): 3, ('MISSED', 'EXPERIMENTAL'): 67, ('PARTIAL', 'stable'): 9, ('DEFERRED (spec)', 'stable'): 51, ('COVERED', 'stable'): 10, ('MISSED', 'stable'): 32}
Mapped names not in schema (typos): []
