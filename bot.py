import asyncio
import os
import discord
from discord.ext import commands, tasks
from config import TOKEN, BOT_OWNER_IDS
from data import DataManager

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.data: DataManager = None
        self.owner_ids_set = BOT_OWNER_IDS

    async def setup_hook(self):
        self.data = DataManager()
        await self.data.setup()

        # Load all cogs
        for cog in ["cogs.moderation", "cogs.modmail", "cogs.automod",
                    "cogs.roles", "cogs.onboarding", "cogs.admin"]:
            await self.load_extension(cog)

        await self.tree.sync()
        self.check_tempbans.start()
        self.modmail_sla_task.start()
        self.role_cleanup_task.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")

    async def on_guild_join(self, guild: discord.Guild):
        await self.data.provision()

    @tasks.loop(minutes=1)
    async def check_tempbans(self):
        import datetime
        guild = self.guilds[0] if self.guilds else None
        if not guild:
            return
        now = datetime.datetime.utcnow().timestamp()
        bans = await self.data.get_expired_tempbans(now)
        for user_id in bans:
            try:
                await guild.unban(discord.Object(id=user_id), reason="Tempban expired")
                await self.data.remove_tempban(user_id)
            except Exception:
                pass

    @tasks.loop(minutes=10)
    async def modmail_sla_task(self):
        guild = self.guilds[0] if self.guilds else None
        if not guild:
            return
        config = await self.data.get_config()
        sla_hours = config.get("modmail_sla_hours", 24)
        tickets = await self.data.get_open_tickets()
        import datetime
        now = datetime.datetime.utcnow().timestamp()
        alert_channel_id = config.get("modmail_alert_channel")
        if not alert_channel_id:
            return
        channel = guild.get_channel(int(alert_channel_id))
        if not channel:
            return
        for ticket in tickets:
            age_hours = (now - ticket["created_at"]) / 3600
            if age_hours > sla_hours and not ticket.get("sla_alerted"):
                await channel.send(f"Modmail ticket from <@{ticket['user_id']}> has been open for {age_hours:.0f} hours.")
                await self.data.mark_ticket_sla_alerted(ticket["user_id"])

    @tasks.loop(hours=6)
    async def role_cleanup_task(self):
        guild = self.guilds[0] if self.guilds else None
        if not guild:
            return
        config = await self.data.get_config()
        if not config.get("role_cleanup_enabled"):
            return
        anchor_role_id = config.get("anchor_role_id")
        if not anchor_role_id:
            return
        anchor_role = guild.get_role(int(anchor_role_id))
        if not anchor_role:
            return
        custom_roles = await self.data.get_all_custom_roles()
        for user_id, role_data in custom_roles.items():
            member = guild.get_member(int(user_id))
            if member and anchor_role not in member.roles:
                role = guild.get_role(int(role_data["role_id"]))
                if role:
                    try:
                        await member.remove_roles(role, reason="Role cleanup: lost anchor role")
                    except Exception:
                        pass

    @check_tempbans.before_loop
    @modmail_sla_task.before_loop
    @role_cleanup_task.before_loop
    async def before_tasks(self):
        await self.wait_until_ready()

def main():
    bot = Bot()
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
