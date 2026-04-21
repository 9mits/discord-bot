"""
cogs/dev.py — Developer-only commands, synced exclusively to DEV_GUILD_ID.

All commands in this cog silently reject any user whose ID is not in BOT_OWNER_IDS
(interaction_check returns False with no response sent to Discord).
The /dev command group is registered only to DEV_GUILD_ID so it never appears
in autocomplete on any other server.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from modules.mbx_constants import BOT_OWNER_IDS, DEV_GUILD_ID
from modules.mbx_utils import truncate_text

logger = logging.getLogger("MGXBot")

_DEV_GUILD = discord.Object(id=DEV_GUILD_ID) if DEV_GUILD_ID else None


async def _parse_guild_id(interaction: discord.Interaction, guild_id: str) -> Optional[int]:
    """Parse guild_id string to int, sending an ephemeral error and returning None on failure."""
    try:
        return int(guild_id)
    except ValueError:
        await interaction.followup.send("Invalid guild ID.", ephemeral=True)
        return None


def _chunk_lines(lines: list[str], limit: int = 1900) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}".strip()
    if current:
        chunks.append(current)
    return chunks


class DevCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id in BOT_OWNER_IDS

    # ------------------------------------------------------------------ #
    #  /dev command group                                                  #
    # ------------------------------------------------------------------ #

    dev = app_commands.Group(
        name="dev",
        description="Developer-only commands",
        guild_ids=[DEV_GUILD_ID] if DEV_GUILD_ID else [],
    )

    @dev.command(name="sync", description="Sync slash commands globally or to a specific guild")
    @app_commands.describe(guild_id="Guild ID to sync to (leave blank for global sync)")
    async def dev_sync(self, interaction: discord.Interaction, guild_id: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if guild_id:
            try:
                target = discord.Object(id=int(guild_id))
                synced = await self.bot.tree.sync(guild=target)
                await interaction.followup.send(
                    f"Synced **{len(synced)}** command(s) to guild `{guild_id}`.", ephemeral=True
                )
            except Exception as exc:
                await interaction.followup.send(f"Error: {exc}", ephemeral=True)
        else:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(
                f"Synced **{len(synced)}** command(s) globally.", ephemeral=True
            )

    @dev.command(name="guilds", description="List all guilds the bot is active in")
    async def dev_guilds(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        dm = self.bot.data_manager
        if not dm:
            await interaction.followup.send("DataManager not ready.", ephemeral=True)
            return

        guild_ids = await dm.get_all_active_guild_ids()
        lines = []
        for gid in guild_ids:
            g = self.bot.get_guild(gid)
            name = g.name if g else "Unknown / Not cached"
            member_count = g.member_count if g else "?"
            lines.append(f"`{gid}` — **{name}** ({member_count} members)")

        if not lines:
            await interaction.followup.send("No active guilds in the database.", ephemeral=True)
            return

        chunks = _chunk_lines(lines)
        for chunk in chunks:
            await interaction.followup.send(chunk, ephemeral=True)

    @dev.command(name="leave", description="Force the bot to leave a guild and archive its data")
    @app_commands.describe(guild_id="Guild ID to leave")
    async def dev_leave(self, interaction: discord.Interaction, guild_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        gid = await _parse_guild_id(interaction, guild_id)
        if gid is None:
            return

        guild = self.bot.get_guild(gid)
        if guild:
            await guild.leave()
        if self.bot.data_manager:
            await self.bot.data_manager.archive_guild(gid)
        await interaction.followup.send(
            f"Left guild `{guild_id}` and archived its data.", ephemeral=True
        )

    @dev.command(name="blacklist", description="Blacklist a guild — bot will leave immediately and never rejoin")
    @app_commands.describe(guild_id="Guild ID to blacklist")
    async def dev_blacklist(self, interaction: discord.Interaction, guild_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        gid = await _parse_guild_id(interaction, guild_id)
        if gid is None:
            return

        dm = self.bot.data_manager
        if dm:
            await dm.blacklist_guild(gid)

        guild = self.bot.get_guild(gid)
        if guild:
            await guild.leave()
            if dm:
                await dm.archive_guild(gid)

        await interaction.followup.send(f"Guild `{guild_id}` has been blacklisted.", ephemeral=True)

    @dev.command(name="unblacklist", description="Remove a guild from the blacklist")
    @app_commands.describe(guild_id="Guild ID to unblacklist")
    async def dev_unblacklist(self, interaction: discord.Interaction, guild_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        gid = await _parse_guild_id(interaction, guild_id)
        if gid is None:
            return

        if self.bot.data_manager:
            await self.bot.data_manager.unblacklist_guild(gid)
        await interaction.followup.send(
            f"Guild `{guild_id}` removed from the blacklist.", ephemeral=True
        )

    @dev.command(name="broadcast", description="Send a message to every guild's configured log channel")
    @app_commands.describe(message="The message to broadcast")
    async def dev_broadcast(self, interaction: discord.Interaction, message: str) -> None:
        await interaction.response.defer(ephemeral=True)
        dm = self.bot.data_manager
        if not dm:
            await interaction.followup.send("DataManager not ready.", ephemeral=True)
            return

        guild_ids = await dm.get_all_active_guild_ids()
        sent = 0
        failed = 0

        for gid in guild_ids:
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            config = dm._configs.get(gid, {})
            ch_id = config.get("general_log_channel_id") or config.get("log_channel_id")
            if not ch_id:
                continue
            ch = guild.get_channel(int(ch_id))
            if not ch:
                continue
            try:
                await ch.send(
                    f"**[Developer Broadcast]** {message}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                sent += 1
            except Exception:
                failed += 1

        await interaction.followup.send(
            f"Broadcast sent to **{sent}** channel(s). Failed: {failed}.", ephemeral=True
        )

    @dev.command(name="guildconfig", description="View the raw stored config for any guild (read-only)")
    @app_commands.describe(guild_id="Guild ID to inspect")
    async def dev_guildconfig(self, interaction: discord.Interaction, guild_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        gid = await _parse_guild_id(interaction, guild_id)
        if gid is None:
            return

        dm = self.bot.data_manager
        cfg = dm._configs.get(gid, {}) if dm else {}
        text = truncate_text(json.dumps(cfg, indent=2, default=str), 1900)
        await interaction.followup.send(f"```json\n{text}\n```", ephemeral=True)

    @dev.command(name="stats", description="Bot-wide statistics across all guilds")
    async def dev_stats(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        dm = self.bot.data_manager
        if not dm:
            await interaction.followup.send("DataManager not ready.", ephemeral=True)
            return

        guild_ids = await dm.get_all_active_guild_ids()

        total_punishments = sum(
            sum(len(v) for v in dm._punishments.get(gid, {}).values())
            for gid in guild_ids
        )
        total_tickets = sum(len(dm._modmail.get(gid, {})) for gid in guild_ids)
        discord_guilds = len(self.bot.guilds)
        uptime_secs = int(time.time() - self.bot.start_time)
        hours, rem = divmod(uptime_secs, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        lines = [
            f"**Active guilds (DB):** {len(guild_ids)}",
            f"**Discord guilds:** {discord_guilds}",
            f"**Total punishment records:** {total_punishments}",
            f"**Total modmail tickets:** {total_tickets}",
            f"**Uptime:** {uptime_str}",
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = DevCog(bot)
    await bot.add_cog(cog)
    if DEV_GUILD_ID:
        bot.tree.add_command(cog.dev, guild=_DEV_GUILD, override=True)
        logger.info("DevCog loaded — /dev synced to guild %s", DEV_GUILD_ID)
    else:
        logger.warning("DEV_GUILD_ID not set — /dev commands will not be registered")
