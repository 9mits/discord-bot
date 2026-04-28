import discord

class SetupView(discord.ui.View):
    def __init__(self, data, config: dict):
        super().__init__(timeout=300)
        self.data = data
        self.config = config

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.secondary)
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChannelConfigModal(self.data, "log_channel_id", "Log Channel ID"))

    @discord.ui.button(label="Set Mod Role", style=discord.ButtonStyle.secondary)
    async def set_mod_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleConfigModal(self.data, "mod_role_id", "Mod Role ID"))

    @discord.ui.button(label="Set Modmail Category", style=discord.ButtonStyle.secondary)
    async def set_modmail_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChannelConfigModal(self.data, "modmail_category_id", "Modmail Category ID"))

    @discord.ui.button(label="Set Anchor Role", style=discord.ButtonStyle.secondary)
    async def set_anchor_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleConfigModal(self.data, "anchor_role_id", "Anchor Role ID"))

    @discord.ui.button(label="Set Welcome Channel", style=discord.ButtonStyle.secondary)
    async def set_welcome_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChannelConfigModal(self.data, "welcome_channel_id", "Welcome Channel ID"))

class ChannelConfigModal(discord.ui.Modal):
    channel_id = discord.ui.TextInput(label="Channel ID", max_length=20)

    def __init__(self, data, config_key: str, title: str):
        super().__init__(title=title)
        self.data = data
        self.config_key = config_key

    async def on_submit(self, interaction: discord.Interaction):
        val = self.channel_id.value.strip()
        if not val.isdigit():
            await interaction.response.send_message("Please enter a valid channel ID.", ephemeral=True)
            return
        await self.data.set_config(self.config_key, int(val))
        await interaction.response.send_message(f"Set `{self.config_key}` to `{val}`", ephemeral=True)

class RoleConfigModal(discord.ui.Modal):
    role_id = discord.ui.TextInput(label="Role ID", max_length=20)

    def __init__(self, data, config_key: str, title: str):
        super().__init__(title=title)
        self.data = data
        self.config_key = config_key

    async def on_submit(self, interaction: discord.Interaction):
        val = self.role_id.value.strip()
        if not val.isdigit():
            await interaction.response.send_message("Please enter a valid role ID.", ephemeral=True)
            return
        await self.data.set_config(self.config_key, int(val))
        await interaction.response.send_message(f"Set `{self.config_key}` to `{val}`", ephemeral=True)
