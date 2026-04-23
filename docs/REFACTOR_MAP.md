# Refactor map — modules/mbx_legacy.py

Working document. Drives the extraction order. Line numbers are from the current HEAD and will drift as extraction progresses — treat this as a map, not a source of truth.

## Target structure

See conversation — target is:

```
guilda/
  bot.py, constants.py, context.py (temp)
  core/ — data, models, services, permissions, utils
  features/ — moderation, modmail, automod, roles, branding, setup, dev
  tasks/ — background loops
  ui/ — shared widgets only
```

## Domain inventory

Symbols grouped by destination. "L<n>" = line in `mbx_legacy.py`.

### core/utils.py (leaf — no bot state)

- `read_json_file` L98
- `parse_iso_datetime` L108
- `hex_valid` L258
- `format_duration` L485
- `create_progress_bar` L498
- `format_log_quote` / `format_plain_log_block` / `format_reason_value` / `format_log_notes` L503–537
- `truncate_text` L939
- `join_lines` L1197
- `get_modal_item_label` L1210
- `get_user_display_name` / `format_user_ref` / `format_user_id_ref` L1218–1232
- `extract_snowflake_id` L1241
- `ExpirableMixin` L551
- numeric parsers (`parse_positive_integer_input`, `parse_minutes_input`, `format_minutes_interval`, `format_seconds_interval`, `format_compact_minutes_input`) L2361–2431

### core/images.py (leaf — HTTP + validation)

- `_resolve_image_host_addresses` L268
- `_is_public_image_ip` L292
- `validate_image_fetch_url` L299
- `_format_image_size_limit` L318
- `fetch_image_asset` L326
- `fetch_image_bytes` L377
- `_make_image_data_uri` L386
- `fetch_image_data_uri` L391

### core/logging.py (leaf — log embeds + sending)

- `normalize_log_field_name` / `format_log_field_value` / `build_log_detail_fields` L629–651
- `make_action_log_embed` L674
- `normalize_log_embed` L720
- `get_general_log_channel_ids` / `get_general_log_channel_id` L778–796
- `get_punishment_log_channel_ids` / `get_punishment_log_channel_id` L801–819
- `_send_log_to_channels` L824
- `send_log` L854
- `send_punishment_log` L872
- `send_automod_log` L1319

### core/embeds.py (leaf — embed builders, branding footer)

- `_get_branding_config` L981
- `_build_footer_text` / `_build_footer_text_with_detail` L987–993
- `_get_footer_icon_url` L999
- `_set_footer_branding` L1005
- `make_embed` L1107
- `brand_embed` L1144
- `make_empty_state_embed` / `make_error_embed` / `make_confirmation_embed` L1156–1188
- `make_analytics_card` L1188
- `upsert_embed_field` L1202
- `fmt_role` / `fmt_channel` L959–970

### core/permissions.py (leaf — centralized auth)

- `has_dangerous_perm` L218
- `has_permission_capability` L893
- `respond_with_error` L904
- `is_staff_member` / `is_staff` L912–930
- `check_admin` / `check_owner` L9248–9251
- `requires_setup` L9254
- `get_primary_guild` / `get_context_guild` L1248–1258
- `resolve_member` L948

This is the core of the new permission engine. For now, move as-is. Redesign in a later phase.

### features/branding/

- `_refresh_branding_panel` L1026
- `apply_guild_member_branding` L1031
- `save_branding_settings` L1089
- `build_branding_error_embed` L1103
- `_build_branding_panel_embed` L10237
- `BrandingColorModal` / `BrandingDisplayNameModal` / `BrandingAvatarModal` / `BrandingBannerModal` / `BrandingBioModal` L10286–10375
- `BrandingPanelView` L10398
- `branding_cmd` L10445

### features/moderation/ (the biggest domain)

Commands:
- `ModGroup` L9484
- `punish_context` L10566, `history_context` L10574
- `publicexecution` L9863
- `rules` L10055
- `access` L10470
- `lockdown` / `unlockdown` L10488–10521
- `stats` L9711, `directory` L9797
- `internals` L9869

Logic:
- `calculate_smart_punishment` L142
- `execute_punishment` L3523
- `handle_abuse` L3020
- `punish_rogue_mod` L3048
- `reverse_punishment_effect` L1548
- `undo_case_record` L1597
- `clear_user_history_records` L1625
- `record_case_reversal_stats` L1523
- `pop_case_record` L1537
- `get_active_records_for_user` L1753
- `get_valid_duration` L889
- `calculate_member_risk` L1714
- `get_mod_cases` L6302

Case formatting:
- `get_case_id` / `get_case_label` / `get_record_expiry` / `format_case_status` L1346–1374
- `is_record_active` / `describe_punishment_record` / `get_punishment_duration_and_expiry` L1384–1417
- `get_undo_reason_details` L1437
- `build_case_summary_lines` / `format_case_summary_block` / `add_punishment_record_log_fields` L1445–1501
- `build_history_archive_attachment` L1501
- `_split_case_input` L5457
- `log_case_management_action` L5430

Embeds:
- `build_punishment_execution_log_embed` L1674
- `build_history_overview_embed` / `build_no_history_embed` / `build_history_case_detail_embed` L1761–1797
- `build_undo_panel_embed` L1837
- `build_punishment_undo_log_embed` / `build_history_cleared_log_embed` L1871–1895
- `build_case_detail_embed` L1917
- `build_active_punishments_embed` L1970
- `build_mod_help_embed` L2015
- `build_punish_embed` L3776
- `build_rules_dashboard_embed` L2238
- `build_escalation_matrix_embed` L2932
- `get_staff_stats_embed` L6310
- `build_public_execution_embed` L4511
- `execute_public_execution_vote` L4541
- `get_public_execution_action_label` L4500

Views/Modals (~30+):
- Appeal flow: `DenyAppealModal`, `RevokeAppealView`, `AppealModal`, `AppealView`, `ConfirmRevokeView` L3961–4221
- Punish flow: `PublicExecutionApprovalView`, `PunishDetailsModal`, `CustomPunishDetailsModal`, `CustomTypeSelect/View`, `PunishSelect`, `PunishView` L4651–5783
- History flow: `HistorySelect`, `UndoCaseSelect/Reason*`, `HistoryActionButton`, `HistoryNavButton`, `UndoConfirmView`, `HistoryClearConfirmView`, `HistoryView`, `FirstConfirmClear`, `FinalConfirmClear` L4963–5765
- Case panel: `CaseNoteModal`, `CaseLinksModal`, `CaseStateSelect/View`, `CaseSwitchSelect`, `CasePanelView` L5461–5650
- Rules: `RuleEditModal`, `RuleDeleteSelect/View`, `RuleSelectForEdit/View`, `RulesDashboardView`, `ActiveSelect/View`, `AccessView` L5816–6265
- Staff: `ModCasesSelect`, `StaffProfileView`, `StaffSelect`, `StaffView` L6416–6560
- Misc: `TestEnvView`, `SafetyView`, `AntiNukeResolveConfirm1/2`, `AntiNukeResolveView`, `ImmunityModal` L6580–6741
- Revoke: `RevokeUndoView` L9339, `show_punish_menu` / `show_history_menu` / `show_case_panel` L9388–9419

Events:
- `on_raw_reaction_add` L10668 (case reactions)
- `on_guild_role_update` L10613 (role escalation triggers)
- `on_app_command_error` L10582

### features/modmail/

- `prepare_modmail_relay_attachments` L402
- `send_modmail_thread_intro` L437
- `build_modmail_panel_embed` L2072
- `build_modmail_settings_embed` L2194
- `send_modmail_panel_message` L1262, `maybe_send_dm_modmail_panel` L1290
- `log_modmail_action` L6761
- `apply_modmail_ticket_state` L6774
- `refresh_modmail_message` L6801
- `refresh_modmail_ticket_log` L6824
- `export_modmail_transcript` L6844
- `_parse_user_id` / `resolve_modmail_user` / `resolve_modmail_thread` L6862–6903
- `generate_transcript_html` L6050
- Views/Modals: `ModmailPrioritySelect/View`, `ModmailTagsModal`, `CannedReplySelect/View`, `ModmailControlView`, `ModmailModal`, `ModmailPanelSelect/View`, `ModmailSettingsView`, `ModmailDiscussionThreadSelect` L6903–7865
- Canned replies: `CannedReplyModal`, `CannedRepliesView` L7946–7965

### features/automod/

Native automod:
- `get_native_automod_stats_bucket` L3109
- `prune_native_automod_bucket` L3127
- `record_native_automod_event` L3145
- `count_recent_native_automod_hits` L3160
- `has_recent_native_automod_step_application` / `record_native_automod_step_application` L3178–3207
- `get_triggered_native_automod_step` L3230
- `build_native_automod_dedupe_key` L3257
- `claim_native_automod_execution` L3267
- `get_native_automod_action_label` L3283
- `native_automod_rule_has_enforcement` L3287
- `is_native_automod_exempt` L3300
- `apply_native_automod_escalation` L3315
- `claim_native_automod_bridge_event` L10759
- `claim_native_automod_alert_message` L10792
- `clean_native_automod_alert_value` / `extract_native_automod_alert_context` L10814–10819
- `find_recent_native_automod_audit_entry` / `find_matching_native_automod_alert_message` L10864–10897
- `get_native_automod_audit_action_label` / `is_native_automod_audit_blocked` L10955–10967
- `run_native_automod_bridge` L10977
- `handle_native_automod_execution` L11180
- `handle_native_automod_alert_message` L11256
- `on_automod_action` L11318
- `on_socket_raw_receive` L11323

Smart automod:
- `run_smart_automod` L3425
- `get_smart_automod_settings` L2460
- `store_native_automod_settings` / `store_smart_automod_settings` L2474–2480

Automod config:
- `format_automod_punishment_label` L2495
- `get_automod_report_preset` L2506
- `build_default_native_automod_policy` L2510
- `get_native_automod_policy_steps` L2518
- `build_default_native_automod_step` L2545
- `format_native_automod_step_summary` L2562
- `get_native_rule_override` / `ensure_native_rule_override_policy` L2567, L7974
- `render_id_mentions` L2575
- `parse_automod_punishment_input` L2431

Automod embeds:
- `build_automod_bridge_embed` L2585
- `build_automod_policy_embed` L2610
- `build_automod_immunity_embed` L2647
- `build_automod_routing_embed` L2662
- `build_smart_automod_embed` L2683
- `build_automod_rule_browser_embed` L2705
- `describe_automod_rule_trigger` / `describe_automod_rule_actions` L2736–2762
- `serialize_automod_rule` L2777
- `build_automod_trigger_from_payload` L2813
- `build_automod_actions_from_payload` L2842
- `fetch_native_automod_rules` L2867
- `build_native_automod_rules_embed` / `build_native_automod_rule_detail_embed` L2871–2897

Automod views/modals:
- `AutoModPolicyReasonModal`, `AutoModStepValuesModal`, `AutoModStepSelect`, `AutoModStepPunishmentTypeSelect`, `AutoModStepThresholdSelect`, `AutoModStepWindowSelect`, `AutoModStepTimeoutDurationSelect` L7985–8175
- `AutoModRuleSelect`, `AutoModBridgeSettingsView`, `AutoModRuleBrowserView`, `AutoModPolicyEditorView` L8175–8267
- `AutoModChannelSelect/SettingsView/ActionSelect` L8476–8504
- `AutoModStoredValueRemoveSelect/View` L8535–8560
- `AutoModImmunity*Select`, `AutoModImmunityView` L8566–8608
- `SmartAutoModThresholdModal`, `SmartAutoModPatternModal`, `SmartAutoModExempt*`, `SmartAutoModSettingsView` L8656–8741
- `AutoModDashboardView` L8800
- `AutoModCustomReportResponseModal`, `AutoModReportResponseSelect/View`, `AutoModReportModal`, `AutoModWarningView` L8919–9098
- `resolve_user_for_automod_report` / `apply_automod_report_response` L8827–8841
- `automod_cmd` L10231
- `build_automod_dashboard_embed` L2260

### features/roles/

- `get_custom_role_limit` L225
- `build_role_info_embed` L3721
- `build_role_landing_embed` L2053
- `build_role_settings_embed` L7412
- `build_role_permissions_overview_embed` L7437
- `split_embed_entries` L7468
- `build_custom_role_registry_entries` / `add_custom_role_registry_fields` / `build_role_registry_embed` L7489–7524
- Views/Modals: `CreateRoleModal`, `EditNameModal`, `EditColorModal`, `GradientModal`, `RoleStyleView`, `IconURLModal`, `UploadIconView`, `RoleActionSelect`, `EditView`, `ConfirmDelete` L3799–4500
- `RoleSettingsTargetModal`, `RoleSettingsManageMemberModal`, `RoleSettingsAccessSelect/View`, `RoleSettingsActionSelect`, `RoleSettingsView` L7537–7673
- Commands: `role_cmd` L7683 (uses @tree.command inline), `role_manage` L10070, `role_settings` L10224, `roleadmin` L10058, `rolesettings` L10221, `help_cmd` L10547

### features/setup/

- `_setup_health_check` L2110
- `build_setup_dashboard_embed` L2140
- `build_config_dashboard_embed` L2216
- `build_feature_flags_embed` L2916
- `build_setup_validation_embed` L2967
- `ConfigRoleSelect`, `MultiConfigRoleSelect`, `ConfigChannelSelect`, `ConfigTypeSelect` L7734–7784
- `FeatureFlagSelect/View` L7870–7891
- `EscalationMatrixModal/View` L7897–7931
- `CannedReplyModal/View` (shared w/ modmail? check) L7946
- `ConfigImportModal` L9122
- `ConfigDashboardActionSelect/View` L9153–9199
- `SetupDashboardActionSelect/View` L9205–9240
- `ModmailSettingsView` L7865 (could go to modmail instead — borderline)
- Commands: `setup` L9846, `config_cmd` L9850
- `_categorise_commands` L9276
- `CommandCategorySelect/CommandBrowserView` L9291–9314
- `list_commands` L9323

### features/channels/ (small, maybe merge into moderation)

- `archive` L9913, `unarchive` L9950, `clone` L10021
- `ArchiveConfirmView`, `CloneConfirmView` L6130–6189

### features/status/ (tiny)

- `build_status_embed` L2988
- `status_cmd` L10701
- `build_test_env_embed` / `TestEnvView` L6565–6580

### events (bot.py or features/events.py)

- `on_member_update` L10710 (role branding sync)
- `on_message` L11354 (smart automod + modmail dispatch)
- `sync` L10672 — the legacy `!sync` prefix command; kill or absorb into dev

### Resolver / misc

- `resolve_bot_token` L117 — used by `bot.py`, move to `bot.py` or `core/utils.py`
- `get_feature_flag_name` L1380 — services.py already has feature flag logic; merge there

## Extraction order (safest → most entangled)

1. **Phase 1 (this commit):** delete fake stub modules (`mbx_moderation.py`, `mbx_automod.py`, `mbx_modmail.py`, `mbx_roles.py`, `mbx_permissions.py`). Cogs import straight from `mbx_legacy`. No logic moved.
2. **Phase 2:** extract `core/utils.py`, `core/images.py`, `core/logging.py`, `core/embeds.py`, `core/permissions.py`. These are leaves — nothing in `mbx_legacy` calls *out* to anything in here that it can't replace with an import.
3. **Phase 3:** extract `features/roles/` (fewest cross-domain deps — self-contained UI + commands).
4. **Phase 4:** extract `features/automod/` (big but self-contained — has its own state, its own config).
5. **Phase 5:** extract `features/modmail/` (touches logging, embeds, but shouldn't touch moderation).
6. **Phase 6:** extract `features/branding/`.
7. **Phase 7:** extract `features/setup/` and `features/channels/` and `features/status/`.
8. **Phase 8:** extract `features/moderation/` (the trunk — biggest and most cross-referenced; by now everything it depends on has moved).
9. **Phase 9:** kill `mbx_context.py` proxy, move `on_message` / `on_member_update` to `bot.py` or `features/events.py`, rename the remaining `mbx_legacy.py` (if anything's left).
10. **Phase 10:** package rename `modules/` → `guilda/`, `mbx_main.py` → `guilda.py`, update imports.

## Known risks

- `get_primary_guild()` L1248 is a single-guild leftover. After extraction, rip this out and replace all call sites with explicit guild passing.
- `handle_abuse` L3020 and `punish_rogue_mod` L3048 interact with `abuse_system` via the proxy — they'll need the real bot reference plumbed.
- `ExpirableMixin` is used across 7+ views. Belongs in `core/utils.py` or `core/views.py`. Must extract before any View that uses it.
- The `/dev` commands in `cogs/dev.py` already work and are clean — do NOT touch during extraction.
