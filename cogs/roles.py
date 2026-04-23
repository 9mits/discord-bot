from __future__ import annotations

from modules import mbx_legacy


async def setup(bot) -> None:
    bot.tree.add_command(mbx_legacy.role_cmd)
    bot.tree.add_command(mbx_legacy.role_manage)
    bot.tree.add_command(mbx_legacy.role_settings)
    bot.tree.add_command(mbx_legacy.help_cmd)
