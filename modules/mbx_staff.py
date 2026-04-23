"""Staff stats and case-management helpers."""
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


async def log_case_management_action(
    guild: discord.Guild,
    actor: discord.Member,
    target_user_id: str,
    record: dict,
    action: str,
    details: str,
):
    detail_lines = [line.strip() for line in str(details or "").splitlines() if line.strip()]
    embed = make_action_log_embed(
        f"{get_case_label(record)} Updated",
        "A case-management action modified the record metadata.",
        guild=guild,
        kind="info",
        scope=SCOPE_MODERATION,
        actor=format_user_ref(actor),
        target=f"<@{target_user_id}> (`{target_user_id}`)",
        reason=action,
        duration="Record Updated",
        expires="N/A",
        notes=detail_lines or [f"Result: {truncate_text(details, 500)}"],
    )
    if record.get("action_id"):
        embed.add_field(name="Action ID", value=f"`{record['action_id']}`", inline=True)
    await send_punishment_log(guild, embed)

def _split_case_input(value: str) -> List[str]:
    return [part.strip() for part in re.split(r"[\n,]+", value or "") if part.strip()]

def get_mod_cases(mod_id: str) -> list:
    cases = []
    for uid, records in bot.data_manager.punishments.items():
        for r in records:
            if str(r.get("moderator")) == mod_id:
                cases.append((uid, r))
    return cases

def get_staff_stats_embed(target: discord.Member, cases: list, reversals: int) -> discord.Embed:
    total = len(cases)

    # Sort cases by timestamp (newest first) for calculations
    sorted_cases = sorted(cases, key=lambda x: x[1].get("timestamp", ""), reverse=True)

    action_counter = Counter()
    reasons = Counter()
    timestamps = []

    for uid, r in sorted_cases:
        reasons[r.get("reason", "Unknown")] += 1
        ts_str = r.get("timestamp")
        if ts_str:
            dt = iso_to_dt(ts_str)
            if dt: timestamps.append(dt)

        action_type = r.get("type")
        if not action_type:
            dur = r.get("duration_minutes", 0)
            if dur == -1:
                action_type = "ban"
            elif dur == 0:
                action_type = "warn"
            else:
                action_type = "timeout"
        action_counter[action_type] += 1

    embed = make_embed(
        f"Staff Profile: {target.display_name}",
        "> Moderation performance snapshot based on logged actions and reversals.",
        kind="info",
        scope=SCOPE_ANALYTICS,
        guild=target.guild,
        thumbnail=target.display_avatar.url,
    )
    if target.color != discord.Color.default():
        embed.color = target.color

    joined = discord.utils.format_dt(target.joined_at, "d") if target.joined_at else "Unknown"
    roles_str = truncate_text(", ".join([r.mention for r in target.roles if not r.is_default()][-5:]) or "None", 1024)
    embed.add_field(name="Member", value=format_user_ref(target), inline=True)
    embed.add_field(name="Joined Server", value=joined, inline=True)
    embed.add_field(name="Roles", value=roles_str, inline=False)

    # Activity Overview
    first_action = timestamps[-1] if timestamps else None
    last_action = timestamps[0] if timestamps else None

    days_active = (last_action - first_action).days if (first_action and last_action) else 0
    days_active = max(1, days_active)

    avg_daily = round(total / days_active, 2) if total > 0 else 0
    reversal_rate = round((reversals / total) * 100, 1) if total > 0 else 0

    overview = (
        f"**Total Actions:** `{total}`\n"
        f"**Reversals:** `{reversals}` ({reversal_rate}%)\n"
        f"**Avg Actions/Day:** `{avg_daily}`\n"
        f"**First Action:** {discord.utils.format_dt(first_action, 'd') if first_action else 'N/A'}\n"
        f"**Last Action:** {discord.utils.format_dt(last_action, 'R') if last_action else 'N/A'}"
    )
    now = discord.utils.utcnow()
    embed.add_field(name="Performance Overview", value=f">>> {overview}", inline=False)

    # Recent Activity
    last_24h = sum(1 for t in timestamps if (now - t).days < 1)
    last_7d = sum(1 for t in timestamps if (now - t).days < 7)
    last_30d = sum(1 for t in timestamps if (now - t).days < 30)

    recent = (
        f"**24 Hours:** `{last_24h}`\n"
        f"**7 Days:** `{last_7d}`\n"
        f"**30 Days:** `{last_30d}`"
    )
    embed.add_field(name="Recent Activity", value=f">>> {recent}", inline=True)

    # Action Distribution (Visual)
    if total > 0:
        bans = action_counter.get("ban", 0)
        timeouts = action_counter.get("timeout", 0)
        warns = action_counter.get("warn", 0)
        p_bans = bans / total
        p_to = timeouts / total
        p_warn = warns / total

        dist_desc = (
            f"**Bans** ({bans})\n`{create_progress_bar(p_bans)}` {round(p_bans*100)}%\n"
            f"**Timeouts** ({timeouts})\n`{create_progress_bar(p_to)}` {round(p_to*100)}%\n"
            f"**Warnings** ({warns})\n`{create_progress_bar(p_warn)}` {round(p_warn*100)}%"
        )
        embed.add_field(name="Action Distribution", value=f">>> {dist_desc}", inline=False)
    else:
        embed.add_field(name="Action Distribution", value="> No data available.", inline=False)

    # Top Reasons
    if reasons:
        top = reasons.most_common(5)
        reason_lines = []
        for r, c in top:
            pct = (c / total) * 100
            reason_lines.append(f"**{truncate_text(r, 60)}**: {c} ({round(pct)}%)")
        embed.add_field(name="Most Common Violations", value=">>> " + "\n".join(reason_lines), inline=False)

    return embed

def build_test_env_embed():
    debug = bot.data_manager.config.get("debug", {})
    boost_status = "Enabled (Requirement Ignored)" if debug.get("bypass_boost") else "Disabled (Requirement Enforced)"
    cd_status = "Enabled (No Cooldowns)" if debug.get("bypass_cooldown") else "Disabled (Standard Cooldowns)"

    embed = make_embed(
        "Test Environment Control",
        "> Toggle debug-only flags used to validate premium and cooldown flows.",
        kind="warning",
        scope=SCOPE_SYSTEM,
    )
    embed.add_field(name="Boost Requirement Bypass", value=boost_status, inline=False)
    embed.add_field(name="Cooldown Bypass", value=cd_status, inline=False)
    return embed


__all__ = [
    "get_mod_cases",
    "get_staff_stats_embed",
    "build_test_env_embed",
    "log_case_management_action",
    "_split_case_input",
]
