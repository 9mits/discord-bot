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

class ModmailCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is not None:
            return  # Only handle DMs

        config = await self.bot.data.get_config()
        if not config.get("feature_flags", {}).get("advanced_modmail"):
            return

        guild_id = config.get("guild_id")
        if not guild_id:
            return
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return

        ticket = await self.bot.data.get_ticket(message.author.id)

        if ticket and ticket["status"] == "open":
            channel = guild.get_channel(int(ticket["channel_id"]))
            if channel:
                embed = discord.Embed(description=message.content, color=0x5865F2)
                embed.set_author(name=f"{message.author.display_name} (DM)", icon_url=message.author.display_avatar.url)
                for att in message.attachments:
                    embed.set_image(url=att.url)
                await channel.send(embed=embed)
                await self.bot.data.append_ticket_transcript(message.author.id, {
                    "author_id": message.author.id,
                    "content": message.content,
                    "is_staff": False,
                    "created_at": message.created_at.timestamp()
                })
        else:
            await self._open_new_ticket(message.author, guild, message.content, config)

    async def _open_new_ticket(self, user: discord.User, guild: discord.Guild, content: str, config: dict):
        category_id = config.get("modmail_category_id")
        category = guild.get_channel(int(category_id)) if category_id else None

        try:
            channel = await guild.create_text_channel(
                name=f"modmail-{user.name}",
                category=category,
                topic=f"Modmail from {user} ({user.id})"
            )
        except Exception:
            return

        opened = await self.bot.data.open_ticket(user.id, channel.id)
        if not opened:
            await channel.delete()
            return

        await self.bot.data.set_config("guild_id", guild.id)

        embed = discord.Embed(title="New Modmail Ticket", color=0x5865F2)
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="First Message", value=content[:1024], inline=False)

        from ui.modmail import ModmailControlView
        view = ModmailControlView(self.bot.data, user.id)
        await channel.send(embed=embed, view=view)

        try:
            await user.send("Your message has been received. A staff member will respond shortly.")
        except Exception:
            pass

        await self.bot.data.append_ticket_transcript(user.id, {
            "author_id": user.id,
            "content": content,
            "is_staff": False,
            "created_at": __import__("time").time()
        })

    @app_commands.command(name="modmail_close", description="Close the current modmail ticket")
    @is_mod()
    async def modmail_close(self, interaction: discord.Interaction):
        ticket = await self.bot.data.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This is not a modmail channel.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.bot.data.close_ticket(ticket["user_id"])
        try:
            user = await self.bot.fetch_user(ticket["user_id"])
            await user.send("Your modmail ticket has been closed. Feel free to message again if you need help.")
        except Exception:
            pass
        await interaction.followup.send("Ticket closed. This channel will be deleted in 5 seconds.")
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @app_commands.command(name="modmail_reply", description="Reply to a modmail ticket")
    @is_mod()
    @app_commands.describe(message="Message to send to the user")
    async def modmail_reply(self, interaction: discord.Interaction, message: str):
        ticket = await self.bot.data.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This is not a modmail channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            user = await self.bot.fetch_user(ticket["user_id"])
            embed = discord.Embed(description=message, color=0x5865F2)
            embed.set_author(name="Staff Reply", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.set_footer(text=interaction.guild.name)
            await user.send(embed=embed)
            await self.bot.data.append_ticket_transcript(ticket["user_id"], {
                "author_id": interaction.user.id,
                "content": message,
                "is_staff": True,
                "created_at": __import__("time").time()
            })
            await interaction.followup.send("Reply sent to user.")
        except Exception as e:
            await interaction.followup.send(f"Failed to send reply: {e}")

    @app_commands.command(name="modmail_panel", description="Send the modmail panel to a channel")
    @is_mod()
    @app_commands.describe(channel="Channel to send panel to")
    async def modmail_panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        from ui.modmail import ModmailPanelView
        embed = discord.Embed(
            title="Contact Staff",
            description="Click the button below to open a private ticket with the moderation team.",
            color=0x5865F2
        )
        view = ModmailPanelView(self.bot.data)
        await target.send(embed=embed, view=view)
        await interaction.response.send_message(f"Panel sent to {target.mention}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModmailCog(bot))
