"""Punishment execution helpers extracted from mbx_legacy."""
from __future__ import annotations

from datetime import timedelta

import discord

from modules.mbx_cases import (
    build_punishment_execution_log_embed,
    calculate_member_risk,
    get_active_records_for_user,
)
from modules.mbx_constants import SCOPE_MODERATION
from modules.mbx_context import abuse_system, bot
from modules.mbx_embeds import make_embed
from modules.mbx_formatters import (
    format_user_ref,
    get_case_label,
    get_user_display_name,
)
from modules.mbx_logging import (
    format_log_quote,
    format_reason_value,
    send_punishment_log,
)
from modules.mbx_permissions import resolve_member
from modules.mbx_utils import format_duration, now_iso


def get_valid_duration(minutes: int) -> timedelta:
    # Discord max timeout is 28 days (40320 minutes).
    return timedelta(minutes=min(minutes, 40320))


async def handle_abuse(*args, **kwargs):
    from modules.mbx_automod import handle_abuse as automod_handle_abuse

    return await automod_handle_abuse(*args, **kwargs)


def AppealView(*args, **kwargs):
    from ui.moderation import AppealView as appeal_view

    return appeal_view(*args, **kwargs)


async def execute_punishment(interaction, target, moderator, reason, minutes, note, user_msg, is_escalated, origin_message=None, punishment_type="auto", public=False):
    uid = str(target.id)
    history = bot.data_manager.punishments.get(uid, [])
    guild = interaction.guild
    member_target = target if isinstance(target, discord.Member) else await resolve_member(guild, target.id)

    # Determine Type
    if punishment_type == "auto":
        if minutes == -1: punishment_type = "ban"
        elif minutes == 0: punishment_type = "warn"
        else: punishment_type = "timeout"

    is_ban = (punishment_type == "ban")
    is_kick = (punishment_type == "kick")
    is_softban = (punishment_type == "softban")
    is_warning = (punishment_type == "warn")

    # Anti-Abuse: Hierarchy Check
    if member_target and member_target.id != guild.owner_id and member_target != moderator:
        if member_target.top_role >= moderator.top_role:
            await interaction.response.send_message("**Anti-Abuse:** You cannot punish a user with equal or higher role hierarchy.", ephemeral=True)
            return

    # Anti-Abuse: Rate Limit
    if abuse_system.check_rate_limit(moderator.id):
        await handle_abuse(interaction, moderator)
        return

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    try:
        if is_kick:
            if not member_target:
                await interaction.followup.send("User is not in the server, cannot kick.", ephemeral=True)
                return
            await guild.kick(member_target, reason=f"{reason} (By {moderator})")
        elif is_softban:
            # Softban: Ban (Delete 1 day of messages) -> Unban
            await guild.ban(target, reason=f"{reason} (By {moderator})", delete_message_days=1)
            await guild.unban(discord.Object(id=target.id), reason=f"Softban cleanup (By {moderator})")
        elif is_ban:
            # Handles both Perm (-1) and Temp (>0) bans
            await guild.ban(target, reason=f"{reason} (By {moderator})", delete_message_days=0)
        elif punishment_type == "timeout":
            if not member_target:
                await interaction.followup.send("User is not in the server, cannot timeout.", ephemeral=True)
                return
            duration = get_valid_duration(minutes)
            await member_target.timeout(duration, reason=f"{reason} (By {moderator})")
    except discord.Forbidden:
        await interaction.followup.send("I cannot punish this user (Permission Error).", ephemeral=True)
        return
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)
        return

    timestamp_iso = now_iso()

    # DM User
    dm_delivered = False
    try:
        if is_kick:
            action_verb = "Kicked"
        elif is_softban:
            action_verb = "Softbanned (Kicked + Messages Purged)"
        elif is_ban:
            action_verb = "Banned" if minutes == -1 else f"Banned for {format_duration(minutes)}"
        else:
            action_verb = "Warned" if is_warning else "Timed Out"

        dm_embed = make_embed(
            "Moderation Action Issued",
            f"> You have been **{action_verb}** in **{interaction.guild.name}**.",
            kind="danger",
            scope=SCOPE_MODERATION,
            guild=interaction.guild,
            thumbnail=interaction.guild.icon.url if interaction.guild.icon else None,
        )
        dm_embed.add_field(name="Reason", value=format_reason_value(reason, limit=1000), inline=False)
        if user_msg:
            dm_embed.add_field(name="Moderator Message", value=format_log_quote(user_msg, limit=1024), inline=False)

        if punishment_type == "timeout":
            dm_embed.add_field(name="Duration", value=format_duration(minutes), inline=True)
            unmute_dt = discord.utils.utcnow() + get_valid_duration(minutes if minutes > 0 else 0)
            dm_embed.add_field(name="Expires", value=discord.utils.format_dt(unmute_dt, "R"), inline=True)
        elif is_ban and minutes == -1:
            dm_embed.add_field(name="Duration", value="Ban", inline=True)

        if interaction.guild.icon:
            dm_embed.set_thumbnail(url=interaction.guild.icon.url)

        view = AppealView(interaction.guild.id, target.id, moderator.id, minutes, timestamp_iso, reason)
        await target.send(embed=dm_embed, view=view)
        dm_delivered = True
    except discord.Forbidden:
        pass

    # Log punishment
    record = {
        "reason": reason,
        "moderator": moderator.id,
        "duration_minutes": minutes,
        "timestamp": timestamp_iso,
        "escalated": is_escalated,
        "note": note,
        "user_msg": user_msg,
        "target_name": get_user_display_name(target),
        "type": punishment_type,
        "active": is_ban,
        "dm_delivered": dm_delivered,
    }
    record = await bot.data_manager.add_punishment(uid, record, persist=False)
    case_label = get_case_label(record, len(history) + 1)

    # Update Stats
    bot.data_manager.config["stats"]["total_issued"] = bot.data_manager.config["stats"].get("total_issued", 0) + 1
    bot.data_manager.mark_config_dirty()
    await bot.data_manager.save_all()

    if is_kick:
        status = "Kicked"
    elif is_softban:
        status = "Softbanned"
    elif is_ban:
        status = "Banned"
    else:
        status = "Warning Logged" if is_warning else ("Escalated (Recidivism)" if is_escalated else "Standard")

    if reason == "Custom Punishment":
        status = "Custom"
        if is_ban: status = "Custom (Ban)"

    log_embed = build_punishment_execution_log_embed(
        guild=interaction.guild,
        case_label=case_label,
        actor=format_user_ref(moderator),
        target=format_user_ref(target),
        record=record,
        thumbnail=target.display_avatar.url,
    )

    # Response Embed (Private)
    response_embed = make_embed(
        "Action Successful",
        f"> **{target.mention}** has been punished successfully.",
        kind="success",
        scope=SCOPE_MODERATION,
        guild=interaction.guild,
        thumbnail=target.display_avatar.url,
    )
    response_embed.add_field(name="Case", value=case_label, inline=True)
    response_embed.add_field(name="Reason", value=format_reason_value(reason, limit=500), inline=False)
    response_embed.add_field(name="Type", value=status, inline=True)
    if not is_warning:
        response_embed.add_field(name="Duration", value=format_duration(minutes), inline=True)

    if interaction.message:
        try:
            await interaction.message.edit(content=None, embed=response_embed, view=None)
        except Exception:
            await interaction.followup.send(embed=response_embed, ephemeral=True)
    else:
        await interaction.followup.send(embed=response_embed, ephemeral=True)

    try:
        await interaction.delete_original_response()
    except Exception:
        pass

    if public:
        pub_embed = make_embed(
            f"{case_label} Issued",
            f"> **{target.mention}** has been punished.",
            kind="danger",
            scope=SCOPE_MODERATION,
            guild=interaction.guild,
        )
        pub_embed.add_field(name="Reason", value=format_reason_value(reason, limit=200), inline=False)
        pub_embed.add_field(name="Type", value=status, inline=True)
        if not is_warning and minutes != 0:
             pub_embed.add_field(name="Duration", value=format_duration(minutes), inline=True)
        pub_embed.add_field(name="Handled By", value=moderator.display_name, inline=True)
        try:
            await interaction.channel.send(embed=pub_embed)
        except Exception:
            pass

    await send_punishment_log(interaction.guild, log_embed)

    if origin_message:
        try:
            await origin_message.edit(embed=build_punish_embed(target))
        except Exception:
            pass

def build_punish_embed(user: discord.Member) -> discord.Embed:
    uid = str(user.id)
    history = bot.data_manager.punishments.get(uid, [])
    active_records = get_active_records_for_user(user.id)
    risk_score, risk_label = calculate_member_risk(history)
    embed = make_embed(
        "Moderation Console",
        "> Select a violation category below, then review history if needed before acting.",
        kind="muted",
        scope=SCOPE_MODERATION,
        guild=user.guild if isinstance(user, discord.Member) else None,
        thumbnail=user.display_avatar.url,
    )
    embed.add_field(name="Target", value=format_user_ref(user), inline=True)
    embed.add_field(name="Total Cases", value=str(len(history)), inline=True)
    embed.add_field(name="Active Cases", value=str(len(active_records)), inline=True)
    embed.add_field(name="Risk", value=f"{risk_label} ({risk_score})", inline=True)
    if isinstance(user, discord.Member) and user.joined_at:
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(user.joined_at, "f"), inline=True)
    embed.add_field(name="Account Created", value=discord.utils.format_dt(user.created_at, "f"), inline=True)
    return embed


__all__ = [
    "build_punish_embed",
    "execute_punishment",
]
