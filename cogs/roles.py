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

roles_group = app_commands.Group(name="role", description="Custom role management")

class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.tree.add_command(roles_group)

    @roles_group.command(name="create", description="Create a custom role for a user")
    @is_mod()
    @app_commands.describe(user="User to give a custom role", name="Role name", color="Hex color (e.g. #FF0000)")
    async def role_create(self, interaction: discord.Interaction, user: discord.Member, name: str, color: str = "#000000"):
        await interaction.response.defer(ephemeral=True)
        config = await self.bot.data.get_config()

        existing = await self.bot.data.get_custom_role(user.id)
        if existing:
            await interaction.followup.send(f"{user.mention} already has a custom role. Use `/role edit` or `/role delete` first.", ephemeral=True)
            return

        try:
            hex_color = int(color.strip("#"), 16)
        except ValueError:
            hex_color = 0

        anchor_role_id = config.get("anchor_role_id")
        anchor_role = interaction.guild.get_role(int(anchor_role_id)) if anchor_role_id else None

        role = await interaction.guild.create_role(name=name, color=discord.Color(hex_color), reason=f"Custom role for {user}")

        if anchor_role:
            try:
                await interaction.guild.edit_role_positions({role: anchor_role.position})
            except Exception:
                pass

        await user.add_roles(role)
        await self.bot.data.set_custom_role(user.id, role.id, name)
        await interaction.followup.send(f"Created custom role **{name}** for {user.mention}", ephemeral=True)

    @roles_group.command(name="edit", description="Edit a user's custom role")
    @is_mod()
    @app_commands.describe(user="User whose role to edit", name="New name (optional)", color="New hex color (optional)")
    async def role_edit(self, interaction: discord.Interaction, user: discord.Member, name: str = None, color: str = None):
        await interaction.response.defer(ephemeral=True)
        existing = await self.bot.data.get_custom_role(user.id)
        if not existing:
            await interaction.followup.send(f"{user.mention} doesn't have a custom role.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(existing["role_id"]))
        if not role:
            await interaction.followup.send("Role not found in server.", ephemeral=True)
            return

        kwargs = {}
        if name:
            kwargs["name"] = name
        if color:
            try:
                kwargs["color"] = discord.Color(int(color.strip("#"), 16))
            except ValueError:
                pass

        if kwargs:
            await role.edit(**kwargs)

        await interaction.followup.send(f"Updated custom role for {user.mention}", ephemeral=True)

    @roles_group.command(name="delete", description="Delete a user's custom role")
    @is_mod()
    @app_commands.describe(user="User whose role to delete")
    async def role_delete(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        existing = await self.bot.data.get_custom_role(user.id)
        if not existing:
            await interaction.followup.send(f"{user.mention} doesn't have a custom role.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(existing["role_id"]))
        if role:
            await role.delete(reason=f"Custom role deleted by {interaction.user}")
        await self.bot.data.remove_custom_role(user.id)
        await interaction.followup.send(f"Deleted custom role for {user.mention}", ephemeral=True)

    @roles_group.command(name="info", description="View a user's custom role info")
    @app_commands.describe(user="User to check")
    async def role_info(self, interaction: discord.Interaction, user: discord.Member):
        existing = await self.bot.data.get_custom_role(user.id)
        if not existing:
            await interaction.response.send_message(f"{user.mention} doesn't have a custom role.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(existing["role_id"]))
        embed = discord.Embed(title="Custom Role Info", color=role.color if role else discord.Color.default())
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Role", value=role.mention if role else "Deleted", inline=True)
        embed.add_field(name="Name", value=existing["role_name"], inline=True)
        import datetime as dt
        ts = dt.datetime.utcfromtimestamp(existing["created_at"]).strftime("%Y-%m-%d")
        embed.set_footer(text=f"Created: {ts}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RolesCog(bot))
