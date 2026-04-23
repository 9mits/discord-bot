import base64
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import copy
import ipaddress
from discord.ext import tasks
import json
import os
import socket
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Union, Set, Tuple, Any
from collections import Counter, deque, defaultdict
import html
import re
import io
import logging
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from discord.http import Route
from modules.mbx_constants import (
    BRAND_NAME,
    COOLDOWN_SECONDS,
    DEFAULT_ARCHIVE_CAT_ID,
    DEFAULT_MAX_UNREAD_PINGS,
    DEFAULT_MESSAGE_CACHE_LIMIT,
    DEFAULT_MESSAGE_CACHE_RETENTION_DAYS,
    DEFAULT_RULES,
    EMBED_PALETTE,
    FEATURE_FLAG_LABELS,
    HOLO_PRIMARY,
    HOLO_SECONDARY,
    HOLO_TERTIARY,
    MODMAIL_PANEL_BANNER_URL,
    MODMAIL_PANEL_CATEGORIES,
    SCOPE_ANALYTICS,
    SCOPE_MODERATION,
    SCOPE_ROLES,
    SCOPE_SUPPORT,
    SCOPE_SYSTEM,
    THEME_ORANGE,
    TOKEN_ENV_VARS,
)
from modules.mbx_models import CaseNote
from modules.mbx_services import (
    DEFAULT_CANNED_REPLIES,
    DEFAULT_ESCALATION_MATRIX,
    DEFAULT_FEATURE_FLAGS,
    DEFAULT_NATIVE_AUTOMOD_SETTINGS,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_TICKET_PRIORITIES,
    export_case_payload,
    export_config_payload,
    get_feature_flag,
    get_escalation_steps,
    get_native_automod_settings,
    has_capability,
    import_config_payload,
    normalize_case_record,
    normalize_modmail_ticket,
    resolve_escalation_duration,
    resolve_native_automod_policy,
    run_schema_migrations,
    sanitize_evidence_links,
    sanitize_linked_cases,
    sanitize_tags,
    ticket_needs_sla_alert,
    validate_guild_configuration,
)
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
    get_primary_guild,
    has_dangerous_perm,
    has_permission_capability,
    is_staff,
    is_staff_member,
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

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("MGXBot")
# Suppress noisy rate limit warnings from discord.http
logging.getLogger("discord.http").setLevel(logging.ERROR)

# ----------------- PATHS -----------------
BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "database"
ROLES_FILE = DB_DIR / "roles.json"
CONFIG_FILE = DB_DIR / "config.json"
PUNISHMENTS_FILE = DB_DIR / "punishments.json"
MOD_STATS_FILE = DB_DIR / "mod_stats.json"
MESSAGE_CACHE_FILE = DB_DIR / "message_cache.json"
PINGS_FILE = DB_DIR / "pings.json"
LOCKDOWN_FILE = DB_DIR / "lockdown.json"
MODMAIL_FILE = DB_DIR / "modmail.json"
# -----------------------------------------


def read_json_file(path: Path, default: Any):
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", path.name, exc)
    return default


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def resolve_bot_token() -> str:
    bootstrap_config = read_json_file(CONFIG_FILE, {})
    env_var_order: List[str] = []

    configured_env_var = bootstrap_config.get("token_env_var")
    if isinstance(configured_env_var, str) and configured_env_var.strip():
        env_var_order.append(configured_env_var.strip())

    for env_var in TOKEN_ENV_VARS:
        if env_var not in env_var_order:
            env_var_order.append(env_var)

    for env_var in env_var_order:
        token = os.getenv(env_var)
        if token:
            return token.strip()

    raise RuntimeError(
        "Discord bot token is not configured. Set one of the supported environment variables "
        f"({', '.join(env_var_order)})."
    )


# Runtime bootstrap moved to modules.mbx_bot.



# ----------------- Utility functions -----------------





def get_valid_duration(minutes: int) -> timedelta:
    # Discord max timeout is 28 days (40320 minutes)
    return timedelta(minutes=min(minutes, 40320))





















def _setup_health_check(guild: discord.Guild, config: dict) -> str:
    """Return a compact health status line for the setup dashboard."""
    general_log_id = get_general_log_channel_id(config)

    def _role_ok(key: str) -> bool:
        rid = config.get(key)
        return bool(rid and guild.get_role(int(rid)))

    def _ch_ok(cid) -> bool:
        return bool(cid and guild.get_channel(int(cid)))

    checks = [
        ("Owner role", _role_ok("role_owner")),
        ("Mod role", _role_ok("role_mod")),
        ("General log", _ch_ok(general_log_id)),
        ("Modmail inbox", _ch_ok(config.get("modmail_inbox_channel"))),
        ("Appeals channel", _ch_ok(config.get("appeal_channel_id"))),
    ]

    ok = sum(1 for _, v in checks if v)
    total = len(checks)
    if ok == total:
        return "✅ All critical settings look good"
    lines = [f"⚠️ {ok}/{total} checks passed — fix the items below:"]
    for name, v in checks:
        if not v:
            lines.append(f"  • **{name}** — not set or deleted")
    return "\n".join(lines)






















































































































# ----------------- Embeds -----------------

# ----------------- Modals -----------------








































































def generate_transcript_html(messages, user):
    style = """
    body { background-color: #313338; color: #dbdee1; font-family: "gg sans", "Helvetica Neue", Helvetica, Arial, sans-serif; margin: 0; padding: 20px; }
    .chat-container { max-width: 100%; display: flex; flex-direction: column; }
    .message { display: flex; margin-top: 1rem; padding: 5px; }
    .message:hover { background-color: #2e3035; }
    .message.deleted { background-color: rgba(242, 63, 66, 0.1); border-left: 3px solid #f23f42; }
    .avatar { width: 40px; height: 40px; border-radius: 50%; margin-right: 16px; margin-top: 2px; }
    .content { display: flex; flex-direction: column; width: 100%; }
    .header { display: flex; align-items: center; margin-bottom: 2px; }
    .username { font-weight: 500; color: #f2f3f5; margin-right: 0.25rem; font-size: 1rem; }
    .timestamp { font-size: 0.75rem; color: #949ba4; margin-left: 0.25rem; }
    .msg-content { font-size: 1rem; line-height: 1.375rem; white-space: pre-wrap; color: #dbdee1; }
    .attachment-container { margin-top: 5px; }
    .attachment-img { max-width: 400px; max-height: 300px; border-radius: 8px; cursor: pointer; }
    .deleted-tag { font-size: 0.625rem; color: #f23f42; margin-left: 4px; border: 1px solid #f23f42; border-radius: 3px; padding: 0 4px; vertical-align: middle; }
    .edited-tag { font-size: 0.625rem; color: #949ba4; margin-left: 4px; vertical-align: middle; }
    .channel-ref { font-size: 0.75rem; color: #949ba4; font-weight: bold; margin-bottom: 2px; }
    a { color: #00a8fc; text-decoration: none; }
    a:hover { text-decoration: underline; }
    """
    
    safe_display_name = html.escape(user.display_name)
    html_parts = [
        f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>History - {safe_display_name}</title><style>{style}</style></head><body>',
        f'<div class="chat-container"><h2 style="color:white; border-bottom: 1px solid #4e5058; padding-bottom: 10px;">Chat History: {safe_display_name} ({user.id})</h2>'
    ]

    # messages is Newest -> Oldest. Reverse to show Oldest -> Newest in HTML.
    for m in reversed(messages):
        ts = m["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        content = html.escape(m.get("content", ""))
        if not content: content = "<em>[No Text Content]</em>"
        author_name = html.escape(m.get("author_name", user.display_name))
        author_avatar_url = html.escape(m.get("author_avatar_url", user.display_avatar.url if getattr(user, "display_avatar", None) else ""))

        # Status tags
        tags = ""
        if m.get("deleted"): tags += '<span class="deleted-tag">DELETED</span>'
        if m.get("edited"): tags += '<span class="edited-tag">(edited)</span>'

        # Attachments
        att_html = ""
        if m.get("attachments"):
            att_html += '<div class="attachment-container">'
            for a in m["attachments"]:
                safe_url = html.escape(a["url"])
                safe_filename = html.escape(a["filename"])
                ext = a["filename"].split('.')[-1].lower()
                if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                    att_html += f'<a href="{safe_url}" target="_blank"><img src="{safe_url}" class="attachment-img" alt="{safe_filename}"></a><br>'
                else:
                    att_html += f'<a href="{safe_url}" target="_blank">Attachment: {safe_filename}</a><br>'
            att_html += '</div>'

        # Stickers
        if m.get("stickers"):
            att_html += f'<div style="color:#949ba4; font-size:0.8rem;">Stickers: {html.escape(", ".join(m["stickers"]))}</div>'

        div_class = "message deleted" if m.get("deleted") else "message"
        row = f"""
        <div class="{div_class}">
            <img class="avatar" src="{author_avatar_url}" alt="Avatar">
            <div class="content">
                <div class="channel-ref">#{html.escape(str(m['channel_id']))}</div>
                <div class="header">
                    <span class="username">{author_name}</span>
                    <span class="timestamp">{ts}</span>
                    {tags}
                </div>
                <div class="msg-content">{content}</div>
                {att_html}
            </div>
        </div>
        """
        html_parts.append(row)
        
    html_parts.append('</div></body></html>')
    return "\n".join(html_parts)

















# ----------------- Modmail System -----------------











































# ----------------- Commands -----------------
# --- Command Groups ---

@tree.command(name="role", description="Manage your personal custom role")
async def role_cmd(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.HTTPException as e:
        if e.code != 40060:
            raise e
    
    # Check for Booster or Whitelist
    is_booster = interaction.user.premium_since is not None
    limit = get_custom_role_limit(interaction.user)
    
    if not is_booster and limit <= 0:
        await interaction.followup.send("You must be a **Server Booster** to use this perk.", ephemeral=True)
        return

    rec = bot.data_manager.roles.get(str(interaction.user.id))
    
    # Check if role exists on Discord
    role = None
    if rec:
        role_id = rec.get("role_id")
        role = interaction.guild.get_role(role_id)
        if not role:
            try:
                role = await interaction.guild.fetch_role(role_id)
            except discord.NotFound:
                # Role was deleted manually, clean up DB
                bot.data_manager.roles.pop(str(interaction.user.id), None)
                await bot.data_manager.save_roles()
                rec = None
            except Exception: pass
    
    if role:
        # User has a valid role -> Show Manage View
        embed = build_role_info_embed(interaction.user, rec, role, include_tips=True)
        view = EditView(interaction.user, role)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    else:
        # User has no role (or it's deleted) -> Show Create Option
        embed = build_role_landing_embed(interaction.user, is_booster=is_booster, limit=max(1, limit))
        view = discord.ui.View()
        btn = discord.ui.Button(label="Create Role", style=discord.ButtonStyle.success)
        
        async def create_callback(inter: discord.Interaction):
            await inter.response.send_modal(CreateRoleModal(inter.user))
        
        btn.callback = create_callback
        view.add_item(btn)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# --- Setup / Config System ---































































































# --- Permission Checks live in modules.mbx_permissions (re-exported above) ---

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






@tree.command(name="listcommands", description="Browse all available commands by category | admin/owner")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
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
        if not is_staff(interaction):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="punish", description="Sanction a user with a warning, timeout, or ban | mod")
    @app_commands.default_permissions(moderate_members=True)
    async def punish(self, interaction: discord.Interaction, user: discord.User):
        await show_punish_menu(interaction, user)

    @app_commands.command(name="publicpunish", description="Punish a user and announce it publicly in this channel | mod")
    @app_commands.default_permissions(moderate_members=True)
    async def publicpunish(self, interaction: discord.Interaction, user: discord.User):
        await show_punish_menu(interaction, user, public=True)

    @app_commands.command(name="history", description="Retrieve the complete disciplinary history of a user | mod")
    @app_commands.default_permissions(moderate_members=True)
    async def history(self, interaction: discord.Interaction, user: discord.Member):
        await show_history_menu(interaction, user)

    @app_commands.command(name="active", description="Display a list of all currently active punishments | mod")
    @app_commands.default_permissions(moderate_members=True)
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

    @app_commands.command(name="undopunish", description="Open the punishment undo control panel | mod")
    @app_commands.describe(reason="Optional reason to prefill in the undo panel")
    @app_commands.default_permissions(moderate_members=True)
    async def undopunish(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        await show_history_menu(interaction, user, mode="undo", initial_undo_reason=reason)

    @app_commands.command(name="purge", description="Bulk delete messages (Channel or User) | mod")
    @app_commands.describe(amount="Messages to check/delete (max 999)", user="Optional: Target specific user", keyword="Optional: Filter by keyword")
    @app_commands.default_permissions(manage_messages=True)
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

    @app_commands.command(name="lock", description="Restrict message sending permissions in this channel | mod")
    @app_commands.default_permissions(manage_channels=True)
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

    @app_commands.command(name="unlock", description="Restore message sending permissions in this channel | mod")
    @app_commands.default_permissions(manage_channels=True)
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

    @app_commands.command(name="case", description="Open the case panel for a user or case ID | mod")
    @app_commands.describe(case_id="Open a specific case by ID", user="Open the most recent case for a user")
    async def case(self, interaction: discord.Interaction, case_id: Optional[app_commands.Range[int, 1, 999999]] = None, user: Optional[discord.Member] = None):
        await show_case_panel(interaction, case_id=case_id, user=user)


# --- Admin Commands (Flattened) ---

@tree.command(name="stats", description="Display comprehensive server-wide moderation analytics | admin")
@app_commands.default_permissions(manage_guild=True)
@app_commands.check(check_admin)
async def stats(interaction: discord.Interaction, target: Optional[discord.Member] = None):
    if target:
        uid = str(target.id)
        cases = get_mod_cases(uid)

        # Check if user is currently staff or has history
        target_is_staff = False
        if target.guild_permissions.administrator:
            target_is_staff = True
        else:
            mod_role_ids = bot.data_manager.config.get("mod_roles", [])
            if mod_role_ids:
                if any(r.id in mod_role_ids for r in target.roles):
                    target_is_staff = True
            elif target.guild_permissions.moderate_members:
                target_is_staff = True

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

@tree.command(name="directory", description="Display staff team directory | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def directory(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    admins = []
    mods = []
    mod_role_ids = bot.data_manager.config.get("mod_roles", [])
    
    for member in interaction.guild.members:
        if member.bot: continue
        if member.guild_permissions.administrator:
            admins.append(member)
        elif any(r.id in mod_role_ids for r in member.roles):
            mods.append(member)
        elif not mod_role_ids and member.guild_permissions.moderate_members:
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

@tree.command(name="setup", description="Open the configuration dashboard | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def setup(interaction: discord.Interaction):
    embed = build_setup_dashboard_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, view=SetupDashboardView(), ephemeral=True)

@tree.command(name="config", description="Open the bot settings panel | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def config_cmd(interaction: discord.Interaction):
    if not get_feature_flag(bot.data_manager.config, "config_panel", True):
        await respond_with_error(interaction, "The bot settings panel is currently turned off in the feature settings.", scope=SCOPE_SYSTEM)
        return
    embed = build_config_dashboard_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, view=ConfigDashboardView(), ephemeral=True)

@tree.command(name="publicexecution", description="Start a public vote to ban a user | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def publicexecution(interaction: discord.Interaction, user: discord.User, reaction_count: int):
    await show_punish_menu(interaction, user, public=True, reaction_count=reaction_count)

@tree.command(name="internals", description="View system constants and definitions | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
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

@tree.command(name="archive", description="Move this channel to the archive category | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
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

@tree.command(name="unarchive", description="Restore this channel from the archives | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
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

@tree.command(name="clone", description="Archive current channel and create a fresh clone | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
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

@tree.command(name="rules", description="Configure automated punishment escalation rules | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def rules(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_rules_dashboard_embed(interaction.guild), view=RulesDashboardView(), ephemeral=True)

@tree.command(name="roleadmin", description="Manage custom role permissions | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
@app_commands.choices(action=[
    app_commands.Choice(name="Whitelist", value="whitelist"),
    app_commands.Choice(name="Blacklist", value="blacklist"),
    app_commands.Choice(name="Reset", value="reset"),
    app_commands.Choice(name="List Permissions", value="list_permission"),
    app_commands.Choice(name="List All Roles", value="list_all"),
    app_commands.Choice(name="Manage User Role", value="manage_user")
])
@app_commands.describe(action="Action to perform", target="User or Role (Optional for List)", limit="Max roles (Whitelist only)")
async def role_manage(interaction: discord.Interaction, action: str, target: Optional[Union[discord.Member, discord.Role]] = None, limit: int = 1):
    await interaction.response.defer(ephemeral=True)
    conf = bot.data_manager.config
    
    if action == "list_permission":
        embed = make_embed(
            "Custom Role Permissions",
            "> Current whitelist and blacklist rules for personal role access.",
            kind="info",
            scope=SCOPE_ROLES,
            guild=interaction.guild,
        )
        
        # Whitelisted Users
        wl_users = conf.get("cr_whitelist_users", {})
        if wl_users:
            lines = [f"<@{uid}>: {lim}" for uid, lim in wl_users.items()]
            val = "\n".join(lines)
            if len(val) > 1024: val = val[:1021] + "..."
            embed.add_field(name="Whitelisted Users", value=val, inline=False)
        else:
            embed.add_field(name="Whitelisted Users", value="None", inline=False)

        # Blacklisted Users
        bl_users = conf.get("cr_blacklist_users", [])
        if bl_users:
            lines = [f"<@{uid}>" for uid in bl_users]
            val = ", ".join(lines)
            if len(val) > 1024: val = val[:1021] + "..."
            embed.add_field(name="Blacklisted Users", value=val, inline=False)
        else:
            embed.add_field(name="Blacklisted Users", value="None", inline=False)

        # Whitelisted Roles
        wl_roles = conf.get("cr_whitelist_roles", {})
        if wl_roles:
            lines = [f"<@&{rid}>: {lim}" for rid, lim in wl_roles.items()]
            val = "\n".join(lines)
            if len(val) > 1024: val = val[:1021] + "..."
            embed.add_field(name="Whitelisted Roles", value=val, inline=False)
        else:
            embed.add_field(name="Whitelisted Roles", value="None", inline=False)

        # Blacklisted Roles
        bl_roles = conf.get("cr_blacklist_roles", [])
        if bl_roles:
            lines = [f"<@&{rid}>" for rid in bl_roles]
            val = ", ".join(lines)
            if len(val) > 1024: val = val[:1021] + "..."
            embed.add_field(name="Blacklisted Roles", value=val, inline=False)
        else:
            embed.add_field(name="Blacklisted Roles", value="None", inline=False)
            
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if action == "list_all":
        # List all custom roles
        embed = make_embed(
            "Server Custom Roles Registry",
            "> Inventory of tracked custom roles and their recorded owners.",
            kind="warning",
            scope=SCOPE_ROLES,
            guild=interaction.guild,
        )
        total_roles = add_custom_role_registry_fields(embed, interaction.guild, field_name="Tracked Roles")
        embed.add_field(name="Total Roles", value=str(total_roles), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if action == "manage_user":
        if not isinstance(target, discord.Member):
            await interaction.followup.send("Target must be a user.", ephemeral=True)
            return
        
        rec = bot.data_manager.roles.get(str(target.id))
        role = None
        if rec:
            role = interaction.guild.get_role(rec.get("role_id"))
        
        if role:
            embed = build_role_info_embed(target, rec, role, include_tips=True)
            _set_footer_branding(embed, f"Admin Control Panel for {target.display_name}", interaction.guild)
            view = EditView(target, role)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(f"{target.mention} does not have a custom role.", ephemeral=True)
        return

    if target is None:
        await interaction.followup.send("Target is required for this action.", ephemeral=True)
        return

    tid = str(target.id)
    msg = ""

    if action == "whitelist":
        if isinstance(target, discord.Member):
            if "cr_whitelist_users" not in conf: conf["cr_whitelist_users"] = {}
            conf["cr_whitelist_users"][tid] = limit
            if "cr_blacklist_users" in conf and tid in conf["cr_blacklist_users"]:
                conf["cr_blacklist_users"].remove(tid)
            msg = f"Whitelisted user {target.mention} with limit **{limit}**."
        else:
            if "cr_whitelist_roles" not in conf: conf["cr_whitelist_roles"] = {}
            conf["cr_whitelist_roles"][tid] = limit
            if "cr_blacklist_roles" in conf and tid in conf["cr_blacklist_roles"]:
                conf["cr_blacklist_roles"].remove(tid)
            msg = f"Whitelisted role {target.mention} with limit **{limit}**."
    
    elif action == "blacklist":
        if isinstance(target, discord.Member):
            if "cr_blacklist_users" not in conf: conf["cr_blacklist_users"] = []
            if tid not in conf["cr_blacklist_users"]:
                conf["cr_blacklist_users"].append(tid)
            if "cr_whitelist_users" in conf and tid in conf["cr_whitelist_users"]:
                del conf["cr_whitelist_users"][tid]
            msg = f"Blacklisted user {target.mention}."
        else:
            if "cr_blacklist_roles" not in conf: conf["cr_blacklist_roles"] = []
            if tid not in conf["cr_blacklist_roles"]:
                conf["cr_blacklist_roles"].append(tid)
            if "cr_whitelist_roles" in conf and tid in conf["cr_whitelist_roles"]:
                del conf["cr_whitelist_roles"][tid]
            msg = f"Blacklisted role {target.mention}."

    elif action == "reset":
        changes = []
        if isinstance(target, discord.Member):
            if "cr_whitelist_users" in conf and tid in conf["cr_whitelist_users"]:
                del conf["cr_whitelist_users"][tid]
                changes.append("Removed from User Whitelist")
            if "cr_blacklist_users" in conf and tid in conf["cr_blacklist_users"]:
                conf["cr_blacklist_users"].remove(tid)
                changes.append("Removed from User Blacklist")
        else:
            if "cr_whitelist_roles" in conf and tid in conf["cr_whitelist_roles"]:
                del conf["cr_whitelist_roles"][tid]
                changes.append("Removed from Role Whitelist")
            if "cr_blacklist_roles" in conf and tid in conf["cr_blacklist_roles"]:
                conf["cr_blacklist_roles"].remove(tid)
                changes.append("Removed from Role Blacklist")
        
        if changes:
            msg = f"Reset {target.mention}: {', '.join(changes)}"
        else:
            msg = f"{target.mention} was not in any list."

    await bot.data_manager.save_config()
    await interaction.followup.send(msg, ephemeral=True)

@tree.command(name="rolesettings", description="Open the custom role settings panel | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def role_settings(interaction: discord.Interaction):
    embed = build_role_settings_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, view=RoleSettingsView(), ephemeral=True)

@tree.command(name="automod", description="Open the AutoMod control panel | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def automod_cmd(interaction: discord.Interaction):
    if not get_feature_flag(bot.data_manager.config, "automod_panel", True):
        await respond_with_error(interaction, "The AutoMod panel is currently turned off in feature settings.", scope=SCOPE_MODERATION)
        return
    await interaction.response.send_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView(), ephemeral=True)















@tree.command(name="branding", description="Customize the bot's look for this server | admin")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_admin)
async def branding_cmd(interaction: discord.Interaction):
    embed = _build_branding_panel_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, view=BrandingPanelView(), ephemeral=True)


@tree.command(name="safetypanel", description="Manage anti-nuke immunity settings | owner")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_owner)
async def safety_panel(interaction: discord.Interaction, key: str):
    if key != "saori":
        await interaction.response.send_message("**Access Denied:** Invalid Security Key.", ephemeral=True)
        return
    
    embed = make_embed(
        "Anti-Nuke Safety Panel",
        "> Manage users who are immune to automated anti-nuke enforcement.",
        kind="warning",
        scope=SCOPE_SYSTEM,
        guild=interaction.guild,
    )
    await interaction.response.send_message(embed=embed, view=SafetyView(), ephemeral=True)

@tree.command(name="access", description="Manage role-based access to moderation tools | owner")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_owner)
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

@tree.command(name="lockdown", description="Emergency: hide all channels from @everyone | owner")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_owner)
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

@tree.command(name="unlockdown", description="Restore channel visibility after lockdown | owner")
@app_commands.default_permissions(administrator=True)
@app_commands.check(check_owner)
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

@tree.command(name="help", description="Guide for creating and managing custom roles")
async def help_cmd(interaction: discord.Interaction):
    embed = make_embed(
        "Custom Role Guide",
        "> Create, edit, and manage your booster custom role from one reusable control panel.",
        kind="warning",
        scope=SCOPE_ROLES,
        guild=interaction.guild,
    )
    embed.add_field(name="Requirement", value="You must be a server booster to unlock this perk.", inline=False)
    embed.add_field(name="1. Open the Studio", value="Run `/role` to open your personal role dashboard.", inline=False)
    embed.add_field(name="2. Create or Edit", value="Set a name, primary color, icon, and advanced style options.", inline=False)
    embed.add_field(name="3. Reopen Anytime", value="Use `/role` again whenever you want to update or remove your role.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

tree.add_command(ModGroup())

# --- Context Menus (Apps) ---
@tree.context_menu(name="Punish User")
@app_commands.default_permissions(moderate_members=True)
async def punish_context(interaction: discord.Interaction, user: discord.User):
    if not is_staff(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    await show_punish_menu(interaction, user)

@tree.context_menu(name="Mod History")
@app_commands.default_permissions(moderate_members=True)
async def history_context(interaction: discord.Interaction, user: discord.Member):
    if not is_staff(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    await show_history_menu(interaction, user)

# ----------------- Bot Events -----------------
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

@bot.event
async def on_raw_reaction_add(payload):
    return

@bot.command()
async def sync(ctx):
    """Admin override: force re-sync slash commands. Normally not needed — bot auto-syncs on startup."""
    if not ctx.guild:
        await ctx.send("This command can only be used in a server.")
        return
    if bot.data_manager:
        bot.data_manager._current_guild_id = ctx.guild.id
        await bot.data_manager.ensure_guild_loaded(ctx.guild.id)

    # Permission check
    owner_role = bot.data_manager.config.get("role_owner") if bot.data_manager else None
    is_owner = ctx.author.id == ctx.guild.owner_id
    has_role = owner_role and any(r.id == owner_role for r in ctx.author.roles)
    is_admin = ctx.author.guild_permissions.administrator

    if not (is_owner or has_role or is_admin):
        await ctx.send("Access Denied: You need the Owner role, Server Owner status, or Administrator permission.")
        return

    msg = await ctx.send("Syncing global slash commands...")
    try:
        cmds = await bot.tree.sync()
        await msg.edit(content=f"Synced **{len(cmds)}** global slash command(s). All servers will see updates within ~1 hour.")
    except Exception as exc:
        await msg.edit(content=f"Sync failed: {exc}")
    logger.info(f"Synced commands: {[c.name for c in cmds]}")

@tree.command(name="status", description="View bot latency and uptime | mod")
@app_commands.default_permissions(moderate_members=True)
async def status_cmd(interaction: discord.Interaction):
    if not is_staff(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    embed = build_status_embed(interaction.guild)
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


@bot.event
async def on_message(message: discord.Message):
    if message.guild and message.type is discord.MessageType.auto_moderation_action:
        await handle_native_automod_alert_message(message)
        return
    if message.author.bot: return

    if bot.data_manager and message.guild:
        bot.data_manager._current_guild_id = message.guild.id
        await bot.data_manager.ensure_guild_loaded(message.guild.id)
    elif not message.guild:
        return

    # Anti-Spam: Mentions
    # Check immunity
    is_immune = str(message.author.id) in bot.data_manager.config.get("immunity_list", [])

    # Check for mentions
    has_everyone = message.mention_everyone
    
    # Specific Role ID
    target_role_id = bot.data_manager.config.get("role_mention_spam_target")
    has_role = any(r.id == target_role_id for r in message.role_mentions)
    
    if (has_everyone or has_role) and not is_immune:
        # Only apply to staff (Admins/Mods) as requested
        mod_roles_ids = bot.data_manager.config.get("mod_roles", [])
        is_staff_member = False
        if any(r.id in mod_roles_ids for r in message.author.roles):
            is_staff_member = True
        elif message.author.guild_permissions.administrator:
            is_staff_member = True
            
        if is_staff_member:
            now = time.time()
            q = abuse_system.mention_spam_tracker[message.author.id]
            q.append(now)
            
            # Clean old timestamps (> 60s)
            while q and now - q[0] > 60:
                q.popleft()
                
            if len(q) > 2:
                # Trigger
                q.clear() # Reset tracker
                
                # Build Embed
                embed = make_embed(
                    "Security Alert: Mention Spam Detected",
                    "> The anti-spam guard detected repeated protected mentions and triggered an automatic response.",
                    kind="danger",
                    scope=SCOPE_SYSTEM,
                    guild=message.guild,
                    thumbnail=message.author.display_avatar.url,
                )
                embed.add_field(name="Actor", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
                embed.add_field(name="Violation", value="Mass mention spam (@everyone/@here/member role)", inline=True)
                
                # Prepare restore data for resolve button (restores roles only)
                restore_data = {
                    "type": "spam_pardon",
                    "actor_id": message.author.id
                }
                
                # Punish & Delete
                await punish_rogue_mod(message.guild, message.author, "Mention Spam (Mass Pings)", embed=embed, restore_data=restore_data)
                try: await message.delete()
                except Exception: pass

    # Modmail Logic
    # 1. User -> Bot (DM)
    if isinstance(message.channel, discord.DMChannel):
        ticket = bot.data_manager.modmail.get(str(message.author.id))
        if ticket and ticket.get("status") == "open":
            # Resolve thread without assuming a primary guild — derive guild from thread itself
            thread = await resolve_modmail_thread(None, ticket)

            if thread:
                guild = thread.guild
                content = message.content if message.content else None
                embed = make_embed(
                    "User Reply",
                    truncate_text(content, 4096) or None,
                    kind="success",
                    scope=SCOPE_SUPPORT,
                    guild=guild,
                    author_name=message.author.display_name,
                    author_icon=message.author.display_avatar.url,
                )

                files, attachment_notice = await prepare_modmail_relay_attachments(message.attachments)

                try:
                    relay_kwargs = {"embed": embed}
                    if files:
                        relay_kwargs["files"] = files
                    await thread.send(**relay_kwargs)
                    ticket["last_user_message_at"] = now_iso()
                    ticket["last_sla_alert_at"] = None
                    await bot.data_manager.save_modmail()
                    await refresh_modmail_ticket_log(guild, str(message.author.id))
                    if attachment_notice:
                        await message.channel.send(attachment_notice)
                except Exception as e:
                    await message.channel.send(f"Error relaying message: {e}")
            else:
                await message.channel.send("Your previous ticket thread could not be found, so please open a new ticket below.")
                await maybe_send_dm_modmail_panel(
                    message.author,
                    force=True,
                    intro="> Your old ticket could not be found. Please open a new ticket below so staff can help you again.",
                )
            return

        await maybe_send_dm_modmail_panel(
            message.author,
            guild=guild,
            intro="> You can open a ticket from this DM panel. Once it is open, just keep replying here and staff will receive it.",
        )
        return

    # 2. Staff -> Bot (Thread)
    if isinstance(message.channel, discord.Thread):
        # Check if this thread is a modmail thread
        target_uid = bot.data_manager.get_modmail_user_id(message.channel.id)
        
        if target_uid:
            # It is a modmail thread
            ticket = bot.data_manager.modmail.get(target_uid)
            if ticket and ticket.get("status") == "open":
                user = await resolve_modmail_user(target_uid)
                if user is None:
                    await message.channel.send("Failed to send: The ticket user could not be resolved.")
                    return
                try:
                    content = message.content if message.content else None
                    embed = make_embed(
                        "Staff Reply",
                        truncate_text(content, 4096) or None,
                        kind="info",
                        scope=SCOPE_SUPPORT,
                        guild=message.guild,
                        author_name=f"{message.guild.name} Staff Team",
                        author_icon=message.guild.icon.url if message.guild.icon else None,
                    )
                    
                    files, attachment_notice = await prepare_modmail_relay_attachments(message.attachments)
                        
                    relay_kwargs = {"embed": embed}
                    if files:
                        relay_kwargs["files"] = files
                    await user.send(**relay_kwargs)
                    ticket["last_staff_message_at"] = now_iso()
                    await bot.data_manager.save_modmail()
                    await refresh_modmail_ticket_log(message.guild, target_uid)
                    if attachment_notice:
                        await message.channel.send(attachment_notice)
                except discord.Forbidden:
                    await message.channel.send("Failed to send: User has blocked the bot or DMs are disabled.")
                except Exception as e:
                    await message.channel.send(f"Failed to send message: {e}")
            return

    await bot.process_commands(message)

async def on_ready():
    pass  # Handled by MGXBot.on_ready in mbx_bot.py
