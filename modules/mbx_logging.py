"""Log channel dispatch + action-log embed construction."""
from __future__ import annotations

import io
import logging
from typing import List, Optional, Tuple

import discord

from modules.mbx_constants import SCOPE_MODERATION, SCOPE_SYSTEM
from modules.mbx_context import bot
from modules.mbx_embeds import (
    _build_footer_text,
    _set_footer_branding,
    brand_embed,
    make_embed,
)
from modules.mbx_utils import truncate_text


logger = logging.getLogger("MGXBot")


LOG_QUOTE_FIELD_NAMES = {
    "message",
    "blocked message",
    "flagged message",
    "appeal statement",
    "original violation",
    "internal note",
    "message to user",
    "user report",
    "extra context",
    "details",
}
LOG_NONINLINE_FIELD_NAMES = {
    "message",
    "blocked message",
    "flagged message",
    "appeal statement",
    "original violation",
    "internal note",
    "message to user",
    "user report",
    "extra context",
    "escalation",
    "result",
    "reason template",
    "actions",
    "trigger",
}


def format_log_quote(value: Optional[str], *, limit: int = 1000) -> str:
    text = truncate_text(str(value or "None").strip(), limit)
    return f">>> {text}" if text else ">>> None"


def format_plain_log_block(*lines: Optional[str], limit: int = 1000) -> str:
    cleaned: List[str] = []
    for line in lines:
        for raw_part in str(line or "").splitlines():
            value = raw_part.strip()
            if not value:
                continue
            if value.startswith(">>>"):
                value = value[3:].strip()
            elif value.startswith("> "):
                value = value[2:].strip()
            elif value.startswith(">"):
                value = value[1:].strip()
            if value:
                cleaned.append(value)
    if not cleaned:
        return "None"
    return truncate_text("\n".join(cleaned), limit)


def format_reason_value(value: Optional[str], *, limit: int = 1000) -> str:
    text = truncate_text(str(value or "None").strip(), limit)
    if not text:
        return "> None"
    if text.startswith(">"):
        return text
    return f"> {text}"


def format_log_notes(*lines: Optional[str], limit: int = 1000) -> str:
    cleaned = []
    for line in lines:
        value = str(line or "").strip()
        if not value:
            continue
        if value.startswith("- ") or value.startswith("> "):
            value = value[2:]
        cleaned.append(value)
    if not cleaned:
        return "> None"
    return truncate_text("\n".join(f"> {line}" for line in cleaned), limit)


def normalize_log_field_name(name: str) -> str:
    parts = []
    for raw_part in str(name or "Detail").strip().split():
        part = raw_part.strip()
        if not part:
            continue
        lowered = part.lower()
        if lowered in {"id", "dm", "sla", "url"}:
            parts.append(lowered.upper())
        else:
            parts.append(part[0].upper() + part[1:])
    return truncate_text(" ".join(parts) or "Detail", 256)


def format_log_field_value(
    name: str, value: Optional[str], *, limit: int = 1024
) -> str:
    field_name = str(name or "").strip().lower()
    text = truncate_text(
        str(value or "None").strip() or "None",
        limit if field_name not in LOG_QUOTE_FIELD_NAMES else min(limit, 950),
    )
    if field_name in LOG_QUOTE_FIELD_NAMES:
        return format_log_quote(text, limit=min(limit, 950))
    return text


def build_log_detail_fields(
    *lines: Optional[str], limit: int = 8
) -> List[Tuple[str, str, bool]]:
    detail_fields = []
    for line in lines:
        value = str(line or "").strip()
        if not value:
            continue
        value = value[2:] if value.startswith("- ") else value
        if ":" in value:
            name, detail_value = value.split(":", 1)
            name = normalize_log_field_name(name)
            detail_value = detail_value.strip() or "None"
        else:
            name = "Detail"
            detail_value = value
        lowered = name.lower()
        formatted_value = format_log_field_value(name, detail_value)
        inline = (
            len(str(detail_value)) <= 80
            and lowered not in LOG_NONINLINE_FIELD_NAMES
        )
        detail_fields.append((name, formatted_value, inline))
        if len(detail_fields) >= limit:
            break
    return detail_fields


def make_action_log_embed(
    title: str,
    description: str,
    *,
    guild: discord.Guild,
    kind: str = "info",
    scope: str = SCOPE_MODERATION,
    actor: Optional[str] = None,
    target: Optional[str] = None,
    reason: Optional[str] = None,
    duration: Optional[str] = None,
    expires: Optional[str] = None,
    message: Optional[str] = None,
    notes: Optional[List[str]] = None,
    thumbnail: Optional[str] = None,
    author_name: Optional[str] = None,
    author_icon: Optional[str] = None,
) -> discord.Embed:
    embed = make_embed(
        title,
        description if description.startswith(">") else f"> {description}",
        kind=kind,
        scope=scope,
        guild=guild,
        thumbnail=thumbnail,
        author_name=author_name,
        author_icon=author_icon,
    )
    if actor:
        embed.add_field(name="Actor", value=actor, inline=True)
    if target:
        embed.add_field(name="Target", value=target, inline=True)
    if reason:
        embed.add_field(
            name="Reason",
            value=format_reason_value(reason, limit=500),
            inline=False,
        )
    if duration:
        embed.add_field(name="Duration", value=duration, inline=True)
    if expires:
        embed.add_field(name="Expires", value=expires, inline=True)
    if message:
        embed.add_field(
            name="Message",
            value=format_log_quote(message, limit=900),
            inline=False,
        )
    if notes:
        for detail_name, detail_value, detail_inline in build_log_detail_fields(
            *notes
        ):
            embed.add_field(
                name=detail_name, value=detail_value, inline=detail_inline
            )
    return embed


def normalize_log_embed(
    embed: discord.Embed, *, guild: Optional[discord.Guild] = None
) -> discord.Embed:
    payload = embed.to_dict()
    description = payload.get("description")
    if description and not str(description).startswith(">"):
        payload["description"] = f"> {description}"

    normalized_fields = []
    for field in payload.get("fields", []):
        name = str(field.get("name", ""))
        value = str(field.get("value", ""))
        lowered = name.lower()
        if lowered == "reason":
            field["value"] = truncate_text(
                format_reason_value(value, limit=950), 1024
            )
            field["inline"] = False
            normalized_fields.append(field)
            continue
        if lowered in LOG_QUOTE_FIELD_NAMES:
            stripped = value.strip()
            if not stripped.startswith((">>>", "```")):
                value = format_log_field_value(name, stripped)
            field["value"] = truncate_text(value, 1024)
            normalized_fields.append(field)
            continue
        if lowered == "notes":
            detail_fields = build_log_detail_fields(
                *[line.strip() for line in value.splitlines() if line.strip()],
                limit=10,
            )
            if detail_fields:
                for detail_name, detail_value, detail_inline in detail_fields:
                    normalized_fields.append(
                        {
                            "name": detail_name,
                            "value": truncate_text(detail_value, 1024),
                            "inline": detail_inline,
                        }
                    )
                continue
        field["value"] = truncate_text(value, 1024)
        normalized_fields.append(field)
    payload["fields"] = normalized_fields

    normalized = discord.Embed.from_dict(payload)
    footer = embed.footer
    if guild is not None:
        _set_footer_branding(
            normalized,
            footer.text
            if footer and footer.text
            else _build_footer_text(SCOPE_SYSTEM, guild),
            guild,
        )
    elif footer and footer.text:
        normalized.set_footer(text=footer.text, icon_url=footer.icon_url)
    else:
        brand_embed(normalized, guild=guild)
    if embed.author and embed.author.name:
        normalized.set_author(
            name=embed.author.name, icon_url=embed.author.icon_url
        )
    if embed.thumbnail and embed.thumbnail.url:
        normalized.set_thumbnail(url=embed.thumbnail.url)
    if embed.image and embed.image.url:
        normalized.set_image(url=embed.image.url)
    return normalized


def get_general_log_channel_ids(config: Optional[dict] = None) -> List[int]:
    config = config or bot.data_manager.config
    channel_ids: List[int] = []
    for raw_channel_id in (
        config.get("general_log_channel_id"),
        config.get("log_channel_id"),
    ):
        if not raw_channel_id:
            continue
        try:
            channel_id = int(raw_channel_id)
        except (TypeError, ValueError):
            continue
        if channel_id not in channel_ids:
            channel_ids.append(channel_id)
    return channel_ids


def get_general_log_channel_id(config: Optional[dict] = None) -> Optional[int]:
    channel_ids = get_general_log_channel_ids(config)
    return channel_ids[0] if channel_ids else None


def get_punishment_log_channel_ids(config: Optional[dict] = None) -> List[int]:
    config = config or bot.data_manager.config
    channel_ids: List[int] = []
    for raw_channel_id in (
        config.get("punishment_log_channel_id"),
        *get_general_log_channel_ids(config),
    ):
        if not raw_channel_id:
            continue
        try:
            channel_id = int(raw_channel_id)
        except (TypeError, ValueError):
            continue
        if channel_id not in channel_ids:
            channel_ids.append(channel_id)
    return channel_ids


def get_punishment_log_channel_id(
    config: Optional[dict] = None,
) -> Optional[int]:
    channel_ids = get_punishment_log_channel_ids(config)
    return channel_ids[0] if channel_ids else None


async def _send_log_to_channels(
    guild: discord.Guild,
    channel_ids: List[int],
    embed: discord.Embed,
    *,
    content: Optional[str] = None,
    view: Optional[discord.ui.View] = None,
    attachments: Optional[List[Tuple[str, bytes]]] = None,
    log_label: str = "log",
) -> bool:
    if not channel_ids:
        return False

    normalized_embed = normalize_log_embed(embed, guild=guild)
    for channel_id in channel_ids:
        channel = guild.get_channel_or_thread(channel_id) or guild.get_channel(
            channel_id
        )
        if channel is None:
            logger.warning(
                "Configured %s channel %s was not found in guild %s.",
                log_label,
                channel_id,
                guild.id,
            )
            continue
        try:
            files = None
            if attachments:
                files = [
                    discord.File(io.BytesIO(data), filename=filename)
                    for filename, data in attachments
                ]
            await channel.send(
                content=content, embed=normalized_embed, view=view, files=files
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to send %s to channel %s: %s",
                log_label,
                channel_id,
                exc,
            )
    return False


async def send_log(
    guild: discord.Guild,
    embed: discord.Embed,
    content: str = None,
    view: discord.ui.View = None,
    attachments: Optional[List[Tuple[str, bytes]]] = None,
):
    await _send_log_to_channels(
        guild,
        get_general_log_channel_ids(),
        embed,
        content=content,
        view=view,
        attachments=attachments,
        log_label="general log",
    )


async def send_punishment_log(
    guild: discord.Guild,
    embed: discord.Embed,
    content: str = None,
    view: discord.ui.View = None,
    attachments: Optional[List[Tuple[str, bytes]]] = None,
):
    await _send_log_to_channels(
        guild,
        get_punishment_log_channel_ids(),
        embed,
        content=content,
        view=view,
        attachments=attachments,
        log_label="punishment log",
    )


async def send_automod_log(
    guild: discord.Guild,
    embed: discord.Embed,
    *,
    content: Optional[str] = None,
    preferred_channel_id: Optional[int] = None,
):
    candidate_ids = []
    for raw_channel_id in (
        preferred_channel_id,
        bot.data_manager.config.get("automod_log_channel_id"),
        *get_punishment_log_channel_ids(),
    ):
        if not raw_channel_id:
            continue
        channel_id = int(raw_channel_id)
        if channel_id not in candidate_ids:
            candidate_ids.append(channel_id)

    await _send_log_to_channels(
        guild,
        candidate_ids,
        embed,
        content=content,
        log_label="automod log",
    )
