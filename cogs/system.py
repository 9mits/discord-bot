"""System, setup, safety, and administrative commands."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from modules.mbx_constants import DEFAULT_ARCHIVE_CAT_ID, SCOPE_ANALYTICS, SCOPE_SYSTEM
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

_CMD_CATEGORIES = {
    "Moderation":  {"mod", "punish", "history", "case", "active", "undopunish", "clear", "lock", "unlock"},
    "Modmail":     {"modmail"},
    "AutoMod":     {"automod"},
    "Roles":       {"role", "role-manage", "role-settings", "role-help"},
    "System":      {"setup", "config", "rules", "branding", "access", "safety", "archive", "unarchive",
                    "clone", "lockdown", "unlockdown", "status", "stats", "directory", "listcommands",
                    "publicpunish", "internals"},
}

def _categorise_commands() -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {cat: [] for cat in _CMD_CATEGORIES}
    buckets["Other"] = []
    for cmd in bot.tree.walk_commands():
        matched = False
        for cat, names in _CMD_CATEGORIES.items():
            if cmd.qualified_name.split(" ")[0] in names:
                buckets[cat].append(f"`/{cmd.qualified_name}` — {cmd.description}")
                matched = True
                break
        if not matched:
            buckets["Other"].append(f"`/{cmd.qualified_name}` — {cmd.description}")
    return {k: v for k, v in buckets.items() if v}

@tree.command(name="setup", description="Open the configuration dashboard")
@app_commands.default_permissions(manage_guild=True)
@require_capability("setup.run")
async def setup_cmd(interaction: discord.Interaction):
    embed = build_setup_dashboard_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, view=SetupDashboardView(), ephemeral=True)

@tree.command(name="listcommands", description="Browse all available commands by category")
@app_commands.default_permissions(manage_guild=True)
@require_capability("setup.run")
async def list_commands(interaction: discord.Interaction):
    buckets = _categorise_commands()
    embed = make_embed(
        "Command Registry",
        f"> **{sum(len(v) for v in buckets.values())} command(s)** across {len(buckets)} categories.\n"
        "> Use the dropdown below to browse each category.",
        kind="info",
        scope=SCOPE_SYSTEM,
        guild=interaction.guild,
    )
    for cat, lines in buckets.items():
        embed.add_field(name=cat, value=f"{len(lines)} command(s)", inline=True)
    view = CommandBrowserView(interaction.guild)
    msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    view.message = msg

@tree.command(name="stats", description="Display comprehensive server-wide moderation analytics")
@app_commands.default_permissions(manage_guild=True)
@require_capability("system.stats")
async def stats(interaction: discord.Interaction, target: Optional[discord.Member] = None):
    if target:
        uid = str(target.id)
        cases = get_mod_cases(uid)

        target_is_staff = is_staff_member(target)

        if not target_is_staff and not cases:
            await interaction.response.send_message(f"{target.mention} is not a staff member and has no recorded history.", ephemeral=True)
            return

        reversals = bot.data_manager.mod_stats.get("reversals", {}).get(uid, 0)
        embed = get_staff_stats_embed(target, cases, reversals)

        view = StaffProfileView(target, cases, [], None, embed, interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return

    # Server-wide logic
    await interaction.response.defer(ephemeral=True)

    all_records = []
    for records in bot.data_manager.punishments.values():
        all_records.extend(records)

    # Basic Counts
    active_cases = sum(1 for record in all_records if is_record_active(record))
    total_issued = bot.data_manager.config.get("stats", {}).get("total_issued", active_cases)
    cases_cleared = bot.data_manager.config.get("stats", {}).get("cases_cleared", 0)

    bans = sum(1 for r in all_records if r.get("type") == "ban")
    warns = sum(1 for r in all_records if r.get("type") == "warn")
    timeouts = sum(1 for r in all_records if r.get("type") == "timeout")

    # Advanced Stats
    mod_counts = Counter(r.get("moderator") for r in all_records)
    top_mods = mod_counts.most_common(3)

    reason_counts = Counter(r.get("reason") for r in all_records)
    top_reasons = reason_counts.most_common(3)

    now = discord.utils.utcnow()
    last_24h = sum(1 for r in all_records if (dt := iso_to_dt(r.get("timestamp"))) and dt > now - timedelta(hours=24))
    last_7d = sum(1 for r in all_records if (dt := iso_to_dt(r.get("timestamp"))) and dt > now - timedelta(days=7))

    embed = make_embed(
        "Server Moderation Analytics",
        "> Server-wide moderation totals, recent activity, and staff output trends.",
        kind="analytics",
        scope=SCOPE_ANALYTICS,
        guild=interaction.guild,
        thumbnail=interaction.guild.icon.url if interaction.guild.icon else None,
    )

    # Overview
    embed.add_field(name="Lifetime Overview", value=f">>> Total Issued: **{total_issued}**\nCases Cleared: **{cases_cleared}**\nActive Records: **{active_cases}**", inline=False)

    # Breakdown
    embed.add_field(name="Action Breakdown", value=f">>> Bans: **{bans}**\nTimeouts: **{timeouts}**\nWarnings: **{warns}**", inline=True)
    embed.add_field(name="Recent Activity", value=f">>> Last 24 Hours: **{last_24h}**\nLast 7 Days: **{last_7d}**", inline=True)

    # Top Mods
    if top_mods:
        mod_str = "\n".join([f"<@{m}>: **{c}**" for m, c in top_mods])
        embed.add_field(name="Top Moderators", value=f">>> {mod_str}", inline=True)

    # Top Reasons
    if top_reasons:
        reason_str = "\n".join([f"{r}: **{c}**" for r, c in top_reasons])
        embed.add_field(name="Common Violations", value=f">>> {reason_str}", inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="directory", description="Display staff team directory")
@app_commands.default_permissions(manage_guild=True)
@require_capability("system.directory")
async def directory(interaction: discord.Interaction):
    from modules.mbx_permission_engine import PermissionEngine

    await interaction.response.defer(ephemeral=True)

    config = bot.data_manager.config
    engine = PermissionEngine.for_guild(config)
    guild_owner_id = interaction.guild.owner_id

    admins: list[discord.Member] = []
    mods: list[discord.Member] = []

    for member in interaction.guild.members:
        if member.bot:
            continue
        role_ids = [int(r.id) for r in member.roles]
        is_admin = engine.has_capability(
            "setup.run",
            user_id=int(member.id),
            role_ids=role_ids,
            guild_owner_id=guild_owner_id,
            discord_permissions=member.guild_permissions,
        )
        if is_admin:
            admins.append(member)
            continue
        is_mod = engine.has_capability(
            "mod.case_panel",
            user_id=int(member.id),
            role_ids=role_ids,
            guild_owner_id=guild_owner_id,
            discord_permissions=member.guild_permissions,
        )
        if is_mod:
            mods.append(member)

    admins.sort(key=lambda m: m.top_role.position, reverse=True)
    mods.sort(key=lambda m: m.top_role.position, reverse=True)

    embed = make_embed(
        "Staff Team Directory",
        "> Current configured staff roster for moderation and administrative access.",
        kind="info",
        scope=SCOPE_ANALYTICS,
        guild=interaction.guild,
    )

    if admins:
        embed.add_field(name="Administrator", value=">>> " + "\n".join([m.mention for m in admins]), inline=False)
    if mods:
        embed.add_field(name="Moderator", value=">>> " + "\n".join([m.mention for m in mods]), inline=False)

    if not admins and not mods:
        embed.description = "> No staff members found."

    all_staff = admins + mods
    unique_staff = []
    seen = set()
    for m in all_staff:
        if m.id not in seen:
            unique_staff.append(m)
            seen.add(m.id)

    view = StaffView(unique_staff) if unique_staff else None
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@tree.command(name="config", description="Open the bot settings panel")
@app_commands.default_permissions(manage_guild=True)
@require_capability("config.edit")
async def config_cmd(interaction: discord.Interaction):
    if not get_feature_flag(bot.data_manager.config, "config_panel", True):
        await respond_with_error(interaction, "The bot settings panel is currently turned off in the feature settings.", scope=SCOPE_SYSTEM)
        return
    embed = build_config_dashboard_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, view=ConfigDashboardView(), ephemeral=True)

@tree.command(name="publicexecution", description="Start a public vote to ban a user")
@app_commands.default_permissions(manage_guild=True)
@require_capability("mod.public_punish")
async def publicexecution(interaction: discord.Interaction, user: discord.User, reaction_count: int):
    from cogs.moderation import show_punish_menu

    await show_punish_menu(interaction, user, public=True, reaction_count=reaction_count)

@tree.command(name="internals", description="View system constants and definitions")
@app_commands.default_permissions(manage_guild=True)
@require_capability("system.internals")
async def internals(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    conf = bot.data_manager.config

    embed = make_embed(
        "System Internals",
        "> Read-only view of the bot's configured safety constants and operational roles.",
        kind="muted",
        scope=SCOPE_SYSTEM,
        guild=interaction.guild,
    )

    # Dangerous Permissions
    perms_list = [p.replace('_', ' ').title() for p in DANGEROUS_PERMISSIONS]
    embed.add_field(name="Dangerous Permissions (Anti-Nuke Triggers)", value=">>> " + "\n".join(perms_list), inline=False)

    # Current Config
    g = interaction.guild
    roles_info = (
        f"**Owner Role:** {fmt_role(g, conf.get('role_owner'))}\n"
        f"**Admin Role:** {fmt_role(g, conf.get('role_admin'))}\n"
        f"**Mod Role:** {fmt_role(g, conf.get('role_mod'))}\n"
        f"**Community Manager:** {fmt_role(g, conf.get('role_community_manager'))}\n"
        f"**Anchor Role:** {fmt_role(g, conf.get('role_anchor'))}"
    )
    embed.add_field(name="Current Role Configuration", value=f">>> {roles_info}", inline=False)

    # Mod Commands
    mod_commands = [
        "/mod punish", "/mod history", "/mod active", "/mod undopunish",
        "/mod lock", "/mod unlock", "/mod purge"
    ]
    mod_cmds_fmt = "\n".join(mod_commands)
    embed.add_field(name="Classified Mod Commands", value=f">>> {mod_cmds_fmt}", inline=False)

    # Immunity List
    immune_count = len(bot.data_manager.config.get("immunity_list", []))
    embed.add_field(name="Immunity List", value=f"> {immune_count} users immune", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="archive", description="Move this channel to the archive category")
@app_commands.default_permissions(manage_channels=True)
@require_capability("system.archive")
async def archive(interaction: discord.Interaction):
    # Do not defer immediately, we need to send the confirmation view first
    channel = interaction.channel
    guild = interaction.guild
    target_cat_id = bot.data_manager.config.get("category_archive", DEFAULT_ARCHIVE_CAT_ID)
    target_cat = guild.get_channel(target_cat_id)

    if not target_cat or not isinstance(target_cat, discord.CategoryChannel):
        await interaction.response.send_message(f"Archive category ({target_cat_id}) not found.", ephemeral=True)
        return

    old_name = channel.name
    new_name = f"archived-{old_name}"[:100]

    # Save state before archiving
    overwrites_data = []
    for target, overwrite in channel.overwrites.items():
        allow, deny = overwrite.pair()
        overwrites_data.append({
            "id": target.id,
            "type": "role" if isinstance(target, discord.Role) else "member",
            "allow": allow.value,
            "deny": deny.value
        })

    # Overwrites: Reset all, set @everyone to deny view
    final_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }

    view = ArchiveConfirmView(channel, target_cat, old_name, new_name, overwrites_data, final_overwrites)
    await interaction.response.send_message(f"Are you sure you want to archive **{channel.name}**?", view=view, ephemeral=True)

@tree.command(name="unarchive", description="Restore this channel from the archives")
@app_commands.default_permissions(manage_channels=True)
@require_capability("system.archive")
async def unarchive(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    cid = str(channel.id)
    archives = bot.data_manager.config.get("archived_channels", {})

    if cid not in archives:
        # Migration Logic: Check for name match
        found_old_id = None
        for old_id, entry in archives.items():
            orig = entry.get("original_name", "")
            expected = f"archived-{orig}"[:100]
            if channel.name == expected:
                found_old_id = old_id
                break

        if found_old_id:
            data = archives.pop(found_old_id)
            archives[cid] = data
            bot.data_manager.config["archived_channels"] = archives
            await bot.data_manager.save_config()
            await interaction.followup.send(f"**System:** Channel ID mismatch detected (Server Transfer?).\n> Migrated archive data from `{found_old_id}` to `{cid}`.", ephemeral=True)
        else:
            await interaction.followup.send("This channel is not in the archive registry.", ephemeral=True)
            return

    data = archives[cid]

    # Restore Logic
    new_name = data.get("original_name", channel.name.replace("archived-", ""))
    cat_id = data.get("category_id")
    category = interaction.guild.get_channel(cat_id) if cat_id else None

    # Reconstruct Overwrites
    new_overwrites = {}
    for item in data.get("overwrites", []):
        obj_id = item["id"]
        target = interaction.guild.get_role(obj_id) if item["type"] == "role" else interaction.guild.get_member(obj_id)
        if target:
            allow = discord.Permissions(item["allow"])
            deny = discord.Permissions(item["deny"])
            new_overwrites[target] = discord.PermissionOverwrite.from_pair(allow, deny)

    try:
        await channel.edit(name=new_name, category=category, overwrites=new_overwrites, reason=f"Unarchived by {interaction.user}")
    except Exception as e:
        await interaction.followup.send(f"Failed to unarchive channel: {e}", ephemeral=True)
        return

    # Cleanup
    del bot.data_manager.config["archived_channels"][cid]
    await bot.data_manager.save_config()

    await interaction.followup.send(f"Channel unarchived and restored.", ephemeral=True)

    # Log
    log_embed = make_embed(
        "Channel Unarchived",
        "> An archived channel was restored to its previous structure and permissions.",
        kind="success",
        scope=SCOPE_SYSTEM,
        guild=interaction.guild,
    )
    log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
    log_embed.add_field(name="Channel", value=f"{channel.mention} (`{channel.id}`)", inline=True)
    log_embed.add_field(name="Restored Name", value=new_name, inline=True)
    await send_log(interaction.guild, log_embed)

@tree.command(name="clone", description="Archive current channel and create a fresh clone")
@app_commands.default_permissions(manage_channels=True)
@require_capability("system.archive")
async def clone(interaction: discord.Interaction):
    channel = interaction.channel
    guild = interaction.guild
    target_cat_id = bot.data_manager.config.get("category_archive", DEFAULT_ARCHIVE_CAT_ID)
    target_cat = guild.get_channel(target_cat_id)

    if not target_cat or not isinstance(target_cat, discord.CategoryChannel):
        await interaction.response.send_message(f"Archive category ({target_cat_id}) not found.", ephemeral=True)
        return

    old_name = channel.name
    new_name = f"archived-{old_name}"[:100]

    overwrites_data = []
    for target, overwrite in channel.overwrites.items():
        allow, deny = overwrite.pair()
        overwrites_data.append({
            "id": target.id,
            "type": "role" if isinstance(target, discord.Role) else "member",
            "allow": allow.value,
            "deny": deny.value
        })

    final_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }

    view = CloneConfirmView(channel, target_cat, old_name, new_name, overwrites_data, final_overwrites)
    await interaction.response.send_message(f"**WARNING:** This will archive **{channel.name}** and create a fresh clone.\nAre you sure?", view=view, ephemeral=True)

@tree.command(name="rules", description="Configure automated punishment escalation rules")
@app_commands.default_permissions(manage_guild=True)
@require_capability("rules.edit")
async def rules(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_rules_dashboard_embed(interaction.guild), view=RulesDashboardView(), ephemeral=True)

@tree.command(name="branding", description="Customize the bot's look for this server")
@app_commands.default_permissions(manage_guild=True)
@require_capability("branding.edit")
async def branding_cmd(interaction: discord.Interaction):
    embed = _build_branding_panel_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, view=BrandingPanelView(), ephemeral=True)

@tree.command(name="safetypanel", description="Manage anti-nuke immunity settings")
@app_commands.default_permissions(manage_guild=True)
@require_capability("system.safety")
async def safety_panel(interaction: discord.Interaction):
    embed = make_embed(
        "Anti-Nuke Safety Panel",
        "> Manage users who are immune to automated anti-nuke enforcement.",
        kind="warning",
        scope=SCOPE_SYSTEM,
        guild=interaction.guild,
    )
    await interaction.response.send_message(embed=embed, view=SafetyView(), ephemeral=True)

@tree.command(name="access", description="Manage role-based access to moderation tools")
@app_commands.default_permissions(manage_guild=True)
@require_capability("permissions.edit")
async def access(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    roles = bot.data_manager.config.get("mod_roles", [])
    mentions = [f"<@&{rid}>" for rid in roles]
    desc = "**Allowed Mod Roles:**\n" + ", ".join(mentions) if mentions else "No specific roles configured (Admins & Mods allowed)."
    embed = make_embed(
        "Mod Access Configuration",
        f"> {desc}",
        kind="info",
        scope=SCOPE_SYSTEM,
        guild=interaction.guild,
    )
    view = AccessView()
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@tree.command(name="lockdown", description="Emergency: hide all channels from @everyone")
@app_commands.default_permissions(manage_guild=True)
@require_capability("system.lockdown")
async def lockdown(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    # Save current state
    lockdown_data = {}
    channels_affected = 0

    for channel in guild.channels:
        # Skip if not a text/voice/stage channel (categories handled implicitly or skipped)
        if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel)):
            continue

        overwrite = channel.overwrites_for(guild.default_role)
        # Save the current 'view_channel' setting (True, False, or None)
        lockdown_data[str(channel.id)] = overwrite.view_channel

        # Apply Lockdown
        overwrite.view_channel = False
        try:
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"Server Lockdown by {interaction.user}")
            channels_affected += 1
        except Exception:
            pass

    bot.data_manager.lockdown = lockdown_data
    await bot.data_manager.save_lockdown()

    await interaction.followup.send(f"**SERVER LOCKDOWN ACTIVE.**\n> Hidden {channels_affected} channels from @everyone.", ephemeral=True)

@tree.command(name="unlockdown", description="Restore channel visibility after lockdown")
@app_commands.default_permissions(manage_guild=True)
@require_capability("system.lockdown")
async def unlockdown(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    lockdown_data = bot.data_manager.lockdown

    if not lockdown_data:
        await interaction.followup.send("No lockdown data found.", ephemeral=True)
        return

    restored_count = 0
    for cid, original_perm in lockdown_data.items():
        channel = guild.get_channel(int(cid))
        if channel:
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.view_channel = original_perm
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"Lockdown Lifted by {interaction.user}")
                restored_count += 1
            except Exception: pass

    bot.data_manager.lockdown = {}
    await bot.data_manager.save_lockdown()

    await interaction.followup.send(f"**LOCKDOWN LIFTED.**\n> Restored visibility for {restored_count} channels.", ephemeral=True)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        if str(error) == "guild_not_configured":
            msg = "> This server hasn't been configured yet. Ask an admin to run `/setup`."
        else:
            msg = "> You do not have permission to use this command."
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=make_error_embed("Access Denied", msg, scope=SCOPE_SYSTEM, guild=interaction.guild),
                ephemeral=True,
            )
        return

    if isinstance(error, app_commands.CommandInvokeError):
        if isinstance(error.original, discord.NotFound) and error.original.code == 10062:
            logger.warning("Interaction timed out (10062).")
            return
        logger.exception("Command invoke failure [%s]: %s", interaction.command.qualified_name if interaction.command else "unknown", error.original)
    else:
        logger.exception("Command failed [%s]: %s", interaction.command.qualified_name if interaction.command else "unknown", error)

    try:
        await respond_with_error(
            interaction,
            "The bot hit an unexpected error while processing this action. No further changes were applied.",
            scope=SCOPE_SYSTEM,
        )
    except Exception:
        pass

@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    if bot.data_manager and after.guild:
        bot.data_manager._current_guild_id = after.guild.id
        await bot.data_manager.ensure_guild_loaded(after.guild.id)
    # Check if dangerous permissions were ADDED
    if not has_dangerous_perm(before.permissions) and has_dangerous_perm(after.permissions):
        # Calculate dangerous added permissions IMMEDIATELY before reverting
        dangerous_added = []
        for p in DANGEROUS_PERMISSIONS:
            if getattr(after.permissions, p) and not getattr(before.permissions, p):
                dangerous_added.append(p.replace('_', ' ').title())
        val_str = ", ".join(dangerous_added) if dangerous_added else "Unknown"

        # Fetch audit log to find the culprit
        async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
            if entry.target.id == after.id:
                actor = entry.user
                if actor.id == bot.user.id: return # Ignore self

                # Check Immunity
                if str(actor.id) in bot.data_manager.config.get("immunity_list", []):
                    return

                # Capture dangerous state for potential resolve
                restore_data = {"type": "role_perm", "target_id": after.id, "permissions": after.permissions.value}

                # REVERT
                try:
                    await after.edit(permissions=before.permissions, reason=f"Anti-Nuke: Reverting unauthorized permission change by {actor}")
                except Exception:
                    pass

                # Build Detailed Embed
                embed = make_embed(
                    "Security Alert: Dangerous Permissions Added",
                    "> A protected role permission change was reverted automatically.",
                    kind="danger",
                    scope=SCOPE_SYSTEM,
                    guild=after.guild,
                )
                embed.add_field(name="Actor", value=f"{actor.mention} (`{actor.id}`)", inline=True)
                joined_at = getattr(actor, "joined_at", None)
                embed.add_field(name="Actor Account Age", value=f"Created: {discord.utils.format_dt(actor.created_at, 'R')}\nJoined: {discord.utils.format_dt(joined_at, 'R') if joined_at else 'Unknown'}", inline=True)

                embed.add_field(name="Role", value=f"{after.mention} (`{after.id}`)", inline=True)
                embed.add_field(name="Role Created", value=discord.utils.format_dt(after.created_at, 'F'), inline=True)

                embed.add_field(name="Permissions Added", value=f"> {val_str}", inline=True)
                embed.add_field(name="Immediate Action", value="> Changes Reverted", inline=True)

                # PUNISH
                await punish_rogue_mod(after.guild, actor, f"Added dangerous permissions to role **{after.name}**", embed=embed, restore_data=restore_data)
                break

@tree.command(name="status", description="View bot latency and uptime")
@app_commands.default_permissions(moderate_members=True)
@require_capability("system.status")
async def status_cmd(interaction: discord.Interaction):
    embed = await build_status_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if bot.data_manager and after.guild:
        bot.data_manager._current_guild_id = after.guild.id
        await bot.data_manager.ensure_guild_loaded(after.guild.id)
    # Check if roles were added
    if len(before.roles) < len(after.roles):
        added_roles = [r for r in after.roles if r not in before.roles]
        for role in added_roles:
            if has_dangerous_perm(role.permissions):
                # Dangerous role added
                async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update):
                    if entry.target.id == after.id:
                        actor = entry.user
                        if actor.id == bot.user.id: return # Ignore self

                        # Check Immunity
                        if str(actor.id) in bot.data_manager.config.get("immunity_list", []):
                            return

                        # Capture dangerous state for potential resolve
                        restore_data = {"type": "member_role", "target_id": after.id, "extra_id": role.id}

                        # REVERT (Remove the role from the target)
                        try:
                            await after.remove_roles(role, reason=f"Anti-Nuke: Reverting unauthorized role grant by {actor}")
                        except Exception:
                            pass

                        # Build Detailed Embed
                        embed = make_embed(
                            "Security Alert: Dangerous Role Granted",
                            "> A protected role grant was reverted and the actor was flagged.",
                            kind="danger",
                            scope=SCOPE_SYSTEM,
                            guild=after.guild,
                        )
                        embed.add_field(name="Actor", value=f"{actor.mention} (`{actor.id}`)", inline=True)

                        embed.add_field(name="Target", value=f"{after.mention} (`{after.id}`)", inline=True)
                        embed.add_field(name="Target Account Age", value=f"Created: {discord.utils.format_dt(after.created_at, 'R')}\nJoined: {discord.utils.format_dt(after.joined_at, 'R') if after.joined_at else 'Unknown'}", inline=True)

                        embed.add_field(name="Role Granted", value=f"{role.mention} (`{role.id}`)", inline=True)
                        embed.add_field(name="Role Created", value=discord.utils.format_dt(role.created_at, 'F'), inline=True)
                        embed.add_field(name="Immediate Action", value="> Role Grant Reverted", inline=True)

                        # PUNISH
                        await punish_rogue_mod(after.guild, actor, f"Granted dangerous role **{role.name}** to {after.mention}", embed=embed, restore_data=restore_data)
                        break


async def setup(bot_instance: commands.Bot) -> None:
    bot_instance.tree.add_command(branding_cmd)
    bot_instance.tree.add_command(list_commands)
    bot_instance.tree.add_command(stats)
    bot_instance.tree.add_command(directory)
    bot_instance.tree.add_command(setup_cmd)
    bot_instance.tree.add_command(config_cmd)
    bot_instance.tree.add_command(publicexecution)
    bot_instance.tree.add_command(internals)
    bot_instance.tree.add_command(archive)
    bot_instance.tree.add_command(unarchive)
    bot_instance.tree.add_command(clone)
    bot_instance.tree.add_command(rules)
    bot_instance.tree.add_command(safety_panel)
    bot_instance.tree.add_command(access)
    bot_instance.tree.add_command(lockdown)
    bot_instance.tree.add_command(unlockdown)
    bot_instance.tree.add_command(status_cmd)
    bot_instance.add_listener(on_guild_role_update, "on_guild_role_update")
    bot_instance.add_listener(on_member_update, "on_member_update")
    bot_instance.tree.on_error = on_app_command_error
