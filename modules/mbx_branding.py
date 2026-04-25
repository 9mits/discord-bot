"""Server-specific bot branding helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import discord
from discord.http import Route

from modules.mbx_constants import SCOPE_SYSTEM
from modules.mbx_context import bot
from modules.mbx_embeds import (
    _build_footer_text,
    _format_branding_panel_value,
    _get_branding_config,
    _get_footer_icon_url,
    make_embed,
    make_error_embed,
)
from modules.mbx_images import fetch_image_data_uri
from modules.mbx_utils import truncate_text

logger = logging.getLogger("MGXBot")


def BrandingPanelView(*args, **kwargs):
    from ui.config import BrandingPanelView as _cls
    return _cls(*args, **kwargs)


def _active_bot():
    return bot


MAX_GUILD_MEMBER_BIO_LENGTH = 190

BRANDING_UNSET = object()

async def _refresh_branding_panel(interaction: discord.Interaction) -> None:
    embed = _build_branding_panel_embed(interaction.guild)
    await interaction.response.edit_message(embed=embed, view=BrandingPanelView())

async def apply_guild_member_branding(
    guild: discord.Guild,
    *,
    display_name: Any = BRANDING_UNSET,
    avatar_url: Any = BRANDING_UNSET,
    banner_url: Any = BRANDING_UNSET,
    bio: Any = BRANDING_UNSET,
    reason: Optional[str] = None,
) -> Optional[str]:
    if guild is None:
        return "This command can only be used in a server."

    payload: Dict[str, Any] = {}

    if display_name is not BRANDING_UNSET:
        payload["nick"] = str(display_name or "").strip() or None

    if avatar_url is not BRANDING_UNSET:
        avatar_value = str(avatar_url or "").strip()
        if avatar_value:
            data_uri, error = await fetch_image_data_uri(avatar_value)
            if error:
                return f"Avatar update failed: {error}"
            payload["avatar"] = data_uri
        else:
            payload["avatar"] = None

    if banner_url is not BRANDING_UNSET:
        banner_value = str(banner_url or "").strip()
        if banner_value:
            data_uri, error = await fetch_image_data_uri(banner_value)
            if error:
                return f"Banner update failed: {error}"
            payload["banner"] = data_uri
        else:
            payload["banner"] = None

    if bio is not BRANDING_UNSET:
        payload["bio"] = str(bio or "").strip() or None

    if not payload:
        return None

    try:
        await _active_bot().http.request(
            Route("PATCH", "/guilds/{guild_id}/members/@me", guild_id=guild.id),
            json=payload,
            reason=reason,
        )
    except discord.Forbidden:
        return "Discord rejected the branding update. Check the bot's permissions and current member profile support."
    except discord.HTTPException as exc:
        detail = getattr(exc, "text", None) or str(exc)
        return f"Discord rejected the branding update: {truncate_text(detail, 200)}"

    return None

async def save_branding_settings(guild_id: int, updates: Dict[str, Optional[str]]) -> None:
    active_bot = _active_bot()
    cfg = active_bot.data_manager._configs.setdefault(guild_id, {})
    branding = cfg.setdefault("_branding", {})
    for key, value in updates.items():
        if value is None or value == "":
            branding.pop(key, None)
        else:
            branding[key] = value
    if not branding:
        cfg["_branding"] = {}
    active_bot.data_manager._mark_dirty(guild_id, "guild_configs")
    await active_bot.data_manager.save_guild(guild_id, {"guild_configs"})

def build_branding_error_embed(guild: Optional[discord.Guild], detail: str) -> discord.Embed:
    return make_error_embed("Branding Update Failed", f"> {detail}", scope=SCOPE_SYSTEM, guild=guild)

def _build_branding_panel_embed(guild: discord.Guild) -> discord.Embed:
    branding = _get_branding_config(guild.id)
    member = guild.me
    active_bot = _active_bot()
    if member is None and getattr(active_bot, "user", None) is not None:
        member = guild.get_member(active_bot.user.id)
    current_display_name = getattr(member, "display_name", None) or getattr(active_bot.user, "name", None) or "Mysterious Bot X"
    avatar_status = branding.get("avatar_url") or ("Set" if member and getattr(member, "guild_avatar", None) else None)
    banner_status = branding.get("banner_url") or ("Set" if member and getattr(member, "guild_banner", None) else None)
    bio_status = branding.get("bio")
    modmail_banner_status = branding.get("modmail_banner_url")
    footer_icon_status = "Server icon" if _get_footer_icon_url(guild) else None

    embed = make_embed(
        "Server Branding",
        (
            "> Manage the bot's server-specific profile and panel appearance.\n"
            "> Display name uses the bot nickname for this server. Footer format is fixed to `Server Name • Area`."
        ),
        kind="neutral",
        scope=SCOPE_SYSTEM,
        guild=guild,
    )
    if member and getattr(member, "display_avatar", None):
        embed.set_thumbnail(url=member.display_avatar.url)
    if member and getattr(member, "guild_banner", None):
        embed.set_image(url=member.guild_banner.url)

    embed.add_field(name="Embed Color", value=_format_branding_panel_value(branding.get("embed_color")), inline=True)
    embed.add_field(name="Display Name", value=_format_branding_panel_value(current_display_name), inline=True)
    embed.add_field(
        name="Display Name Override",
        value=_format_branding_panel_value(branding.get("display_name")),
        inline=True,
    )
    embed.add_field(name="Profile Bio", value=_format_branding_panel_value(bio_status), inline=True)
    embed.add_field(name="Profile Avatar", value=_format_branding_panel_value(avatar_status), inline=True)
    embed.add_field(name="Profile Banner", value=_format_branding_panel_value(banner_status), inline=True)
    embed.add_field(name="Modmail Banner", value=_format_branding_panel_value(modmail_banner_status), inline=True)
    embed.add_field(name="Footer Preview", value=_format_branding_panel_value(_build_footer_text(SCOPE_SYSTEM, guild)), inline=True)
    embed.add_field(name="Footer Icon", value=_format_branding_panel_value(footer_icon_status), inline=True)
    embed.add_field(
        name="How to edit",
        value=(
            "> Use the buttons below to update the bot profile for this server.\n"
            "> Reset clears stored branding and removes the server-specific bot profile."
        ),
        inline=False,
    )
    return embed


__all__ = [
    "MAX_GUILD_MEMBER_BIO_LENGTH",
    "BRANDING_UNSET",
    "_refresh_branding_panel",
    "apply_guild_member_branding",
    "save_branding_settings",
    "build_branding_error_embed",
    "_build_branding_panel_embed",
]
