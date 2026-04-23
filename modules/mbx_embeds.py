"""Embed builders and branding-footer helpers.

Extracted from mbx_legacy as part of the phased refactor. Owned by core/ in the
target structure; for now kept as a flat module so call sites keep working via
re-export from mbx_legacy.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import discord

from modules.mbx_constants import (
    BRAND_NAME,
    EMBED_PALETTE,
    SCOPE_ANALYTICS,
    SCOPE_SYSTEM,
)
from modules.mbx_context import bot
from modules.mbx_utils import truncate_text


def _legacy_value(name: str):
    try:
        from modules import mbx_legacy

        return getattr(mbx_legacy, name)
    except Exception:
        return None


def _active_bot():
    return _legacy_value("bot") or bot


def _get_data_manager():
    try:
        return getattr(_active_bot(), "data_manager", None)
    except RuntimeError:
        return None


def fmt_role(guild: Optional[discord.Guild], role_id: Optional[int]) -> str:
    """Format a role mention, or 'Not set' if the role doesn't exist in the guild."""
    if not role_id:
        return "Not set"
    if guild is not None:
        role = guild.get_role(int(role_id))
        if role is None:
            return "Not set"
    return f"<@&{role_id}>"


def fmt_channel(guild: Optional[discord.Guild], channel_id: Optional[int]) -> str:
    """Format a channel mention, or 'Not set' if the channel doesn't exist."""
    if not channel_id:
        return "Not set"
    if guild is not None:
        ch = guild.get_channel(int(channel_id))
        if ch is None:
            return "Not set"
    return f"<#{channel_id}>"


def _get_branding_config(guild_id: int) -> Dict[str, Any]:
    override = _legacy_value("_get_branding_config")
    if override is not None and override is not _get_branding_config:
        return override(guild_id)
    data_manager = _get_data_manager()
    if data_manager is None:
        return {}
    return data_manager._configs.get(guild_id, {}).get("_branding", {})


def _build_footer_text(scope: str, guild: Optional[discord.Guild]) -> str:
    """Build footer text with the current guild name first, then the scope."""
    parts = [guild.name if guild is not None else BRAND_NAME, scope]
    return " • ".join(parts)


def _build_footer_text_with_detail(
    scope: str, guild: Optional[discord.Guild], detail: Optional[str]
) -> str:
    base_text = _build_footer_text(scope, guild)
    detail_text = str(detail or "").strip()
    return f"{base_text} • {detail_text}" if detail_text else base_text


def _get_footer_icon_url(guild: Optional[discord.Guild]) -> Optional[str]:
    if guild and getattr(guild, "icon", None):
        return guild.icon.url
    return None


def _set_footer_branding(
    embed: discord.Embed, text: str, guild: Optional[discord.Guild]
) -> discord.Embed:
    icon_url = _get_footer_icon_url(guild)
    if icon_url:
        embed.set_footer(text=text, icon_url=icon_url)
    else:
        embed.set_footer(text=text)
    return embed


def _format_branding_panel_value(
    value: Optional[str],
    *,
    empty: str = "Not set",
    limit: int = 60,
) -> str:
    clean = str(value or "").strip()
    if not clean:
        return f"`{empty}`"
    return f"`{truncate_text(clean, limit)}`"


def make_embed(
    title: str,
    description: Optional[str] = None,
    *,
    kind: str = "neutral",
    scope: str = SCOPE_SYSTEM,
    guild: Optional[discord.Guild] = None,
    thumbnail: Optional[str] = None,
    author_name: Optional[str] = None,
    author_icon: Optional[str] = None,
) -> discord.Embed:
    color = EMBED_PALETTE.get(kind, EMBED_PALETTE["neutral"])

    # Per-guild custom embed color
    data_manager = _get_data_manager()
    if guild is not None and data_manager is not None:
        try:
            hex_color = (
                data_manager._configs.get(guild.id, {})
                .get("_branding", {})
                .get("embed_color")
            )
            if hex_color:
                color = discord.Color(int(str(hex_color).lstrip("#"), 16))
        except Exception:
            pass

    footer_text = _build_footer_text(scope, guild)
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = discord.utils.utcnow()
    _set_footer_branding(embed, footer_text, guild)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon)
    return embed


def brand_embed(
    embed: discord.Embed,
    *,
    guild: Optional[discord.Guild] = None,
    scope: str = SCOPE_SYSTEM,
) -> discord.Embed:
    embed.timestamp = discord.utils.utcnow()
    footer_text = _build_footer_text(scope, guild)
    _set_footer_branding(embed, footer_text, guild)
    return embed


def make_empty_state_embed(
    title: str,
    description: str,
    *,
    scope: str = SCOPE_SYSTEM,
    guild: Optional[discord.Guild] = None,
    thumbnail: Optional[str] = None,
) -> discord.Embed:
    return make_embed(
        title, description, kind="muted", scope=scope, guild=guild, thumbnail=thumbnail
    )


def make_error_embed(
    title: str,
    description: str,
    *,
    scope: str = SCOPE_SYSTEM,
    guild: Optional[discord.Guild] = None,
) -> discord.Embed:
    return make_embed(title, description, kind="danger", scope=scope, guild=guild)


def make_confirmation_embed(
    title: str,
    description: str,
    *,
    scope: str = SCOPE_SYSTEM,
    guild: Optional[discord.Guild] = None,
    thumbnail: Optional[str] = None,
) -> discord.Embed:
    return make_embed(
        title, description, kind="success", scope=scope, guild=guild, thumbnail=thumbnail
    )


def make_analytics_card(
    title: str,
    *,
    description: Optional[str] = None,
    guild: Optional[discord.Guild] = None,
) -> discord.Embed:
    return make_embed(
        title, description, kind="analytics", scope=SCOPE_ANALYTICS, guild=guild
    )


def upsert_embed_field(
    embed: discord.Embed, name: str, value: str, *, inline: bool = False
):
    for index, field in enumerate(embed.fields):
        if field.name == name:
            embed.set_field_at(index, name=name, value=value, inline=inline)
            return
    embed.add_field(name=name, value=value, inline=inline)
