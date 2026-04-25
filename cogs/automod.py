"""AutoMod commands and gateway listeners."""
from __future__ import annotations

import json
import logging

import discord
from discord import app_commands
from discord.ext import commands
from modules.mbx_constants import SCOPE_MODERATION
from modules.mbx_context import abuse_system, bot, tree
from modules.mbx_embeds import (
    _build_footer_text,
    _build_footer_text_with_detail,
    _format_branding_panel_value,
    _get_branding_config,
    _get_footer_icon_url,
    _set_footer_branding,
    brand_embed,
    fmt_channel,
    fmt_role,
    make_analytics_card,
    make_confirmation_embed,
    make_embed,
    make_empty_state_embed,
    make_error_embed,
    upsert_embed_field,
)
from modules.mbx_logging import (
    LOG_NONINLINE_FIELD_NAMES,
    LOG_QUOTE_FIELD_NAMES,
    _send_log_to_channels,
    build_log_detail_fields,
    format_log_field_value,
    format_log_notes,
    format_log_quote,
    format_plain_log_block,
    format_reason_value,
    get_general_log_channel_id,
    get_general_log_channel_ids,
    get_punishment_log_channel_id,
    get_punishment_log_channel_ids,
    make_action_log_embed,
    normalize_log_embed,
    normalize_log_field_name,
    send_automod_log,
    send_log,
    send_punishment_log,
)
from modules.mbx_permissions import (
    DANGEROUS_PERMISSIONS,
    check_admin,
    check_owner,
    get_context_guild,
    has_capability,
    has_dangerous_perm,
    has_permission_capability,
    is_staff,
    is_staff_member,
    require_capability,
    requires_setup,
    resolve_member,
    respond_with_error,
)
from modules.mbx_images import (
    MODMAIL_RELAY_MAX_FILE_BYTES,
    MODMAIL_RELAY_MAX_FILES,
    MODMAIL_RELAY_MAX_TOTAL_BYTES,
    PROFILE_BRANDING_MAX_BYTES,
    ROLE_ICON_MAX_BYTES,
    _format_image_size_limit,
    _is_public_image_ip,
    _make_image_data_uri,
    _resolve_image_host_addresses,
    fetch_image_asset,
    fetch_image_bytes,
    fetch_image_data_uri,
    prepare_modmail_relay_attachments,
    validate_image_fetch_url,
)
from modules.mbx_formatters import (
    describe_punishment_record,
    format_case_status,
    format_user_id_ref,
    format_user_ref,
    get_case_id,
    get_case_label,
    get_modal_item_label,
    get_punishment_duration_and_expiry,
    get_record_expiry,
    get_user_display_name,
    hex_valid,
    is_record_active,
    join_lines,
)
from modules.mbx_automod import (
    AUTOMOD_PUNISHMENT_OPTIONS,
    AUTOMOD_THRESHOLD_PRESETS,
    AUTOMOD_WINDOW_PRESETS,
    AUTOMOD_TIMEOUT_PRESETS,
    SMART_DUPLICATE_THRESHOLD_PRESETS,
    SMART_DUPLICATE_WINDOW_PRESETS,
    SMART_CAPS_PERCENT_PRESETS,
    SMART_CAPS_LENGTH_PRESETS,
    AUTOMOD_REPORT_RESPONSE_PRESETS,
    SMART_AUTOMOD_DEFAULTS,
    calculate_smart_punishment,
    build_automod_dashboard_embed,
    format_minutes_interval,
    format_seconds_interval,
    format_compact_minutes_input,
    parse_positive_integer_input,
    parse_minutes_input,
    parse_automod_punishment_input,
    build_numeric_select_options,
    get_smart_automod_settings,
    store_native_automod_settings,
    store_smart_automod_settings,
    format_automod_punishment_label,
    get_automod_report_preset,
    build_default_native_automod_policy,
    get_native_automod_policy_steps,
    build_default_native_automod_step,
    format_native_automod_step_summary,
    get_native_rule_override,
    render_id_mentions,
    build_automod_bridge_embed,
    build_automod_policy_embed,
    build_automod_immunity_embed,
    build_automod_routing_embed,
    build_smart_automod_embed,
    build_automod_rule_browser_embed,
    describe_automod_rule_trigger,
    describe_automod_rule_actions,
    serialize_automod_rule,
    build_automod_trigger_from_payload,
    build_automod_actions_from_payload,
    fetch_native_automod_rules,
    build_native_automod_rules_embed,
    build_native_automod_rule_detail_embed,
    handle_abuse,
    punish_rogue_mod,
    get_native_automod_stats_bucket,
    prune_native_automod_bucket,
    record_native_automod_event,
    count_recent_native_automod_hits,
    has_recent_native_automod_step_application,
    record_native_automod_step_application,
    get_triggered_native_automod_step,
    build_native_automod_dedupe_key,
    claim_native_automod_execution,
    get_native_automod_action_label,
    native_automod_rule_has_enforcement,
    is_native_automod_exempt,
    apply_native_automod_escalation,
    run_smart_automod,
    ensure_native_rule_override_policy,
    resolve_user_for_automod_report,
    apply_automod_report_response,
    claim_native_automod_bridge_event,
    claim_native_automod_alert_message,
    clean_native_automod_alert_value,
    extract_native_automod_alert_context,
    find_recent_native_automod_audit_entry,
    find_matching_native_automod_alert_message,
    get_native_automod_audit_action_label,
    is_native_automod_audit_blocked,
    run_native_automod_bridge,
    handle_native_automod_execution,
    handle_native_automod_alert_message,
)
from modules.mbx_cases import (
    UNDO_REASON_PRESET_MAP,
    UNDO_REASON_PRESETS,
    add_punishment_record_log_fields,
    build_active_punishments_embed,
    build_case_detail_embed,
    build_case_summary_lines,
    build_history_archive_attachment,
    build_history_case_detail_embed,
    build_history_clear_summary,
    build_history_cleared_log_embed,
    build_history_overview_embed,
    build_no_history_embed,
    build_punishment_execution_log_embed,
    build_punishment_undo_log_embed,
    build_undo_panel_embed,
    calculate_member_risk,
    clear_user_history_records,
    format_case_summary_block,
    get_active_records_for_user,
    get_undo_reason_details,
    pop_case_record,
    record_case_reversal_stats,
    reverse_punishment_effect,
    undo_case_record,
)
from modules.mbx_punish import build_punish_embed, execute_punishment
from modules.mbx_branding import (
    BRANDING_UNSET,
    MAX_GUILD_MEMBER_BIO_LENGTH,
    _build_branding_panel_embed,
    _refresh_branding_panel,
    apply_guild_member_branding,
    build_branding_error_embed,
    save_branding_settings,
)
from modules.mbx_setup import (
    build_canned_replies_embed,
    build_config_dashboard_embed,
    build_escalation_matrix_embed,
    build_feature_flags_embed,
    build_mod_help_embed,
    build_modmail_settings_embed,
    build_rules_dashboard_embed,
    build_setup_dashboard_embed,
    build_setup_validation_embed,
    build_status_embed,
    get_feature_flag_name,
)
from modules.mbx_modmail import (
    _parse_user_id,
    apply_modmail_ticket_state,
    build_modmail_panel_embed,
    export_modmail_transcript,
    log_modmail_action,
    maybe_send_dm_modmail_panel,
    refresh_modmail_message,
    refresh_modmail_ticket_log,
    resolve_modmail_thread,
    resolve_modmail_user,
    send_modmail_panel_message,
    send_modmail_thread_intro,
)
from modules.mbx_staff import (
    _split_case_input,
    build_test_env_embed,
    get_mod_cases,
    get_staff_stats_embed,
    log_case_management_action,
)
from modules.mbx_public import (
    build_public_execution_embed,
    execute_public_execution_vote,
    get_public_execution_action_label,
)
from modules.mbx_roles import (
    add_custom_role_registry_fields,
    build_custom_role_registry_entries,
    build_role_info_embed,
    build_role_landing_embed,
    build_role_permissions_overview_embed,
    build_role_registry_embed,
    build_role_settings_embed,
    get_custom_role_limit,
    split_embed_entries,
)
from modules.mbx_services import get_feature_flag
from modules.mbx_utils import (
    create_progress_bar,
    extract_snowflake_id,
    format_duration,
    iso_to_dt,
    now_iso,
    parse_duration_str,
    truncate_text,
)
from ui.shared import (
    CommandBrowserView,
    CommandCategorySelect,
    ExpirableMixin,
    ModCasesSelect,
    StaffProfileView,
    StaffSelect,
    StaffView,
)
from ui.config import (
    AccessView,
    ActiveSelect,
    ActiveView,
    AntiNukeResolveConfirm1,
    AntiNukeResolveConfirm2,
    AntiNukeResolveView,
    ArchiveConfirmView,
    BrandingAvatarModal,
    BrandingBannerModal,
    BrandingBioModal,
    BrandingColorModal,
    BrandingDisplayNameModal,
    BrandingModmailBannerModal,
    BrandingPanelView,
    CannedRepliesView,
    CannedReplyModal,
    CloneConfirmView,
    ConfigChannelSelect,
    ConfigDashboardActionSelect,
    ConfigDashboardView,
    ConfigImportModal,
    ConfigRoleSelect,
    ConfigTypeSelect,
    EscalationMatrixModal,
    EscalationMatrixView,
    FeatureFlagSelect,
    FeatureFlagView,
    ImmunityModal,
    ModmailDiscussionThreadSelect,
    ModmailSettingsView,
    MultiConfigRoleSelect,
    RuleDeleteSelect,
    RuleDeleteView,
    RuleEditModal,
    RuleSelectForEdit,
    RuleSelectView,
    RulesDashboardView,
    SafetyView,
    SetupDashboardActionSelect,
    SetupDashboardView,
    TestEnvView,
)
from ui.automod import (
    AutoModBridgeSettingsView,
    AutoModChannelActionSelect,
    AutoModChannelSelect,
    AutoModChannelSettingsView,
    AutoModCustomReportResponseModal,
    AutoModDashboardView,
    AutoModImmunityChannelSelect,
    AutoModImmunityRoleSelect,
    AutoModImmunityUserSelect,
    AutoModImmunityView,
    AutoModPolicyEditorView,
    AutoModPolicyReasonModal,
    AutoModReportModal,
    AutoModReportResponseSelect,
    AutoModReportResponseView,
    AutoModRuleBrowserView,
    AutoModRuleSelect,
    AutoModStepPunishmentTypeSelect,
    AutoModStepSelect,
    AutoModStepThresholdSelect,
    AutoModStepTimeoutDurationSelect,
    AutoModStepValuesModal,
    AutoModStepWindowSelect,
    AutoModStoredValueRemoveSelect,
    AutoModStoredValueRemoveView,
    AutoModWarningView,
    SmartAutoModExemptChannelSelect,
    SmartAutoModExemptRoleSelect,
    SmartAutoModPatternModal,
    SmartAutoModSettingsView,
    SmartAutoModThresholdModal,
)
from ui.roles import (
    ConfirmDelete,
    CreateRoleModal,
    EditColorModal,
    EditNameModal,
    EditView,
    GradientModal,
    IconURLModal,
    RoleActionSelect,
    RoleSettingsAccessSelect,
    RoleSettingsAccessView,
    RoleSettingsActionSelect,
    RoleSettingsManageMemberModal,
    RoleSettingsTargetModal,
    RoleSettingsView,
    RoleStyleView,
    UploadIconView,
)
from ui.modmail import (
    CannedReplySelect,
    CannedReplyView,
    ModmailControlView,
    ModmailModal,
    ModmailPanelSelect,
    ModmailPanelView,
    ModmailPrioritySelect,
    ModmailPriorityView,
    ModmailTagsModal,
)
from ui.moderation import (
    AppealModal,
    AppealView,
    CaseLinksModal,
    CaseNoteModal,
    CasePanelView,
    CaseStateSelect,
    CaseStateView,
    CaseSwitchSelect,
    ConfirmRevokeView,
    CustomPunishDetailsModal,
    CustomTypeSelect,
    CustomTypeView,
    DenyAppealModal,
    FinalConfirmClear,
    FirstConfirmClear,
    HistoryActionButton,
    HistoryClearConfirmView,
    HistoryNavButton,
    HistorySelect,
    HistoryView,
    PublicExecutionApprovalView,
    PunishDetailsModal,
    PunishSelect,
    PunishView,
    RevokeAppealView,
    RevokeUndoView,
    UndoCaseSelect,
    UndoConfirmView,
    UndoReasonModal,
    UndoReasonSelect,
)

logger = logging.getLogger("MGXBot")

@tree.command(name="automod", description="Open the AutoMod control panel | admin")
@app_commands.default_permissions(administrator=True)
@require_capability("automod.configure")
async def automod_cmd(interaction: discord.Interaction):
    if not has_capability(interaction, "automod.view"):
        await respond_with_error(interaction, "Access denied.", scope=SCOPE_MODERATION)
        return
    if not get_feature_flag(bot.data_manager.config, "automod_panel", True):
        await respond_with_error(interaction, "The AutoMod panel is currently turned off in feature settings.", scope=SCOPE_MODERATION)
        return
    await interaction.response.send_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView(), ephemeral=True)

@bot.event
async def on_automod_action(execution: discord.AutoModAction):
    await handle_native_automod_execution(execution, source="gateway event")

@bot.event
async def on_socket_raw_receive(message):
    if isinstance(message, bytes):
        try:
            message = message.decode("utf-8")
        except UnicodeDecodeError:
            return
    if "AUTO_MODERATION_ACTION_EXECUTION" not in message:
        return

    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return

    if payload.get("t") != "AUTO_MODERATION_ACTION_EXECUTION":
        return

    data = payload.get("d")
    if not isinstance(data, dict):
        return

    try:
        execution = discord.AutoModAction(data=data, state=bot._connection)
    except Exception as exc:
        logger.warning("Failed to parse raw native AutoMod payload: %s", exc)
        return

    await handle_native_automod_execution(execution, source="raw gateway fallback")


async def setup(bot_instance: commands.Bot) -> None:
    bot_instance.tree.add_command(automod_cmd)
    bot_instance.add_listener(on_automod_action, "on_automod_action")
    bot_instance.add_listener(on_socket_raw_receive, "on_socket_raw_receive")
