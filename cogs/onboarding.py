import discord
from discord import app_commands
from discord.ext import commands

def is_mod():
    async def predicate(interaction: discord.Interaction) -> bool:
        config = await interaction.client.data.get_config()
        mod_role_id = config.get("mod_role_id")
        if not mod_role_id:
            return interaction.user.guild_permissions.manage_messages
        mod_role = interaction.guild.get_role(int(mod_role_id))
        return mod_role in interaction.user.roles if mod_role else interaction.user.guild_permissions.manage_messages
    return app_commands.check(predicate)

class OnboardingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await self.bot.data.get_config()
        flags = config.get("feature_flags", {})
        if not flags.get("onboarding_enabled"):
            return

        welcome_channel_id = config.get("welcome_channel_id")
        if not welcome_channel_id:
            return
        channel = member.guild.get_channel(int(welcome_channel_id))
        if not channel:
            return

        await self.bot.data.set_onboarding(member.id)

        from ui.onboarding import OnboardingView
        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}!",
            description=config.get("welcome_message", "Welcome! Please complete the onboarding below."),
            color=0x5865F2
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        view = OnboardingView(self.bot.data, member.id, config)
        await channel.send(f"{member.mention}", embed=embed, view=view)

    @app_commands.command(name="onboarding_send", description="Send the onboarding panel")
    @is_mod()
    @app_commands.describe(channel="Channel to send panel in", user="Specific user (optional)")
    async def onboarding_send(self, interaction: discord.Interaction, channel: discord.TextChannel = None, user: discord.Member = None):
        config = await self.bot.data.get_config()
        target = channel or interaction.channel
        target_user = user or interaction.user

        from ui.onboarding import OnboardingView
        embed = discord.Embed(
            title=f"Welcome to {interaction.guild.name}!",
            description=config.get("welcome_message", "Please complete the onboarding below."),
            color=0x5865F2
        )
        view = OnboardingView(self.bot.data, target_user.id, config)
        await target.send(f"{target_user.mention}", embed=embed, view=view)
        await interaction.response.send_message(f"Onboarding sent in {target.mention}", ephemeral=True)

    @app_commands.command(name="onboarding_status", description="Check a user's onboarding status")
    @is_mod()
    @app_commands.describe(user="User to check")
    async def onboarding_status(self, interaction: discord.Interaction, user: discord.Member):
        data = await self.bot.data.get_onboarding(user.id)
        if not data:
            await interaction.response.send_message(f"{user.mention} has not started onboarding.", ephemeral=True)
            return

        import json
        embed = discord.Embed(title=f"Onboarding — {user.display_name}", color=0x5865F2)
        embed.add_field(name="Completed", value="Yes" if data["completed"] else "No", inline=True)
        embed.add_field(name="Step", value=str(data["step"]), inline=True)
        roles_granted = json.loads(data.get("roles_granted", "[]"))
        embed.add_field(name="Roles Granted", value=str(len(roles_granted)), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(OnboardingCog(bot))
