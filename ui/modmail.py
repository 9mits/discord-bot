import discord

class ModmailPanelView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=None)
        self.data = data
        self.custom_id = "modmail_panel"

    @discord.ui.button(label="Contact Staff", style=discord.ButtonStyle.primary, custom_id="modmail_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await self.data.get_ticket(interaction.user.id)
        if ticket and ticket["status"] == "open":
            await interaction.response.send_message("You already have an open ticket. Please check your DMs.", ephemeral=True)
            return
        try:
            await interaction.user.send("Hi! Please send your message and a staff member will respond shortly.")
            await interaction.response.send_message("Check your DMs to start the conversation.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I couldn't DM you. Please enable DMs from server members.", ephemeral=True)

class ModmailControlView(discord.ui.View):
    def __init__(self, data, user_id: int):
        super().__init__(timeout=None)
        self.data = data
        self.user_id = user_id

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.data.close_ticket(self.user_id)
        try:
            user = await interaction.client.fetch_user(self.user_id)
            await user.send("Your modmail ticket has been closed. Feel free to message again if you need help.")
        except Exception:
            pass
        await interaction.response.send_message("Ticket closed. Deleting channel in 5 seconds.")
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Reply", style=discord.ButtonStyle.primary)
    async def reply(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReplyModal(self.data, self.user_id))

class ReplyModal(discord.ui.Modal, title="Reply to Ticket"):
    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, data, user_id: int):
        super().__init__()
        self.data = data
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user = await interaction.client.fetch_user(self.user_id)
            embed = discord.Embed(description=self.message.value, color=0x5865F2)
            embed.set_author(name="Staff Reply", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.set_footer(text=interaction.guild.name)
            await user.send(embed=embed)
            await self.data.append_ticket_transcript(self.user_id, {
                "author_id": interaction.user.id,
                "content": self.message.value,
                "is_staff": True,
                "created_at": __import__("time").time()
            })
            await interaction.response.send_message("Reply sent.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to send: {e}", ephemeral=True)
