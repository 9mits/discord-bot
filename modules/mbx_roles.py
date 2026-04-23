"""Custom role feature helpers.

Extracted from mbx_legacy. Owns: eligibility logic, embed builders for the
role landing/info/settings panels, and the registry helpers.
Views, Modals, and slash commands remain in mbx_legacy until the tree
registration is refactored.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import discord

from modules.mbx_constants import EMBED_PALETTE, SCOPE_ROLES
from modules.mbx_context import bot
from modules.mbx_embeds import make_embed
from modules.mbx_formatters import hex_valid, join_lines
from modules.mbx_utils import iso_to_dt, truncate_text


def get_custom_role_limit(member: discord.Member) -> int:
    conf = bot.data_manager.config
    uid = str(member.id)

    if uid in conf.get("cr_blacklist_users", []):
        return 0

    blocked_roles = conf.get("cr_blacklist_roles", [])
    for r in member.roles:
        if str(r.id) in blocked_roles:
            return 0

    limit = 0

    if member.premium_since is not None:
        limit = 1

    wl_users = conf.get("cr_whitelist_users", {})
    if uid in wl_users:
        limit = max(limit, int(wl_users[uid]))

    wl_roles = conf.get("cr_whitelist_roles", {})
    for r in member.roles:
        rid = str(r.id)
        if rid in wl_roles:
            limit = max(limit, int(wl_roles[rid]))

    return limit


def build_role_landing_embed(member: discord.Member, *, is_booster: bool, limit: int) -> discord.Embed:
    embed = make_embed(
        "Custom Role",
        "> Server boosters can create and personalize a custom role as a boost perk.",
        kind="info",
        scope=SCOPE_ROLES,
        guild=member.guild,
        thumbnail=member.display_avatar.url,
    )
    embed.add_field(name="Booster Slot", value=f"1 of {limit}", inline=True)
    embed.add_field(name="Customizable", value="Name, color, icon, style", inline=True)
    embed.add_field(
        name="How It Works",
        value="> 1. Create your role below.\n> 2. Adjust name, color, icon, and style at any time.\n> 3. Return to this panel whenever you want to make changes.",
        inline=False,
    )
    return embed


def build_role_info_embed(member: discord.Member, rec: dict, role_obj: Optional[discord.Role], include_tips=False) -> discord.Embed:
    color_hex = rec.get("color", "#000000")
    color = discord.Color(int(color_hex.lstrip("#"), 16)) if hex_valid(color_hex) else EMBED_PALETTE["muted"]
    embed = make_embed(
        "Manage Your Custom Role",
        "> Review and update your saved custom role configuration.",
        kind="info" if color.value == 0 else "neutral",
        scope=SCOPE_ROLES,
        guild=member.guild,
    )
    embed.color = EMBED_PALETTE["muted"] if color.value == 0 else color
    if role_obj:
        embed.add_field(name="Role", value=f"{role_obj.mention}", inline=False)
        embed.add_field(name="Name", value=role_obj.name, inline=True)
        embed.add_field(name="Members", value=str(len(role_obj.members)), inline=True)
        if rec.get("secondary_color"):
            embed.add_field(name="Secondary (Gradient)", value=f"`{rec.get('secondary_color')}`", inline=True)
        if rec.get("tertiary_color"):
            embed.add_field(name="Tertiary (Holograph)", value=f"`{rec.get('tertiary_color')}`", inline=True)
    else:
        embed.add_field(name="Role", value=f"<@&{rec.get('role_id')}> (missing)", inline=False)
        embed.add_field(name="Name", value=rec.get("name", "Unknown"), inline=True)

    embed.add_field(name="Color", value=f"`{rec.get('color','Unknown')}`", inline=True)

    created_at = rec.get("created_at")
    if created_at:
        dt = iso_to_dt(created_at)
        if dt:
            embed.add_field(name="Created", value=discord.utils.format_dt(dt, style="f"), inline=True)
            delta = discord.utils.utcnow() - dt
            days = delta.days
            hours = delta.seconds // 3600
            embed.add_field(name="Age", value=f"{days}d {hours}h", inline=True)
        else:
            embed.add_field(name="Created", value=created_at, inline=True)

    icon_url = rec.get("icon")
    if icon_url and icon_url.startswith(("http://", "https://")):
        embed.set_thumbnail(url=icon_url)
    else:
        embed.set_thumbnail(url=member.display_avatar.url)

    if include_tips:
        embed.add_field(
            name="Tips",
            value=join_lines([
                "Use the action menu below to update the name, colors, icon, and style.",
                "If the icon URL fails, use the upload flow instead.",
            ]),
            inline=False,
        )

    return embed


def build_role_settings_embed(guild: discord.Guild) -> discord.Embed:
    conf = bot.data_manager.config
    embed = make_embed(
        "Custom Role Settings",
        "> Manage who can create custom roles, review tracked roles, and open admin edit tools from one control panel.",
        kind="info",
        scope=SCOPE_ROLES,
        guild=guild,
    )
    embed.add_field(name="Whitelisted Users", value=str(len(conf.get("cr_whitelist_users", {}))), inline=True)
    embed.add_field(name="Whitelisted Roles", value=str(len(conf.get("cr_whitelist_roles", {}))), inline=True)
    embed.add_field(name="Blocked Entries", value=str(len(conf.get("cr_blacklist_users", [])) + len(conf.get("cr_blacklist_roles", []))), inline=True)
    embed.add_field(name="Tracked Custom Roles", value=str(len(bot.data_manager.roles)), inline=True)
    embed.add_field(
        name="What You Can Do",
        value=join_lines([
            "Review the current allow/block lists.",
            "Allow or block specific members or roles from custom role access.",
            "Reset one entry or open a member's custom role admin panel.",
        ]),
        inline=False,
    )
    return embed


def build_role_permissions_overview_embed(guild: discord.Guild) -> discord.Embed:
    conf = bot.data_manager.config
    embed = make_embed(
        "Custom Role Access Rules",
        "> Current allow and block rules for the booster custom role system.",
        kind="info",
        scope=SCOPE_ROLES,
        guild=guild,
    )

    wl_users = conf.get("cr_whitelist_users", {})
    if wl_users:
        lines = [f"<@{uid}>: {limit}" for uid, limit in wl_users.items()]
        embed.add_field(name="Allowed Users", value=truncate_text("\n".join(lines), 1024), inline=False)
    else:
        embed.add_field(name="Allowed Users", value="None", inline=False)

    wl_roles = conf.get("cr_whitelist_roles", {})
    if wl_roles:
        lines = [f"<@&{rid}>: {limit}" for rid, limit in wl_roles.items()]
        embed.add_field(name="Allowed Roles", value=truncate_text("\n".join(lines), 1024), inline=False)
    else:
        embed.add_field(name="Allowed Roles", value="None", inline=False)

    bl_users = conf.get("cr_blacklist_users", [])
    embed.add_field(name="Blocked Users", value=truncate_text(", ".join(f"<@{uid}>" for uid in bl_users) or "None", 1024), inline=False)
    bl_roles = conf.get("cr_blacklist_roles", [])
    embed.add_field(name="Blocked Roles", value=truncate_text(", ".join(f"<@&{rid}>" for rid in bl_roles) or "None", 1024), inline=False)
    return embed


def split_embed_entries(entries: List[str], *, limit: int = 1024) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_length = 0

    for raw_entry in entries:
        entry = truncate_text(raw_entry, min(limit, 950))
        entry_length = len(entry)
        if current and current_length + entry_length + 2 > limit:
            chunks.append("\n\n".join(current))
            current = [entry]
            current_length = entry_length
            continue
        current.append(entry)
        current_length = current_length + entry_length + (2 if len(current) > 1 else 0)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def build_custom_role_registry_entries(guild: discord.Guild) -> List[str]:
    entries: List[Tuple[str, str]] = []
    for uid, data in bot.data_manager.roles.items():
        rid = data.get("role_id")
        role = guild.get_role(rid) if rid else None
        owner = guild.get_member(int(uid)) if str(uid).isdigit() else None
        role_name = discord.utils.escape_markdown(str(role.name if role else data.get("name", "Unknown") or "Unknown"))
        role_ref = role.mention if role else f"`Missing role ({rid or 'unknown'})`"
        owner_ref = owner.mention if owner else f"<@{uid}>"

        entry_lines = [
            f"**{truncate_text(role_name, 90)}**",
            f"> Role: {role_ref}",
            f"> Owner: {owner_ref}",
        ]
        if role is None:
            entry_lines.append("> Status: Missing from server")
        entries.append((role_name.lower(), "\n".join(entry_lines)))

    entries.sort(key=lambda item: item[0])
    return [entry for _, entry in entries]


def add_custom_role_registry_fields(embed: discord.Embed, guild: discord.Guild, *, field_name: str = "Registry") -> int:
    entries = build_custom_role_registry_entries(guild)
    if not entries:
        embed.add_field(name=field_name, value="No custom roles are currently tracked.", inline=False)
        return 0

    for index, chunk in enumerate(split_embed_entries(entries)):
        name = field_name if index == 0 else f"{field_name} Cont."
        embed.add_field(name=name, value=chunk, inline=False)
    return len(entries)


def build_role_registry_embed(guild: discord.Guild) -> discord.Embed:
    embed = make_embed(
        "Tracked Custom Roles",
        "> Registry of current custom roles and their recorded owners.",
        kind="warning",
        scope=SCOPE_ROLES,
        guild=guild,
    )
    total_roles = add_custom_role_registry_fields(embed, guild, field_name="Registry")
    embed.add_field(name="Total Roles", value=str(total_roles), inline=True)
    return embed
