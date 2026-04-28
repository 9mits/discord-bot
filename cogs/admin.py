import discord
from discord import app_commands
from discord.ext import commands
from config import BOT_OWNER_IDS, DEFAULT_FEATURE_FLAGS

def is_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id in BOT_OWNER_IDS
    return app_commands.check(predicate)

def is_mod():
    async def predicate(interaction: discord.Interaction) -> bool:
        config = await interaction.client.data.get_config()
        mod_role_id = config.get("mod_role_id")
        if not mod_role_id:
            return interaction.user.guild_permissions.manage_messages
        mod_role = interaction.guild.get_role(int(mod_role_id))
        return mod_role in interaction.user.roles if mod_role else interaction.user.guild_permissions.manage_messages
    return app_commands.check(predicate)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configure the bot")
    @is_owner()
    async def setup(self, interaction: discord.Interaction):
        from ui.admin import SetupView
        config = await self.bot.data.get_config()
        view = SetupView(self.bot.data, config)
        embed = discord.Embed(title="Bot Setup", description="Configure the bot settings below.", color=0x5865F2)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="stats", description="View moderation statistics")
    @is_mod()
    async def stats(self, interaction: discord.Interaction):
        all_stats = await self.bot.data.get_all_mod_stats()
        embed = discord.Embed(title="Moderation Statistics", color=0x5865F2)
        if not all_stats:
            embed.description = "No moderation actions recorded yet."
        else:
            lines = []
            for stat in all_stats[:10]:
                member = interaction.guild.get_member(stat["moderator_id"])
                name = member.display_name if member else f"<@{stat['moderator_id']}>"
                total = stat["warns"] + stat["timeouts"] + stat["bans"] + stat["kicks"]
                lines.append(f"**{name}** — {total} actions (W:{stat['warns']} T:{stat['timeouts']} B:{stat['bans']} K:{stat['kicks']})")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="config", description="View or update a config value")
    @is_owner()
    @app_commands.describe(key="Config key", value="New value (leave empty to view current)")
    async def config_cmd(self, interaction: discord.Interaction, key: str = None, value: str = None):
        config = await self.bot.data.get_config()
        if key is None:
            lines = [f"`{k}`: {v}" for k, v in config.items() if k != "provisioned"]
            embed = discord.Embed(title="Current Config", description="\n".join(lines) or "Empty", color=0x5865F2)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif value is None:
            val = config.get(key, "Not set")
            await interaction.response.send_message(f"`{key}` = `{val}`", ephemeral=True)
        else:
            try:
                import json
                parsed = json.loads(value)
            except Exception:
                parsed = value
            await self.bot.data.set_config(key, parsed)
            await interaction.response.send_message(f"Set `{key}` = `{parsed}`", ephemeral=True)

    @app_commands.command(name="feature", description="Toggle a feature flag")
    @is_owner()
    @app_commands.describe(flag="Feature flag name", enabled="Enable or disable")
    async def feature(self, interaction: discord.Interaction, flag: str, enabled: bool):
        config = await self.bot.data.get_config()
        flags = config.get("feature_flags", DEFAULT_FEATURE_FLAGS.copy())
        if flag not in flags:
            await interaction.response.send_message(f"Unknown flag `{flag}`. Available: {', '.join(flags)}", ephemeral=True)
            return
        flags[flag] = enabled
        await self.bot.data.set_config("feature_flags", flags)
        await interaction.response.send_message(f"`{flag}` is now {'enabled' if enabled else 'disabled'}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
