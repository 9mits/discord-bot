import unittest
from types import SimpleNamespace

import discord

from cogs.moderation import ModGroup
from modules.mbx_permission_engine import default_permission_payload


class ModGroupPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_check_uses_punish_capability_for_punish_command(self):
        import modules.mbx_permissions as mbx_permissions

        config = {"permissions": default_permission_payload()}
        config["permissions"]["role_capabilities"] = {"10": ["mod.punish"]}
        group = ModGroup()
        interaction = SimpleNamespace(
            command=SimpleNamespace(name="punish"),
            guild_id=1,
            guild=SimpleNamespace(owner_id=99),
            user=SimpleNamespace(
                id=7,
                roles=[SimpleNamespace(id=10)],
                guild_permissions=discord.Permissions.none(),
            ),
        )
        original_bot = mbx_permissions.bot
        mbx_permissions.bot = SimpleNamespace(data_manager=SimpleNamespace(_configs={1: config}))
        try:
            self.assertTrue(await group.interaction_check(interaction))
        finally:
            mbx_permissions.bot = original_bot


if __name__ == "__main__":
    unittest.main()
