import discord
from discord import app_commands
from discord.ext import commands
import datetime
from config import DEFAULT_ESCALATION_MATRIX

def is_mod():
    async def predicate(interaction: discord.Interaction) -> bool:
        config = await interaction.client.data.get_config()
        mod_role_id = config.get("mod_role_id")
        if not mod_role_id:
            return interaction.user.guild_permissions.manage_messages
        mod_role = interaction.guild.get_role(int(mod_role_id))
        return mod_role in interaction.user.roles if mod_role else interaction.user.guild_permissions.manage_messages
    return app_commands.check(predicate)

async def _check_escalation(bot, guild: discord.Guild, member: discord.Member, moderator: discord.Member):
    """Check if user should be escalated based on points."""
    points = await bot.data.get_user_points(member.id)
    config = await bot.data.get_config()
    matrix = config.get("escalation_matrix", DEFAULT_ESCALATION_MATRIX)

    triggered = None
    for step in sorted(matrix, key=lambda x: x["points"], reverse=True):
        if points >= step["points"]:
            triggered = step
            break

    if not triggered:
        return

    reason = f"Auto-escalation: {points} warning points"
    if triggered["action"] == "timeout":
        duration = datetime.timedelta(hours=triggered["duration_hours"])
        try:
            await member.timeout(duration, reason=reason)
            await bot.data.add_punishment(member.id, moderator.id, "timeout", reason, points=0, duration_hours=triggered["duration_hours"])
        except discord.Forbidden:
            pass
    elif triggered["action"] == "ban":
        try:
            await member.ban(reason=reason)
            await bot.data.add_punishment(member.id, moderator.id, "ban", reason, points=0)
        except discord.Forbidden:
            pass

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="warn", description="Warn a user")
    @is_mod()
    @app_commands.describe(user="User to warn", reason="Reason for warning", points="Warning points (default 1)")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str, points: int = 1):
        await interaction.response.defer(ephemeral=True)
        case_num = await self.bot.data.add_punishment(user.id, interaction.user.id, "warn", reason, points=points)

        embed = discord.Embed(
            title=f"Warning — Case #{case_num}",
            description=f"**User:** {user.mention}\n**Reason:** {reason}\n**Points:** {points}",
            color=0xFFA500
        )
        embed.set_footer(text=f"Moderator: {interaction.user.display_name}")

        config = await self.bot.data.get_config()
        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            ch = interaction.guild.get_channel(int(log_channel_id))
            if ch:
                await ch.send(embed=embed)

        try:
            await user.send(f"You have been warned in **{interaction.guild.name}**.\nReason: {reason}")
        except Exception:
            pass

        await _check_escalation(self.bot, interaction.guild, user, interaction.user)
        await interaction.followup.send(f"Warned {user.mention} — Case #{case_num}", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a user")
    @is_mod()
    @app_commands.describe(user="User to kick", reason="Reason")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        case_num = await self.bot.data.add_punishment(user.id, interaction.user.id, "kick", reason, points=2)
        try:
            await user.send(f"You have been kicked from **{interaction.guild.name}**.\nReason: {reason}")
        except Exception:
            pass
        await user.kick(reason=reason)

        embed = discord.Embed(title=f"Kick — Case #{case_num}", description=f"**User:** {user.mention}\n**Reason:** {reason}", color=0xFF6600)
        embed.set_footer(text=f"Moderator: {interaction.user.display_name}")
        config = await self.bot.data.get_config()
        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            ch = interaction.guild.get_channel(int(log_channel_id))
            if ch:
                await ch.send(embed=embed)
        await interaction.followup.send(f"Kicked {user.mention} — Case #{case_num}", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a user")
    @is_mod()
    @app_commands.describe(user="User to timeout", duration_hours="Duration in hours", reason="Reason")
    async def timeout_cmd(self, interaction: discord.Interaction, user: discord.Member, duration_hours: float, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        duration = datetime.timedelta(hours=duration_hours)
        await user.timeout(duration, reason=reason)
        case_num = await self.bot.data.add_punishment(user.id, interaction.user.id, "timeout", reason, points=2, duration_hours=duration_hours)

        embed = discord.Embed(title=f"Timeout — Case #{case_num}", description=f"**User:** {user.mention}\n**Duration:** {duration_hours}h\n**Reason:** {reason}", color=0xFF9900)
        embed.set_footer(text=f"Moderator: {interaction.user.display_name}")
        config = await self.bot.data.get_config()
        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            ch = interaction.guild.get_channel(int(log_channel_id))
            if ch:
                await ch.send(embed=embed)
        await interaction.followup.send(f"Timed out {user.mention} for {duration_hours}h — Case #{case_num}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a user")
    @is_mod()
    @app_commands.describe(user="User to ban", reason="Reason", duration_hours="Temp ban duration in hours (0 = permanent)")
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided", duration_hours: float = 0):
        await interaction.response.defer(ephemeral=True)
        try:
            await user.send(f"You have been banned from **{interaction.guild.name}**.\nReason: {reason}")
        except Exception:
            pass
        await user.ban(reason=reason)
        case_num = await self.bot.data.add_punishment(user.id, interaction.user.id, "ban", reason, points=5, duration_hours=duration_hours)

        if duration_hours > 0:
            import time
            expires_at = time.time() + duration_hours * 3600
            await self.bot.data.add_tempban(user.id, expires_at, reason)

        embed = discord.Embed(
            title=f"Ban — Case #{case_num}",
            description=f"**User:** {user.mention}\n**Reason:** {reason}\n**Duration:** {'Permanent' if not duration_hours else f'{duration_hours}h'}",
            color=0xFF0000
        )
        embed.set_footer(text=f"Moderator: {interaction.user.display_name}")
        config = await self.bot.data.get_config()
        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            ch = interaction.guild.get_channel(int(log_channel_id))
            if ch:
                await ch.send(embed=embed)
        await interaction.followup.send(f"Banned {user.mention} — Case #{case_num}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user")
    @is_mod()
    @app_commands.describe(user_id="User ID to unban", reason="Reason")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.guild.unban(discord.Object(id=int(user_id)), reason=reason)
            await self.bot.data.remove_tempban(int(user_id))
            await interaction.followup.send(f"Unbanned user `{user_id}`", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("User is not banned.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="modcase", description="View or manage a moderation case")
    @is_mod()
    @app_commands.describe(case_number="Case number to view")
    async def modcase(self, interaction: discord.Interaction, case_number: int):
        await interaction.response.defer(ephemeral=True)
        case = await self.bot.data.get_case(case_number)
        if not case:
            await interaction.followup.send(f"Case #{case_number} not found.", ephemeral=True)
            return
        from ui.moderation import CaseView
        view = CaseView(self.bot.data, case)
        embed = await _build_case_embed(interaction.guild, case)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="history", description="View a user's punishment history")
    @is_mod()
    @app_commands.describe(user="User to look up")
    async def history(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        punishments = await self.bot.data.get_user_punishments(user.id)
        points = await self.bot.data.get_user_points(user.id)

        embed = discord.Embed(title=f"History — {user.display_name}", color=0x5865F2)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Total Points", value=str(points), inline=True)
        embed.add_field(name="Total Cases", value=str(len(punishments)), inline=True)

        if punishments:
            lines = []
            for p in punishments[:10]:
                import datetime as dt
                ts = dt.datetime.utcfromtimestamp(p["created_at"]).strftime("%Y-%m-%d")
                lines.append(f"**#{p['case_number']}** `{p['type'].upper()}` — {p['reason'] or 'No reason'} ({ts})")
            embed.add_field(name="Cases", value="\n".join(lines), inline=False)
        else:
            embed.description = "No punishments on record."

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="search", description="Search moderation cases")
    @is_mod()
    @app_commands.describe(user="Filter by user", moderator="Filter by moderator", type="Filter by type", status="Filter by status")
    async def search(self, interaction: discord.Interaction, user: discord.Member = None, moderator: discord.Member = None, type: str = None, status: str = None):
        await interaction.response.defer(ephemeral=True)
        cases = await self.bot.data.search_cases(
            user_id=user.id if user else None,
            moderator_id=moderator.id if moderator else None,
            type=type,
            status=status
        )
        if not cases:
            await interaction.followup.send("No cases found.", ephemeral=True)
            return

        lines = []
        for c in cases[:20]:
            import datetime as dt
            ts = dt.datetime.utcfromtimestamp(c["created_at"]).strftime("%Y-%m-%d")
            lines.append(f"**#{c['case_number']}** `{c['type'].upper()}` <@{c['user_id']}> — {c['reason'] or 'No reason'} ({ts})")

        embed = discord.Embed(title=f"Search Results ({len(cases)} total)", description="\n".join(lines), color=0x5865F2)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def _build_case_embed(guild: discord.Guild, case: dict) -> discord.Embed:
    import datetime as dt
    color_map = {"warn": 0xFFA500, "timeout": 0xFF9900, "kick": 0xFF6600, "ban": 0xFF0000}
    color = color_map.get(case["type"], 0x5865F2)
    embed = discord.Embed(title=f"Case #{case['case_number']} — {case['type'].upper()}", color=color)

    user = guild.get_member(case["user_id"])
    mod = guild.get_member(case["moderator_id"])

    embed.add_field(name="User", value=user.mention if user else f"<@{case['user_id']}>", inline=True)
    embed.add_field(name="Moderator", value=mod.mention if mod else f"<@{case['moderator_id']}>", inline=True)
    embed.add_field(name="Status", value=case.get("status", "open").title(), inline=True)
    embed.add_field(name="Reason", value=case.get("reason") or "No reason", inline=False)

    ts = dt.datetime.utcfromtimestamp(case["created_at"]).strftime("%Y-%m-%d %H:%M UTC")
    embed.set_footer(text=f"Created: {ts}")

    import json
    notes = json.loads(case.get("notes", "[]"))
    if notes:
        note_lines = []
        for n in notes[-3:]:
            note_mod = guild.get_member(n["author_id"])
            note_ts = dt.datetime.utcfromtimestamp(n["created_at"]).strftime("%m/%d")
            note_lines.append(f"**{note_mod.display_name if note_mod else 'Unknown'}** ({note_ts}): {n['note']}")
        embed.add_field(name="Notes", value="\n".join(note_lines), inline=False)

    return embed

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
