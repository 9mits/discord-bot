"""Permission & auth helpers.

Extracted from mbx_legacy as part of the phased refactor. Lifted as-is — the
shape of these checks is a single-guild leftover (per-guild data via the
proxy) and will be redesigned when the real per-guild permission engine
lands.
"""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands

from modules.mbx_constants import SCOPE_SYSTEM
from modules.mbx_context import bot
from modules.mbx_embeds import make_error_embed
from modules.mbx_services import has_capability


DANGEROUS_PERMISSIONS = {
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "ban_members",
    "kick_members",
    "manage_webhooks",
    "mention_everyone",
}


def has_dangerous_perm(perms: discord.Permissions) -> bool:
    for p in DANGEROUS_PERMISSIONS:
        if getattr(perms, p, False):
            return True
    return False


def has_permission_capability(
    interaction: discord.Interaction, capability: str
) -> bool:
    return has_capability(
        [role.id for role in interaction.user.roles],
        capability,
        bot.data_manager.config,
        administrator=interaction.user.guild_permissions.administrator,
        user_id=interaction.user.id,
        guild_owner_id=interaction.guild.owner_id if interaction.guild else None,
    )


async def respond_with_error(
    interaction: discord.Interaction, message: str, *, scope: str = SCOPE_SYSTEM
):
    embed = make_error_embed(
        "Request Failed", f"> {message}", scope=scope, guild=interaction.guild
    )
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(embed=embed, ephemeral=True)


def is_staff_member(member: discord.Member) -> bool:
    conf = bot.data_manager.config
    allowed = {
        r
        for r in (
            conf.get("role_mod"),
            conf.get("role_admin"),
            conf.get("role_owner"),
            conf.get("role_community_manager"),
        )
        if r
    }
    if allowed and any(role.id in allowed for role in member.roles):
        return True
    mod_roles = bot.data_manager.config.get("mod_roles", [])
    if any(role.id in mod_roles for role in member.roles):
        return True
    return member.guild_permissions.moderate_members


def is_staff(interaction: discord.Interaction) -> bool:
    if has_permission_capability(interaction, "case_panel"):
        return True
    mod_roles = bot.data_manager.config.get("mod_roles", [])
    if any(r.id in mod_roles for r in interaction.user.roles):
        return True
    return interaction.user.guild_permissions.moderate_members


async def resolve_member(
    guild: discord.Guild, user_id: int
) -> Optional[discord.Member]:
    member = guild.get_member(user_id)
    if member:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


def get_primary_guild() -> Optional[discord.Guild]:
    """Return the guild that owns the current data_manager context, if any."""
    if not getattr(bot, "data_manager", None):
        return None
    guild_id = bot.data_manager._current_guild_id
    if guild_id:
        return bot.get_guild(int(guild_id))
    return None


def get_context_guild(
    interaction: discord.Interaction,
) -> Optional[discord.Guild]:
    return interaction.guild or get_primary_guild()


def check_admin(interaction: discord.Interaction) -> bool:
    return has_permission_capability(interaction, "setup_panel")


def check_owner(interaction: discord.Interaction) -> bool:
    return has_permission_capability(interaction, "owner_panel")


def requires_setup(interaction: discord.Interaction) -> bool:
    """app_commands.check: rejects commands if the guild hasn't run /setup."""
    if not interaction.guild_id:
        return True
    cfg = {}
    if getattr(bot, "data_manager", None):
        cfg = bot.data_manager._configs.get(interaction.guild_id, {})
    if not cfg.get("_setup_complete", False):
        raise app_commands.CheckFailure("guild_not_configured")
    return True
