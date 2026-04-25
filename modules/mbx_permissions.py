"""Permission & auth helpers — public surface over the capability engine.

This module is the API everything else imports from. The actual resolution
logic lives in ``mbx_permission_engine`` so this file stays a thin, stable
surface that command handlers call into.

Capability checks (preferred):

    has_capability(interaction, "mod.case_panel")
    require_capability("mod.punish")           # decorator-friendly
    can_use_command(interaction, "mod punish", "mod.punish")

Legacy compatibility:

    is_staff(interaction)        — alias for ``mod.case_panel``
    check_admin(interaction)     — alias for ``setup.run``
    check_owner(interaction)     — alias for ``permissions.edit``

These legacy names exist so the cogs/ui layer can be migrated incrementally
without breaking. New code should use the capability functions directly.
"""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands

from modules.mbx_constants import SCOPE_SYSTEM
from modules.mbx_context import bot
from modules.mbx_embeds import make_error_embed
from modules.mbx_permission_engine import (
    CAPABILITIES,
    PermissionEngine,
    can_member_use,
    evaluate_command_access,
    normalize_capability,
)


# ---------------------------------------------------------------------------
# Dangerous-permission set (for anti-nuke triggers — unchanged).
# ---------------------------------------------------------------------------

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
    return any(getattr(perms, p, False) for p in DANGEROUS_PERMISSIONS)


# ---------------------------------------------------------------------------
# Config / guild context helpers.
# ---------------------------------------------------------------------------

def _config_for(interaction: discord.Interaction) -> dict:
    dm = getattr(bot, "data_manager", None)
    if dm is None or not interaction.guild_id:
        return {}
    return dm._configs.get(interaction.guild_id, {})


async def resolve_member(guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
    member = guild.get_member(user_id)
    if member:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


def get_context_guild(interaction: discord.Interaction) -> Optional[discord.Guild]:
    """Return the guild for this interaction, or None if it's a DM.

    Note: ``get_primary_guild()`` (the old single-guild fallback) was removed.
    Slash commands always carry a guild context except in DMs, where the
    caller must handle ``None`` explicitly.
    """
    return interaction.guild


# ---------------------------------------------------------------------------
# Capability checks (preferred public API).
# ---------------------------------------------------------------------------

def has_capability(interaction: discord.Interaction, capability: str) -> bool:
    """True if the interaction's user has the named capability in this guild."""
    if interaction.user is None:
        return False
    config = _config_for(interaction)
    guild_owner_id = getattr(interaction.guild, "owner_id", None) if interaction.guild else None
    return can_member_use(
        interaction.user,
        capability,
        config,
        guild_owner_id=guild_owner_id,
    )


def can_use_command(interaction: discord.Interaction, command_key: str, capability: str) -> bool:
    """Apply per-command override (if any) then a capability check."""
    if interaction.user is None:
        return False
    config = _config_for(interaction)
    guild_owner_id = getattr(interaction.guild, "owner_id", None) if interaction.guild else None
    return evaluate_command_access(
        interaction.user,
        command_key,
        capability,
        config,
        guild_owner_id=guild_owner_id,
    )


def _interaction_command_key(interaction: discord.Interaction) -> Optional[str]:
    command = getattr(interaction, "command", None)
    if command is None:
        return None
    qualified_name = getattr(command, "qualified_name", None)
    if qualified_name:
        return str(qualified_name)
    name = getattr(command, "name", None)
    return str(name) if name else None


def require_capability(capability: str):
    """``app_commands.check`` builder that gates a command on a capability."""
    cap = normalize_capability(capability)

    def predicate(interaction: discord.Interaction) -> bool:
        command_key = _interaction_command_key(interaction)
        if command_key:
            return can_use_command(interaction, command_key, cap)
        return has_capability(interaction, cap)

    return app_commands.check(predicate)


def can_use_panel(interaction: discord.Interaction, panel_key: str, capability: str) -> bool:
    """Apply per-panel override (if any), then fall back to a capability check."""
    if interaction.user is None:
        return False
    config = _config_for(interaction)
    guild_owner_id = getattr(interaction.guild, "owner_id", None) if interaction.guild else None
    engine = PermissionEngine.for_guild(config)
    role_ids = [int(role.id) for role in getattr(interaction.user, "roles", []) or [] if hasattr(role, "id")]
    user_id = int(getattr(interaction.user, "id", 0)) or None
    discord_permissions = getattr(interaction.user, "guild_permissions", None)

    override_result = engine.check_override(
        "panel",
        panel_key,
        user_id=user_id,
        role_ids=role_ids,
        guild_owner_id=guild_owner_id,
        discord_permissions=discord_permissions,
    )
    if override_result is not None:
        return override_result

    return engine.has_capability(
        capability,
        user_id=user_id,
        role_ids=role_ids,
        guild_owner_id=guild_owner_id,
        discord_permissions=discord_permissions,
    )


# ---------------------------------------------------------------------------
# Legacy compatibility shims — keep until every call site is migrated.
# ---------------------------------------------------------------------------

def has_permission_capability(interaction: discord.Interaction, capability: str) -> bool:
    """Compatibility alias used by the old code. Maps onto has_capability."""
    return has_capability(interaction, capability)


def is_staff_member(member: discord.Member) -> bool:
    dm = getattr(bot, "data_manager", None)
    config = {}
    if dm is not None and getattr(member, "guild", None) is not None:
        config = dm._configs.get(member.guild.id, {})
    guild_owner_id = member.guild.owner_id if getattr(member, "guild", None) else None
    return can_member_use(member, "mod.case_panel", config, guild_owner_id=guild_owner_id)


def is_staff(interaction: discord.Interaction) -> bool:
    return has_capability(interaction, "mod.case_panel")


def check_admin(interaction: discord.Interaction) -> bool:
    return has_capability(interaction, "setup.run")


def check_owner(interaction: discord.Interaction) -> bool:
    return has_capability(interaction, "permissions.edit")


def requires_setup(interaction: discord.Interaction) -> bool:
    """``app_commands.check`` that rejects commands until ``/start`` finishes."""
    if not interaction.guild_id:
        return True
    cfg = _config_for(interaction)
    if not cfg.get("_setup_complete", False):
        raise app_commands.CheckFailure("guild_not_configured")
    return True


# ---------------------------------------------------------------------------
# Error response helper (unchanged).
# ---------------------------------------------------------------------------

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


__all__ = [
    "CAPABILITIES",
    "DANGEROUS_PERMISSIONS",
    "PermissionEngine",
    "can_use_command",
    "can_use_panel",
    "check_admin",
    "check_owner",
    "get_context_guild",
    "has_capability",
    "has_dangerous_perm",
    "has_permission_capability",
    "is_staff",
    "is_staff_member",
    "require_capability",
    "requires_setup",
    "resolve_member",
    "respond_with_error",
]
