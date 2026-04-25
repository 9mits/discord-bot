"""Modmail panel, ticket state, and resolver helpers."""
from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import re
import time
from datetime import timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple, Union

import discord
from discord.ext import commands

from modules.mbx_constants import (
    EMBED_PALETTE,
    MODMAIL_PANEL_BANNER_URL,
    MODMAIL_PANEL_CATEGORIES,
    SCOPE_SUPPORT,
)
from modules.mbx_context import bot
from modules.mbx_embeds import _get_branding_config, brand_embed, make_embed, upsert_embed_field
from modules.mbx_formatters import is_record_active, join_lines
from modules.mbx_images import PROFILE_BRANDING_MAX_BYTES, fetch_image_bytes
from modules.mbx_services import get_feature_flag
from modules.mbx_utils import iso_to_dt

logger = logging.getLogger("MGXBot")


def _active_bot():
    return bot


def _data_manager():
    try:
        return getattr(_active_bot(), "data_manager", None)
    except RuntimeError:
        return None


def ModmailPanelView(*args, **kwargs):
    from ui.modmail import ModmailPanelView as view_cls

    return view_cls(*args, **kwargs)


def ModmailControlView(*args, **kwargs):
    from ui.modmail import ModmailControlView as view_cls

    return view_cls(*args, **kwargs)


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
        f'<div class="chat-container"><h2 style="color:white; border-bottom: 1px solid #4e5058; padding-bottom: 10px;">Chat History: {safe_display_name} ({user.id})</h2>',
    ]

    # messages is Newest -> Oldest. Reverse to show Oldest -> Newest in HTML.
    for message in reversed(messages):
        timestamp = message["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        content = html.escape(message.get("content", ""))
        if not content:
            content = "<em>[No Text Content]</em>"
        author_name = html.escape(message.get("author_name", user.display_name))
        author_avatar_url = html.escape(
            message.get(
                "author_avatar_url",
                user.display_avatar.url if getattr(user, "display_avatar", None) else "",
            )
        )

        tags = ""
        if message.get("deleted"):
            tags += '<span class="deleted-tag">DELETED</span>'
        if message.get("edited"):
            tags += '<span class="edited-tag">(edited)</span>'

        attachment_html = ""
        if message.get("attachments"):
            attachment_html += '<div class="attachment-container">'
            for attachment in message["attachments"]:
                safe_url = html.escape(attachment["url"])
                safe_filename = html.escape(attachment["filename"])
                ext = attachment["filename"].split(".")[-1].lower()
                if ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                    attachment_html += (
                        f'<a href="{safe_url}" target="_blank"><img src="{safe_url}" '
                        f'class="attachment-img" alt="{safe_filename}"></a><br>'
                    )
                else:
                    attachment_html += f'<a href="{safe_url}" target="_blank">Attachment: {safe_filename}</a><br>'
            attachment_html += "</div>"

        if message.get("stickers"):
            attachment_html += (
                f'<div style="color:#949ba4; font-size:0.8rem;">Stickers: '
                f'{html.escape(", ".join(message["stickers"]))}</div>'
            )

        div_class = "message deleted" if message.get("deleted") else "message"
        html_parts.append(
            f"""
        <div class="{div_class}">
            <img class="avatar" src="{author_avatar_url}" alt="Avatar">
            <div class="content">
                <div class="channel-ref">#{html.escape(str(message['channel_id']))}</div>
                <div class="header">
                    <span class="username">{author_name}</span>
                    <span class="timestamp">{timestamp}</span>
                    {tags}
                </div>
                <div class="msg-content">{content}</div>
                {attachment_html}
            </div>
        </div>
        """
        )

    html_parts.append("</div></body></html>")
    return "\n".join(html_parts)




async def send_modmail_thread_intro(thread: discord.Thread, user, category: str, fields_data: List[str]) -> None:
    guild = getattr(thread, "guild", None)
    user_id = getattr(user, "id", None)
    member = guild.get_member(user_id) if guild and user_id is not None else None
    avatar = getattr(getattr(user, "display_avatar", None), "url", None)

    embed = make_embed(
        "New Support Ticket",
        f"> A new ticket has been opened by {user.mention}.",
        kind="support",
        scope=SCOPE_SUPPORT,
        guild=guild,
        thumbnail=avatar,
    )
    user_value = f"{user.mention}\n`{user_id}`" if user_id is not None else str(getattr(user, "mention", "Unknown"))
    embed.add_field(name="User", value=user_value, inline=True)
    embed.add_field(name="Category", value=category, inline=True)

    now = discord.utils.utcnow()
    created_at = getattr(user, "created_at", None)
    if created_at:
        account_age_days = (now - created_at.replace(tzinfo=timezone.utc)).days
        embed.add_field(
            name="Account Created",
            value=f"{discord.utils.format_dt(created_at, 'D')}\n({account_age_days}d ago)",
            inline=True,
        )

    if member and member.joined_at:
        join_age_days = (now - member.joined_at.replace(tzinfo=timezone.utc)).days
        embed.add_field(
            name="Joined Server",
            value=f"{discord.utils.format_dt(member.joined_at, 'D')}\n({join_age_days}d ago)",
            inline=True,
        )

    data_manager = _data_manager()
    history = data_manager.punishments.get(str(user_id), []) if data_manager and user_id is not None else []
    active_cases = [r for r in history if is_record_active(r)]
    embed.add_field(name="Prior Cases", value=str(len(history)), inline=True)
    embed.add_field(name="Active Cases", value=str(len(active_cases)), inline=True)

    for line in fields_data:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            name, value = line.split(":", 1)
            embed.add_field(name=name.strip(), value=value.strip() or "—", inline=False)
        else:
            embed.add_field(name="Note", value=line, inline=False)

    await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

async def send_modmail_panel_message(
    destination: Union[discord.abc.Messageable, discord.TextChannel, discord.User],
    guild: discord.Guild,
    *,
    intro: Optional[str] = None,
    in_dm: bool = False,
):
    is_dm_panel = in_dm or isinstance(destination, (discord.User, discord.Member, discord.DMChannel))
    embed = build_modmail_panel_embed(guild, in_dm=is_dm_panel)
    branding = _get_branding_config(guild.id)
    panel_banner_url = branding.get("modmail_banner_url") or MODMAIL_PANEL_BANNER_URL
    if intro:
        note_value = str(intro).strip()
        if note_value and not note_value.lstrip().startswith((">", "-", "*")):
            note_value = f"> {note_value}"
        if note_value:
            embed.add_field(name="Quick Note", value=note_value, inline=False)

    img_data, _ = await fetch_image_bytes(panel_banner_url, max_bytes=PROFILE_BRANDING_MAX_BYTES)
    if img_data:
        embed.set_image(url="attachment://banner.png")
        file = discord.File(io.BytesIO(img_data), filename="banner.png")
        return await destination.send(embed=embed, file=file, view=ModmailPanelView())

    embed.set_image(url=panel_banner_url)
    return await destination.send(embed=embed, view=ModmailPanelView())

async def maybe_send_dm_modmail_panel(user: discord.User, *, guild: Optional[discord.Guild] = None, force: bool = False, intro: Optional[str] = None) -> bool:
    if guild is None:
        # In a multi-server bot there is no "primary" guild — callers must
        # pass the originating guild explicitly. Bail out silently if missing.
        return False

    if not get_feature_flag(bot.data_manager._configs.get(guild.id, {}), "dm_modmail_prompt", True):
        return False

    cooldown_minutes = max(1, int(bot.data_manager._configs.get(guild.id, {}).get("dm_modmail_panel_cooldown_minutes", 30) or 30))
    now_ts = time.time()
    # Cooldown keyed per (guild_id, user_id) so multi-server prompts don't suppress each other
    cooldown_key = (guild.id, user.id)
    last_sent = bot.dm_modmail_prompt_cooldowns.get(cooldown_key, 0.0)
    if not force and last_sent and now_ts - last_sent < cooldown_minutes * 60:
        return False

    note = intro or "Need staff help? Open one private ticket below. Once it is open, keep replying in this DM."
    try:
        await send_modmail_panel_message(user, guild, intro=note, in_dm=True)
    except discord.Forbidden:
        return False
    except Exception as exc:
        logger.warning("Failed to send DM modmail panel to %s: %s", user.id, exc)
        return False

    bot.dm_modmail_prompt_cooldowns[cooldown_key] = now_ts
    return True

def build_modmail_panel_embed(guild: discord.Guild, *, in_dm: bool = False) -> discord.Embed:
    # Per-guild branding overrides
    branding = {}
    if guild is not None and getattr(bot, "data_manager", None) is not None:
        try:
            branding = bot.data_manager._configs.get(guild.id, {}).get("_branding", {})
        except Exception:
            pass
    banner_url = branding.get("modmail_banner_url") or MODMAIL_PANEL_BANNER_URL
    categories = branding.get("modmail_categories") or MODMAIL_PANEL_CATEGORIES

    description = (
        "> Need staff help? Open a ticket below — once it's open, continue replying here in DMs."
        if in_dm
        else "> Need staff help? Open a private ticket below — the bot will follow up with you in DMs."
    )
    embed = make_embed(
        "Contact Staff",
        description,
        kind="support",
        scope=SCOPE_SUPPORT,
        guild=guild,
    )
    for cat_name, cat_desc in categories:
        embed.add_field(name=cat_name, value=cat_desc, inline=True)
    embed.add_field(
        name="Before You Open",
        value="> Include usernames, links, IDs, or screenshots when possible.\n> Pick the closest type so staff can route your ticket faster.",
        inline=False,
    )
    if banner_url:
        try:
            embed.set_image(url=banner_url)
        except Exception:
            pass
    return embed

async def log_modmail_action(guild, title, fields):
    cid = bot.data_manager.config.get("modmail_action_log_channel")
    if not cid: return
    channel = guild.get_channel(cid)
    if not channel: return

    embed = make_embed(title, "> A staff action was performed on a modmail ticket.", kind="support", scope=SCOPE_SUPPORT, guild=guild)
    for n, v in fields:
        embed.add_field(name=n, value=v, inline=True)
    try: await channel.send(embed=embed)
    except Exception: pass

def apply_modmail_ticket_state(embed: discord.Embed, ticket: dict, guild: discord.Guild) -> discord.Embed:
    status = str(ticket.get("status", "open")).title()
    priority = str(ticket.get("priority", "normal")).title()
    tags = ", ".join(f"`{tag}`" for tag in ticket.get("tags", [])) or "None"
    assigned = ticket.get("assigned_moderator")
    assignee = f"<@{assigned}>" if assigned else "Unclaimed"
    last_user = iso_to_dt(ticket.get("last_user_message_at"))
    last_staff = iso_to_dt(ticket.get("last_staff_message_at"))

    embed.color = EMBED_PALETTE["danger"] if ticket.get("status") == "closed" else (EMBED_PALETTE["warning"] if ticket.get("priority") in {"high", "urgent"} else EMBED_PALETTE["support"])
    upsert_embed_field(embed, "Status", status, inline=True)
    upsert_embed_field(embed, "Urgency", priority, inline=True)
    upsert_embed_field(embed, "Assigned To", assignee, inline=True)
    upsert_embed_field(
        embed,
        "Activity",
        join_lines([
            f"User: {discord.utils.format_dt(last_user, 'R') if last_user else 'Unknown'}",
            f"Staff: {discord.utils.format_dt(last_staff, 'R') if last_staff else 'No reply yet'}",
        ]),
        inline=True,
    )
    upsert_embed_field(embed, "Tags", tags, inline=True)
    brand_embed(embed, guild=guild, scope=SCOPE_SUPPORT)
    return embed

async def refresh_modmail_message(
    message: Optional[discord.Message],
    guild: Optional[discord.Guild],
    user_id: str,
    view: "ModmailControlView",
) -> bool:
    ticket = bot.data_manager.modmail.get(user_id)
    if not ticket or message is None or not message.embeds or guild is None:
        return False
    view.sync_buttons(ticket)
    embed = apply_modmail_ticket_state(message.embeds[0], ticket, guild)
    try:
        await message.edit(embed=embed, view=view)
        return True
    except discord.NotFound:
        logger.warning("Modmail panel message for user %s no longer exists.", user_id)
    except discord.Forbidden:
        logger.warning("Missing permission to refresh modmail panel message for user %s.", user_id)
    except discord.HTTPException as exc:
        logger.warning("Failed to refresh modmail panel message for user %s: %s", user_id, exc)
    return False

async def refresh_modmail_ticket_log(guild: discord.Guild, user_id: str):
    ticket = bot.data_manager.modmail.get(user_id)
    if not ticket:
        return
    log_channel_id = bot.data_manager.config.get("modmail_inbox_channel")
    log_id = ticket.get("log_id")
    if not log_channel_id or not log_id:
        return
    channel = guild.get_channel(log_channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(log_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return
    view = ModmailControlView(user_id)
    view.message = message
    await refresh_modmail_message(message, guild, user_id, view)

async def export_modmail_transcript(thread: discord.Thread, user_id: str) -> discord.File:
    messages = []
    async for message in thread.history(limit=None, oldest_first=True):
        messages.append({
            "author_name": message.author.display_name,
            "author_avatar_url": message.author.display_avatar.url,
            "created_at": message.created_at,
            "content": message.content,
            "attachments": [{"filename": attachment.filename, "url": attachment.url} for attachment in message.attachments],
            "channel_id": thread.id,
            "deleted": False,
            "edited": bool(message.edited_at),
        })
    transcript_user = SimpleNamespace(display_name=f"Ticket {user_id}", id=int(user_id))
    html_content = generate_transcript_html(messages, transcript_user)
    return discord.File(io.BytesIO(html_content.encode("utf-8")), filename=f"modmail_transcript_{user_id}.html")

def _parse_user_id(value: Union[str, int, None]) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

async def resolve_modmail_user(user_id: Union[str, int, None]) -> Optional[discord.User]:
    normalized_user_id = _parse_user_id(user_id)
    if normalized_user_id is None:
        return None
    cached = bot.get_user(normalized_user_id)
    if cached is not None:
        return cached
    try:
        return await bot.fetch_user(normalized_user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None

async def resolve_modmail_thread(guild: Optional[discord.Guild], ticket: Optional[dict]) -> Optional[discord.Thread]:
    if not isinstance(ticket, dict):
        return None

    thread_id = _parse_user_id(ticket.get("thread_id"))
    if thread_id is None:
        return None

    # Try guild cache first if guild is available
    if guild is not None:
        candidate = guild.get_thread(thread_id) or guild.get_channel_or_thread(thread_id)
        if isinstance(candidate, discord.Thread):
            return candidate

    # Fall back to a global fetch — works without knowing the guild
    try:
        fetched = await bot.fetch_channel(thread_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None
    return fetched if isinstance(fetched, discord.Thread) else None


__all__ = [
    "send_modmail_thread_intro",
    "send_modmail_panel_message",
    "maybe_send_dm_modmail_panel",
    "build_modmail_panel_embed",
    "log_modmail_action",
    "apply_modmail_ticket_state",
    "refresh_modmail_message",
    "refresh_modmail_ticket_log",
    "export_modmail_transcript",
    "_parse_user_id",
    "resolve_modmail_user",
    "resolve_modmail_thread",
]
