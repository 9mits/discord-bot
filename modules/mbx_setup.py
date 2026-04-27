"""Setup/configuration dashboard embed builders."""
from __future__ import annotations

import asyncio
import copy
import html
import io
import json
import logging
import re
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.http import Route

from modules.mbx_automod import *
from modules.mbx_cases import *
from modules.mbx_constants import *
from modules.mbx_context import abuse_system, bot, tree
from modules.mbx_embeds import *
from modules.mbx_embeds import (
    _build_footer_text,
    _build_footer_text_with_detail,
    _format_branding_panel_value,
    _get_branding_config,
    _get_footer_icon_url,
    _set_footer_branding,
)
from modules.mbx_formatters import *
from modules.mbx_fleet import build_status_numbers
from modules.mbx_images import *
from modules.mbx_images import (
    _format_image_size_limit,
    _is_public_image_ip,
    _make_image_data_uri,
    _resolve_image_host_addresses,
)
from modules.mbx_logging import *
from modules.mbx_logging import _send_log_to_channels
from modules.mbx_models import *
from modules.mbx_permissions import *
from modules.mbx_punish import build_punish_embed, execute_punishment, get_valid_duration
from modules.mbx_roles import *
from modules.mbx_services import *
from modules.mbx_utils import *

logger = logging.getLogger("MGXBot")


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

    ok = sum(1 for _, valid in checks if valid)
    total = len(checks)
    if ok == total:
        return "✅ All critical settings look good"
    lines = [f"⚠️ {ok}/{total} checks passed — fix the items below:"]
    for name, valid in checks:
        if not valid:
            lines.append(f"  • **{name}** — not set or deleted")
    return "\n".join(lines)


def get_feature_flag_name(key: str) -> str:
    return FEATURE_FLAG_LABELS.get(key, key.replace("_", " ").title())

def build_mod_help_embed(guild: discord.Guild) -> discord.Embed:
    embed = make_embed(
        "Moderation Command Guide",
        "> Core moderation workflows, context tools, and channel controls.",
        kind="info",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(
        name="Case Management",
        value="\n".join([
            "`/mod case` — Open a case panel for notes, status, evidence, and assignment.",
            "`/mod history` — Browse a user’s disciplinary record case-by-case.",
            "`/mod active` — View all active bans and timeouts.",
            "`/mod undopunish` — Reverse a punishment with a reason and case selector.",
        ]),
        inline=False,
    )
    embed.add_field(
        name="Actions",
        value="\n".join([
            "`/mod punish` — Open the sanction console with smart escalation.",
            "`/mod publicpunish` — Punish and post the result publicly in the channel.",
            "`/mod purge` — Bulk-delete messages with user or keyword filtering.",
        ]),
        inline=False,
    )
    embed.add_field(
        name="Channel Controls",
        value="\n".join([
            "`/mod lock` — Restrict messaging in the current channel.",
            "`/mod unlock` — Restore messaging in the current channel.",
        ]),
        inline=False,
    )
    return embed

def build_setup_dashboard_embed(guild: discord.Guild) -> discord.Embed:
    config = bot.data_manager.config
    general_log_channel_id = get_general_log_channel_id(config)
    configured_punishment_log_channel_id = config.get("punishment_log_channel_id")

    health = _setup_health_check(guild, config)
    all_ok = health.startswith("✅")
    embed = make_embed(
        "Server Configuration",
        f"> Use the panels below to configure roles, channels, and guild-wide settings.\n\n{health}",
        kind="success" if all_ok else "warning",
        scope=SCOPE_SYSTEM,
        guild=guild,
    )

    # --- Roles ---
    embed.add_field(name="Owner", value=fmt_role(guild, config.get("role_owner")), inline=True)
    embed.add_field(name="Admin", value=fmt_role(guild, config.get("role_admin")), inline=True)
    embed.add_field(name="Moderator", value=fmt_role(guild, config.get("role_mod")), inline=True)
    embed.add_field(name="Anchor Role", value=fmt_role(guild, config.get("role_anchor")), inline=True)
    embed.add_field(name="Community Manager", value=fmt_role(guild, config.get("role_community_manager")), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer

    # --- Log Channels ---
    _automod_log = config.get("automod_log_channel_id")
    _automod_report = config.get("automod_report_channel_id")
    embed.add_field(
        name="Log Channels",
        value=join_lines([
            "General: " + fmt_channel(guild, general_log_channel_id),
            "Punishments: " + (fmt_channel(guild, configured_punishment_log_channel_id) if configured_punishment_log_channel_id else "Falls back to general"),
            "AutoMod: " + fmt_channel(guild, _automod_log),
            "Reports: " + fmt_channel(guild, _automod_report),
        ]),
        inline=True,
    )

    # --- Support Channels ---
    _modmail_inbox = config.get("modmail_inbox_channel")
    _modmail_panel = config.get("modmail_panel_channel")
    _appeal = config.get("appeal_channel_id")
    embed.add_field(
        name="Support Channels",
        value=join_lines([
            "Modmail Inbox: " + fmt_channel(guild, _modmail_inbox),
            "Modmail Panel: " + fmt_channel(guild, _modmail_panel),
            "Appeals: " + fmt_channel(guild, _appeal),
        ]),
        inline=True,
    )

    return embed

def build_modmail_settings_embed(guild: discord.Guild) -> discord.Embed:
    config = bot.data_manager.config
    discussion_threads = config.get("modmail_discussion_threads", True)
    dm_prompt = get_feature_flag(config, "dm_modmail_prompt", True)
    sla = config.get("modmail_sla_minutes", 60)
    cooldown = config.get("dm_modmail_panel_cooldown_minutes", 30)
    open_count = sum(1 for t in bot.data_manager.modmail.values() if t.get("status") == "open")
    embed = make_embed(
        "Modmail Settings",
        "> Configure how the ticket inbox behaves for staff and users.",
        kind="support",
        scope=SCOPE_SUPPORT,
        guild=guild,
    )
    embed.add_field(name="Discussion Threads", value="On" if discussion_threads else "Off", inline=True)
    embed.add_field(name="DM Prompt", value="On" if dm_prompt else "Off", inline=True)
    embed.add_field(name="SLA Reminder", value=f"{sla} min", inline=True)
    embed.add_field(name="DM Panel Cooldown", value=f"{cooldown} min", inline=True)
    embed.add_field(name="Open Tickets", value=str(open_count), inline=True)
    return embed

def build_config_dashboard_embed(guild: discord.Guild) -> discord.Embed:
    config = bot.data_manager.config
    flags = config.get("feature_flags", {})
    enabled_count = sum(1 for value in flags.values() if value)
    native_settings = get_native_automod_settings(config)
    embed = make_embed(
        "Bot Settings",
        "> Manage backups, feature toggles, punishment scaling, and quick replies.",
        kind="info",
        scope=SCOPE_SYSTEM,
        guild=guild,
    )
    embed.add_field(name="Features Active", value=f"{enabled_count} / {len(flags)}", inline=True)
    embed.add_field(name="Schema Version", value=f"v{config.get('schema_version', DEFAULT_SCHEMA_VERSION)}", inline=True)
    embed.add_field(name="SLA Reminder", value=f"{config.get('modmail_sla_minutes', 60)} min", inline=True)
    embed.add_field(name="Native AutoMod", value="On" if native_settings.get("enabled", True) else "Off", inline=True)
    embed.add_field(name="Escalation Steps", value=str(len(get_escalation_steps(config))), inline=True)
    canned = config.get("modmail_canned_replies", {})
    embed.add_field(name="Saved Replies", value=str(len(canned)), inline=True)
    return embed

def build_rules_dashboard_embed(guild: discord.Guild) -> discord.Embed:
    rules = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
    steps = get_escalation_steps(bot.data_manager.config)
    embed = make_embed(
        "Punishment Rules",
        "> Preset rule baselines used by the punishment console. Base = first offence, Escalated = repeat offence.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(name="Total Rules", value=str(len(rules)), inline=True)
    embed.add_field(name="Escalation Tiers", value=str(len(steps)), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    for rule_name, data in list(rules.items())[:6]:
        embed.add_field(
            name=rule_name,
            value=f"Base: {format_duration(data['base'])}\nEsc: {format_duration(data['escalated'])}",
            inline=True,
        )
    return embed

def build_feature_flags_embed(guild: discord.Guild) -> discord.Embed:
    flags = bot.data_manager.config.get("feature_flags", {})
    enabled_count = sum(1 for v in flags.values() if v)
    embed = make_embed(
        "Feature Toggles",
        f"> **{enabled_count}/{len(flags)}** systems are currently active. Use the toggles below to enable or disable features.",
        kind="info",
        scope=SCOPE_SYSTEM,
        guild=guild,
    )
    for key, value in sorted(flags.items()):
        status = "On" if value else "Off"
        embed.add_field(name=get_feature_flag_name(key), value=status, inline=True)
    return embed

def build_escalation_matrix_embed(guild: discord.Guild) -> discord.Embed:
    embed = make_embed(
        "Punishment Scaling",
        "> Controls how punishments scale when a user reoffends. Each tier activates at a point threshold.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    for step in get_escalation_steps(bot.data_manager.config):
        mode_label = "Base duration" if step.mode == "base" else ("Scaled duration" if step.mode == "escalated" else "Ban")
        ban_note = " • Auto Ban" if step.force_ban else ""
        embed.add_field(
            name=step.label or f"{step.mode.title()} Tier",
            value=f"From **{step.minimum_points}** pts\n{mode_label} × {step.multiplier}{ban_note}",
            inline=True,
        )
    return embed

def build_canned_replies_embed(guild: discord.Guild) -> discord.Embed:
    replies = bot.data_manager.config.get("modmail_canned_replies", {})
    embed = make_embed(
        "Saved Replies",
        "> Quick reply templates staff can send in modmail.",
        kind="support",
        scope=SCOPE_SUPPORT,
        guild=guild,
    )
    for key, value in list(replies.items())[:10]:
        embed.add_field(name=key, value=truncate_text(value, 200), inline=False)
    if not replies:
        embed.add_field(name="Templates", value="No saved replies have been added yet.", inline=False)
    return embed

def build_setup_validation_embed(guild: discord.Guild, findings: List[Any]) -> discord.Embed:
    summary_counter = Counter(finding.level for finding in findings)
    kind = "success" if summary_counter.get("error", 0) == 0 and summary_counter.get("warning", 0) == 0 else ("warning" if summary_counter.get("error", 0) == 0 else "danger")
    embed = make_embed(
        "Setup Check",
        "> This checks whether your saved channels, roles, and bot permissions still look correct.",
        kind=kind,
        scope=SCOPE_SYSTEM,
        guild=guild,
    )
    embed.add_field(name="Errors", value=str(summary_counter.get("error", 0)), inline=True)
    embed.add_field(name="Warnings", value=str(summary_counter.get("warning", 0)), inline=True)
    embed.add_field(name="Success", value=str(summary_counter.get("success", 0)), inline=True)
    grouped = defaultdict(list)
    for finding in findings:
        grouped[finding.section].append(f"[{finding.level.upper()}] {finding.message}")
    for section, messages in grouped.items():
        embed.add_field(name=section, value=truncate_text("\n".join(messages), 1024), inline=False)
    return embed

async def build_status_embed(guild: discord.Guild) -> discord.Embed:
    latency = round(bot.latency * 1000)
    uptime_seconds = int(time.time() - bot.start_time)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

    if latency < 100:
        latency_label = f"`{latency}ms` — Good"
    elif latency < 250:
        latency_label = f"`{latency}ms` — Fair"
    else:
        latency_label = f"`{latency}ms` — High"

    instance, fleet = await build_status_numbers(bot)
    embed = make_embed(
        "System Status",
        "> Operational health for this runtime and the shared bot fleet.",
        kind="info",
        scope=SCOPE_SYSTEM,
        guild=guild,
    )
    embed.add_field(name="Latency", value=latency_label, inline=True)
    embed.add_field(name="Uptime", value=f"`{uptime_str}`", inline=True)
    embed.add_field(name="Instance Servers", value=str(instance.guild_count), inline=True)
    embed.add_field(name="Instance Members", value=str(instance.member_count), inline=True)
    embed.add_field(name="Instance Cases", value=str(instance.total_cases), inline=True)
    embed.add_field(name="Fleet Bots", value=str(fleet.instance_count), inline=True)
    embed.add_field(name="Fleet Servers", value=str(fleet.guild_count), inline=True)
    embed.add_field(name="Fleet Members", value=str(fleet.member_count), inline=True)
    embed.add_field(name="Fleet Cases", value=str(fleet.total_cases), inline=True)
    embed.add_field(name="Open Tickets", value=str(fleet.open_tickets), inline=True)
    embed.add_field(name="Cache Size", value=str(len(bot.data_manager.message_cache)), inline=True)
    return embed


__all__ = [
    "get_feature_flag_name",
    "build_mod_help_embed",
    "build_setup_dashboard_embed",
    "build_modmail_settings_embed",
    "build_config_dashboard_embed",
    "build_rules_dashboard_embed",
    "build_feature_flags_embed",
    "build_escalation_matrix_embed",
    "build_canned_replies_embed",
    "build_setup_validation_embed",
    "build_status_embed",
]
