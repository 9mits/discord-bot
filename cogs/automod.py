import discord
from discord import app_commands
from discord.ext import commands
import re

def is_mod():
    async def predicate(interaction: discord.Interaction) -> bool:
        config = await interaction.client.data.get_config()
        mod_role_id = config.get("mod_role_id")
        if not mod_role_id:
            return interaction.user.guild_permissions.manage_messages
        mod_role = interaction.guild.get_role(int(mod_role_id))
        return mod_role in interaction.user.roles if mod_role else interaction.user.guild_permissions.manage_messages
    return app_commands.check(predicate)

class AutomodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._message_timestamps: dict = {}  # user_id -> list of timestamps

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        config = await self.bot.data.get_config()
        flags = config.get("feature_flags", {})
        if not flags.get("automod_enabled"):
            return
        automod = config.get("automod", {})

        await self._check_spam(message, automod)
        await self._check_banned_words(message, automod)
        await self._check_links(message, automod)
        await self._check_mentions(message, automod)

    async def _check_spam(self, message: discord.Message, automod: dict):
        threshold = automod.get("spam_threshold", 5)
        window = automod.get("spam_window_seconds", 10)
        import time
        now = time.time()
        uid = message.author.id
        self._message_timestamps.setdefault(uid, [])
        self._message_timestamps[uid] = [t for t in self._message_timestamps[uid] if now - t < window]
        self._message_timestamps[uid].append(now)
        if len(self._message_timestamps[uid]) >= threshold:
            await self._take_action(message, "spam", "Spamming messages")
            self._message_timestamps[uid] = []

    async def _check_banned_words(self, message: discord.Message, automod: dict):
        banned = automod.get("banned_words", [])
        content_lower = message.content.lower()
        for word in banned:
            if word.lower() in content_lower:
                await self._take_action(message, "banned_word", f"Used banned word: {word}")
                return

    async def _check_links(self, message: discord.Message, automod: dict):
        if not automod.get("link_filter"):
            return
        if re.search(r"https?://", message.content):
            await self._take_action(message, "link", "Posting links")

    async def _check_mentions(self, message: discord.Message, automod: dict):
        limit = automod.get("mention_limit", 10)
        if len(message.mentions) >= limit:
            await self._take_action(message, "mass_mention", f"Mass mentioning ({len(message.mentions)} users)")

    async def _take_action(self, message: discord.Message, rule: str, reason: str):
        try:
            await message.delete()
        except Exception:
            pass

        config = await self.bot.data.get_config()
        action = config.get("automod", {}).get(f"{rule}_action", "delete")

        await self.bot.data.log_automod(message.author.id, rule, message.content[:500], action)

        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            ch = message.guild.get_channel(int(log_channel_id))
            if ch:
                embed = discord.Embed(
                    title="AutoMod Action",
                    description=f"**User:** {message.author.mention}\n**Rule:** {rule}\n**Reason:** {reason}\n**Action:** {action}",
                    color=0xFF4444
                )
                await ch.send(embed=embed)

        if action == "warn":
            await self.bot.data.add_punishment(
                message.author.id, self.bot.user.id, "warn", f"AutoMod: {reason}", points=1
            )

    @app_commands.command(name="automod", description="Configure automod settings")
    @is_mod()
    async def automod_config(self, interaction: discord.Interaction):
        from ui.automod import AutomodView
        config = await self.bot.data.get_config()
        automod = config.get("automod", {})
        view = AutomodView(self.bot.data, automod)
        embed = discord.Embed(title="AutoMod Configuration", color=0x5865F2)
        embed.add_field(name="Spam Threshold", value=str(automod.get("spam_threshold", 5)), inline=True)
        embed.add_field(name="Spam Window", value=f"{automod.get('spam_window_seconds', 10)}s", inline=True)
        embed.add_field(name="Link Filter", value="On" if automod.get("link_filter") else "Off", inline=True)
        embed.add_field(name="Mention Limit", value=str(automod.get("mention_limit", 10)), inline=True)
        banned = automod.get("banned_words", [])
        embed.add_field(name="Banned Words", value=str(len(banned)), inline=True)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AutomodCog(bot))
