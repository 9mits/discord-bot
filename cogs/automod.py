from __future__ import annotations

from modules import mbx_legacy


async def setup(bot) -> None:
    bot.tree.add_command(mbx_legacy.automod_cmd)
    bot.add_listener(mbx_legacy.on_automod_action)
    bot.add_listener(mbx_legacy.on_socket_raw_receive)
