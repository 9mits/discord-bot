from __future__ import annotations

from modules import mbx_legacy


async def setup(bot) -> None:
    bot.tree.add_command(mbx_legacy.branding_cmd)
    bot.tree.add_command(mbx_legacy.list_commands)
    bot.tree.add_command(mbx_legacy.stats)
    bot.tree.add_command(mbx_legacy.directory)
    bot.tree.add_command(mbx_legacy.setup)
    bot.tree.add_command(mbx_legacy.config_cmd)
    bot.tree.add_command(mbx_legacy.publicexecution)
    bot.tree.add_command(mbx_legacy.internals)
    bot.tree.add_command(mbx_legacy.archive)
    bot.tree.add_command(mbx_legacy.unarchive)
    bot.tree.add_command(mbx_legacy.clone)
    bot.tree.add_command(mbx_legacy.rules)
    bot.tree.add_command(mbx_legacy.safety_panel)
    bot.tree.add_command(mbx_legacy.access)
    bot.tree.add_command(mbx_legacy.lockdown)
    bot.tree.add_command(mbx_legacy.unlockdown)
    bot.tree.add_command(mbx_legacy.status_cmd)
    bot.add_listener(mbx_legacy.on_guild_role_update)
    bot.add_listener(mbx_legacy.on_member_update)
    bot.add_listener(mbx_legacy.on_message)
    bot.add_listener(mbx_legacy.on_ready)
    bot.tree.on_error = mbx_legacy.on_app_command_error
