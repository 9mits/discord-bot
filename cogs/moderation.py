"""Moderation commands and context menus."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Union

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
    can_use_command,
    get_context_guild,
    has_capability,
    has_dangerous_perm,
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

async def show_punish_menu(interaction: discord.Interaction, user: discord.User, public=False, reaction_count=None):
    await interaction.response.defer(ephemeral=True)
    embed = build_punish_embed(user)
    view = PunishView(user, interaction.user, public=public, reaction_count=reaction_count)
    msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    view.message = msg

async def show_history_menu(
    interaction: discord.Interaction,
    user: discord.Member,
    *,
    mode: str = "history",
    selected_case_id: Optional[int] = None,
    initial_undo_reason: Optional[str] = None,
):
    await interaction.response.defer(ephemeral=True)
    uid = str(user.id)
    history_data = bot.data_manager.punishments.get(uid, [])
    if not history_data:
        await interaction.followup.send(embed=build_no_history_embed(user, interaction.guild), ephemeral=True)
        return
    view = HistoryView(
        user,
        mode=mode,
        selected_case_id=selected_case_id,
        initial_undo_reason=initial_undo_reason,
    )
    message = await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True, wait=True)
    view.message = message

async def show_case_panel(
    interaction: discord.Interaction,
    *,
    case_id: Optional[int] = None,
    user: Optional[discord.Member] = None,
):
    if not get_feature_flag(bot.data_manager.config, "advanced_case_panel", True):
        await respond_with_error(interaction, "The case panel is currently turned off in the feature settings.", scope=SCOPE_MODERATION)
        return

    await interaction.response.defer(ephemeral=True)

    target_user_id: Optional[str] = None
    target_user: Optional[Union[discord.Member, discord.User]] = user
    case_ids: List[int] = []

    if case_id:
        target_user_id, record = bot.data_manager.get_case(case_id)
        if not record or not target_user_id:
            await interaction.followup.send(
                embed=make_empty_state_embed(
                    "Case Not Found",
                    f"> No case with ID `{case_id}` was found.",
                    scope=SCOPE_MODERATION,
                    guild=interaction.guild,
                ),
                ephemeral=True,
            )
            return
        case_ids = [case_id]
        if not target_user:
            target_user = interaction.guild.get_member(int(target_user_id))

    elif user:
        target_user_id = str(user.id)
        case_ids = [record.get("case_id") for record in bot.data_manager.get_user_cases(user.id) if record.get("case_id")]
        if not case_ids:
            await interaction.followup.send(
                embed=make_empty_state_embed(
                    "No Cases Found",
                    f"> **{user.display_name}** has no recorded cases to manage.",
                    scope=SCOPE_MODERATION,
                    guild=interaction.guild,
                    thumbnail=user.display_avatar.url,
                ),
                ephemeral=True,
            )
            return
    else:
        await interaction.followup.send(
            embed=make_error_embed(
                "Case Panel Requires Context",
                "> Choose a `case_id` or a `user` so the bot knows which case to open.",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            ),
            ephemeral=True,
        )
        return

    view = CasePanelView(target_user_id, case_ids, target_user=target_user)
    message = await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True, wait=True)
    view.message = message

@app_commands.default_permissions(moderate_members=True)
class ModGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="mod", description="Advanced moderation suite")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Group-level gate: let each subcommand use its own narrower
        # capability. Requiring only mod.case_panel here blocks roles that can
        # punish but cannot open case panels.
        command_capabilities = {
            "punish": "mod.punish",
            "publicpunish": "mod.public_punish",
            "history": "mod.history",
            "active": "mod.active",
            "undopunish": "mod.undo",
            "purge": "mod.purge",
            "lock": "mod.lock",
            "unlock": "mod.lock",
            "case": "mod.case_panel",
        }
        command_name = getattr(getattr(interaction, "command", None), "name", None)
        capability = command_capabilities.get(command_name, "mod.case_panel")
        command_key = f"mod {command_name}" if command_name else "mod"
        if not can_use_command(interaction, command_key, capability):
            await respond_with_error(
                interaction,
                "You do not have permission to use these moderation tools.",
                scope=SCOPE_MODERATION,
            )
            return False
        return True

    @app_commands.command(name="punish", description="Sanction a user with a warning, timeout, or ban")
    @app_commands.default_permissions(moderate_members=True)
    @require_capability("mod.punish")
    async def punish(self, interaction: discord.Interaction, user: discord.User):
        await show_punish_menu(interaction, user)

    @app_commands.command(name="publicpunish", description="Punish a user and announce it publicly in this channel")
    @app_commands.default_permissions(moderate_members=True)
    @require_capability("mod.public_punish")
    async def publicpunish(self, interaction: discord.Interaction, user: discord.User):
        await show_punish_menu(interaction, user, public=True)

    @app_commands.command(name="history", description="Retrieve the complete disciplinary history of a user")
    @app_commands.default_permissions(moderate_members=True)
    @require_capability("mod.history")
    async def history(self, interaction: discord.Interaction, user: discord.Member):
        await show_history_menu(interaction, user)

    @app_commands.command(name="active", description="Display a list of all currently active punishments")
    @app_commands.default_permissions(moderate_members=True)
    @require_capability("mod.active")
    async def active(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        now = discord.utils.utcnow()
        active_list = []
        for uid, records in bot.data_manager.punishments.items():
            for i, rec in enumerate(records):
                dur = rec.get("duration_minutes", 0)
                p_type = rec.get("type", "timeout")
                if p_type == "ban" and not rec.get("active", True):
                    continue
                if dur == 0: continue
                ts_str = rec.get("timestamp")
                ts = iso_to_dt(ts_str)
                if not ts: continue

                if dur == -1:
                    # Bans are always active for this list
                    expiry = datetime.max.replace(tzinfo=timezone.utc)
                elif dur > 0:
                    expiry = ts + timedelta(minutes=dur)
                else:
                    continue

                if dur == -1 or expiry > now:
                    member = interaction.guild.get_member(int(uid))
                    name = member.display_name if member else uid
                    active_list.append((uid, rec, expiry, i+1, name))
        if not active_list:
            await interaction.followup.send("No active punishments found.", ephemeral=True)
            return
        active_list.sort(key=lambda x: x[2])
        embed = build_active_punishments_embed(interaction.guild, active_list, now)
        view = ActiveView(active_list)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="undopunish", description="Open the punishment undo control panel")
    @app_commands.describe(reason="Optional reason to prefill in the undo panel")
    @app_commands.default_permissions(moderate_members=True)
    @require_capability("mod.undo")
    async def undopunish(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        await show_history_menu(interaction, user, mode="undo", initial_undo_reason=reason)

    @app_commands.command(name="purge", description="Bulk delete messages (Channel or User)")
    @app_commands.describe(amount="Messages to check/delete (max 999)", user="Optional: Target specific user", keyword="Optional: Filter by keyword")
    @app_commands.default_permissions(manage_messages=True)
    @require_capability("mod.purge")
    async def purge(self, interaction: discord.Interaction, amount: int, user: discord.Member = None, keyword: str = None):
        if amount < 1 or amount > 999:
            await interaction.response.send_message("Amount must be between 1 and 999.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Scenario 1: Simple Channel Purge (No filters)
        if not user and not keyword:
            try:
                deleted = await interaction.channel.purge(limit=amount)
                await interaction.followup.send(f"Cleared **{len(deleted)}** messages.", ephemeral=True)

                log_embed = make_embed(
                    "Messages Purged",
                    "> A bulk message purge was executed in a channel.",
                    kind="warning",
                    scope=SCOPE_MODERATION,
                    guild=interaction.guild,
                )
                log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
                log_embed.add_field(name="Channel", value=f"{interaction.channel.mention} (`{interaction.channel.id}`)", inline=True)
                log_embed.add_field(name="Amount", value=str(len(deleted)), inline=True)
                await send_punishment_log(interaction.guild, log_embed)
            except discord.HTTPException as e:
                await interaction.followup.send(f"Failed to purge: {e}", ephemeral=True)
            return

        # Scenario 2: Filtered Purge (User or Keyword)
        to_delete = []
        manual_delete = []
        deleted_count = 0

        now = discord.utils.utcnow()
        two_weeks_ago = now - timedelta(days=14)

        # Scan deeper for filtered purge
        async for message in interaction.channel.history(limit=10000):
            if deleted_count + len(to_delete) + len(manual_delete) >= amount:
                break

            # Filter Logic
            if user and message.author.id != user.id:
                continue
            if keyword and keyword.lower() not in message.content.lower():
                continue

            if message.created_at > two_weeks_ago:
                to_delete.append(message)
                if len(to_delete) >= 100:
                    try:
                        await interaction.channel.delete_messages(to_delete)
                        deleted_count += len(to_delete)
                        to_delete = []
                    except Exception: pass
            else:
                manual_delete.append(message)

        if to_delete:
            try:
                await interaction.channel.delete_messages(to_delete)
                deleted_count += len(to_delete)
            except Exception: pass

        for m in manual_delete:
            try:
                await m.delete()
                deleted_count += 1
                await asyncio.sleep(1.2)
            except Exception: pass

        if deleted_count == 0:
             await interaction.followup.send(f"No matching messages found to purge.", ephemeral=True)
             return

        target_str = user.mention if user else "Anyone"
        await interaction.followup.send(f"Cleared **{deleted_count}** messages from {target_str}.", ephemeral=True)

        log_embed = make_embed(
            "Filtered Purge",
            "> A targeted purge removed messages using user or keyword filters.",
            kind="warning",
            scope=SCOPE_MODERATION,
            guild=interaction.guild,
        )
        log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
        log_embed.add_field(name="Target", value=f"{target_str}", inline=True)
        log_embed.add_field(name="Channel", value=f"{interaction.channel.mention} (`{interaction.channel.id}`)", inline=True)
        log_embed.add_field(name="Amount", value=str(deleted_count), inline=True)
        if keyword: log_embed.add_field(name="Keyword", value=keyword, inline=True)
        await send_punishment_log(interaction.guild, log_embed)

    @app_commands.command(name="lock", description="Restrict message sending permissions in this channel")
    @app_commands.default_permissions(manage_channels=True)
    @require_capability("mod.lock")
    async def lock(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        default_role = interaction.guild.default_role
        overwrite = channel.overwrites_for(default_role)
        overwrite.send_messages = False
        try:
            await channel.set_permissions(default_role, overwrite=overwrite, reason=f"Locked by {interaction.user}")
            public_embed = make_embed(
                "Channel Locked",
                "> This channel is temporarily locked by the moderation team.",
                kind="danger",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            )
            msg = await channel.send(embed=public_embed)
            if "locked_channels" not in bot.data_manager.config: bot.data_manager.config["locked_channels"] = {}
            bot.data_manager.config["locked_channels"][str(channel.id)] = msg.id
            await bot.data_manager.save_config()
            await interaction.followup.send("Channel locked.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="unlock", description="Restore message sending permissions in this channel")
    @app_commands.default_permissions(manage_channels=True)
    @require_capability("mod.lock")
    async def unlock(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        default_role = interaction.guild.default_role
        overwrite = channel.overwrites_for(default_role)
        overwrite.send_messages = None
        try:
            await channel.set_permissions(default_role, overwrite=overwrite, reason=f"Unlocked by {interaction.user}")
            cid = str(channel.id)
            if "locked_channels" in bot.data_manager.config:
                if cid in bot.data_manager.config["locked_channels"]:
                    try:
                        msg = await channel.fetch_message(bot.data_manager.config["locked_channels"][cid])
                        await msg.delete()
                    except Exception: pass
                    del bot.data_manager.config["locked_channels"][cid]
                    await bot.data_manager.save_config()
            await interaction.followup.send("Channel unlocked.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="help", description="View all moderation commands")
    async def help(self, interaction: discord.Interaction):
        embed = build_mod_help_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="case", description="Open the case panel for a user or case ID")
    @app_commands.describe(case_id="Open a specific case by ID", user="Open the most recent case for a user")
    @require_capability("mod.case_panel")
    async def case(self, interaction: discord.Interaction, case_id: Optional[app_commands.Range[int, 1, 999999]] = None, user: Optional[discord.Member] = None):
        await show_case_panel(interaction, case_id=case_id, user=user)

@tree.context_menu(name="Punish User")
@app_commands.default_permissions(moderate_members=True)
async def punish_context(interaction: discord.Interaction, user: discord.User):
    if not has_capability(interaction, "mod.punish"):
        await respond_with_error(interaction, "You do not have permission to use this command.", scope=SCOPE_MODERATION)
        return
    await show_punish_menu(interaction, user)

@tree.context_menu(name="Mod History")
@app_commands.default_permissions(moderate_members=True)
async def history_context(interaction: discord.Interaction, user: discord.Member):
    if not has_capability(interaction, "mod.history"):
        await respond_with_error(interaction, "You do not have permission to use this command.", scope=SCOPE_MODERATION)
        return
    await show_history_menu(interaction, user)

@bot.event
async def on_raw_reaction_add(payload):
    return


async def setup(bot_instance: commands.Bot) -> None:
    bot_instance.tree.add_command(ModGroup())
    bot_instance.tree.add_command(punish_context)
    bot_instance.tree.add_command(history_context)
    bot_instance.add_listener(on_raw_reaction_add, "on_raw_reaction_add")
