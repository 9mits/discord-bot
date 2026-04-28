import discord

class SpamSettingsModal(discord.ui.Modal, title="Spam Settings"):
    threshold = discord.ui.TextInput(label="Message threshold", placeholder="5", max_length=3)
    window = discord.ui.TextInput(label="Time window (seconds)", placeholder="10", max_length=4)

    def __init__(self, data, current: dict):
        super().__init__()
        self.data = data
        self.threshold.default = str(current.get("spam_threshold", 5))
        self.window.default = str(current.get("spam_window_seconds", 10))

    async def on_submit(self, interaction: discord.Interaction):
        config = await self.data.get_config()
        automod = config.get("automod", {})
        try:
            automod["spam_threshold"] = int(self.threshold.value)
            automod["spam_window_seconds"] = int(self.window.value)
        except ValueError:
            await interaction.response.send_message("Invalid numbers.", ephemeral=True)
            return
        await self.data.set_config("automod", automod)
        await interaction.response.send_message("Spam settings updated.", ephemeral=True)

class BannedWordsModal(discord.ui.Modal, title="Banned Words"):
    words = discord.ui.TextInput(label="Words (comma-separated)", style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, data, current: dict):
        super().__init__()
        self.data = data
        self.words.default = ", ".join(current.get("banned_words", []))

    async def on_submit(self, interaction: discord.Interaction):
        config = await self.data.get_config()
        automod = config.get("automod", {})
        automod["banned_words"] = [w.strip() for w in self.words.value.split(",") if w.strip()]
        await self.data.set_config("automod", automod)
        await interaction.response.send_message(f"Updated {len(automod['banned_words'])} banned words.", ephemeral=True)

class MentionLimitModal(discord.ui.Modal, title="Mention Limit"):
    limit = discord.ui.TextInput(label="Max mentions per message", placeholder="10", max_length=3)

    def __init__(self, data, current: dict):
        super().__init__()
        self.data = data
        self.limit.default = str(current.get("mention_limit", 10))

    async def on_submit(self, interaction: discord.Interaction):
        config = await self.data.get_config()
        automod = config.get("automod", {})
        try:
            automod["mention_limit"] = int(self.limit.value)
        except ValueError:
            await interaction.response.send_message("Invalid number.", ephemeral=True)
            return
        await self.data.set_config("automod", automod)
        await interaction.response.send_message("Mention limit updated.", ephemeral=True)

class AutomodView(discord.ui.View):
    def __init__(self, data, automod: dict):
        super().__init__(timeout=300)
        self.data = data
        self.automod = automod

    @discord.ui.button(label="Spam Settings", style=discord.ButtonStyle.secondary)
    async def spam_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SpamSettingsModal(self.data, self.automod))

    @discord.ui.button(label="Banned Words", style=discord.ButtonStyle.secondary)
    async def banned_words(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BannedWordsModal(self.data, self.automod))

    @discord.ui.button(label="Toggle Link Filter", style=discord.ButtonStyle.secondary)
    async def link_filter(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.data.get_config()
        automod = config.get("automod", {})
        automod["link_filter"] = not automod.get("link_filter", False)
        await self.data.set_config("automod", automod)
        state = "enabled" if automod["link_filter"] else "disabled"
        await interaction.response.send_message(f"Link filter {state}.", ephemeral=True)

    @discord.ui.button(label="Mention Limit", style=discord.ButtonStyle.secondary)
    async def mention_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MentionLimitModal(self.data, self.automod))
