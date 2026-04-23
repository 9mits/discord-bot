"""Public execution vote helpers."""
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


def _legacy_value(name: str):
    from modules import mbx_legacy

    return getattr(mbx_legacy, name)


def AppealView(*args, **kwargs):
    from ui.moderation import AppealView as view_cls

    return view_cls(*args, **kwargs)


def get_public_execution_action_label(punishment_type: str) -> str:
    mapping = {
        "ban": "Ban",
        "kick": "Kick",
        "timeout": "Timeout",
        "warn": "Warn",
        "softban": "Softban",
    }
    return mapping.get(punishment_type, "Punish")

def build_public_execution_embed(
    guild: discord.Guild,
    *,
    target_id: int,
    target_avatar_url: Optional[str],
    punishment_type: str,
    reason: str,
    threshold: int,
    minutes: int,
    approvals: int = 0,
) -> discord.Embed:
    action_label = get_public_execution_action_label(punishment_type)
    embed = make_embed(
        "Public Execution Started",
        (
            f"Use the button below to approve **{action_label}** for <@{target_id}>.\n\n"
            f"The action will run once **{threshold}** approval(s) are recorded."
        ),
        kind="danger",
        scope=SCOPE_MODERATION,
        guild=guild,
        thumbnail=target_avatar_url,
    )
    embed.add_field(name="Reason", value=format_reason_value(reason, limit=200), inline=False)
    if minutes > 0:
        embed.add_field(name="Duration", value=format_duration(minutes), inline=True)
    embed.add_field(name="Approvals", value=f"{approvals}/{threshold}", inline=True)
    return embed

async def execute_public_execution_vote(
    channel: discord.abc.Messageable,
    guild: discord.Guild,
    data: Dict[str, Any],
) -> None:
    try:
        target = await guild.fetch_member(data["target_id"])
    except discord.NotFound:
        try:
            target = await bot.fetch_user(data["target_id"])
        except Exception:
            target = None

    if target is None:
        return

    target_member = target if isinstance(target, discord.Member) else await resolve_member(guild, data["target_id"])

    try:
        moderator = await guild.fetch_member(data["moderator_id"])
    except Exception:
        moderator = None

    try:
        p_type = data["type"]
        minutes = data["duration"]
        action_verb = "Banned" if p_type == "ban" else ("Kicked" if p_type == "kick" else "Timed Out")

        dm_embed = make_embed(
            "Public Execution Result",
            f"> You have been **{action_verb}** in **{guild.name}** through a public execution vote.",
            kind="danger",
            scope=SCOPE_MODERATION,
            guild=guild,
        )
        dm_embed.add_field(name="Reason", value=format_reason_value(data["reason"], limit=1000), inline=False)
        if data["user_msg"]:
            dm_embed.add_field(name="Moderator Message", value=format_log_quote(data["user_msg"], limit=1024), inline=False)

        if p_type == "ban" and minutes == -1:
            dm_embed.add_field(name="Duration", value="Ban", inline=True)
        elif minutes > 0:
            dm_embed.add_field(name="Duration", value=format_duration(minutes), inline=True)

        view = AppealView(guild.id, target.id, data["moderator_id"], minutes, now_iso(), data["reason"])
        await target.send(embed=dm_embed, view=view)
    except Exception:
        pass

    try:
        p_type = data["type"]
        minutes = data["duration"]
        reason = f"Public Execution (Vote passed) - {data['reason']}"

        if p_type == "ban":
            await guild.ban(target, reason=reason)
        elif p_type == "kick":
            if not target_member:
                raise ValueError("User is not in the server, cannot kick.")
            await guild.kick(target_member, reason=reason)
        elif p_type == "timeout":
            if not target_member:
                raise ValueError("User is not in the server, cannot timeout.")
            await target_member.timeout(get_valid_duration(minutes), reason=reason)
        elif p_type == "softban":
            await guild.ban(target, reason=reason, delete_message_days=1)
            await guild.unban(discord.Object(id=target.id), reason="Softban cleanup")

        record = {
            "reason": f"Public Execution: {data['reason']}",
            "moderator": moderator.id if moderator else data["moderator_id"],
            "duration_minutes": minutes,
            "timestamp": now_iso(),
            "escalated": data["escalated"],
            "note": data["note"],
            "user_msg": data["user_msg"],
            "target_name": get_user_display_name(target),
            "type": p_type,
            "active": p_type == "ban",
        }
        record = await bot.data_manager.add_punishment(str(target.id), record)
        case_label = get_case_label(record)

        action_msg = "has been banned"
        if p_type == "kick":
            action_msg = "has been kicked"
        elif p_type == "timeout":
            action_msg = "has been timed out"
        elif p_type == "warn":
            action_msg = "has been warned"

        await channel.send(f"{case_label}: {target.mention} {action_msg}.")

        actor_ref = format_user_ref(moderator) if moderator else format_user_id_ref(data["moderator_id"])
        log_embed = build_punishment_execution_log_embed(
            guild=guild,
            case_label=case_label,
            actor=actor_ref,
            target=format_user_ref(target),
            record=record,
            thumbnail=target.display_avatar.url,
        )
        log_embed.title = f"{case_label} Public Execution"
        log_embed.description = "> A community vote threshold was reached and the configured action was executed."
        log_embed.insert_field_at(2, name="Votes Reached", value=str(data["count"]), inline=True)
        await send_punishment_log(guild, log_embed)
    except Exception as e:
        await channel.send(f"Execution failed: {e}")


__all__ = [
    "get_public_execution_action_label",
    "build_public_execution_embed",
    "execute_public_execution_vote",
]
