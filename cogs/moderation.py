from __future__ import annotations

from modules import mbx_legacy


async def setup(bot) -> None:
    bot.tree.add_command(mbx_legacy.ModGroup())
    bot.tree.add_command(mbx_legacy.punish_context)
    bot.tree.add_command(mbx_legacy.history_context)
    bot.add_listener(mbx_legacy.on_raw_reaction_add)
