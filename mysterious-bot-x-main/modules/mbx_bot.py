from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Dict, Optional, Tuple

import aiohttp
import discord
from discord.ext import commands, tasks

from modules.mbx_constants import (
    BOT_OWNER_IDS,
    DEFAULT_GUILD_ID,
    DEV_GUILD_ID,
    SCOPE_ROLES,
    SCOPE_SUPPORT,
    WHITELISTED_GUILDS,
)
from modules.mbx_context import set_bot
from modules.mbx_data import DataManager, resolve_bot_token
from modules.mbx_services import get_feature_flag, ticket_needs_sla_alert
from modules.mbx_utils import iso_to_dt, now_iso

logger = logging.getLogger("MGXBot")

EXTENSIONS = (
    "cogs.roles",
    "cogs.moderation",
    "cogs.modmail",
    "cogs.automod",
    "cogs.system",
    "cogs.dev",
)


def _build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.message_content = True
    if hasattr(intents, "auto_moderation_configuration"):
        intents.auto_moderation_configuration = True
    if hasattr(intents, "auto_moderation_execution"):
        intents.auto_moderation_execution = True
    return intents


class MGXBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: Optional[aiohttp.ClientSession] = None
        self.data_manager: Optional[DataManager] = None
        self.start_time = time.time()
        self.active_executions = {}
        self.dm_modmail_prompt_cooldowns: Dict[int, float] = {}
        self.native_automod_event_cache: Dict[Tuple[int, int, int, str, str], float] = {}
        self.abuse_system = None

    async def setup_hook(self):
        from modules.mbx_data import AntiAbuseSystem

        self.session = aiohttp.ClientSession()
        self.data_manager = DataManager(self)
        self.abuse_system = AntiAbuseSystem()
        await self.data_manager.load_all()

        for extension in EXTENSIONS:
            await self.load_extension(extension)

        # Interaction middleware: set per-guild context before every slash command
        bot_ref = self

        async def _guild_context_middleware(interaction: discord.Interaction) -> bool:
            if interaction.guild_id and bot_ref.data_manager:
                bot_ref.data_manager._current_guild_id = interaction.guild_id
                await bot_ref.data_manager.ensure_guild_loaded(interaction.guild_id)
            else:
                if bot_ref.data_manager:
                    bot_ref.data_manager._current_guild_id = None
            return True

        self.tree.interaction_check = _guild_context_middleware

        await self._restore_persistent_views()

        # Guild join / leave listeners
        self.add_listener(self._on_guild_join, "on_guild_join")
        self.add_listener(self._on_guild_remove, "on_guild_remove")

        self.check_tempbans.start()
        self.background_save_task.start()
        self.status_task.start()
        self.modmail_sla_task.start()
        self.role_cleanup_task.start()

    # ------------------------------------------------------------------ #
    #  Guild join / leave                                                  #
    # ------------------------------------------------------------------ #

    async def _on_guild_join(self, guild: discord.Guild) -> None:
        if not self.data_manager:
            return

        blacklisted = await self.data_manager.get_blacklisted_guilds()
        rejected = guild.id in blacklisted or (
            bool(WHITELISTED_GUILDS) and guild.id not in WHITELISTED_GUILDS
        )

        if rejected:
            reason = "blacklisted" if guild.id in blacklisted else "not in the whitelist"
            logger.warning("Leaving guild %s (%s) — %s", guild.name, guild.id, reason)
            for oid in BOT_OWNER_IDS:
                try:
                    owner = await self.fetch_user(oid)
                    await owner.send(
                        f"\u26a0\ufe0f **Rejected guild join**\n"
                        f"**Server:** {guild.name} (`{guild.id}`)\n"
                        f"**Reason:** {reason}"
                    )
                except Exception:
                    pass
            await guild.leave()
            return

        await self.data_manager.provision_guild(guild.id)
        logger.info("Joined and provisioned guild %s (%s)", guild.name, guild.id)

        try:
            await guild.owner.send(
                f"Thanks for adding **{self.user.name}** to **{guild.name}**!\n"
                f"Run `/setup` to configure the bot for your server."
            )
        except Exception:
            pass

    async def _on_guild_remove(self, guild: discord.Guild) -> None:
        if self.data_manager:
            await self.data_manager.archive_guild(guild.id)
            logger.info("Left guild %s (%s) — data archived", guild.name, guild.id)

    # ------------------------------------------------------------------ #
    #  Persistent views                                                    #
    # ------------------------------------------------------------------ #

    async def _restore_persistent_views(self) -> None:
        from ui.modmail import ModmailControlView, ModmailPanelView

        self.add_view(ModmailPanelView())
        if not self.data_manager:
            return

        for guild_id, modmail in self.data_manager._modmail.items():
            for uid, data in modmail.items():
                if data.get("status") == "open":
                    log_id = data.get("log_id")
                    if log_id:
                        self.add_view(ModmailControlView(uid), message_id=log_id)

    # ------------------------------------------------------------------ #
    #  Close                                                               #
    # ------------------------------------------------------------------ #

    async def close(self):
        for task_loop in (
            self.check_tempbans,
            self.background_save_task,
            self.status_task,
            self.modmail_sla_task,
            self.role_cleanup_task,
        ):
            task_loop.cancel()

        if self.data_manager:
            await self.data_manager.save_all(force=True)
            await self.data_manager.close()
        if self.session:
            await self.session.close()
        await super().close()

    # ------------------------------------------------------------------ #
    #  Background tasks                                                    #
    # ------------------------------------------------------------------ #

    @tasks.loop(minutes=1)
    async def check_tempbans(self):
        if not self.data_manager:
            return
        now = discord.utils.utcnow()
        for gid in await self.data_manager.get_all_active_guild_ids():
            try:
                await self._check_tempbans_for_guild(gid, now)
            except Exception as exc:
                logger.error("check_tempbans failed for guild %s: %s", gid, exc)

    async def _check_tempbans_for_guild(self, guild_id: int, now: discord.utils.utcnow) -> None:
        punishments = self.data_manager._punishments.get(guild_id, {})
        changed = False
        for uid, records in punishments.items():
            for record in records:
                if record.get("type") == "ban" and record.get("active", False):
                    minutes = record.get("duration_minutes", 0)
                    if minutes > 0:
                        issued_at = iso_to_dt(record.get("timestamp"))
                        if issued_at and now >= issued_at + timedelta(minutes=minutes):
                            guild = self.get_guild(guild_id)
                            if guild:
                                try:
                                    await guild.unban(
                                        discord.Object(id=int(uid)), reason="Tempban Expired"
                                    )
                                except Exception:
                                    pass
                            record["active"] = False
                            changed = True
        if changed:
            self.data_manager._mark_dirty(guild_id, "guild_punishments")
            await self.data_manager.save_guild(guild_id, {"guild_punishments"})

    @tasks.loop(minutes=2)
    async def background_save_task(self):
        if self.data_manager:
            await self.data_manager.save_all()

    @tasks.loop(minutes=30)
    async def status_task(self):
        await self.change_presence(activity=discord.Game(name="DM for modmail"))

    @tasks.loop(minutes=10)
    async def modmail_sla_task(self):
        if not self.data_manager:
            return
        for gid in await self.data_manager.get_all_active_guild_ids():
            try:
                config = self.data_manager._configs.get(gid, {})
                if not get_feature_flag(config, "advanced_modmail", True):
                    continue
                guild = self.get_guild(gid)
                if not guild:
                    continue
                await self._modmail_sla_for_guild(gid, guild, config)
            except Exception as exc:
                logger.error("modmail_sla_task failed for guild %s: %s", gid, exc)

    async def _modmail_sla_for_guild(self, guild_id: int, guild: discord.Guild, config: dict) -> None:
        from ui.shared import make_embed

        now = discord.utils.utcnow()
        sla_minutes = max(5, int(config.get("modmail_sla_minutes", 60)))
        changed = False

        for ticket in self.data_manager._modmail.get(guild_id, {}).values():
            if not isinstance(ticket, dict):
                continue
            if not ticket_needs_sla_alert(ticket, now, sla_minutes):
                continue

            thread_id = ticket.get("thread_id")
            thread = guild.get_thread(thread_id) if thread_id else None
            if not thread and thread_id:
                try:
                    thread = await self.fetch_channel(thread_id)
                except Exception:
                    thread = None

            assigned = ticket.get("assigned_moderator")
            assigned_text = f"<@{assigned}>" if assigned else "Unassigned"
            embed = make_embed(
                "Reply Reminder",
                f"> This ticket has not received a staff reply in over **{sla_minutes} minute{'s' if sla_minutes != 1 else ''}**.",
                kind="warning",
                scope=SCOPE_SUPPORT,
                guild=guild,
            )
            embed.add_field(name="Assigned To", value=assigned_text, inline=True)
            embed.add_field(name="SLA Threshold", value=f"{sla_minutes} min", inline=True)
            if thread:
                try:
                    await thread.send(embed=embed)
                except Exception:
                    pass

            ticket["last_sla_alert_at"] = now_iso()
            changed = True

        if changed:
            self.data_manager._mark_dirty(guild_id, "guild_modmail")
            await self.data_manager.save_guild(guild_id, {"guild_modmail"})

    @tasks.loop(hours=6)
    async def role_cleanup_task(self):
        if not self.data_manager:
            return
        for gid in await self.data_manager.get_all_active_guild_ids():
            try:
                config = self.data_manager._configs.get(gid, {})
                if not get_feature_flag(config, "role_cleanup", True):
                    continue
                guild = self.get_guild(gid)
                if not guild:
                    continue
                await self._role_cleanup_for_guild(gid, guild)
            except Exception as exc:
                logger.error("role_cleanup_task failed for guild %s: %s", gid, exc)

    async def _role_cleanup_for_guild(self, guild_id: int, guild: discord.Guild) -> None:
        from modules.mbx_logging import send_log
        from modules.mbx_roles import get_custom_role_limit
        from ui.shared import format_reason_value, make_embed

        # Set context so send_log reads the right guild config
        prev = self.data_manager._current_guild_id
        self.data_manager._current_guild_id = guild_id

        try:
            removed_any = False
            for user_id, record in list(self.data_manager._roles.get(guild_id, {}).items()):
                if not isinstance(record, dict):
                    continue

                role_id = record.get("role_id")
                role = guild.get_role(role_id) if role_id else None
                member = guild.get_member(int(user_id))
                if not member:
                    try:
                        member = await guild.fetch_member(int(user_id))
                    except Exception:
                        member = None

                if member and get_custom_role_limit(member) > 0:
                    continue

                if role:
                    try:
                        await role.delete(reason="Custom role eligibility cleanup")
                    except Exception:
                        pass

                self.data_manager._roles.get(guild_id, {}).pop(user_id, None)
                removed_any = True

                embed = make_embed(
                    "Custom Role Cleanup",
                    "> A custom role was removed because the owner no longer meets eligibility.",
                    kind="warning",
                    scope=SCOPE_ROLES,
                    guild=guild,
                )
                embed.add_field(name="Target", value=f"<@{user_id}> (`{user_id}`)", inline=True)
                embed.add_field(
                    name="Reason",
                    value=format_reason_value("Lost booster or approved-role eligibility", limit=300),
                    inline=False,
                )
                await send_log(guild, embed)

            if removed_any:
                self.data_manager._mark_dirty(guild_id, "guild_roles")
                await self.data_manager.save_guild(guild_id, {"guild_roles"})
        finally:
            self.data_manager._current_guild_id = prev

    # Before-loop hooks
    @status_task.before_loop
    async def before_status_task(self):
        await self.wait_until_ready()

    @modmail_sla_task.before_loop
    async def before_modmail_sla_task(self):
        await self.wait_until_ready()

    @role_cleanup_task.before_loop
    async def before_role_cleanup_task(self):
        await self.wait_until_ready()


def create_bot() -> MGXBot:
    bot = MGXBot(command_prefix="!", intents=_build_intents())
    set_bot(bot)
    return bot


def run() -> None:
    bot = create_bot()
    bot.run(resolve_bot_token())
